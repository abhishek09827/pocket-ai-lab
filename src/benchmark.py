"""Modular, reproducible Edge AI benchmarking runner for Ollama."""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import math
import os
import re
import sys
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests

from src.evaluator import evaluate_response
from src.schema import (
    BenchmarkRecord,
    ExecutionLocation,
    GenerationConfig,
    ModelIdentity,
    PerformanceMetrics,
    QualityEvaluation,
    RunStatus,
    RunType,
    SourceCategory,
    compute_wilson_score_interval,
)
from src.telemetry import GpuPeakSampler, capture_hardware_telemetry


def validate_loopback_url(api_base: str) -> None:
    """Enforce strict loopback binding rule.
    
    Hard-fails if the host is not 127.0.0.1, localhost, or ::1.
    """
    parsed = urllib.parse.urlparse(api_base)
    hostname = parsed.hostname
    allowed = {"127.0.0.1", "localhost", "::1"}
    if not hostname or hostname.lower() not in allowed:
        raise ValueError(
            f"SECURITY ERROR: Pocket AI Lab strictly requires loopback binding. "
            f"Provided api-base '{api_base}' (hostname: '{hostname}') is rejected. "
            f"Allowed hostnames: {sorted(list(allowed))}"
        )


def query_ollama_runtime_info(api_base: str) -> str:
    """Retrieve Ollama runtime version."""
    try:
        resp = requests.get(f"{api_base}/api/version", timeout=3.0)
        if resp.status_code == 200:
            return str(resp.json().get("version", "unknown"))
    except Exception:
        pass
    return "unknown"


def query_model_identity(api_base: str, model_tag: str) -> ModelIdentity:
    """Inspect model tags and details via Ollama API."""
    runtime_version = query_ollama_runtime_info(api_base)
    digest: Optional[str] = None
    family: Optional[str] = None
    parameter_size: Optional[str] = None
    quantization_level: Optional[str] = None

    # Try /api/tags first for exact digest and details
    try:
        tags_resp = requests.get(f"{api_base}/api/tags", timeout=4.0)
        if tags_resp.status_code == 200:
            models = tags_resp.json().get("models", [])
            for m in models:
                name = m.get("name", "")
                model_str = m.get("model", "")
                if name == model_tag or model_str == model_tag or name.startswith(f"{model_tag}:") or model_tag.startswith(name):
                    digest = m.get("digest")
                    details = m.get("details", {})
                    family = details.get("family")
                    parameter_size = details.get("parameter_size")
                    quantization_level = details.get("quantization_level")
                    break
    except Exception:
        pass

    # Try /api/show if any fields are still missing
    if not parameter_size or not quantization_level:
        try:
            show_resp = requests.post(f"{api_base}/api/show", json={"name": model_tag}, timeout=4.0)
            if show_resp.status_code == 200:
                data = show_resp.json()
                details = data.get("details", {})
                if not family:
                    family = details.get("family")
                if not parameter_size:
                    parameter_size = details.get("parameter_size")
                if not quantization_level:
                    quantization_level = details.get("quantization_level")
        except Exception:
            pass

    return ModelIdentity(
        model_tag=model_tag,
        digest_sha256=digest,
        family=family,
        parameter_size=parameter_size,
        quantization_level=quantization_level,
        runtime_name="ollama",
        runtime_version=runtime_version,
    )


def load_dataset(dataset_path: str) -> List[Dict[str, Any]]:
    """Load prompts and validation rules from JSONL file."""
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(f"Dataset not found at: {dataset_path}")

    records = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                records.append(data)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {dataset_path}:{idx}: {exc}")
    return records


