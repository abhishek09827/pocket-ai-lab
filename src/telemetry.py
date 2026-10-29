"""Hardware telemetry collector supporting CPU, RAM, and NVIDIA GPU metrics."""
from __future__ import annotations

import platform
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, Optional, Tuple

import psutil

from src.schema import HardwareTelemetry


def get_host_cpu() -> str:
    """Retrieve host CPU brand and topology."""
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
            for line in f:
                if "model name" in line:
                    model = line.split(":", 1)[1].strip()
                    cores = psutil.cpu_count(logical=False) or "?"
                    threads = psutil.cpu_count(logical=True) or "?"
                    return f"{model} ({cores}C / {threads}T)"
    except Exception:
        pass
    return f"{platform.processor() or platform.machine()} ({psutil.cpu_count()} threads)"


def get_host_os() -> str:
    """Retrieve OS distribution and kernel release."""
    distro = "Linux"
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    distro = line.split("=", 1)[1].strip().strip('"')
                    break
    except Exception:
        pass
    return f"{distro} ({platform.system()} {platform.release()} {platform.machine()})"


def read_linux_pressure(subsystem: str = "memory") -> Dict[str, Optional[float]]:
    """Parse Linux Pressure Stall Information (PSI) from /proc/pressure/{subsystem}.
    
    Returns 'some_avg10' and 'full_avg10' stall percentages.
    """
    path = f"/proc/pressure/{subsystem}"
    res: Dict[str, Optional[float]] = {"some_avg10": None, "full_avg10": None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                prefix = parts[0]  # 'some' or 'full'
                for item in parts[1:]:
                    if item.startswith("avg10="):
                        val = float(item.split("=")[1])
                        if prefix == "some":
                            res["some_avg10"] = val
                        elif prefix == "full":
                            res["full_avg10"] = val
    except Exception:
        pass
    return res


def read_nvidia_gpu_stats() -> Dict[str, Optional[Any]]:
    """Query nvidia-smi for instantaneous GPU metrics.
    
    Returns None for GPU fields if nvidia-smi is unavailable.
    """
    default_res: Dict[str, Optional[Any]] = {
        "gpu_name": None,
        "gpu_driver_version": None,
        "gpu_vram_total_mb": None,
        "gpu_vram_used_mb": None,
        "gpu_util_pct": None,
        "gpu_temp_c": None,
    }

    if not shutil.which("nvidia-smi"):
        return default_res

    cmd = [
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5, check=False)
        if result.returncode != 0:
            return default_res

        line = result.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 6:
            return {
                "gpu_name": parts[0],
                "gpu_driver_version": parts[1],
                "gpu_vram_total_mb": float(parts[2]),
                "gpu_vram_used_mb": float(parts[3]),
                "gpu_util_pct": float(parts[4]),
                "gpu_temp_c": float(parts[5]),
            }
    except Exception:
        pass

    return default_res


class GpuPeakSampler:
    """Background sampler thread sampling GPU metrics every interval_sec during inference."""

    def __init__(self, interval_sec: float = 0.20):
        self.interval_sec = interval_sec
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.peak_vram_used_mb: Optional[float] = None
        self.peak_gpu_util_pct: Optional[float] = None
        self.peak_gpu_temp_c: Optional[float] = None
        self._has_gpu = bool(shutil.which("nvidia-smi"))

    def _sample_loop(self) -> None:
        while not self._stop_event.is_set():
            stats = read_nvidia_gpu_stats()
            vram = stats.get("gpu_vram_used_mb")
            util = stats.get("gpu_util_pct")
            temp = stats.get("gpu_temp_c")

            if vram is not None:
                self.peak_vram_used_mb = (
                    max(self.peak_vram_used_mb, vram)
                    if self.peak_vram_used_mb is not None
                    else vram
                )
            if util is not None:
                self.peak_gpu_util_pct = (
                    max(self.peak_gpu_util_pct, util)
                    if self.peak_gpu_util_pct is not None
                    else util
                )
            if temp is not None:
                self.peak_gpu_temp_c = (
                    max(self.peak_gpu_temp_c, temp)
                    if self.peak_gpu_temp_c is not None
                    else temp
                )

            time.sleep(self.interval_sec)

    def start(self) -> "GpuPeakSampler":
        if not self._has_gpu:
            return self
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=1.0)
        return (self.peak_vram_used_mb, self.peak_gpu_util_pct, self.peak_gpu_temp_c)

    def __enter__(self) -> "GpuPeakSampler":
        return self.start()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()


def capture_hardware_telemetry(
    peak_vram: Optional[float] = None,
    peak_util: Optional[float] = None,
    peak_temp: Optional[float] = None,
) -> HardwareTelemetry:
    """Capture full hardware telemetry snapshot."""
    vm = psutil.virtual_memory()
    sys_ram_used_mb = round((vm.total - vm.available) / (1024 * 1024), 2)
    sys_ram_available_mb = round(vm.available / (1024 * 1024), 2)
    cpu_util = round(psutil.cpu_percent(interval=None), 2)

    gpu_stats = read_nvidia_gpu_stats()

    # If peak values were not provided by a sampler, fallback to instantaneous
    resolved_peak_vram = peak_vram if peak_vram is not None else gpu_stats.get("gpu_vram_used_mb")
    resolved_peak_util = peak_util if peak_util is not None else gpu_stats.get("gpu_util_pct")
    resolved_peak_temp = peak_temp if peak_temp is not None else gpu_stats.get("gpu_temp_c")

    mem_psi = read_linux_pressure("memory")
    cpu_psi = read_linux_pressure("cpu")

    return HardwareTelemetry(
        host_os=get_host_os(),
        host_cpu=get_host_cpu(),
        sys_ram_used_mb=sys_ram_used_mb,
        sys_ram_available_mb=sys_ram_available_mb,
        cpu_util_pct=cpu_util,
        gpu_name=gpu_stats.get("gpu_name"),
        gpu_driver_version=gpu_stats.get("gpu_driver_version"),
        gpu_vram_total_mb=gpu_stats.get("gpu_vram_total_mb"),
        gpu_vram_used_mb=gpu_stats.get("gpu_vram_used_mb"),
        gpu_util_pct=gpu_stats.get("gpu_util_pct"),
        gpu_temp_c=gpu_stats.get("gpu_temp_c"),
        peak_gpu_vram_used_mb=resolved_peak_vram,
        peak_gpu_util_pct=resolved_peak_util,
        peak_gpu_temp_c=resolved_peak_temp,
        memory_pressure_psi_some_pct=mem_psi.get("some_avg10"),
        memory_pressure_psi_full_pct=mem_psi.get("full_avg10"),
        cpu_pressure_psi_some_pct=cpu_psi.get("some_avg10"),
    )
