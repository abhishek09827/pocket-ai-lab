"""Pocket AI Lab — Extra Visual Charts Generator.

Generates 4 additional high-resolution research charts:
1. hardware_duel_task_breakdown.png — Per-task decode & prefill TPS comparison (PC vs Phone).
2. energy_efficiency_pareto.png — Tokens-per-Watt Pareto frontier with iso-efficiency curves.
3. ttft_latency_comparison.png — Time-to-First-Token and latency distribution across models.
4. cognitive_reasoning_tradeoff.png — Multi-dimensional reasoning vs speed vs memory bubble chart.
"""
from __future__ import annotations

import os
import shutil
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def set_plot_style():
    """Configure modern, publication-grade styling."""
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Helvetica", "Arial"]
    plt.rcParams["axes.edgecolor"] = "#374151"
    plt.rcParams["axes.linewidth"] = 1.0


def plot_hardware_duel_tasks(output_png: str):
    """Chart 1: Cross-Platform Per-Task Throughput Comparison."""
    set_plot_style()
    tasks = [
        "Short Factual\n(Capital)",
        "Summarization\n(History)",
        "Python Coding\n(Algorithm)",
        "Strict JSON\n(Schema)",
        "Translation\n(EN -> HI)",
    ]
    pc_decode = [46.4, 46.4, 45.8, 46.0, 46.2]
    phone_decode = [18.0, 9.1, 9.1, 9.9, 8.7]

    pc_prompt = [330.0, 354.2, 340.0, 345.0, 335.0]
    phone_prompt = [15.8, 15.1, 15.5, 15.1, 15.1]

    x = np.arange(len(tasks))
    width = 0.35

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    # Panel A: Generation Decode TPS
    rects1 = ax1.bar(x - width/2, pc_decode, width, label="Host PC (GTX 1650 CUDA)", color="#0284c7", edgecolor="#0369a1")
    rects2 = ax1.bar(x + width/2, phone_decode, width, label="realme 9 Pro+ (Dimensity 920 CPU)", color="#10b981", edgecolor="#059669")
    ax1.set_ylabel("Autoregressive Decode Speed (Tokens/s)", fontsize=11, fontweight="bold")
    ax1.set_title("Autoregressive Decode Throughput (Memory-Bandwidth Bound)", fontsize=11, fontweight="bold", pad=10)
    ax1.set_xticks(x)
    ax1.set_xticklabels(tasks, fontsize=9)
    ax1.legend(loc="upper right", framealpha=0.9)
    ax1.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax1.set_ylim(0, 55)

    for r in rects1:
        h = r.get_height()
        ax1.annotate(f"{h:.1f}", xy=(r.get_x() + r.get_width()/2, h), xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=8, fontweight="bold", color="#0369a1")
    for r in rects2:
        h = r.get_height()
        ax1.annotate(f"{h:.1f}", xy=(r.get_x() + r.get_width()/2, h), xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=8, fontweight="bold", color="#059669")

    # Panel B: Prompt Prefill TPS (Log scale recommended due to 22x gap)
    rects3 = ax2.bar(x - width/2, pc_prompt, width, label="Host PC (GTX 1650 CUDA)", color="#0284c7", edgecolor="#0369a1")
    rects4 = ax2.bar(x + width/2, phone_prompt, width, label="realme 9 Pro+ (Dimensity 920 CPU)", color="#10b981", edgecolor="#059669")
    ax2.set_ylabel("Prompt Prefill Speed (Tokens/s)", fontsize=11, fontweight="bold")
    ax2.set_title("Prompt Evaluation Throughput (Compute Bound — ~22x CUDA Divergence)", fontsize=11, fontweight="bold", pad=10)
    ax2.set_xticks(x)
    ax2.set_xticklabels(tasks, fontsize=9)
    ax2.legend(loc="upper right", framealpha=0.9)
    ax2.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax2.set_ylim(0, 410)

    for r in rects3:
        h = r.get_height()
        ax2.annotate(f"{h:.0f}", xy=(r.get_x() + r.get_width()/2, h), xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=8, fontweight="bold", color="#0369a1")
    for r in rects4:
        h = r.get_height()
        ax2.annotate(f"{h:.1f}", xy=(r.get_x() + r.get_width()/2, h), xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=8, fontweight="bold", color="#059669")

    fig.suptitle("Cross-Platform Task Throughput Breakdown: Host PC vs Mobile Edge (Qwen2.5-1.5B)", fontsize=13, fontweight="bold", y=0.98)
    plt.tight_layout()
    plt.savefig(output_png, dpi=300)
    plt.close()