def run_single_inference(
    api_base: str,
    model_tag: str,
    prompt: str,
    system_prompt: Optional[str],
    gen_config: GenerationConfig,
) -> Tuple[str, PerformanceMetrics, Tuple[Optional[float], Optional[float], Optional[float]]]:
    """Execute streaming inference call and measure accurate client TTFT and engine metrics."""
    options: Dict[str, Any] = {
        "temperature": gen_config.temperature,
        "top_p": gen_config.top_p,
        "seed": gen_config.seed,
        "num_ctx": gen_config.num_ctx,
        "num_predict": gen_config.max_tokens if gen_config.max_tokens is not None else 512,
    }

    payload: Dict[str, Any] = {
        "model": model_tag,
        "prompt": prompt,
        "stream": True,
        "options": options,
    }
    if system_prompt:
        payload["system"] = system_prompt

    sampler = GpuPeakSampler(interval_sec=0.20)
    sampler.start()

    ttft_client_ms: Optional[float] = None
    chunks: List[str] = []
    final_data: Dict[str, Any] = {}

    t_start = time.perf_counter()
    try:
        with requests.post(
            f"{api_base}/api/generate",
            json=payload,
            stream=True,
            timeout=120.0,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except Exception:
                    continue

                part = chunk.get("response", "")
                if part:
                    if ttft_client_ms is None:
                        ttft_client_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
                    chunks.append(part)

                if chunk.get("done", False):
                    final_data = chunk
                    break

        t_end = time.perf_counter()
        e2e_client_ms = round((t_end - t_start) * 1000.0, 2)
    finally:
        peak_gpu = sampler.stop()

    full_response = "".join(chunks)

    # Convert Ollama nanosecond durations to milliseconds
    def ns_to_ms(val: Optional[int]) -> Optional[float]:
        return round(val / 1e6, 2) if val is not None else None

    server_total_duration_ms = ns_to_ms(final_data.get("total_duration"))
    load_duration_ms = ns_to_ms(final_data.get("load_duration"))
    prompt_tokens = final_data.get("prompt_eval_count")
    prompt_eval_duration_ms = ns_to_ms(final_data.get("prompt_eval_duration"))
    response_tokens = final_data.get("eval_count")
    decode_duration_ms = ns_to_ms(final_data.get("eval_duration"))

    # Prompt Cache Hit Detection:
    # When Ollama reuses KV prompt prefixes, prompt_eval_duration drops to ~0ms even for long prompts.
    # We identify cache hits explicitly so low TTFT is not misattributed to raw prefill throughput.
    prompt_cache_hit = False
    if prompt_tokens and prompt_tokens > 5 and prompt_eval_duration_ms is not None:
        if prompt_eval_duration_ms < 10.0:
            prompt_cache_hit = True

    # Network / socket scheduling overhead: client-observed TTFT minus engine prompt evaluation + model loading
    network_overhead_ms: Optional[float] = None
    if ttft_client_ms is not None and prompt_eval_duration_ms is not None:
        server_prefill_and_load = prompt_eval_duration_ms + (load_duration_ms or 0.0)
        network_overhead_ms = round(max(0.0, ttft_client_ms - server_prefill_and_load), 2)

    prompt_tps: Optional[float] = None
    if prompt_tokens is not None and prompt_eval_duration_ms and prompt_eval_duration_ms > 0:
        prompt_tps = round(prompt_tokens / (prompt_eval_duration_ms / 1000.0), 2)

    decode_tps: Optional[float] = None
    if response_tokens is not None and decode_duration_ms and decode_duration_ms > 0:
        decode_tps = round(response_tokens / (decode_duration_ms / 1000.0), 2)

    metrics = PerformanceMetrics(
        load_duration_ms=load_duration_ms,
        ttft_client_ms=ttft_client_ms,
        e2e_client_ms=e2e_client_ms,
        prompt_tokens=prompt_tokens,
        prompt_eval_duration_ms=prompt_eval_duration_ms,
        prompt_tps=prompt_tps,
        response_tokens=response_tokens,
        decode_duration_ms=decode_duration_ms,
        decode_tps=decode_tps,
        prompt_cache_hit=prompt_cache_hit,
        server_total_duration_ms=server_total_duration_ms,
        network_overhead_ms=network_overhead_ms,
    )

    return full_response, metrics, peak_gpu


def append_record_to_jsonl(record: BenchmarkRecord, path: str) -> None:
    """Append validated record to JSONL file."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def append_record_to_csv(record: BenchmarkRecord, path: str) -> None:
    """Append flattened record to CSV file."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    flat_dict = record.to_csv_dict()
    file_exists = os.path.exists(path)

    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(flat_dict.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(flat_dict)


def compute_stats(values: List[float]) -> Dict[str, float]:
    """Compute mean, median, p90, min, max, and sample stdev."""
    if not values:
        return {"mean": 0.0, "median": 0.0, "p90": 0.0, "stdev": 0.0, "min": 0.0, "max": 0.0}
    sorted_v = sorted(values)
    n = len(sorted_v)
    mean_v = sum(sorted_v) / n

    # Median
    mid = n // 2
    median_v = (sorted_v[mid] + sorted_v[mid - 1]) / 2.0 if n % 2 == 0 else sorted_v[mid]

    # p90
    idx_p90 = min(int(math.ceil(0.90 * n)) - 1, n - 1)
    p90_v = sorted_v[max(0, idx_p90)]

    # Stdev
    if n > 1:
        variance = sum((x - mean_v) ** 2 for x in sorted_v) / (n - 1)
        stdev_v = math.sqrt(variance)
    else:
        stdev_v = 0.0

    return {
        "mean": round(mean_v, 2),
        "median": round(median_v, 2),
        "p90": round(p90_v, 2),
        "stdev": round(stdev_v, 2),
        "min": round(sorted_v[0], 2),
        "max": round(sorted_v[-1], 2),
    }


def print_summary_table(records: List[BenchmarkRecord]) -> None:
    """Print terminal summary reporting statistical distribution of measured runs."""
    measured = [r for r in records if r.run_type == "measured" and r.status == "success"]
    if not measured:
        print("\nNo successful measured runs to summarize.")
        return

    ttft_vals = [r.metrics.ttft_client_ms for r in measured if r.metrics.ttft_client_ms is not None]
    prompt_tps_vals = [r.metrics.prompt_tps for r in measured if r.metrics.prompt_tps is not None]
    decode_tps_vals = [r.metrics.decode_tps for r in measured if r.metrics.decode_tps is not None]
    vram_vals = [r.hardware.peak_gpu_vram_used_mb for r in measured if r.hardware.peak_gpu_vram_used_mb is not None]
    passed_count = sum(1 for r in measured if r.quality.quality_passed)
    pass_rate, ci_low, ci_high = compute_wilson_score_interval(passed_count, len(measured))

    s_ttft = compute_stats(ttft_vals)
    s_prompt_tps = compute_stats(prompt_tps_vals)
    s_decode_tps = compute_stats(decode_tps_vals)
    s_vram = compute_stats(vram_vals)

    print("\n" + "=" * 90)
    print(" POCKET AI LAB — BENCHMARK RESULTS SUMMARY (MEASURED RUNS)")
    print("=" * 90)
    print(f"Total Measured Iterations : {len(measured)}")
    print(f"Quality Pass Rate          : {passed_count}/{len(measured)} ({pass_rate}% | 95% CI: [{ci_low}%, {ci_high}%])")
    print("-" * 90)
    header = f"{'Metric':<24} | {'Mean':>9} | {'Median':>9} | {'P90':>9} | {'Min':>8} | {'Max':>8} | {'Stdev':>8}"
    print(header)
    print("-" * 90)

    rows = [
        ("TTFT (client ms)", s_ttft),
        ("Prompt Speed (TPS)", s_prompt_tps),
        ("Decode Speed (TPS)", s_decode_tps),
        ("Peak VRAM (MB)", s_vram),
    ]

    for label, stat in rows:
        print(f"{label:<24} | {stat['mean']:>9.2f} | {stat['median']:>9.2f} | {stat['p90']:>9.2f} | {stat['min']:>8.2f} | {stat['max']:>8.2f} | {stat['stdev']:>8.2f}")
    print("=" * 90 + "\n")


def run_benchmark(
    model: str,
    dataset_path: str = "datasets/prompts_v1.jsonl",
    api_base: str = "http://127.0.0.1:11434",
    warmups: int = 1,
    repeats: int = 3,
    temperature: float = 0.0,
    top_p: float = 1.0,
    seed: int = 42,
    num_ctx: int = 2048,
    max_tokens: Optional[int] = None,
    experiment_id: Optional[str] = None,
    source_category: SourceCategory = "measured_own_pc",
    execution_location: ExecutionLocation = "local_ubuntu",
) -> List[BenchmarkRecord]:
    """Execute complete edge AI benchmark matrix."""
    validate_loopback_url(api_base)

    if not experiment_id:
        clean_model = re.sub(r"[^a-zA-Z0-9_-]", "_", model)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        experiment_id = f"exp_{timestamp}_{clean_model}"

    jsonl_path = f"results/{experiment_id}.jsonl"
    csv_path = f"results/{experiment_id}.csv"

    print(f"\n[Pocket AI Lab] Initializing Benchmark Experiment: {experiment_id}", flush=True)
    print(f"  Model       : {model}", flush=True)
    print(f"  API Base    : {api_base}", flush=True)
    print(f"  Warmups     : {warmups}", flush=True)
    print(f"  Repeats     : {repeats}", flush=True)
    print(f"  Max Tokens  : {max_tokens or 512}", flush=True)
    print(f"  Dataset     : {dataset_path}", flush=True)
    print(f"  JSONL Output: {jsonl_path}", flush=True)
    print(f"  CSV Output  : {csv_path}\n", flush=True)

    model_identity = query_model_identity(api_base, model)
    print(f"  Resolved Model Digest: {model_identity.digest_sha256[:16] if model_identity.digest_sha256 else 'unknown'}...", flush=True)
    print(f"  Parameters: {model_identity.parameter_size} | Quant: {model_identity.quantization_level} | Family: {model_identity.family}\n", flush=True)

    dataset = load_dataset(dataset_path)
    total_prompts = len(dataset)
    print(f"Loaded {total_prompts} test prompts from {dataset_path}.\n", flush=True)

    gen_config = GenerationConfig(
        temperature=temperature,
        top_p=top_p,
        seed=seed,
        num_ctx=num_ctx,
        max_tokens=max_tokens,
    )

    all_records: List[BenchmarkRecord] = []
    total_iterations = warmups + repeats

    for p_idx, prompt_entry in enumerate(dataset, start=1):
        prompt_id = prompt_entry["prompt_id"]
        category = prompt_entry["category"]
        prompt_text = prompt_entry["prompt"]
        system_prompt = prompt_entry.get("system_prompt")
        validation_rules = prompt_entry.get("validation_rules", {})

        print(f"[{p_idx}/{total_prompts}] Testing prompt '{prompt_id}' ({category})...", flush=True)

        for iter_num in range(1, total_iterations + 1):
            if iter_num == 1 and warmups > 0:
                run_type: RunType = "cold_start"
            elif iter_num <= warmups:
                run_type = "warmup"
            else:
                run_type = "measured"

            run_id = f"{experiment_id}_{prompt_id}_iter{iter_num}"
            timestamp_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

            try:
                response_text, metrics, (peak_vram, peak_util, peak_temp) = run_single_inference(
                    api_base=api_base,
                    model_tag=model,
                    prompt=prompt_text,
                    system_prompt=system_prompt,
                    gen_config=gen_config,
                )

                hardware_telem = capture_hardware_telemetry(
                    peak_vram=peak_vram,
                    peak_util=peak_util,
                    peak_temp=peak_temp,
                )

                passed, notes = evaluate_response(response_text, validation_rules)

                quality = QualityEvaluation(
                    prompt_id=prompt_id,
                    category=category,
                    quality_passed=passed,
                    quality_notes=notes,
                    response_text=response_text,
                )

                status_val: RunStatus = "success"
                if not response_text or len(response_text.strip()) == 0:
                    status_val = "invalid_output"

                record = BenchmarkRecord(
                    schema_version="1.0.0",
                    experiment_id=experiment_id,
                    run_id=run_id,
                    timestamp_utc=timestamp_utc,
                    run_type=run_type,
                    source_category=source_category,
                    execution_location=execution_location,
                    hardware=hardware_telem,
                    model=model_identity,
                    generation=gen_config,
                    metrics=metrics,
                    quality=quality,
                    status=status_val,
                )

                status_mark = "✔ PASS" if passed else "✘ FAIL"
                cache_tag = " [CACHE HIT]" if metrics.prompt_cache_hit else ""
                print(
                    f"    iter {iter_num}/{total_iterations} ({run_type:<10}): "
                    f"TTFT={metrics.ttft_client_ms}ms{cache_tag} | Prompt={metrics.prompt_tps} TPS | "
                    f"Decode={metrics.decode_tps} TPS | VRAM={hardware_telem.peak_gpu_vram_used_mb}MB | "
                    f"Quality: {status_mark}",
                    flush=True,
                )

            except Exception as exc:
                err_str = str(exc)
                if isinstance(exc, requests.exceptions.Timeout) or "timed out" in err_str.lower():
                    status_val = "timeout"
                elif "out of memory" in err_str.lower() or "cuda out of memory" in err_str.lower() or "oom" in err_str.lower():
                    status_val = "oom"
                else:
                    status_val = "error"

                print(f"    iter {iter_num}/{total_iterations} ({run_type:<10}): {status_val.upper()}: {err_str}", flush=True)
                hardware_telem = capture_hardware_telemetry()
                record = BenchmarkRecord(
                    schema_version="1.0.0",
                    experiment_id=experiment_id,
                    run_id=run_id,
                    timestamp_utc=timestamp_utc,
                    run_type=run_type,
                    source_category=source_category,
                    execution_location=execution_location,
                    hardware=hardware_telem,
                    model=model_identity,
                    generation=gen_config,
                    metrics=PerformanceMetrics(),
                    quality=QualityEvaluation(
                        prompt_id=prompt_id,
                        category=category,
                        quality_passed=False,
                        quality_notes=err_str,
                        response_text="",
                    ),
                    status=status_val,
                    error_message=err_str,
                )

            append_record_to_jsonl(record, jsonl_path)
            append_record_to_csv(record, csv_path)
            all_records.append(record)

    print_summary_table(all_records)
    print(f"[Pocket AI Lab] Experiment completed. Saved {len(all_records)} records to {jsonl_path} and {csv_path}.\n")
    return all_records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pocket AI Lab - Reproducible Edge AI Benchmark Suite")
    parser.add_argument("--model", type=str, required=True, help="Ollama model tag e.g. qwen2.5:1.5b")
    parser.add_argument("--dataset", type=str, default="datasets/prompts_v1.jsonl", help="Path to prompts JSONL")
    parser.add_argument("--api-base", type=str, default="http://127.0.0.1:11434", help="Ollama API base URL (must be loopback)")
    parser.add_argument("--warmups", type=int, default=1, help="Number of warmup runs per prompt (iter 1 = cold_start)")
    parser.add_argument("--repeats", type=int, default=3, help="Number of measured repeat runs per prompt")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature")
    parser.add_argument("--top-p", type=float, default=1.0, help="Top-p sampling")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--num-ctx", type=int, default=2048, help="Context window size")
    parser.add_argument("--max-tokens", type=int, default=512, help="Maximum generated tokens (num_predict)")
    parser.add_argument("--experiment-id", type=str, default=None, help="Unique identifier for experiment")
    parser.add_argument("--source-category", type=str, default="measured_own_pc", choices=["measured_own_pc", "measured_own_android", "community_submitted", "emulator"])
    parser.add_argument("--execution-location", type=str, default="local_ubuntu", choices=["local_ubuntu", "local_android", "remote_ubuntu_via_ssh_tunnel"])
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_benchmark(
        model=args.model,
        dataset_path=args.dataset,
        api_base=args.api_base,
        warmups=args.warmups,
        repeats=args.repeats,
        temperature=args.temperature,
        top_p=args.top_p,
        seed=args.seed,
        num_ctx=args.num_ctx,
        max_tokens=args.max_tokens,
        experiment_id=args.experiment_id,
        source_category=args.source_category,
        execution_location=args.execution_location,
    )
