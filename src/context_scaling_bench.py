"""Pocket AI Lab — Context Window & KV-Cache Scaling Benchmark.

Empirically measures how context length (256 -> 4,096 tokens) impacts:
1. Time-to-First-Token (TTFT) and Prompt Evaluation TPS ($O(N)$ vs $O(N^2)$).
2. KV-Cache VRAM memory expansion on the 4GB GTX 1650.
3. Decode throughput degradation under long context windows.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.benchmark import validate_loopback_url
from src.telemetry import GpuPeakSampler


def generate_synthetic_prompt(approx_tokens: int) -> str:
    """Generate a clean, coherent repeated factual text of approximately target token count."""
    base_sentence = (
        "In modern machine learning architectures, transformer attention mechanisms dynamically calculate "
        "relevance weights between token representations across deep residual representations. "
    )
    # Approx 20 tokens per sentence
    repeats = max(1, approx_tokens // 20)
    prompt_text = (base_sentence * repeats) + "\n\nBased on the above context, summarize the key takeaway in one sentence."
    return prompt_text


def run_context_pass(
    api_base: str,
    model: str,
    prompt: str,
    target_ctx: int,
    max_decode_tokens: int = 48,
) -> Dict[str, Any]:
    """Execute a single context evaluation pass with exact GPU peak telemetry."""
    validate_loopback_url(api_base)
    url = f"{api_base.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 42,
            "num_ctx": max(4096, target_ctx + 256),
            "num_predict": max_decode_tokens,
        },
    }

    sampler = GpuPeakSampler(interval_sec=0.1)
    sampler.start()
    t_start = time.perf_counter()

    ttft: Optional[float] = None
    response_chunks: List[str] = []
    final_data: Dict[str, Any] = {}

    try:
        resp = requests.post(url, json=payload, stream=True, timeout=180)
        resp.raise_for_status()

        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            chunk = json.loads(line)
            if ttft is None:
                ttft = (time.perf_counter() - t_start) * 1000.0
            response_chunks.append(chunk.get("response", ""))
            if chunk.get("done", False):
                final_data = chunk
                break
    finally:
        t_end = time.perf_counter()
        peak_vram, peak_util, peak_temp = sampler.stop()

    e2e_ms = (t_end - t_start) * 1000.0
    prompt_tokens = final_data.get("prompt_eval_count", 0)
    prompt_eval_dur = (final_data.get("prompt_eval_duration", 0) / 1e6) or 1.0
    decode_tokens = final_data.get("eval_count", 0)
    decode_dur = (final_data.get("eval_duration", 0) / 1e6) or 1.0

    prompt_tps = (prompt_tokens / (prompt_eval_dur / 1000.0)) if prompt_eval_dur > 0 else 0.0
    decode_tps = (decode_tokens / (decode_dur / 1000.0)) if decode_dur > 0 else 0.0

    return {
        "target_ctx": target_ctx,
        "prompt_tokens": prompt_tokens,
        "prompt_eval_duration_ms": round(prompt_eval_dur, 2),
        "prompt_tps": round(prompt_tps, 2),
        "ttft_ms": round(ttft or 0.0, 2),
        "decode_tokens": decode_tokens,
        "decode_tps": round(decode_tps, 2),
        "e2e_ms": round(e2e_ms, 2),
        "peak_vram_mb": peak_vram or 0.0,
        "peak_gpu_util_pct": peak_util or 0.0,
        "peak_gpu_temp_c": peak_temp or 0.0,
    }


def plot_context_scaling(
    records: List[Dict[str, Any]],
    output_png: str,
    model_tag: str,
) -> None:
    """Generate 2-panel context scaling and KV-cache expansion chart."""
    ctx_lengths = [r["prompt_tokens"] for r in records]
    ttft_vals = [r["ttft_ms"] for r in records]
    prompt_tps_vals = [r["prompt_tps"] for r in records]
    vram_vals = [r["peak_vram_mb"] for r in records]
    decode_tps_vals = [r["decode_tps"] for r in records]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 10), sharex=True)

    # Panel 1: TTFT & Prompt Evaluation Speed
    color_ttft = "#ef4444"
    ax1.set_ylabel("TTFT (ms)", color=color_ttft, fontsize=11, fontweight="bold")
    line1 = ax1.plot(ctx_lengths, ttft_vals, marker="o", color=color_ttft, linewidth=2.5, label="Time to First Token (TTFT ms)")
    ax1.tick_params(axis="y", labelcolor=color_ttft)
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.set_title(f"Context Scaling & KV-Cache Footprint — {model_tag} on GTX 1650 (4GB)", fontsize=13, fontweight="bold", pad=12)

    ax1_twin = ax1.twinx()
    color_tps = "#0284c7"
    ax1_twin.set_ylabel("Prompt Prefill TPS", color=color_tps, fontsize=11, fontweight="bold")
    line2 = ax1_twin.plot(ctx_lengths, prompt_tps_vals, marker="s", color=color_tps, linestyle="--", linewidth=2, label="Prompt Speed (TPS)")
    ax1_twin.tick_params(axis="y", labelcolor=color_tps)

    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper left")

    # Panel 2: KV-Cache Expansion & 4GB Hardware Ceiling
    color_vram = "#8b5cf6"
    ax2.set_xlabel("Input Context Length (Tokens)", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Peak VRAM Footprint (MB)", color=color_vram, fontsize=11, fontweight="bold")
    line_vram = ax2.plot(ctx_lengths, vram_vals, marker="^", color=color_vram, linewidth=2.5, label="Peak VRAM (MB)")
    ax2.axhline(y=4096.0, color="#dc2626", linestyle=":", linewidth=2, label="GTX 1650 4GB Hard Barrier (4,096 MB)")
    ax2.tick_params(axis="y", labelcolor=color_vram)
    ax2.grid(True, linestyle="--", alpha=0.5)

    ax2_twin = ax2.twinx()
    color_dec = "#10b981"
    ax2_twin.set_ylabel("Decode Speed (TPS)", color=color_dec, fontsize=11, fontweight="bold")
    line_dec = ax2_twin.plot(ctx_lengths, decode_tps_vals, marker="d", color=color_dec, linestyle="-.", linewidth=2, label="Decode Throughput (TPS)")
    ax2_twin.tick_params(axis="y", labelcolor=color_dec)

    all_l = line_vram + [ax2.get_lines()[-1]] + line_dec
    all_lbl = [l.get_label() for l in all_l]
    ax2.legend(all_l, all_lbl, loc="center left")

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_png), exist_ok=True)
    plt.savefig(output_png, dpi=300)
    plt.close()


def run_context_scaling_suite(
    model: str = "qwen2.5:1.5b",
    ctx_steps: Optional[List[int]] = None,
    api_base: str = "http://127.0.0.1:11434",
) -> str:
    """Run full context scaling suite and record empirical KV-cache growth."""
    validate_loopback_url(api_base)
    if ctx_steps is None:
        ctx_steps = [256, 512, 1024, 2048, 3072, 4096]

    clean_model = model.replace(":", "_").replace(".", "_").replace("/", "_")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    exp_id = f"context_scaling_{clean_model}_{timestamp}"

    results_dir = "results"
    charts_dir = os.path.join(results_dir, "charts")
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(charts_dir, exist_ok=True)

    csv_path = os.path.join(results_dir, f"{exp_id}.csv")
    chart_png = os.path.join(charts_dir, f"context_scaling_{clean_model}.png")

    print(f"\n========================================================")
    print(f" POCKET AI LAB — CONTEXT SCALING & KV-CACHE BENCHMARK")
    print(f" Target Model : {model}")
    print(f" Context Steps: {ctx_steps} tokens")
    print(f" Hardware     : NVIDIA GeForce GTX 1650 (4,096 MB VRAM)")
    print(f" Output CSV   : {csv_path}")
    print(f"========================================================\n")

    records: List[Dict[str, Any]] = []

    for ctx in ctx_steps:
        print(f"Evaluating context length ~{ctx:4d} tokens...", end=" ", flush=True)
        prompt = generate_synthetic_prompt(ctx)
        pass_metrics = run_context_pass(
            api_base=api_base,
            model=model,
            prompt=prompt,
            target_ctx=ctx,
        )
        pass_metrics["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        pass_metrics["model_tag"] = model
        records.append(pass_metrics)

        print(
            f"Done | Actual Tokens: {pass_metrics['prompt_tokens']:4d} | "
            f"TTFT: {pass_metrics['ttft_ms']:6.1f}ms | "
            f"Prefill: {pass_metrics['prompt_tps']:5.1f} TPS | "
            f"Decode: {pass_metrics['decode_tps']:4.1f} TPS | "
            f"Peak VRAM: {pass_metrics['peak_vram_mb']:5.1f}MB"
        )

    # Save CSV
    if records:
        with open(csv_path, "w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)

    # Plot
    print(f"\n[Plotting] Generating context scaling chart...")
    plot_context_scaling(records, chart_png, model)
    print(f"[Plotting] Saved chart to {chart_png}")

    web_charts = os.path.join("web", "charts")
    if os.path.exists(web_charts):
        shutil.copy(chart_png, os.path.join(web_charts, f"context_scaling_{clean_model}.png"))

    return chart_png


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run context scaling benchmark")
    parser.add_argument("--model", type=str, default="qwen2.5:1.5b", help="Model tag")
    parser.add_argument("--steps", nargs="+", type=int, default=[256, 512, 1024, 2048, 3072], help="Context token lengths")
    args = parser.parse_args()

    run_context_scaling_suite(model=args.model, ctx_steps=args.steps)