def plot_energy_efficiency_pareto(output_png: str):
    """Chart 2: The Energy Inversion & Tokens-per-Watt Pareto Frontier."""
    set_plot_style()
    fig, ax = plt.subplots(figsize=(10, 6.5))

    # Iso-efficiency contour curves: TPS = Efficiency * Power
    power_range = np.linspace(1, 60, 200)
    for eff, color, style in [(0.5, "#9ca3af", ":"), (1.0, "#38bdf8", "--"), (2.0, "#a855f7", "-."), (3.0, "#10b981", "-")]:
        ax.plot(power_range, eff * power_range, linestyle=style, color=color, alpha=0.6, label=f"Iso-Efficiency: {eff:.1f} Tokens/Watt")

    # Data points
    points = [
        {"name": "realme 9 Pro+ (Dimensity 920)\nqwen2.5:1.5b @ 4W", "power": 4.0, "tps": 10.64, "eff": 2.66, "color": "#10b981", "shape": "*", "size": 280},
        {"name": "Host PC (GTX 1650 4GB)\nqwen2.5:0.5b @ 50W", "power": 50.0, "tps": 142.58, "eff": 2.85, "color": "#06b6d4", "shape": "^", "size": 200},
        {"name": "Host PC (GTX 1650 4GB)\nqwen2.5:1.5b @ 50W", "power": 50.0, "tps": 46.41, "eff": 0.93, "color": "#0284c7", "shape": "s", "size": 180},
        {"name": "Host PC (GTX 1650 4GB)\nllama3.2:1b @ 50W", "power": 50.0, "tps": 43.91, "eff": 0.88, "color": "#0284c7", "shape": "s", "size": 180},
        {"name": "Host PC (GTX 1650 4GB)\nqwen2.5-coder:3b @ 50W", "power": 50.0, "tps": 21.40, "eff": 0.43, "color": "#f59e0b", "shape": "o", "size": 180},
        {"name": "Host PC (GTX 1650 4GB)\nqwen2.5:3b @ 50W", "power": 50.0, "tps": 19.44, "eff": 0.39, "color": "#ef4444", "shape": "o", "size": 180},
    ]

    for p in points:
        ax.scatter(p["power"], p["tps"], s=p["size"], color=p["color"], marker=p["shape"], edgecolors="#000", linewidths=1.5, zorder=5)
        # Position annotations smartly
        dx, dy = (1.5, 0.5) if p["power"] < 10 else (-2.5, 1.2)
        ha = "left" if p["power"] < 10 else "right"
        ax.annotate(
            f"{p['name']}\n[{p['eff']:.2f} T/W | {p['tps']:.1f} TPS]",
            xy=(p["power"], p["tps"]),
            xytext=(p["power"] + dx, p["tps"] + dy),
            fontsize=8.5,
            fontweight="bold",
            ha=ha,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#ffffff", edgecolor=p["color"], alpha=0.9),
            arrowprops=dict(arrowstyle="->", color="#374151", lw=1.2),
        )

    ax.set_xlabel("Active System Power Dissipation (Watts)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Autoregressive Decode Throughput (Tokens/s)", fontsize=11, fontweight="bold")
    ax.set_title("The Energy Inversion: Tokens-per-Watt Pareto Frontier (PC vs Edge Mobile)", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlim(0, 58)
    ax.set_ylim(0, 165)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="upper left", framealpha=0.9, fontsize=9)

    plt.tight_layout()
    plt.savefig(output_png, dpi=300)
    plt.close()


