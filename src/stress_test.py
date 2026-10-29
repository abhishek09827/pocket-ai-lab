"""Pocket AI Lab — Sustained Thermal & Degradation Stress Test (Phase 6).

Executes continuous inference loops on the GTX 1650 to empirical measure:
- Thermal rise and equilibrium temperature.
- Clock frequency throttling and decode throughput degradation over time.
- GPU VRAM stability and memory leakage across sustained workloads.
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
from src.telemetry import GpuPeakSampler, capture_hardware_telemetry


def run_single_inference_pass(
    api_base: str,
    model: str,
    prompt: str,
    max_tokens: int = 256,
) -> Dict[str, Any]:
    """Execute a single streaming generation pass and capture timings."""
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
            "num_predict": max_tokens,
        },
    }

    sampler = GpuPeakSampler(interval_sec=0.2)
    sampler.start()
    t_start = time.perf_counter()

    ttft: Optional[float] = None
    response_chunks: List[str] = []
    final_data: Dict[str, Any] = {}

    try:
        resp = requests.post(url, json=payload, stream=True, timeout=120)
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
    prompt_eval_dur = final_data.get("prompt_eval_duration", 0) / 1e6
    eval_dur = final_data.get("eval_duration", 0) / 1e6
    prompt_tokens = final_data.get("prompt_eval_count", 0)
    response_tokens = final_data.get("eval_count", 0)

    prompt_tps = (prompt_tokens / (prompt_eval_dur / 1000.0)) if prompt_eval_dur > 0 else 0.0
    decode_tps = (response_tokens / (eval_dur / 1000.0)) if eval_dur > 0 else 0.0

    return {
        "ttft_ms": round(ttft or 0.0, 2),
        "e2e_ms": round(e2e_ms, 2),
        "prompt_tokens": prompt_tokens,
        "prompt_tps": round(prompt_tps, 2),
        "response_tokens": response_tokens,
        "decode_tps": round(decode_tps, 2),
        "peak_vram_mb": peak_vram,
        "peak_gpu_util_pct": peak_util,
        "peak_gpu_temp_c": peak_temp,
    }


def plot_thermal_stress_results(
    records: List[Dict[str, Any]],
    output_png: str,
    model_tag: str,
) -> None:
    """Generate publication-ready 3-panel thermal degradation plot."""
    iterations = [r["iteration"] for r in records]
    temps = [r["peak_gpu_temp_c"] for r in records]
    decode_tps = [r["decode_tps"] for r in records]
    vram_mb = [r["peak_vram_mb"] for r in records]
    gpu_utils = [r["peak_gpu_util_pct"] for r in records]

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12), sharex=True)

    # Panel 1: Temperature & Throttling Threshold
    ax1.plot(iterations, temps, marker="o", color="#dc2626", linewidth=2.5, label="GPU Peak Temp (°C)")
    ax1.axhline(y=75.0, color="#f59e0b", linestyle="--", linewidth=1.5, label="Warm Boundary (75°C)")
    ax1.axhline(y=83.0, color="#991b1b", linestyle=":", linewidth=1.5, label="NVIDIA Target Temp (83°C)")
    ax1.set_ylabel("Temp (°C)", fontsize=11, fontweight="bold")
    ax1.set_title(f"Sustained Thermal Stress Analysis — {model_tag} on GTX 1650 (4GB)", fontsize=13, fontweight="bold", pad=12)
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(loc="upper left")

    # Annotate max temp
    if temps:
        max_temp = max(temps)
        max_idx = iterations[temps.index(max_temp)]
        ax1.annotate(
            f"Peak: {max_temp}°C",
            xy=(max_idx, max_temp),
            xytext=(max_idx, max_temp + 3),
            arrowprops=dict(facecolor="#dc2626", shrink=0.05, width=1.5, headwidth=6),
            fontweight="bold",
        )

    # Panel 2: Decode Throughput Degradation
    ax2.plot(iterations, decode_tps, marker="s", color="#2563eb", linewidth=2.5, label="Decode Throughput (TPS)")
    baseline_tps = decode_tps[0] if decode_tps else 1.0
    ax2.axhline(y=baseline_tps, color="#6b7280", linestyle="--", alpha=0.7, label=f"Baseline ({baseline_tps} TPS)")
    ax2.set_ylabel("Decode TPS", fontsize=11, fontweight="bold")
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.legend(loc="upper right")

    # Calculate degradation percentage
    if len(decode_tps) > 1:
        final_tps = decode_tps[-1]
        deg_pct = round(((final_tps - baseline_tps) / baseline_tps) * 100.0, 1)
        status_label = f"Throughput Drift: {deg_pct:+.1f}%"
        color = "#16a34a" if abs(deg_pct) <= 3.0 else "#dc2626"
        ax2.text(0.02, 0.15, status_label, transform=ax2.transAxes, fontsize=11, fontweight="bold", color=color,
                 bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=color, alpha=0.8))

    # Panel 3: VRAM Stability & GPU Utilization
    color_vram = "#7c3aed"
    ax3.set_xlabel("Sustained Iteration #", fontsize=11, fontweight="bold")
    ax3.set_ylabel("Peak VRAM (MB)", color=color_vram, fontsize=11, fontweight="bold")
    line1 = ax3.plot(iterations, vram_mb, marker="^", color=color_vram, linewidth=2, label="VRAM (MB)")
    ax3.tick_params(axis="y", labelcolor=color_vram)
    ax3.grid(True, linestyle="--", alpha=0.5)

    ax3_twin = ax3.twinx()
    color_util = "#059669"
    ax3_twin.set_ylabel("GPU Utilization (%)", color=color_util, fontsize=11, fontweight="bold")
    line2 = ax3_twin.plot(iterations, gpu_utils, marker="x", color=color_util, linestyle="--", linewidth=1.5, label="GPU Util (%)")
    ax3_twin.tick_params(axis="y", labelcolor=color_util)

    # Combined legend
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax3.legend(lines, labels, loc="upper right")

    plt.tight_layout()
    os.makedirs(os.path.dirname(output_png), exist_ok=True)
    plt.savefig(output_png, dpi=300)
    plt.close()


def run_sustained_stress_test(
    model: str = "qwen2.5:1.5b",
    iterations: int = 15,
    max_tokens: int = 256,
    api_base: str = "http://127.0.0.1:11434",
) -> str:
    """Execute sustained stress test loop and record thermal degradation."""
    validate_loopback_url(api_base)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    clean_model = model.replace(":", "_").replace(".", "_").replace("/", "_")
    exp_id = f"stress_{clean_model}_{timestamp}"

    results_dir = "results"
    charts_dir = os.path.join(results_dir, "charts")
    os.makedirs(results_dir, exist_ok=True)
    os.makedirs(charts_dir, exist_ok=True)

    jsonl_path = os.path.join(results_dir, f"{exp_id}.jsonl")
    csv_path = os.path.join(results_dir, f"{exp_id}.csv")
    chart_png = os.path.join(charts_dir, f"thermal_stress_{clean_model}.png")

    stress_prompt = (
        "Write a detailed technical explanation of how modern multi-head self-attention mechanisms "
        "compute query, key, and value matrices, followed by a mathematical step-by-step breakdown "
        "of scaled dot-product attention and its computational complexity."
    )

    print(f"\n========================================================")
    print(f" POCKET AI LAB — SUSTAINED THERMAL STRESS TEST (PHASE 6)")
    print(f" Target Model : {model}")
    print(f" Iterations   : {iterations} consecutive passes")
    print(f" Max Tokens   : {max_tokens} tokens/iteration")
    print(f" Output JSONL : {jsonl_path}")
    print(f"========================================================\n")

    records: List[Dict[str, Any]] = []

    for i in range(1, iterations + 1):
        print(f"[{i:02d}/{iterations:02d}] Executing sustained inference pass...", end=" ", flush=True)
        metrics = run_single_inference_pass(
            api_base=api_base,
            model=model,
            prompt=stress_prompt,
            max_tokens=max_tokens,
        )

        row = {
            "iteration": i,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "model_tag": model,
            "decode_tps": metrics["decode_tps"],
            "prompt_tps": metrics["prompt_tps"],
            "ttft_ms": metrics["ttft_ms"],
            "e2e_ms": metrics["e2e_ms"],
            "response_tokens": metrics["response_tokens"],
            "peak_gpu_temp_c": metrics["peak_gpu_temp_c"] or 0.0,
            "peak_vram_mb": metrics["peak_vram_mb"] or 0.0,
            "peak_gpu_util_pct": metrics["peak_gpu_util_pct"] or 0.0,
        }
        records.append(row)

        print(
            f"Done | TPS: {metrics['decode_tps']:5.2f} | "
            f"Temp: {row['peak_gpu_temp_c']:2.0f}°C | "
            f"VRAM: {row['peak_vram_mb']:5.1f}MB | "
            f"Util: {row['peak_gpu_util_pct']:3.0f}%"
        )

        # Write append-only JSONL
        with open(jsonl_path, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(row) + "\n")

    # Export CSV
    if records:
        with open(csv_path, "w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)

    # Plot results
    print(f"\n[Plotting] Generating publication-grade thermal chart...")
    plot_thermal_stress_results(records, chart_png, model)
    print(f"[Plotting] Saved chart to {chart_png}")

    # Copy to web static directory if exists
    web_charts = os.path.join("web", "charts")
    if os.path.exists(web_charts):
        shutil.copy(chart_png, os.path.join(web_charts, f"thermal_stress_{clean_model}.png"))

    # Print summary statistics
    initial_tps = records[0]["decode_tps"]
    final_tps = records[-1]["decode_tps"]
    min_tps = min(r["decode_tps"] for r in records)
    max_tps = max(r["decode_tps"] for r in records)
    peak_temp = max(r["peak_gpu_temp_c"] for r in records)
    initial_temp = records[0]["peak_gpu_temp_c"]
    deg_pct = ((final_tps - initial_tps) / initial_tps) * 100.0 if initial_tps > 0 else 0.0

    print("\n------------------ STRESS TEST SUMMARY ------------------")
    print(f" Initial Decode TPS : {initial_tps:.2f} tokens/sec")
    print(f" Final Decode TPS   : {final_tps:.2f} tokens/sec")
    print(f" Throughput Drift   : {deg_pct:+.2f}%")
    print(f" TPS Range          : [{min_tps:.2f} - {max_tps:.2f}] tokens/sec")
    print(f" GPU Temp Range     : [{initial_temp:.0f}°C -> {peak_temp:.0f}°C]")
    print(f" Results Artifact   : {jsonl_path}")
    print("---------------------------------------------------------\n")

    return chart_png


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run sustained thermal stress test")
    parser.add_argument("--model", type=str, default="qwen2.5:1.5b", help="Model tag")
    parser.add_argument("--iterations", type=int, default=10, help="Number of consecutive iterations")
    parser.add_argument("--max-tokens", type=int, default=256, help="Tokens to generate per iteration")
    parser.add_argument("--api-base", type=str, default="http://127.0.0.1:11434", help="Ollama loopback endpoint")
    args = parser.parse_args()

    run_sustained_stress_test(
        model=args.model,
        iterations=args.iterations,
        max_tokens=args.max_tokens,
        api_base=args.api_base,
    )
