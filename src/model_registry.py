"""Model Registry and Auto-Discovery Engine for Pocket AI Lab.

Automatically discovers new models in Ollama, inspects parameter size,
estimates VRAM compatibility against hardware budgets, and tracks benchmark coverage.
"""
from __future__ import annotations

import argparse
import glob
import os
from typing import Any, Dict, List, Optional

import requests

from src.benchmark import validate_loopback_url


# Hardware VRAM / RAM budgets (MB)
HOST_GPU_VRAM_BUDGET_MB = 4096.0  # NVIDIA GTX 1650 (4 GB)
ANDROID_RAM_BUDGET_MB = 8192.0    # realme 9 Pro+ (8 GB)


def discover_available_models(api_base: str = "http://127.0.0.1:11434") -> List[Dict[str, Any]]:
    """Scan Ollama daemon for all locally pulled models."""
    validate_loopback_url(api_base)
    try:
        resp = requests.get(f"{api_base}/api/tags", timeout=5.0)
        resp.raise_for_status()
        return resp.json().get("models", [])
    except Exception as exc:
        print(f"[Registry] Error querying Ollama tags: {exc}")
        return []


def get_benchmarked_models(results_dir: str = "results") -> set[str]:
    """Scan existing result files to identify models already evaluated."""
    benchmarked = set()
    csv_files = glob.glob(os.path.join(results_dir, "*.csv"))
    for f in csv_files:
        basename = os.path.basename(f)
        # Extract model names from exp_* or reasoning_* filenames
        for tag in ["qwen2.5_1_5b", "qwen2.5_3b", "qwen2.5-coder_3b", "qwen2_5_1_5b", "qwen2_5_3b", "qwen2_5-coder_3b"]:
            if tag in basename:
                # normalize
                normalized = tag.replace("_", ".").replace("-coder.", "-coder:")
                if normalized.endswith(".1.5b"):
                    normalized = "qwen2.5:1.5b"
                elif normalized.endswith(".3b") and "coder" not in normalized:
                    normalized = "qwen2.5:3b"
                benchmarked.add(normalized)
    return benchmarked


def profile_model_fit(model_data: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate whether an incoming model safely fits inside GTX 1650 4GB VRAM."""
    name = model_data.get("name", "unknown")
    size_bytes = model_data.get("size", 0)
    size_mb = round(size_bytes / (1024 * 1024), 2)
    details = model_data.get("details", {})
    param_size = details.get("parameter_size", "unknown")
    quant = details.get("quantization_level", "unknown")
    family = details.get("family", "unknown")

    # Estimated VRAM = weights + ~400MB KV cache buffer (num_ctx=2048)
    estimated_vram_mb = size_mb + 400.0

    fits_gtx_1650 = estimated_vram_mb <= HOST_GPU_VRAM_BUDGET_MB
    fits_android_ram = size_mb <= (ANDROID_RAM_BUDGET_MB * 0.5)  # Leave 50% for OS & app

    return {
        "name": name,
        "parameter_size": param_size,
        "quantization": quant,
        "family": family,
        "size_mb": size_mb,
        "estimated_vram_mb": estimated_vram_mb,
        "fits_gtx_1650_gpu": fits_gtx_1650,
        "fits_android_ram": fits_android_ram,
    }


def list_registry(api_base: str = "http://127.0.0.1:11434") -> List[Dict[str, Any]]:
    """Print complete status of local model registry, hardware budgets, and benchmark coverage."""
    raw_models = discover_available_models(api_base)
    benchmarked = get_benchmarked_models()

    registry = []
    print("\n" + "=" * 90)
    print(" POCKET AI LAB — MODEL REGISTRY & AUTO-INGESTION PIPELINE")
    print("=" * 90)
    print(f"Hardware Budget: GTX 1650 (4,096 MB VRAM) | realme 9 Pro+ (8,192 MB RAM)")
    print("-" * 90)
    header = f"{'Model Tag':<22} | {'Params':>7} | {'Quant':>8} | {'Weight MB':>10} | {'Est VRAM':>10} | {'GTX 1650':>9} | {'Status':>10}"
    print(header)
    print("-" * 90)

    for m in raw_models:
        prof = profile_model_fit(m)
        name = prof["name"]
        status = "Evaluated" if any(b in name for b in benchmarked) else "Ready"
        gpu_fit = "✔ FITS" if prof["fits_gtx_1650_gpu"] else "✘ SPILL"

        print(
            f"{name:<22} | {prof['parameter_size']:>7} | {prof['quantization']:>8} | "
            f"{prof['size_mb']:>9.1f}M | {prof['estimated_vram_mb']:>9.1f}M | {gpu_fit:>9} | {status:>10}"
        )
        registry.append({**prof, "status": status})

    print("=" * 90 + "\n")
    return registry


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    list_registry(args.api_base)