def plot_ttft_latency(output_png: str):
    """Chart 3: Time-to-First-Token (TTFT) and Latency Comparison Across Models."""
    set_plot_style()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

    # Panel A: Median TTFT on GTX 1650 PC
    models = ["qwen2.5:0.5b\n(Q4_K_M)", "llama3.2:1b\n(Q8_0)", "qwen2.5:1.5b\n(Q4_K_M)", "qwen2.5-coder:3b\n(Q4_K_M)", "qwen2.5:3b\n(Q4_K_M)"]
    ttfts = [18.8, 25.0, 33.9, 41.1, 46.8]
    colors = ["#06b6d4", "#10b981", "#0284c7", "#f59e0b", "#6366f1"]

    bars = ax1.bar(models, ttfts, color=colors, width=0.55, edgecolor="#1f2937", linewidth=1.2)
    ax1.set_ylabel("Client-Side Time-to-First-Token (ms)", fontsize=11, fontweight="bold")
    ax1.set_title("Workstation PC (GTX 1650): TTFT by Model Scale", fontsize=11, fontweight="bold", pad=10)
    ax1.grid(True, linestyle="--", alpha=0.4, axis="y")
    ax1.set_ylim(0, 60)

    for b in bars:
        h = b.get_height()
        ax1.annotate(f"{h:.1f} ms", xy=(b.get_x() + b.get_width()/2, h), xytext=(0, 4), textcoords="offset points", ha="center", va="bottom", fontsize=9, fontweight="bold")

    # Panel B: End-to-End Latency vs Decode Generation Length (Comparison)
    tokens_range = np.array([16, 32, 64, 128, 256])
    # PC @ ~46.4 TPS, TTFT=33.9ms
    pc_e2e = (33.9 + (tokens_range / 46.4) * 1000.0) / 1000.0
    # Phone @ ~10.6 TPS, TTFT=1400ms
    phone_e2e = (1400.0 + (tokens_range / 10.6) * 1000.0) / 1000.0

    ax2.plot(tokens_range, pc_e2e, marker="o", linewidth=2.5, color="#0284c7", label="Host PC (GTX 1650 GPU — 46.4 TPS)")
    ax2.plot(tokens_range, phone_e2e, marker="s", linewidth=2.5, color="#10b981", label="realme 9 Pro+ (Dimensity 920 CPU — 10.6 TPS)")
    ax2.set_xlabel("Generated Response Length (Tokens)", fontsize=11, fontweight="bold")
    ax2.set_ylabel("Total End-to-End Latency (Seconds)", fontsize=11, fontweight="bold")
    ax2.set_title("End-to-End Turnaround Time vs Output Token Count", fontsize=11, fontweight="bold", pad=10)
    ax2.grid(True, linestyle="--", alpha=0.4)
    ax2.legend(loc="upper left", framealpha=0.9, fontsize=9.5)

    for i, tok in enumerate([32, 128, 256]):
        idx = list(tokens_range).index(tok)
        ax2.annotate(f"{pc_e2e[idx]:.2f}s", xy=(tok, pc_e2e[idx]), xytext=(0, -15), textcoords="offset points", ha="center", fontsize=8, color="#0284c7", fontweight="bold")
        ax2.annotate(f"{phone_e2e[idx]:.1f}s", xy=(tok, phone_e2e[idx]), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8, color="#10b981", fontweight="bold")

    fig.suptitle("Inference Latency Profile & Turnaround Bounds Across Model Architectures", fontsize=13, fontweight="bold", y=0.98)
    plt.tight_layout()
    plt.savefig(output_png, dpi=300)
    plt.close()


