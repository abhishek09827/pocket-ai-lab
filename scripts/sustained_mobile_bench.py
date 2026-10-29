"""Sustained Mobile Inference and Thermal Analysis Benchmark for realme 9 Pro+.

Executes sustained inference runs on the Dimensity 920 edge SoC over Tailscale SSH tunnel.
Measures:
- Generation throughput over time across consecutive passes
- Cold-start versus warm-run latency
- Memory usage and OOM events
- Battery percentage before and after (explicitly labeled as an indicator, not calibrated Joules)
- Throughput degradation caused by sustained CPU load
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def run_ssh_cmd(
    cmd: str,
    phone_ip: str = "100.84.51.84",
    port: int = 8022,
    timeout: float = 60.0,
) -> Tuple[int, str, str]:
    """Execute command on phone via SSH tunnel."""
    ssh_args = [
        "ssh", "-p", str(port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        phone_ip,
        cmd,
    ]
    proc = subprocess.run(ssh_args, capture_output=True, text=True, timeout=timeout, check=False)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def query_phone_memory(phone_ip: str, port: int) -> Dict[str, Optional[int]]:
    """Parse free -m on phone."""
    rc, out, _ = run_ssh_cmd("free -m", phone_ip=phone_ip, port=port)
    res = {"ram_total_mb": None, "ram_used_mb": None, "ram_available_mb": None}
    if rc == 0:
        lines = out.splitlines()
        for line in lines:
            if line.startswith("Mem:"):
                parts = line.split()
                if len(parts) >= 7:
                    res["ram_total_mb"] = int(parts[1])
                    res["ram_used_mb"] = int(parts[2])
                    res["ram_available_mb"] = int(parts[6])
    return res


def query_battery_indicator(phone_ip: str, port: int) -> Optional[int]:
    """Query battery percentage indicator if available via sysfs or props."""
    cmd = "cat /sys/class/power_supply/battery/capacity 2>/dev/null || getprop ro.boot.battery_capacity 2>/dev/null || echo ''"
    rc, out, _ = run_ssh_cmd(cmd, phone_ip=phone_ip, port=port)
    if rc == 0 and out.strip().isdigit():
        return int(out.strip())
    return None


def run_sustained_mobile_bench(
    phone_ip: str = "100.84.51.84",
    port: int = 8022,
    iterations: int = 15,
    tokens_per_pass: int = 128,
    output_dir: str = "results",
) -> Dict[str, Any]:
    """Execute sustained mobile benchmark."""
    print("=" * 80)
    print(" POCKET AI LAB — SUSTAINED MOBILE INFERENCE & THERMAL ANALYSIS")
    print(f" Target Device : realme 9 Pro+ (MediaTek Dimensity 920 6nm)")
    print(f" Runtime       : llama.cpp ARM64 NEON (-t 6 threads)")
    print(f" Workload      : {iterations} consecutive inference passes ({tokens_per_pass} tokens each)")
    print("=" * 80 + "\n")

    model_path = "~/pocket-ai-lab/models/qwen2.5-1.5b-instruct-q4_k_m.gguf"
    prompt = "Explain in detail the differences between CPU cache hierarchy (L1, L2, L3) and DRAM in modern mobile processors."

    # Pre-workload checks
    mem_before = query_phone_memory(phone_ip, port)
    bat_before = query_battery_indicator(phone_ip, port)
    print(f"[Initial] RAM: Used={mem_before['ram_used_mb']}MB, Available={mem_before['ram_available_mb']}MB")
    if bat_before is not None:
        print(f"[Initial] Battery Level: {bat_before}% (Device Indicator)")

    iteration_records = []
    t_bench_start = time.time()

    for iter_idx in range(1, iterations + 1):
        is_cold = iter_idx == 1
        run_type = "cold_start" if is_cold else "sustained_warm"

        # llama-completion command with explicit single-turn and closed stdin
        llama_cmd = (
            f"llama-completion -m {model_path} -p '{prompt}' -n {tokens_per_pass} "
            f"-t 6 --single-turn -no-cnv --no-display-prompt --no-warmup < /dev/null 2>&1"
        )

        iter_start = time.time()
        rc, out, err = run_ssh_cmd(llama_cmd, phone_ip=phone_ip, port=port, timeout=120.0)
        iter_dur = round(time.time() - iter_start, 2)

        mem_current = query_phone_memory(phone_ip, port)
        oom_occurred = rc == 137 or "out of memory" in out.lower() or "killed" in out.lower()

        # Parse throughput from llama-completion stdout
        # e.g.: llama_perf_sampler_print: ...
        # or parse from prompt eval and eval timing lines
        eval_tps: Optional[float] = None
        prompt_tps: Optional[float] = None

        eval_match = re.search(r"eval time\s*=\s*[\d\.]+\s*ms\s*/\s*(\d+)\s*runs\s*\(\s*[\d\.]+\s*ms per token,\s*([\d\.]+)\s*tokens per second\)", out)
        if eval_match:
            eval_tps = float(eval_match.group(2))

        peval_match = re.search(r"prompt eval time\s*=\s*[\d\.]+\s*ms\s*/\s*(\d+)\s*tokens\s*\(\s*[\d\.]+\s*ms per token,\s*([\d\.]+)\s*tokens per second\)", out)
        if peval_match:
            prompt_tps = float(peval_match.group(2))

        # Fallback approximation from duration if llama banner was silenced
        if eval_tps is None and iter_dur > 0:
            eval_tps = round(tokens_per_pass / iter_dur, 2)

        rec = {
            "iteration": iter_idx,
            "run_type": run_type,
            "duration_sec": iter_dur,
            "decode_tps": eval_tps,
            "prompt_tps": prompt_tps,
            "ram_used_mb": mem_current.get("ram_used_mb"),
            "ram_available_mb": mem_current.get("ram_available_mb"),
            "oom_detected": oom_occurred,
            "exit_code": rc,
        }
        iteration_records.append(rec)

        tps_str = f"{eval_tps:.2f} TPS" if eval_tps else "N/A"
        print(f"  [{iter_idx:02d}/{iterations:02d}] ({run_type:<14}): Decode Speed={tps_str} | Dur={iter_dur}s | RAM Used={rec['ram_used_mb']}MB")

        # Brief sleep between bursts
        time.sleep(1.0)

    total_bench_time = round(time.time() - t_bench_start, 1)
    mem_after = query_phone_memory(phone_ip, port)
    bat_after = query_battery_indicator(phone_ip, port)

    # Compute degradation analysis
    tps_values = [r["decode_tps"] for r in iteration_records if r["decode_tps"] is not None]
    cold_tps = tps_values[0] if tps_values else 0.0
    warm_tps_list = tps_values[1:] if len(tps_values) > 1 else tps_values
    peak_warm_tps = max(warm_tps_list) if warm_tps_list else cold_tps

    # Tail median (last 3-5 runs)
    tail_runs = warm_tps_list[-3:] if len(warm_tps_list) >= 3 else warm_tps_list
    sustained_tail_tps = sorted(tail_runs)[len(tail_runs)//2] if tail_runs else peak_warm_tps

    degradation_pct = round(((peak_warm_tps - sustained_tail_tps) / peak_warm_tps) * 100.0, 2) if peak_warm_tps > 0 else 0.0

    bat_delta = (bat_before - bat_after) if (bat_before is not None and bat_after is not None) else None

    summary = {
        "device": "realme 9 Pro+ (RMX3392)",
        "soc": "MediaTek Dimensity 920 5G",
        "model": "qwen2.5:1.5b",
        "quantization": "Q4_K_M",
        "runtime": "llama.cpp ARM64 NEON",
        "threads": 6,
        "total_iterations": iterations,
        "total_duration_sec": total_bench_time,
        "cold_start_tps": cold_tps,
        "peak_warm_tps": peak_warm_tps,
        "sustained_tail_tps": sustained_tail_tps,
        "performance_degradation_pct": degradation_pct,
        "battery_before_pct": bat_before,
        "battery_after_pct": bat_after,
        "battery_delta_pct": bat_delta,
        "energy_measurement_note": "Battery delta is a secondary device state indicator and not a calibrated Joules measurement.",
        "oom_events": sum(1 for r in iteration_records if r["oom_detected"]),
        "iterations": iteration_records,
    }

    # Save to disk
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "mobile_sustained_qwen2_5_1_5b.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    jsonl_path = os.path.join(output_dir, "mobile_sustained_qwen2_5_1_5b.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in iteration_records:
            f.write(json.dumps(r) + "\n")

    print("\n" + "=" * 80)
    print(" SUSTAINED MOBILE INFERENCE ANALYSIS RESULTS")
    print("=" * 80)
    print(f"Cold Start Throughput    : {cold_tps:.2f} TPS")
    print(f"Peak Warm Throughput     : {peak_warm_tps:.2f} TPS")
    print(f"Sustained Tail Throughput: {sustained_tail_tps:.2f} TPS")
    print(f"Throughput Degradation   : {degradation_pct}% (Thermal throttling effect)")
    print(f"OOM Events Detected      : {summary['oom_events']}")
    print(f"Total Workload Duration  : {total_bench_time} seconds (~{total_bench_time/60:.1f} mins)")
    print(f"Outputs Saved            : {json_path}")
    print("=" * 80 + "\n")

    # Generate degradation plot
    plot_path = os.path.join(output_dir, "charts", "mobile_sustained_thermal_degradation.png")
    plot_sustained_degradation(iteration_records, plot_path, peak_warm_tps, sustained_tail_tps)

    return summary


def plot_sustained_degradation(
    records: List[Dict[str, Any]],
    output_png: str,
    peak_tps: float,
    tail_tps: float,
) -> None:
    """Generate high-resolution sustained throughput chart."""
    os.makedirs(os.path.dirname(os.path.abspath(output_png)), exist_ok=True)
    iters = [r["iteration"] for r in records]
    tps = [r["decode_tps"] for r in records]
    ram = [r["ram_used_mb"] for r in records]

    fig, ax1 = plt.subplots(figsize=(10, 5), dpi=300)

    # Style
    fig.patch.set_facecolor("#0F172A")
    ax1.set_facecolor("#1E293B")
    ax1.grid(True, linestyle="--", alpha=0.3, color="#64748B")

    # Plot TPS line
    color_tps = "#38BDF8"
    line1 = ax1.plot(iters, tps, color=color_tps, marker="o", linewidth=2.5, label="Decode Throughput (TPS)")
    ax1.set_xlabel("Sustained Workload Iteration", color="#F8FAFC", fontsize=11, fontweight="bold")
    ax1.set_ylabel("Generation Throughput (Tokens/sec)", color=color_tps, fontsize=11, fontweight="bold")
    ax1.tick_params(colors="#CBD5E1")

    # Annotate peak and tail
    if peak_tps > 0:
        ax1.axhline(peak_tps, color="#4ADE80", linestyle=":", alpha=0.7, label=f"Peak Warm ({peak_tps:.2f} TPS)")
    if tail_tps > 0:
        ax1.axhline(tail_tps, color="#F87171", linestyle=":", alpha=0.7, label=f"Sustained Tail ({tail_tps:.2f} TPS)")

    # Secondary axis: RAM Used
    ax2 = ax1.twinx()
    color_ram = "#F59E0B"
    line2 = ax2.plot(iters, ram, color=color_ram, linestyle="--", marker="s", alpha=0.8, label="RAM Used (MB)")
    ax2.set_ylabel("RAM Used on Device (MB)", color=color_ram, fontsize=11, fontweight="bold")
    ax2.tick_params(colors="#CBD5E1")

    # Title
    plt.title(
        "realme 9 Pro+ (Dimensity 920): Sustained Inference & Thermal Stability\n"
        "Model: Qwen2.5-1.5B (Q4_K_M) | llama.cpp ARM64 NEON (6 Threads)",
        color="#F8FAFC",
        fontsize=12,
        fontweight="bold",
        pad=15,
    )

    # Combine legends
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper right", facecolor="#0F172A", edgecolor="#475569", labelcolor="#F8FAFC")

    plt.tight_layout()
    plt.savefig(output_png, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close()
    print(f"[Chart] Saved sustained mobile degradation chart to {output_png}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phone-ip", type=str, default="100.84.51.84")
    parser.add_argument("--port", type=int, default=8022)
    parser.add_argument("--iterations", type=int, default=15)
    parser.add_argument("--tokens", type=int, default=128)
    args = parser.parse_args()

    run_sustained_mobile_bench(
        phone_ip=args.phone_ip,
        port=args.port,
        iterations=args.iterations,
        tokens_per_pass=args.tokens,
    )
