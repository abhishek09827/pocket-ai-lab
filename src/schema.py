"""Pydantic v2 schemas for reproducible edge AI benchmarking."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


SourceCategory = Literal[
    "measured_own_pc",
    "measured_own_android",
    "community_submitted",
    "emulator",
]

ExecutionLocation = Literal[
    "local_ubuntu",
    "local_android",
    "remote_ubuntu_via_ssh_tunnel",
]

RunType = Literal[
    "cold_start",
    "warmup",
    "measured",
]

RunStatus = Literal[
    "success",
    "error",
    "skipped",
    "timeout",
    "oom",
    "invalid_output",
    "schema_violation",
]


class HardwareTelemetry(BaseModel):
    """Hardware telemetry and environmental metrics."""
    model_config = ConfigDict(extra="ignore")

    host_os: str = Field(..., description="Operating system details and kernel")
    host_cpu: str = Field(..., description="CPU model name and topology")
    sys_ram_used_mb: Optional[float] = None
    sys_ram_available_mb: Optional[float] = None
    cpu_util_pct: Optional[float] = None
    gpu_name: Optional[str] = None
    gpu_driver_version: Optional[str] = None
    gpu_vram_total_mb: Optional[float] = None
    gpu_vram_used_mb: Optional[float] = None
    gpu_util_pct: Optional[float] = None
    gpu_temp_c: Optional[float] = None
    peak_gpu_vram_used_mb: Optional[float] = None
    peak_gpu_util_pct: Optional[float] = None
    peak_gpu_temp_c: Optional[float] = None
    # Linux Pressure Stall Information (PSI)
    memory_pressure_psi_some_pct: Optional[float] = Field(None, description="Memory pressure stall percentage (some avg10)")
    memory_pressure_psi_full_pct: Optional[float] = Field(None, description="Memory pressure stall percentage (full avg10)")
    cpu_pressure_psi_some_pct: Optional[float] = Field(None, description="CPU pressure stall percentage (some avg10)")


class ModelIdentity(BaseModel):
    """Exact model identity, weights digest, and runtime details."""
    model_config = ConfigDict(extra="ignore")

    model_tag: str = Field(..., description="Requested model tag e.g. qwen2.5:1.5b")
    digest_sha256: Optional[str] = Field(None, description="Cryptographic SHA256 digest of weights")
    family: Optional[str] = None
    parameter_size: Optional[str] = None
    quantization_level: Optional[str] = None
    runtime_name: str = "ollama"
    runtime_version: Optional[str] = None


class GenerationConfig(BaseModel):
    """Inference generation parameters."""
    model_config = ConfigDict(extra="ignore")

    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 42
    num_ctx: int = 2048
    max_tokens: Optional[int] = 512


class PerformanceMetrics(BaseModel):
    """High-precision latency, duration, and token throughput metrics."""
    model_config = ConfigDict(extra="ignore")

    load_duration_ms: Optional[float] = None
    ttft_client_ms: Optional[float] = None
    e2e_client_ms: Optional[float] = None
    prompt_tokens: Optional[int] = None
    prompt_eval_duration_ms: Optional[float] = None
    prompt_tps: Optional[float] = None
    response_tokens: Optional[int] = None
    decode_duration_ms: Optional[float] = None
    decode_tps: Optional[float] = None
    # Measurement boundaries and caching detection
    prompt_cache_hit: Optional[bool] = Field(False, description="True if prompt KV cache prefix was hit in runtime")
    server_total_duration_ms: Optional[float] = Field(None, description="Total duration reported by backend server")
    network_overhead_ms: Optional[float] = Field(None, description="Client TTFT minus server prompt prefill and load time")


class QualityEvaluation(BaseModel):
    """Deterministic quality scoring against defined rules."""
    model_config = ConfigDict(extra="ignore")

    prompt_id: str
    category: str
    quality_passed: bool
    quality_notes: Optional[str] = None
    response_text: str


class BenchmarkRecord(BaseModel):
    """Complete versioned record for an individual benchmark run."""
    model_config = ConfigDict(extra="ignore")

    schema_version: str = "1.0.0"
    experiment_id: str
    run_id: str
    timestamp_utc: str
    run_type: RunType
    source_category: SourceCategory = "measured_own_pc"
    execution_location: ExecutionLocation = "local_ubuntu"
    
    hardware: HardwareTelemetry
    model: ModelIdentity
    generation: GenerationConfig
    metrics: PerformanceMetrics
    quality: QualityEvaluation
    
    status: RunStatus = "success"
    error_message: Optional[str] = None

    def to_csv_dict(self) -> Dict[str, Any]:
        """Flatten record for CSV serialization."""
        return {
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "timestamp_utc": self.timestamp_utc,
            "run_type": self.run_type,
            "source_category": self.source_category,
            "execution_location": self.execution_location,
            "status": self.status,
            "error_message": self.error_message,
            # Hardware
            "host_os": self.hardware.host_os,
            "host_cpu": self.hardware.host_cpu,
            "sys_ram_used_mb": self.hardware.sys_ram_used_mb,
            "sys_ram_available_mb": self.hardware.sys_ram_available_mb,
            "cpu_util_pct": self.hardware.cpu_util_pct,
            "gpu_name": self.hardware.gpu_name,
            "gpu_driver_version": self.hardware.gpu_driver_version,
            "gpu_vram_total_mb": self.hardware.gpu_vram_total_mb,
            "gpu_vram_used_mb": self.hardware.gpu_vram_used_mb,
            "gpu_util_pct": self.hardware.gpu_util_pct,
            "gpu_temp_c": self.hardware.gpu_temp_c,
            "peak_gpu_vram_used_mb": self.hardware.peak_gpu_vram_used_mb,
            "peak_gpu_util_pct": self.hardware.peak_gpu_util_pct,
            "peak_gpu_temp_c": self.hardware.peak_gpu_temp_c,
            "memory_pressure_psi_some_pct": self.hardware.memory_pressure_psi_some_pct,
            "memory_pressure_psi_full_pct": self.hardware.memory_pressure_psi_full_pct,
            "cpu_pressure_psi_some_pct": self.hardware.cpu_pressure_psi_some_pct,
            # Model
            "model_tag": self.model.model_tag,
            "digest_sha256": self.model.digest_sha256,
            "family": self.model.family,
            "parameter_size": self.model.parameter_size,
            "quantization_level": self.model.quantization_level,
            "runtime_name": self.model.runtime_name,
            "runtime_version": self.model.runtime_version,
            # Generation
            "temperature": self.generation.temperature,
            "top_p": self.generation.top_p,
            "seed": self.generation.seed,
            "num_ctx": self.generation.num_ctx,
            "max_tokens": self.generation.max_tokens,
            # Metrics
            "load_duration_ms": self.metrics.load_duration_ms,
            "ttft_client_ms": self.metrics.ttft_client_ms,
            "e2e_client_ms": self.metrics.e2e_client_ms,
            "prompt_tokens": self.metrics.prompt_tokens,
            "prompt_eval_duration_ms": self.metrics.prompt_eval_duration_ms,
            "prompt_tps": self.metrics.prompt_tps,
            "response_tokens": self.metrics.response_tokens,
            "decode_duration_ms": self.metrics.decode_duration_ms,
            "decode_tps": self.metrics.decode_tps,
            "prompt_cache_hit": self.metrics.prompt_cache_hit,
            "server_total_duration_ms": self.metrics.server_total_duration_ms,
            "network_overhead_ms": self.metrics.network_overhead_ms,
            # Quality
            "prompt_id": self.quality.prompt_id,
            "category": self.quality.category,
            "quality_passed": self.quality.quality_passed,
            "quality_notes": self.quality.quality_notes,
            "response_text_len": len(self.quality.response_text),
        }


def compute_wilson_score_interval(
    successes: int,
    total: int,
    confidence: float = 0.95,
) -> Tuple[float, float, float]:
    """Calculate the Wilson score confidence interval for a binomial proportion.
    
    Prevents over-claiming general capability from small sample sizes (e.g. 5 prompts).
    Returns (center, lower_bound_pct, upper_bound_pct).
    """
    import math

    if total == 0:
        return 0.0, 0.0, 0.0

    # z value for two-sided confidence (95% -> 1.95996)
    z = 1.95996 if abs(confidence - 0.95) < 0.01 else 1.64485
    p_hat = successes / total
    denom = 1.0 + (z**2) / total
    center = (p_hat + (z**2) / (2.0 * total)) / denom
    margin = (z / denom) * math.sqrt((p_hat * (1.0 - p_hat) / total) + ((z**2) / (4.0 * (total**2))))

    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)

    return round(p_hat * 100.0, 1), round(lower * 100.0, 1), round(upper * 100.0, 1)