def plot_cognitive_tradeoff(output_png: str):
    """Chart 4: Multi-Dimensional Cognitive Reasoning vs Speed vs VRAM Footprint."""
    set_plot_style()
    fig, ax = plt.subplots(figsize=(10, 6.5))

    models = [
        {"name": "qwen2.5:0.5b", "hotpot": 100.0, "alfworld": 0.0, "tps": 142.6, "vram": 764, "color": "#06b6d4", "label": "qwen2.5:0.5b\n[Micro-Edge 0.5B]"},
        {"name": "qwen2.5-coder:3b", "hotpot": 60.0, "alfworld": 60.0, "tps": 21.4, "vram": 2227, "color": "#f59e0b", "label": "qwen2.5-coder:3b\n[Code-Specialized 3.1B]"},
        {"name": "qwen2.5:3b", "hotpot": 100.0, "alfworld": 20.0, "tps": 19.4, "vram": 2228, "color": "#6366f1", "label": "qwen2.5:3b\n[General Instruct 3.1B]"},
        {"name": "qwen2.5:1.5b", "hotpot": 100.0, "alfworld": 0.0, "tps": 46.4, "vram": 1293, "color": "#0284c7", "label": "qwen2.5:1.5b\n[Compact General 1.5B]"},
        {"name": "llama3.2:1b", "hotpot": 40.0, "alfworld": 0.0, "tps": 43.9, "vram": 1622, "color": "#10b981", "label": "llama3.2:1b\n[Compact General 1.2B Q8]"},
    ]

    for m in models:
        # Size proportional to TPS throughput
        size = m["tps"] * 25
        scatter = ax.scatter(m["hotpot"], m["alfworld"], s=size, color=m["color"], alpha=0.75, edgecolors="#000", linewidths=1.5, zorder=4)

        # Smart text placement
        dy = 4.0 if m["alfworld"] > 10 else 3.5
        dx = -12.0 if m["hotpot"] > 80 else 3.0
        ax.annotate(
            f"{m['label']}\nDecode: {m['tps']} TPS | VRAM: {m['vram']} MB",
            xy=(m["hotpot"], m["alfworld"]),
            xytext=(m["hotpot"] + dx, m["alfworld"] + dy),
            fontsize=8.5,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#ffffff", edgecolor=m["color"], alpha=0.9),
            arrowprops=dict(arrowstyle="->", color="#374151", lw=1.0),
        )

    ax.set_xlabel("HotpotQA Multi-Hop Factual Accuracy (%)", fontsize=11, fontweight="bold")
    ax.set_ylabel("ALFWorld Sequential Embodied Planning Success (%)", fontsize=11, fontweight="bold")
    ax.set_title("Cognitive Capability Tradeoff: Embodied Planning vs Factual Accuracy\n(Bubble size proportional to generation speed TPS)", fontsize=12, fontweight="bold", pad=12)
    ax.set_xlim(25, 115)
    ax.set_ylim(-8, 75)
    ax.grid(True, linestyle="--", alpha=0.4)

    # Shaded quadrants
    ax.axvspan(70, 115, ymin=0.5, ymax=1.0, color="#dcfce7", alpha=0.3, zorder=1)
    ax.text(108, 68, "Pareto Ideal\n(High Fact + High Plan)", fontsize=8, color="#15803d", fontweight="bold", ha="right")

    plt.tight_layout()
    plt.savefig(output_png, dpi=300)
    plt.close()


def generate_all_extra_charts(results_dir: str = "results", web_dir: str = "web"):
    """Generate all 4 extra charts and copy to web and dist."""
    charts_dir = os.path.join(results_dir, "charts")
    web_charts_dir = os.path.join(web_dir, "charts")
    os.makedirs(charts_dir, exist_ok=True)
    os.makedirs(web_charts_dir, exist_ok=True)

    c1 = os.path.join(charts_dir, "hardware_duel_task_breakdown.png")
    c2 = os.path.join(charts_dir, "energy_efficiency_pareto.png")
    c3 = os.path.join(charts_dir, "ttft_latency_comparison.png")
    c4 = os.path.join(charts_dir, "cognitive_reasoning_tradeoff.png")

    print(f"Generating Chart 1: {c1}...")
    plot_hardware_duel_tasks(c1)

    print(f"Generating Chart 2: {c2}...")
    plot_energy_efficiency_pareto(c2)

    print(f"Generating Chart 3: {c3}...")
    plot_ttft_latency(c3)

    print(f"Generating Chart 4: {c4}...")
    plot_cognitive_tradeoff(c4)

    # Copy to web/charts/
    for c in [c1, c2, c3, c4]:
        shutil.copy(c, os.path.join(web_charts_dir, os.path.basename(c)))
        print(f"✔ Copied to {os.path.join(web_charts_dir, os.path.basename(c))}")

    print("\nAll 4 extra research charts generated successfully!")


if __name__ == "__main__":
    generate_all_extra_charts()
