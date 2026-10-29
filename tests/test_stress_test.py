"""Unit tests for Phase 6 Sustained Thermal Stress Test harness."""
import os
import pytest

from src.stress_test import plot_thermal_stress_results
from src.benchmark import validate_loopback_url


def test_stress_test_loopback_enforcement():
    # Should not raise for loopback
    validate_loopback_url("http://127.0.0.1:11434")
    validate_loopback_url("http://localhost:11434")

    # Should raise for non-loopback
    with pytest.raises(ValueError, match="SECURITY ERROR: Pocket AI Lab strictly requires loopback binding"):
        validate_loopback_url("http://192.168.1.50:11434")


def test_plot_thermal_stress_results_generation(tmp_path):
    mock_records = [
        {
            "iteration": 1,
            "peak_gpu_temp_c": 52.0,
            "decode_tps": 46.5,
            "peak_vram_mb": 1280.0,
            "peak_gpu_util_pct": 78.0,
        },
        {
            "iteration": 2,
            "peak_gpu_temp_c": 56.0,
            "decode_tps": 46.2,
            "peak_vram_mb": 1280.0,
            "peak_gpu_util_pct": 82.0,
        },
        {
            "iteration": 3,
            "peak_gpu_temp_c": 58.0,
            "decode_tps": 45.9,
            "peak_vram_mb": 1280.0,
            "peak_gpu_util_pct": 85.0,
        },
    ]

    out_file = str(tmp_path / "test_thermal_curve.png")
    plot_thermal_stress_results(mock_records, out_file, "qwen2.5:1.5b")

    assert os.path.exists(out_file)
    assert os.path.getsize(out_file) > 1000  # valid image file generated
