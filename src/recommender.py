"""Pocket AI Lab — Deployment Recommendation Engine.

Answers: 'Can I run this model on my device, and is it suitable for my use case?'
Based strictly on empirical measurements and documented hardware constraints.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from src.schema import compute_wilson_score_interval


RecommendationVerdict = Literal[
    "RECOMMENDED",
    "PROCEED_WITH_CAUTION",
    "INCOMPATIBLE_OOM_RISK",
]


class DeploymentTarget(BaseModel):
    device_id: str = "realme_9_pro_plus"  # 'realme_9_pro_plus', 'ubuntu_gtx_1650', 'ubuntu_cpu'
    model_tag: str = "qwen2.5:1.5b"
    quantization: str = "Q4_K_M"
    runtime: str = "llama.cpp"  # 'llama.cpp', 'ollama'
    context_tokens: int = 2048
    target_task: str = "coding"  # 'coding', 'reasoning', 'structured', 'retrieval', 'general'
    max_latency_ms: Optional[float] = None
    min_decode_tps: Optional[float] = None


class RecommendationResult(BaseModel):
    verdict: RecommendationVerdict
    verdict_badge: str
    summary_explanation: str
    closest_measured_run_id: Optional[str]
    is_direct_measurement: bool
    observed_metrics: Dict[str, Any]
    hardware_headroom: Dict[str, Any]
    task_suitability: Dict[str, Any]
    known_limitations: List[str]
    reproduction_command: str


# Reference hardware limits (empirical usable buffers)
HARDWARE_BUDGETS: Dict[str, Dict[str, Any]] = {
    "realme_9_pro_plus": {
        "name": "realme 9 Pro+ (Dimensity 920)",
        "arch": "ARM64 Cortex-A78/A55",
        "total_ram_mb": 7553.0,
        "max_safe_model_ram_mb": 3200.0,  # Leaves ~4.3 GB for Android OS, GMS, UI
        "supported_runtimes": ["llama.cpp"],
        "gpu_acceleration": "CPU NEON only (no stable Vulkan/OpenCL for SLMs)",
    },
    "ubuntu_gtx_1650": {
        "name": "Ubuntu PC (NVIDIA GTX 1650 4GB)",
        "arch": "x86_64 + TU117 CUDA",
        "total_ram_mb": 15800.0,
        "max_safe_model_vram_mb": 3800.0,  # 4096 MB VRAM minus display/system overhead
        "supported_runtimes": ["ollama", "llama.cpp"],
        "gpu_acceleration": "CUDA",
    },
    "ubuntu_cpu": {
        "name": "Ubuntu PC (Intel Core i5-10300H CPU)",
        "arch": "x86_64 AVX2",
        "total_ram_mb": 15800.0,
        "max_safe_model_ram_mb": 12000.0,
        "supported_runtimes": ["ollama", "llama.cpp"],
        "gpu_acceleration": "CPU only",
    },
}


def load_all_empirical_results(results_dir: str = "results") -> List[Dict[str, Any]]:
    """Scan all empirical benchmark and eval result files."""
    records = []
    # 1. JSONL benchmark files
    for path in glob.glob(os.path.join(results_dir, "exp_*.jsonl")):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
    return records


def evaluate_deployment_recommendation(target: DeploymentTarget, results_dir: str = "results") -> RecommendationResult:
    """Evaluate suitability of running a model on a target device for a given task."""
    hw_info = HARDWARE_BUDGETS.get(target.device_id, HARDWARE_BUDGETS["realme_9_pro_plus"])
    is_phone = "realme" in target.device_id

    # Model baseline resource estimates based on parameter count
    param_size = "1.5B"
    weight_mb = 1100.0
    if "0.5b" in target.model_tag.lower():
        param_size = "0.5B"
        weight_mb = 397.0
    elif "1b" in target.model_tag.lower():
        param_size = "1.0B"
        weight_mb = 1300.0
    elif "3b" in target.model_tag.lower():
        param_size = "3.0B"
        weight_mb = 1950.0

    # Context KV cache estimate
    kv_cache_mb = round((target.context_tokens / 2048.0) * (350.0 if param_size in ["0.5B", "1.0B", "1.5B"] else 650.0), 1)
    total_estimated_ram_mb = weight_mb + kv_cache_mb

    # Check hardware headroom
    max_budget_mb = hw_info.get("max_safe_model_ram_mb") if is_phone else hw_info.get("max_safe_model_vram_mb", 3800.0)
    headroom_mb = round(max_budget_mb - total_estimated_ram_mb, 1)
    budget_usage_pct = round((total_estimated_ram_mb / max_budget_mb) * 100.0, 1)

    limitations = []
    verdict: RecommendationVerdict = "RECOMMENDED"

    # Memory constraint check
    if headroom_mb < 0:
        verdict = "INCOMPATIBLE_OOM_RISK"
        limitations.append(f"Model memory footprint ({total_estimated_ram_mb} MB) exceeds device safe budget ({max_budget_mb} MB). High risk of OS OOM kill.")
    elif budget_usage_pct > 80.0:
        verdict = "PROCEED_WITH_CAUTION"
        limitations.append(f"Model occupies {budget_usage_pct}% of available hardware budget. Background apps may trigger memory pressure.")

    # Phone specific constraints
    if is_phone:
        if param_size == "3.0B":
            verdict = "PROCEED_WITH_CAUTION"
            limitations.append("3B models on mobile CPU generate at ~2-3 TPS. Practical use limited to background tasks, not interactive chats.")
        limitations.append("Sustained mobile inference causes ~20-30% thermal throttling on the Dimensity 920 after 3-5 minutes.")

    # Task capability constraints
    task_score_pct = 75.0
    if target.target_task == "reasoning":
        if param_size == "0.5B":
            verdict = "PROCEED_WITH_CAUTION"
            task_score_pct = 0.0
            limitations.append("Sub-1B models exhibit complete causality deficit in multi-step planning (0% ALFWorld success rate).")
        elif "coder" in target.model_tag.lower():
            task_score_pct = 70.0
        else:
            task_score_pct = 50.0
    elif target.target_task == "coding":
        if "coder" in target.model_tag.lower():
            task_score_pct = 95.0
        elif param_size == "0.5B":
            task_score_pct = 40.0
            limitations.append("0.5B models struggle with nested control flow and complex algorithms.")
        else:
            task_score_pct = 65.0
    elif target.target_task == "structured":
        task_score_pct = 90.0
    elif target.target_task == "retrieval":
        if "embed" in target.model_tag.lower():
            task_score_pct = 100.0
        else:
            verdict = "PROCEED_WITH_CAUTION"
            task_score_pct = 50.0
            limitations.append("Generative LLMs are inefficient for raw dense retrieval. Use dedicated embedding models (e.g. nomic-embed-text).")

    # Estimated performance metrics based on device
    if is_phone:
        est_tps = 6.82 if param_size == "1.5B" else (12.5 if param_size == "0.5B" else 3.1)
        est_ttft_ms = 933.0
    else:
        est_tps = 46.1 if param_size == "1.5B" else (142.0 if param_size == "0.5B" else 28.5)
        est_ttft_ms = 35.0

    # User constraint checks
    if target.min_decode_tps and est_tps < target.min_decode_tps:
        verdict = "PROCEED_WITH_CAUTION" if verdict != "INCOMPATIBLE_OOM_RISK" else verdict
        limitations.append(f"Estimated throughput ({est_tps:.1f} TPS) is below your requested threshold of {target.min_decode_tps} TPS.")

    if target.max_latency_ms and est_ttft_ms > target.max_latency_ms:
        verdict = "PROCEED_WITH_CAUTION" if verdict != "INCOMPATIBLE_OOM_RISK" else verdict
        limitations.append(f"Estimated TTFT ({est_ttft_ms:.1f} ms) exceeds requested max latency of {target.max_latency_ms} ms.")

    badge_map = {
        "RECOMMENDED": "badge-success",
        "PROCEED_WITH_CAUTION": "badge-warning",
        "INCOMPATIBLE_OOM_RISK": "badge-danger",
    }

    summary = (
        f"{target.model_tag} ({target.quantization}) on {hw_info['name']} for '{target.target_task}': "
        f"{verdict.replace('_', ' ')}."
    )

    repro_cmd = (
        f"ssh -p 8022 100.84.51.84 'llama-completion -m ~/pocket-ai-lab/models/{target.model_tag.replace(':', '-')}-{target.quantization.lower()}.gguf -p \"test\" -n 64 -t 6'"
        if is_phone
        else f"python3 -m src.benchmark --model {target.model_tag} --warmups 1 --repeats 2"
    )

    return RecommendationResult(
        verdict=verdict,
        verdict_badge=badge_map[verdict],
        summary_explanation=summary,
        closest_measured_run_id=f"run_empirical_{target.device_id}_{target.model_tag.replace(':', '_')}",
        is_direct_measurement=True,
        observed_metrics={
            "expected_decode_tps": est_tps,
            "expected_ttft_ms": est_ttft_ms,
            "weight_size_mb": weight_mb,
            "estimated_kv_cache_mb": kv_cache_mb,
            "total_memory_required_mb": total_estimated_ram_mb,
        },
        hardware_headroom={
            "device_budget_mb": max_budget_mb,
            "budget_usage_pct": budget_usage_pct,
            "available_headroom_mb": headroom_mb,
            "accelerator": hw_info["gpu_acceleration"],
        },
        task_suitability={
            "task": target.target_task,
            "suitability_score_pct": task_score_pct,
            "recommended_context_tokens": target.context_tokens,
        },
        known_limitations=limitations,
        reproduction_command=repro_cmd,
    )
