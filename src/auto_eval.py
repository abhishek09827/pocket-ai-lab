"""Continuous Model Ingestion and Auto-Evaluation Pipeline.

Single-command ingestion for any new model:
1. Pulls model if not present.
2. Profiles architecture and checks VRAM safety.
3. Executes baseline benchmark (Milestone 1 suite).
4. Executes reasoning & decision benchmark (HotpotQA & ALFWorld).
5. Automatically re-renders comparison charts.
"""
from __future__ import annotations

import argparse
import subprocess
import sys

from src.benchmark import query_model_identity, run_benchmark, validate_loopback_url
from src.model_registry import profile_model_fit, discover_available_models
from src.run_reasoning_benchmark import run_reasoning_benchmark
from src.visualize_reasoning import generate_charts


def auto_evaluate_model(
    model: str,
    api_base: str = "http://127.0.0.1:11434",
    artifact_dir: str = "/home/abhishek/.gemini/antigravity-cli/brain/ed69ac16-08e2-439f-89b9-b4e2c4e43de4",
    repeats: int = 2,
    warmups: int = 1,
) -> None:
    """Execute complete automated ingestion workflow for a new model."""
    validate_loopback_url(api_base)

    print("\n" + "=" * 80)
    print(f" POCKET AI LAB — INGESTING NEW MODEL: {model}")
    print("=" * 80)

    # Step 1: Check if pulled, else pull
    available = discover_available_models(api_base)
    is_present = any(m.get("name") == model or m.get("model") == model for m in available)

    if not is_present:
        print(f"[AutoEval] Model '{model}' not found locally. Initiating pull via Ollama...", flush=True)
        ret = subprocess.run(["ollama", "pull", model], check=False)
        if ret.returncode != 0:
            print(f"[AutoEval] Failed to pull model '{model}'. Aborting.", file=sys.stderr)
            return
        available = discover_available_models(api_base)

    # Step 2: Architecture & Hardware Fit Profiling
    target_data = next((m for m in available if m.get("name") == model or m.get("model") == model), {})
    prof = profile_model_fit(target_data)

    print("\n--- Model Hardware Profile ---")
    print(f"  Parameter Count   : {prof['parameter_size']}")
    print(f"  Quantization Level: {prof['quantization']}")
    print(f"  Model Weight Size : {prof['size_mb']} MB")
    print(f"  Est. VRAM Footprint: {prof['estimated_vram_mb']} MB")
    if prof["fits_gtx_1650_gpu"]:
        print(f"  GTX 1650 VRAM (4GB): ✔ SAFE TO EVALUATE (Fits in VRAM)")
    else:
        print(f"  GTX 1650 VRAM (4GB): ⚠ WARNING: Model exceeds 4GB VRAM! Will spill to system RAM.")
    print("------------------------------\n", flush=True)

    # Step 3: Run Baseline Suite
    print(f"[AutoEval] Step 1/3: Running Baseline Benchmark Suite on '{model}'...", flush=True)
    run_benchmark(
        model=model,
        api_base=api_base,
        warmups=warmups,
        repeats=repeats,
    )

    # Step 4: Run Reasoning & Decision-Making Suite
    print(f"\n[AutoEval] Step 2/3: Running Reasoning & ALFWorld Suite on '{model}'...", flush=True)
    run_reasoning_benchmark(
        model=model,
        api_base=api_base,
        warmups=warmups,
        repeats=repeats,
    )

    # Step 5: Regenerate Visual Comparison Charts
    print(f"\n[AutoEval] Step 3/3: Updating Visual Comparison Charts & Artifacts...", flush=True)
    generate_charts(output_dir="results/charts", artifact_dir=artifact_dir)

    print("\n" + "=" * 80)
    print(f" POCKET AI LAB — INGESTION & EVALUATION COMPLETE FOR {model}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auto-evaluate incoming models in Pocket AI Lab")
    parser.add_argument("--model", type=str, required=True, help="Ollama model tag e.g. llama3.2:1b")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--api-base", default="http://127.0.0.1:11434")
    args = parser.parse_args()

    auto_evaluate_model(
        model=args.model,
        api_base=args.api_base,
        repeats=args.repeats,
        warmups=args.warmups,
    )
