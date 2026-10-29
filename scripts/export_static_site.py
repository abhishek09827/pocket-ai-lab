"""Pocket AI Lab — Static Site Builder for Public Research Hosting (Phase 5).

Exports the reproducible benchmark dataset, visual analysis gallery, and
multi-dimensional leaderboard to a self-contained, zero-dependency static bundle
in `dist/` ready to be hosted on GitHub Pages or Cloudflare Pages.
"""
from __future__ import annotations

import csv
import glob
import json
import os
import shutil
from typing import Any, Dict, List


def export_static_site(project_root: str = ".") -> str:
    """Build zero-dependency static distribution in dist/."""
    dist_dir = os.path.join(project_root, "dist")
    data_dir = os.path.join(dist_dir, "data")
    charts_dir = os.path.join(dist_dir, "charts")

    os.makedirs(dist_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(charts_dir, exist_ok=True)

    results_dir = os.path.join(project_root, "results")

    # 1. Compile Reasoning Leaderboard
    all_reasoning = []
    for f in glob.glob(os.path.join(results_dir, "reasoning_*.csv")):
        with open(f, "r", encoding="utf-8") as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                all_reasoning.append(row)

    leaderboard = []
    if all_reasoning:
        measured = [r for r in all_reasoning if r.get("run_type") == "measured"]
        models = sorted(list(set(r["model_tag"] for r in measured)))

        for m in models:
            m_rec = [r for r in measured if r["model_tag"] == m]
            alf = [r for r in m_rec if r.get("benchmark_family") == "alfworld_decision"]
            hotpot = [r for r in m_rec if r.get("benchmark_family") == "hotpotqa_multihop"]

            alf_success_pct = round((sum(1 for r in alf if r["outcome"] == "SUCCESS") / (len(alf) or 1)) * 100.0, 1)
            alf_invalid_pct = round((sum(1 for r in alf if r["outcome"] == "INVALID_ACTION") / (len(alf) or 1)) * 100.0, 1)
            hotpot_acc_pct = round((sum(1 for r in hotpot if r["outcome"] == "SUCCESS") / (len(hotpot) or 1)) * 100.0, 1)
            hotpot_hall_pct = round((sum(1 for r in hotpot if r["outcome"] == "HALLUCINATION") / (len(hotpot) or 1)) * 100.0, 1)

            vrams = [float(r["peak_vram_mb"]) for r in m_rec if r.get("peak_vram_mb")]
            tps = [float(r["decode_tps"]) for r in m_rec if r.get("decode_tps")]
            ttfts = [float(r["ttft_client_ms"]) for r in m_rec if r.get("ttft_client_ms")]

            avg_vram = round(sum(vrams) / len(vrams), 1) if vrams else 0.0
            avg_tps = round(sum(tps) / len(tps), 2) if tps else 0.0
            median_ttft = round(sorted(ttfts)[len(ttfts) // 2], 2) if ttfts else 0.0

            leaderboard.append({
                "model_tag": m,
                "hotpotqa_accuracy_pct": hotpot_acc_pct,
                "hotpotqa_hallucination_pct": hotpot_hall_pct,
                "alfworld_success_pct": alf_success_pct,
                "alfworld_invalid_action_pct": alf_invalid_pct,
                "decode_tps": avg_tps,
                "median_ttft_ms": median_ttft,
                "peak_vram_mb": avg_vram,
                "gtx_1650_vram_pct": round((avg_vram / 4096.0) * 100.0, 1),
                "total_measured_trials": len(m_rec),
            })
        leaderboard.sort(key=lambda x: (x["alfworld_success_pct"], x["hotpotqa_accuracy_pct"], x["decode_tps"]), reverse=True)

    with open(os.path.join(data_dir, "leaderboard.json"), "w", encoding="utf-8") as fp:
        json.dump(leaderboard, fp, indent=2)

    # 2. Compile Thermal Stress Data
    stress_files = glob.glob(os.path.join(results_dir, "stress_*.csv"))
    stress_records = []
    if stress_files:
        latest_stress = sorted(stress_files)[-1]
        with open(latest_stress, "r", encoding="utf-8") as fp:
            stress_records = list(csv.DictReader(fp))

    with open(os.path.join(data_dir, "stress_test.json"), "w", encoding="utf-8") as fp:
        json.dump(stress_records, fp, indent=2)

    # 3. Copy visual charts
    source_charts = os.path.join(results_dir, "charts")
    if os.path.exists(source_charts):
        for img in glob.glob(os.path.join(source_charts, "*.png")):
            shutil.copy(img, os.path.join(charts_dir, os.path.basename(img)))

    # 4. Copy and update web/index.html to dist/index.html
    src_html = os.path.join(project_root, "web", "index.html")
    dst_html = os.path.join(dist_dir, "index.html")
    if os.path.exists(src_html):
        shutil.copy(src_html, dst_html)

    print(f"✔ Static bundle successfully generated at: {dist_dir}")
    print(f"  - Leaderboard models: {len(leaderboard)}")
    print(f"  - Charts bundled: {len(glob.glob(os.path.join(charts_dir, '*.png')))}")
    print(f"  - Data artifacts: {data_dir}")
    return dist_dir


if __name__ == "__main__":
    export_static_site()
