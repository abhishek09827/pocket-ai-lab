"""Unit tests for Context Window & KV-Cache Scaling Benchmark."""
import os
from unittest.mock import MagicMock, patch
import pytest

from src.context_scaling_bench import (
    generate_synthetic_prompt,
    plot_context_scaling,
    run_context_pass,
)
from src.benchmark import validate_loopback_url


def test_synthetic_prompt_scaling():
    short_p = generate_synthetic_prompt(50)
    long_p = generate_synthetic_prompt(1000)

    assert len(long_p) > len(short_p)
    assert "Based on the above context, summarize the key takeaway" in short_p
    assert "Based on the above context, summarize the key takeaway" in long_p


def test_context_scaling_loopback_enforcement():
    # Valid loopback
    validate_loopback_url("http://127.0.0.1:11434")
    validate_loopback_url("http://localhost:11434")

    # Insecure external IP
    with pytest.raises(ValueError, match="SECURITY ERROR: Pocket AI Lab strictly requires loopback binding"):
        validate_loopback_url("http://10.0.0.5:11434")


def test_plot_context_scaling(tmp_path):
    mock_records = [
        {
            "prompt_tokens": 256,
            "ttft_ms": 35.0,
            "prompt_tps": 320.0,
            "peak_vram_mb": 1150.0,
            "decode_tps": 47.0,
        },
        {
            "prompt_tokens": 512,
            "ttft_ms": 50.0,
            "prompt_tps": 340.0,
            "peak_vram_mb": 1280.0,
            "decode_tps": 46.5,
        },
        {
            "prompt_tokens": 1024,
            "ttft_ms": 82.0,
            "prompt_tps": 350.0,
            "peak_vram_mb": 1540.0,
            "decode_tps": 46.0,
        },
    ]

    out_file = str(tmp_path / "test_context_scaling.png")
    plot_context_scaling(mock_records, out_file, "qwen2.5:1.5b")

    assert os.path.exists(out_file)
    assert os.path.getsize(out_file) > 1000


@patch("src.context_scaling_bench.requests.post")
@patch("src.context_scaling_bench.GpuPeakSampler")
def test_run_context_pass_mocked(mock_sampler_cls, mock_post):
    mock_sampler = MagicMock()
    mock_sampler.stop.return_value = (1350.0, 85.0, 62.0)
    mock_sampler_cls.return_value = mock_sampler

    mock_resp = MagicMock()
    mock_resp.iter_lines.return_value = [
        b'{"response": "Summary ", "done": false}',
        b'{"response": "token.", "done": true, "prompt_eval_count": 512, "prompt_eval_duration": 1500000000, "eval_count": 25, "eval_duration": 500000000}',
    ]
    mock_resp.raise_for_status.return_value = None
    mock_post.return_value = mock_resp

    res = run_context_pass(
        api_base="http://127.0.0.1:11434",
        model="qwen2.5:1.5b",
        prompt="Test prompt",
        target_ctx=512,
    )

    assert res["prompt_tokens"] == 512
    assert res["decode_tokens"] == 25
    assert res["peak_vram_mb"] == 1350.0
    assert res["peak_gpu_util_pct"] == 85.0
    assert res["peak_gpu_temp_c"] == 62.0
    assert res["prompt_tps"] > 300.0
    assert res["decode_tps"] > 40.0
