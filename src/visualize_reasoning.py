"""Generate publication-ready comparison charts for Edge AI Reasoning Benchmarks."""
from __future__ import annotations

import csv
import glob
import os
import shutil
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def load_all_reasoning_results(results_dir: str = "results") -> List[Dict[str, Any]]:
    """Load records from all reasoning benchmark CSVs."""
    records = []
    csv_files = glob.glob(os.path.join(results_dir, "reasoning_*.csv"))
    for file_path in csv_files:
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(row)
    return records


def generate_charts(output_dir: str = "results/charts", artifact_dir: str = None) -> List[str]:
    """Generate visual analysis charts and optionally copy to brain artifact dir."""
    os.makedirs(output_dir, exist_ok=True)
    all_data = load_all_reasoning_results()

    # Filter to measured runs
    measured = [r for r in all_data if r.get("run_type") == "measured"]
    if not measured:
        print("[Visualizer] No measured data found.")
        return []

    models = sorted(list(set(r["model_tag"] for r in measured)))
    print(f"[Visualizer] Generating charts for models: {models}")

    generated_files = []

    # -------------------------------------------------------------
    # Chart 1: ALFWorld Decision-Making Failure Decomposition
    # -------------------------------------------------------------
    alf_data = [r for r in measured if r.get("benchmark_family") == "alfworld_decision"]
    if alf_data:
        plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
        fig, ax = plt.subplots(figsize=(9, 5.5), dpi=150)

        categories = ["SUCCESS", "INVALID_ACTION", "INCOMPLETE", "HALLUCINATION"]
        cat_labels = ["Success", "Precondition / Invalid Action", "Incomplete Plan", "Hallucination"]
        colors = ["#2ecc71", "#e74c3c", "#f39c12", "#9b59b6"]

        x = np.arange(len(models))
        width = 0.2

        for i, (cat, color, label) in enumerate(zip(categories, colors, cat_labels)):
            counts = []
            for m in models:
                m_records = [r for r in alf_data if r["model_tag"] == m]
                total = len(m_records) or 1
                cat_count = sum(1 for r in m_records if r["outcome"] == cat)
                pct = (cat_count / total) * 100.0
                counts.append(pct)
            ax.bar(x + (i - 1.5) * width, counts, width, label=label, color=color, edgecolor="black", linewidth=0.5)

        ax.set_title("ALFWorld Embodied Decision-Making: Failure Mode Breakdown\n(Inspired by Shinn & Labash et al., 2023 - Reflexion)", fontsize=13, fontweight="bold", pad=12)
        ax.set_ylabel("Percentage of Measured Trials (%)", fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels(models, fontsize=11, fontweight="semibold")
        ax.set_ylim(0, 105)
        ax.legend(title="Outcome / Failure Type", loc="upper right", frameon=True)
        fig.tight_layout()

        c1_path = os.path.join(output_dir, "alfworld_failure_decomposition.png")
        plt.savefig(c1_path)
        plt.close(fig)
        generated_files.append(c1_path)

    # -------------------------------------------------------------
    # Chart 2: HotpotQA Multi-Hop Knowledge Retrieval Accuracy
    # -------------------------------------------------------------
    hotpot_data = [r for r in measured if r.get("benchmark_family") == "hotpotqa_multihop"]
    if hotpot_data:
        fig, ax = plt.subplots(figsize=(8, 5), dpi=150)

        accuracies = []
        hallucination_rates = []

        for m in models:
            m_records = [r for r in hotpot_data if r["model_tag"] == m]
            tot = len(m_records) or 1
            succ = sum(1 for r in m_records if r["outcome"] == "SUCCESS")
            hall = sum(1 for r in m_records if r["outcome"] == "HALLUCINATION")
            accuracies.append((succ / tot) * 100.0)
            hallucination_rates.append((hall / tot) * 100.0)

        x = np.arange(len(models))
        width = 0.35

        ax.bar(x - width/2, accuracies, width, label="Accuracy (Valid Multi-Hop)", color="#3498db", edgecolor="black", linewidth=0.5)
        ax.bar(x + width/2, hallucination_rates, width, label="Hallucination Rate", color="#e67e22", edgecolor="black", linewidth=0.5)

        ax.set_title("HotpotQA Multi-Hop Reasoning: Accuracy vs Hallucination Rate", fontsize=13, fontweight="bold", pad=12)
        ax.set_ylabel("Percentage (%)", fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels(models, fontsize=11, fontweight="semibold")
        ax.set_ylim(0, 110)
        ax.legend(loc="upper right", frameon=True)
        fig.tight_layout()

        c2_path = os.path.join(output_dir, "hotpotqa_hallucination_vs_accuracy.png")
        plt.savefig(c2_path)
        plt.close(fig)
        generated_files.append(c2_path)

    # -------------------------------------------------------------
    # Chart 3: GTX 1650 4GB Hardware Frontier: VRAM vs Throughput
    # -------------------------------------------------------------
    fig, ax1 = plt.subplots(figsize=(8.5, 5), dpi=150)

    vram_vals = []
    decode_tps_vals = []

    for m in models:
        m_records = [r for r in measured if r["model_tag"] == m]
        vrams = [float(r["peak_vram_mb"]) for r in m_records if r.get("peak_vram_mb")]
        tps = [float(r["decode_tps"]) for r in m_records if r.get("decode_tps")]
        vram_vals.append(np.mean(vrams) if vrams else 0)
        decode_tps_vals.append(np.mean(tps) if tps else 0)

    x = np.arange(len(models))
    width = 0.35

    color1 = "#2c3e50"
    color2 = "#27ae60"

    b1 = ax1.bar(x - width/2, vram_vals, width, label="Peak VRAM Footprint (MB)", color=color1, edgecolor="black", linewidth=0.5)
    ax1.set_ylabel("VRAM Footprint (MB)", color=color1, fontsize=11, fontweight="bold")
    ax1.tick_params(axis="y", labelcolor=color1)
    ax1.set_xticks(x)
    ax1.set_xticklabels(models, fontsize=11, fontweight="semibold")
    ax1.axhline(4096, color="#c0392b", linestyle="--", linewidth=1.5, label="GTX 1650 Limit (4096 MB)")
    ax1.set_ylim(0, 4800)

    ax2 = ax1.twinx()
    b2 = ax2.bar(x + width/2, decode_tps_vals, width, label="Token Decode Speed (TPS)", color=color2, edgecolor="black", linewidth=0.5)
    ax2.set_ylabel("Decode Speed (TPS)", color=color2, fontsize=11, fontweight="bold")
    ax2.tick_params(axis="y", labelcolor=color2)
    ax2.set_ylim(0, max(decode_tps_vals) * 1.3 if decode_tps_vals else 100)

    plt.title("NVIDIA GTX 1650 (4GB) Frontier: Memory Footprint vs Throughput", fontsize=13, fontweight="bold", pad=12)
    fig.tight_layout()

    c3_path = os.path.join(output_dir, "edge_hardware_tradeoffs.png")
    plt.savefig(c3_path)
    plt.close(fig)
    generated_files.append(c3_path)

    # Copy to brain artifact directory if specified
    if artifact_dir and os.path.exists(artifact_dir):
        for fpath in generated_files:
            fname = os.path.basename(fpath)
            shutil.copy(fpath, os.path.join(artifact_dir, fname))
            print(f"[Visualizer] Copied {fname} to artifact directory {artifact_dir}")

    print(f"[Visualizer] Successfully generated {len(generated_files)} charts in {output_dir}")
    return generated_files


if __name__ == "__main__":
    artifact_dir = "/home/abhishek/.gemini/antigravity-cli/brain/ed69ac16-08e2-439f-89b9-b4e2c4e43de4"
    generate_charts(output_dir="results/charts", artifact_dir=artifact_dir)
