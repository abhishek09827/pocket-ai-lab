"""Reasoning & Decision-Making Benchmark Runner for HotpotQA and ALFWorld tasks."""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

import requests

from src.benchmark import validate_loopback_url, query_model_identity
from src.reasoning_evaluator import (
    evaluate_alfworld_response,
    evaluate_hotpotqa_response,
)
from src.schema import GenerationConfig, PerformanceMetrics, compute_wilson_score_interval
from src.telemetry import GpuPeakSampler, capture_hardware_telemetry


def run_reasoning_benchmark(
    model: str,
    dataset_path: str = "datasets/reasoning_eval_v1.jsonl",
    api_base: str = "http://127.0.0.1:11434",
    repeats: int = 2,
    warmups: int = 1,
    max_tokens: int = 512,
    temperature: float = 0.0,
) -> str:
    """Execute evaluation on HotpotQA and ALFWorld tasks."""
    validate_loopback_url(api_base)

    clean_model = re.sub(r"[^a-zA-Z0-9_-]", "_", model)
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    experiment_id = f"reasoning_{clean_model}_{timestamp}"

    jsonl_path = f"results/{experiment_id}.jsonl"
    csv_path = f"results/{experiment_id}.csv"

    print(f"\n[Pocket AI Lab] Starting Reasoning & Decision-Making Benchmark: {experiment_id}", flush=True)
    print(f"  Model       : {model}", flush=True)
    print(f"  Repeats     : {repeats} (+ {warmups} warmup)", flush=True)
    print(f"  Dataset     : {dataset_path}", flush=True)
    print(f"  CSV Output  : {csv_path}\n", flush=True)

    model_identity = query_model_identity(api_base, model)

    tasks = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))

    gen_config = GenerationConfig(
        temperature=temperature,
        top_p=1.0,
        seed=42,
        num_ctx=2048,
        max_tokens=max_tokens,
    )

    records: List[Dict[str, Any]] = []
    total_iters = warmups + repeats

    for t_idx, task in enumerate(tasks, start=1):
        task_id = task["task_id"]
        family = task["benchmark_family"]
        category = task["category"]
        question = task["question"]
        context = task.get("context", "")
        system_prompt = task.get("system_prompt", "")
        spec = task.get("evaluation_spec", {})

        full_prompt = f"{context}\n\nQuestion: {question}" if context else question

        print(f"[{t_idx}/{len(tasks)}] Evaluating {task_id} ({family})...", flush=True)

        for iter_num in range(1, total_iters + 1):
            is_warmup = iter_num <= warmups
            run_type = "warmup" if is_warmup else "measured"

            # Execute inference with peak GPU sampling
            sampler = GpuPeakSampler(interval_sec=0.20)
            sampler.start()

            payload = {
                "model": model,
                "prompt": full_prompt,
                "system": system_prompt,
                "stream": True,
                "options": {
                    "temperature": gen_config.temperature,
                    "top_p": gen_config.top_p,
                    "seed": gen_config.seed,
                    "num_ctx": gen_config.num_ctx,
                    "num_predict": gen_config.max_tokens,
                },
            }

            chunks = []
            ttft_client_ms = None
            final_data = {}

            t_start = time.perf_counter()
            with requests.post(f"{api_base}/api/generate", json=payload, stream=True, timeout=120.0) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines(decode_unicode=True):
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
            peak_gpu = sampler.stop()

            e2e_client_ms = round((t_end - t_start) * 1000.0, 2)
            response_text = "".join(chunks)

            # Durations
            prompt_eval_dur = final_data.get("prompt_eval_duration", 0) / 1e6
            eval_dur = final_data.get("eval_duration", 0) / 1e6
            prompt_tokens = final_data.get("prompt_eval_count", 0)
            decode_tokens = final_data.get("eval_count", 0)

            prompt_tps = round(prompt_tokens / (prompt_eval_dur / 1000.0), 2) if prompt_eval_dur > 0 else 0.0
            decode_tps = round(decode_tokens / (eval_dur / 1000.0), 2) if eval_dur > 0 else 0.0

            # Telemetry snapshot
            hw = capture_hardware_telemetry(
                peak_vram=peak_gpu[0],
                peak_util=peak_gpu[1],
                peak_temp=peak_gpu[2],
            )

            # Failure Mode Evaluation
            if family == "hotpotqa_multihop":
                outcome, notes, eval_meta = evaluate_hotpotqa_response(response_text, spec)
            else:
                outcome, notes, eval_meta = evaluate_alfworld_response(response_text, spec)

            record = {
                "experiment_id": experiment_id,
                "model_tag": model,
                "task_id": task_id,
                "benchmark_family": family,
                "category": category,
                "run_type": run_type,
                "iter_num": iter_num,
                "outcome": outcome,
                "outcome_notes": notes,
                "ttft_client_ms": ttft_client_ms,
                "prompt_tps": prompt_tps,
                "decode_tps": decode_tps,
                "peak_vram_mb": hw.peak_gpu_vram_used_mb,
                "gpu_temp_c": hw.peak_gpu_temp_c,
                "response_tokens": decode_tokens,
                "response_text": response_text,
            }

            records.append(record)

            # Append to files
            with open(jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")

            status_icon = "✔" if outcome == "SUCCESS" else "✘"
            print(
                f"   iter {iter_num} [{run_type}]: {status_icon} {outcome} ({notes[:45]}...) | "
                f"TTFT={ttft_client_ms}ms | Decode={decode_tps} TPS | VRAM={hw.peak_gpu_vram_used_mb}MB",
                flush=True,
            )

    # Write CSV
    if records:
        fieldnames = [k for k in records[0].keys() if k != "response_text"]
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for r in records:
                writer.writerow(r)

    print(f"\n[Pocket AI Lab] Completed reasoning benchmark for {model}. Output: {csv_path}\n", flush=True)

    # Statistical Summary with Wilson Confidence Intervals
    measured_runs = [r for r in records if r["run_type"] == "measured"]
    if measured_runs:
        hotpot = [r for r in measured_runs if r["benchmark_family"] == "hotpotqa_multihop"]
        alf = [r for r in measured_runs if r["benchmark_family"] == "alfworld_decision"]

        hp_pass = sum(1 for r in hotpot if r["outcome"] == "SUCCESS")
        alf_pass = sum(1 for r in alf if r["outcome"] == "SUCCESS")

        hp_rate, hp_low, hp_high = compute_wilson_score_interval(hp_pass, len(hotpot))
        alf_rate, alf_low, alf_high = compute_wilson_score_interval(alf_pass, len(alf))

        print("=" * 80)
        print(" REASONING EVALUATION SUMMARY (MEASURED ITERATIONS WITH UNCERTAINTY)")
        print("=" * 80)
        print(f"HotpotQA (Multi-Hop Knowledge) : {hp_pass}/{len(hotpot)} ({hp_rate}% | 95% CI: [{hp_low}%, {hp_high}%])")
        print(f"ALFWorld (Sequential Planning) : {alf_pass}/{len(alf)} ({alf_rate}% | 95% CI: [{alf_low}%, {alf_high}%])")
        print("-" * 80)
        print("Failure Modes Breakdown:")
        for fam_name, subset in [("HotpotQA", hotpot), ("ALFWorld", alf)]:
            outcomes: Dict[str, int] = {}
            for r in subset:
                outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
            breakdown = ", ".join(f"{k}: {v}" for k, v in outcomes.items())
            print(f"  {fam_name:<10}: {breakdown}")
        print("=" * 80 + "\n")

    return csv_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--dataset", type=str, default="datasets/reasoning_eval_v2.jsonl")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--warmups", type=int, default=1)
    args = parser.parse_args()

    # Fallback to v1 if v2 not found
    ds = args.dataset if os.path.exists(args.dataset) else "datasets/reasoning_eval_v1.jsonl"

    run_reasoning_benchmark(
        model=args.model,
        dataset_path=ds,
        repeats=args.repeats,
        warmups=args.warmups,
    )
