"""Generate high-resolution visual preview image for Pocket AI Lab.

Produces a 1200x675 (16:9) publication-quality dashboard showcase graphic
matching the web dashboard's exact dark UI theme (#0a0f1d), typography,
and empirical testbed telemetry without missing glyph warnings.
"""
from __future__ import annotations

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np


def generate_dashboard_preview(output_paths: list[str]) -> None:
    # 1200x675 px at 100 dpi -> 12 x 6.75 inches
    fig = plt.figure(figsize=(12, 6.75), dpi=100, facecolor="#0a0f1d")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("#0a0f1d")
    ax.set_xlim(0, 1200)
    ax.set_ylim(0, 675)
    ax.axis("off")

    # --- 1. Top Header Bar ---
    # Background strip
    header_box = patches.Rectangle((0, 605), 1200, 70, facecolor="#111827", edgecolor="#374151", linewidth=1)
    ax.add_patch(header_box)

    # Title & Subtitle
    ax.text(30, 648, "POCKET AI LAB", fontsize=18, fontweight="bold", color="#38bdf8", va="center")
    ax.text(215, 648, "Empirical Edge AI Benchmarking & Dual-Hardware SLM Research", fontsize=11, color="#9ca3af", va="center")

    # Hardware badges in header
    # PC Badge
    pc_badge = patches.FancyBboxPatch((770, 620), 200, 38, boxstyle="round,pad=3,rounding_size=6",
                                     facecolor="#1e293b", edgecolor="#38bdf8", linewidth=1.2)
    ax.add_patch(pc_badge)
    ax.text(785, 642, "● Workstation (GTX 1650)", fontsize=8.5, fontweight="bold", color="#38bdf8", va="center")
    ax.text(785, 629, "CUDA 12.0 • 4GB VRAM • Online", fontsize=7.5, color="#94a3b8", va="center")

    # Phone Badge
    phone_badge = patches.FancyBboxPatch((980, 620), 200, 38, boxstyle="round,pad=3,rounding_size=6",
                                        facecolor="#1e293b", edgecolor="#34d399", linewidth=1.2)
    ax.add_patch(phone_badge)
    ax.text(995, 642, "● realme 9 Pro+ (Dimensity 920)", fontsize=8.5, fontweight="bold", color="#34d399", va="center")
    ax.text(995, 629, "ARM64 NEON • 8GB RAM • Online", fontsize=7.5, color="#94a3b8", va="center")

    # Navigation tab pills strip
    nav_box = patches.Rectangle((0, 565), 1200, 38, facecolor="#0e1626", edgecolor="#1f2937", linewidth=0.8)
    ax.add_patch(nav_box)
    tabs = [
        ("Hardware Duel", True),
        ("Leaderboard (8 Models)", False),
        ("Deployment Recommender", False),
        ("realme 9 Pro+ Profile", False),
        ("Application Evals", False),
        ("Per-Task Deep Dive", False),
        ("Visual Gallery (10)", False),
        ("Raw Telemetry", False),
    ]
    cur_x = 30
    for title, is_active in tabs:
        w = len(title) * 7.2 + 20
        bg_col = "#2563eb" if is_active else "#1f293d"
        fg_col = "#ffffff" if is_active else "#9ca3af"
        edge_col = "#3b82f6" if is_active else "#374151"
        tab_patch = patches.FancyBboxPatch((cur_x, 571), w, 24, boxstyle="round,pad=2,rounding_size=5",
                                          facecolor=bg_col, edgecolor=edge_col, linewidth=0.8)
        ax.add_patch(tab_patch)
        ax.text(cur_x + w/2, 583, title, fontsize=7.8, fontweight="bold" if is_active else "normal",
                color=fg_col, ha="center", va="center")
        cur_x += w + 10

    # --- 2. Top 4 Metric KPI Cards ---
    card_y = 475
    card_h = 76
    cards_data = [
        ("ENERGY INVERSION", "2.89x More Efficient", "realme 9 Pro+: 2.66 Tok/W\nGTX 1650: 0.92 Tok/W", "#34d399"),
        ("PREFILL vs DECODE", "22.0x -> 4.4x Asymmetry", "Prefill: 354 vs 16.1 TPS (Compute)\nDecode: 46.4 vs 10.6 TPS (Bandwidth)", "#38bdf8"),
        ("MOBILE THROTTLING", "-29.43% Sustained Drop", "Pass 1: 6.8 TPS | Peak: 7.6 TPS\nPass 9: 5.37 TPS (Thermal Saturation)", "#fb923c"),
        ("CODER CAUSAL ANCHOR", "60.0% vs 0% ALFWorld", "Coder 3B: 60% Success, 0% Invalid\nGeneral <3B: 0% Success (40% Invalid)", "#c084fc")
    ]
    for i, (title, highlight, subtext, accent) in enumerate(cards_data):
        cx = 30 + i * 288
        cw = 276
        c_patch = patches.FancyBboxPatch((cx, card_y), cw, card_h, boxstyle="round,pad=3,rounding_size=8",
                                        facecolor="#1f293d", edgecolor=accent, linewidth=1.2)
        ax.add_patch(c_patch)
        ax.text(cx + 14, card_y + 60, title, fontsize=8, fontweight="bold", color=accent)
        ax.text(cx + 14, card_y + 42, highlight, fontsize=12, fontweight="bold", color="#f9fafb")
        ax.text(cx + 14, card_y + 24, subtext.split("\n")[0], fontsize=7.5, color="#9ca3af")
        ax.text(cx + 14, card_y + 11, subtext.split("\n")[1], fontsize=7.5, color="#9ca3af")

    # --- 3. Left Container: Empirical 8-Model Leaderboard Table ---
    tbl_x = 30
    tbl_y = 65
    tbl_w = 640
    tbl_h = 395
    tbl_box = patches.FancyBboxPatch((tbl_x, tbl_y), tbl_w, tbl_h, boxstyle="round,pad=3,rounding_size=8",
                                    facecolor="#111827", edgecolor="#374151", linewidth=1)
    ax.add_patch(tbl_box)

    # Leaderboard Header
    ax.text(tbl_x + 18, tbl_y + tbl_h - 22, "EMPIRICAL LEADERBOARD — 8 Physical Models Evaluated",
            fontsize=10.5, fontweight="bold", color="#f9fafb", va="center")
    ax.text(tbl_x + tbl_w - 18, tbl_y + tbl_h - 22, "GTX 1650 (CUDA) & realme 9 Pro+ (ARM64)",
            fontsize=8, color="#9ca3af", ha="right", va="center")

    # Table Column Headers
    header_y = tbl_y + tbl_h - 48
    head_bg = patches.Rectangle((tbl_x + 10, header_y - 6), tbl_w - 20, 20, facecolor="#1e293b", edgecolor="none")
    ax.add_patch(head_bg)
    ax.text(tbl_x + 16, header_y + 4, "MODEL TAG", fontsize=7.5, fontweight="bold", color="#94a3b8")
    ax.text(tbl_x + 195, header_y + 4, "SCALE / QUANT", fontsize=7.5, fontweight="bold", color="#94a3b8")
    ax.text(tbl_x + 295, header_y + 4, "DECODE TPS", fontsize=7.5, fontweight="bold", color="#94a3b8")
    ax.text(tbl_x + 380, header_y + 4, "PEAK VRAM", fontsize=7.5, fontweight="bold", color="#94a3b8")
    ax.text(tbl_x + 465, header_y + 4, "HOTPOTQA", fontsize=7.5, fontweight="bold", color="#94a3b8")
    ax.text(tbl_x + 550, header_y + 4, "ALFWORLD", fontsize=7.5, fontweight="bold", color="#94a3b8")

    # Table Rows (Empirical Measured Data)
    models_table = [
        ("qwen2.5-coder:3b", "3.1B • Q4_K_M", "31.42 TPS", "2,227 MB (54%)", "100.0%", "60.0% (Anchor)", "#34d399"),
        ("qwen2.5:3b", "3.1B • Q4_K_M", "31.29 TPS", "2,228 MB (54%)", "100.0%", "0.0% (Failed)", "#38bdf8"),
        ("qwen2.5-coder:1.5b", "1.5B • Q4_K_M", "47.78 TPS", "1,293 MB (32%)", "93.3%", "46.7% (Solid)", "#34d399"),
        ("qwen2.5:1.5b", "1.5B • Q4_K_M", "46.41 TPS", "1,293 MB (32%)", "93.3%", "0.0% (Failed)", "#38bdf8"),
        ("deepseek-r1:1.5b", "1.5B • Q4_K_M", "37.44 TPS", "1,872 MB (46%)", "66.7%", "0.0% (CoT Think)", "#c084fc"),
        ("qwen2.5:0.5b-q8_0", "0.5B • Q8_0", "108.74 TPS", "892 MB (22%)", "73.3%", "0.0% (Failed)", "#fb923c"),
        ("qwen2.5:0.5b", "0.5B • Q4_K_M", "142.58 TPS", "764 MB (19%)", "73.3%", "0.0% (Failed)", "#fb923c"),
        ("llama3.2:1b", "1.2B • Q8_0", "59.39 TPS", "1,622 MB (40%)", "80.0%", "0.0% (Failed)", "#93c5fd"),
    ]

    row_y = header_y - 25
    for tag, scale, tps, vram, hotpot, alf, col in models_table:
        row_bg = patches.Rectangle((tbl_x + 10, row_y - 5), tbl_w - 20, 22, facecolor="#151d30", edgecolor="none")
        ax.add_patch(row_bg)
        ax.text(tbl_x + 16, row_y + 4, tag, fontsize=7.8, fontweight="bold", color="#f9fafb")
        ax.text(tbl_x + 195, row_y + 4, scale, fontsize=7.5, color="#9ca3af")
        ax.text(tbl_x + 295, row_y + 4, tps, fontsize=7.8, fontweight="bold", color="#38bdf8")
        ax.text(tbl_x + 380, row_y + 4, vram, fontsize=7.5, color="#9ca3af")
        ax.text(tbl_x + 465, row_y + 4, hotpot, fontsize=7.8, fontweight="bold", color="#34d399")
        ax.text(tbl_x + 550, row_y + 4, alf, fontsize=7.5, fontweight="bold" if "Anchor" in alf else "normal", color=col)
        row_y -= 26

    # Retrieval note under table
    ax.text(tbl_x + 16, row_y + 4, "Dense Retrieval: nomic-embed-text (137M) -> 100% Recall@1, 1.0 MRR, 323 MB VRAM",
            fontsize=7.5, fontstyle="italic", color="#38bdf8")

    # --- 4. Right Container: Telemetry Plots Showcase ---
    plot_x = 690
    plot_y = 65
    plot_w = 480
    plot_h = 395
    plot_box = patches.FancyBboxPatch((plot_x, plot_y), plot_w, plot_h, boxstyle="round,pad=3,rounding_size=8",
                                     facecolor="#111827", edgecolor="#374151", linewidth=1)
    ax.add_patch(plot_box)

    ax.text(plot_x + 18, plot_y + plot_h - 22, "REAL KERNEL SAMPLING & THERMAL TELEMETRY",
            fontsize=10.5, fontweight="bold", color="#f9fafb", va="center")
    ax.text(plot_x + plot_w - 18, plot_y + plot_h - 22, "Zero Interpolation",
            fontsize=8, color="#34d399", ha="right", va="center")

    # Inset Plot 1: Prefill vs Decode Comparison
    ax1 = fig.add_axes([710 / 1200, 275 / 675, 440 / 1200, 140 / 675])
    ax1.set_facecolor("#0f172a")
    categories = ['Prompt Prefill (TPS)', 'Token Decode (TPS)']
    pc_speeds = [354.2, 46.4]
    phone_speeds = [16.1, 10.6]
    y_pos = np.arange(len(categories))
    bar_height = 0.35

    ax1.barh(y_pos + bar_height/2, pc_speeds, bar_height, label='PC: GTX 1650 (CUDA)', color='#38bdf8', edgecolor='#0284c7')
    ax1.barh(y_pos - bar_height/2, phone_speeds, bar_height, label='realme 9 Pro+ (Dimensity 920)', color='#34d399', edgecolor='#059669')

    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(categories, fontsize=8, color="#e2e8f0", fontweight="bold")
    ax1.set_xlabel('Tokens Per Second (TPS)', fontsize=7.5, color="#94a3b8")
    ax1.set_xlim(0, 420)
    ax1.tick_params(colors="#94a3b8", labelsize=7)
    ax1.legend(loc='lower right', fontsize=7, facecolor="#1e293b", edgecolor="#334155", labelcolor="#e2e8f0")
    ax1.grid(axis='x', linestyle='--', alpha=0.3, color="#64748b")
    for spine in ax1.spines.values():
        spine.set_color("#334155")

    # Annotate bar values
    ax1.text(358, 0 + bar_height/2, "354.2", va='center', fontsize=7.5, color='#38bdf8', fontweight='bold')
    ax1.text(20, 0 - bar_height/2, "16.1", va='center', fontsize=7.5, color='#34d399', fontweight='bold')
    ax1.text(50, 1 + bar_height/2, "46.4", va='center', fontsize=7.5, color='#38bdf8', fontweight='bold')
    ax1.text(14, 1 - bar_height/2, "10.6", va='center', fontsize=7.5, color='#34d399', fontweight='bold')

    # Inset Plot 2: Mobile Sustained Thermal Degradation Curve
    ax2 = fig.add_axes([710 / 1200, 95 / 675, 440 / 1200, 140 / 675])
    ax2.set_facecolor("#0f172a")
    passes = list(range(1, 11))
    tps_curve = [6.82, 7.15, 7.42, 7.61, 7.28, 6.94, 6.55, 6.12, 5.37, 5.62]

    ax2.plot(passes, tps_curve, marker='o', linewidth=2, color='#fb923c', label='realme 9 Pro+ Throughput', markersize=4)
    ax2.axhline(y=6.82, color='#94a3b8', linestyle=':', label='Cold Start (6.82 TPS)', alpha=0.7)
    ax2.axhline(y=5.37, color='#ef4444', linestyle='--', label='Thermal Floor (5.37 TPS, -29.4%)', alpha=0.8)

    ax2.set_title("10-Pass Sustained Mobile Thermal Stress (realme 9 Pro+)", fontsize=8, color="#e2e8f0", fontweight="bold", pad=4)
    ax2.set_xlabel('Benchmark Pass (Continuous Workload)', fontsize=7.5, color="#94a3b8")
    ax2.set_ylabel('Decode TPS', fontsize=7.5, color="#94a3b8")
    ax2.set_xticks(passes)
    ax2.set_ylim(4.5, 8.5)
    ax2.tick_params(colors="#94a3b8", labelsize=7)
    ax2.legend(loc='upper right', fontsize=6.8, facecolor="#1e293b", edgecolor="#334155", labelcolor="#e2e8f0")
    ax2.grid(True, linestyle='--', alpha=0.25, color="#64748b")
    for spine in ax2.spines.values():
        spine.set_color("#334155")

    # --- 5. Bottom Callout / Footer Bar ---
    footer_box = patches.Rectangle((0, 0), 1200, 48, facecolor="#0e1626", edgecolor="#1e293b", linewidth=1)
    ax.add_patch(footer_box)

    ax.text(30, 24, "LIVE DASHBOARD: https://abhishek09827.github.io/pocket-ai-lab/",
            fontsize=9.5, fontweight="bold", color="#38bdf8", va="center")
    ax.text(1170, 24, "Zero Fabrication  •  Linux PSI & GPU Telemetry  •  68/68 Tests Green  •  MIT Open Research",
            fontsize=8.5, color="#9ca3af", ha="right", va="center")

    # Ensure output directories exist
    for p in output_paths:
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        fig.savefig(p, dpi=100, facecolor="#0a0f1d", edgecolor="none")
        print(f"✔ Generated dashboard preview: {p}")

    plt.close(fig)


if __name__ == "__main__":
    targets = [
        "docs/assets/dashboard_preview.png",
        "results/charts/dashboard_preview.png",
        "web/charts/dashboard_preview.png",
    ]
    generate_dashboard_preview(targets)
