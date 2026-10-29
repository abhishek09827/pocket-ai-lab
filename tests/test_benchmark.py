"""Automated test suite verifying loopback security, schemas, datasets, evaluator, and telemetry."""
import os
import pytest

from src.benchmark import compute_stats, load_dataset, validate_loopback_url
from src.evaluator import evaluate_response, extract_json_candidate
from src.schema import (
    BenchmarkRecord,
    GenerationConfig,
    HardwareTelemetry,
    ModelIdentity,
    PerformanceMetrics,
    QualityEvaluation,
    compute_wilson_score_interval,
)
from src.telemetry import (
    capture_hardware_telemetry,
    get_host_cpu,
    get_host_os,
    read_linux_pressure,
)


class TestLoopbackSecurity:
    """Ensure strict loopback binding rule cannot be bypassed."""

    @pytest.mark.parametrize("valid_url", [
        "http://127.0.0.1:11434",
        "http://127.0.0.1",
        "http://localhost:11434",
        "http://localhost",
        "http://[::1]:11434",
    ])
    def test_valid_loopback_urls(self, valid_url: str):
        # Should not raise
        validate_loopback_url(valid_url)

    @pytest.mark.parametrize("invalid_url", [
        "http://0.0.0.0:11434",
        "http://192.168.1.50:11434",
        "http://10.0.0.1:11434",
        "http://100.64.0.1:11434",
        "http://myhost.local:11434",
        "http://external-api.com:11434",
    ])
    def test_reject_non_loopback_urls(self, invalid_url: str):
        with pytest.raises(ValueError, match="SECURITY ERROR"):
            validate_loopback_url(invalid_url)


class TestDatasetIntegrity:
    """Verify versioned prompt dataset contains all 7 mandated categories and valid rules."""

    def test_dataset_contains_all_categories(self):
        dataset_path = "datasets/prompts_v1.jsonl"
        assert os.path.exists(dataset_path), f"{dataset_path} does not exist"
        records = load_dataset(dataset_path)

        assert len(records) >= 7, f"Expected at least 7 prompts, got {len(records)}"

        required_categories = {
            "short_factual",
            "summarization",
            "information_extraction",
            "coding",
            "json_generation",
            "instruction_following",
            "multilingual_hi_en",
        }

        found_categories = {r.get("category") for r in records}
        missing = required_categories - found_categories
        assert not missing, f"Dataset is missing required categories: {missing}"

        for r in records:
            assert r.get("dataset_version") == "1.0.0"
            assert "prompt_id" in r
            assert "prompt" in r
            assert "validation_rules" in r
            assert isinstance(r["validation_rules"], dict)


class TestEvaluatorRules:
    """Test deterministic evaluation logic across all rule types."""

    def test_contains_all(self):
        rules = {"contains_all": ["carbon", "atomic"]}
        assert evaluate_response("Carbon has atomic number 6", rules)[0] is True
        assert evaluate_response("Carbon only", rules)[0] is False

    def test_contains_any(self):
        rules = {"contains_any": ["apple", "banana"]}
        assert evaluate_response("I like apples and oranges", rules)[0] is True
        assert evaluate_response("I like cherries", rules)[0] is False

    def test_regex(self):
        rules = {"regex": r"def\s+fibonacci\s*\(\s*n\s*\):"}
        assert evaluate_response("def fibonacci(n):\n    return n", rules)[0] is True
        assert evaluate_response("def solve(x): return x", rules)[0] is False

    def test_json_keys_and_markdown(self):
        rules = {"json_keys": ["sensor_id", "status"]}
        # Raw json
        raw = '{"sensor_id": "s1", "status": "nominal"}'
        assert evaluate_response(raw, rules)[0] is True

        # Markdown wrapped
        md = '```json\n{"sensor_id": "s1", "status": "nominal"}\n```'
        assert evaluate_response(md, rules)[0] is True

        # Missing key
        missing = '{"sensor_id": "s1"}'
        assert evaluate_response(missing, rules)[0] is False

        # Malformed JSON
        malformed = '{"sensor_id": "s1", status: invalid}'
        assert evaluate_response(malformed, rules)[0] is False

    def test_max_words_no_char(self):
        rules = {"max_words_no_char": {"char": ",", "max_words": 5}}
        assert evaluate_response("Red Blue Green", rules)[0] is True
        assert evaluate_response("Red, Blue, Green", rules)[0] is False
        assert evaluate_response("One two three four five six", rules)[0] is False


class TestSchemaAndSerialization:
    """Test Pydantic v2 schema validation, serialization, and null handling."""

    def test_schema_full_and_csv(self):
        record = BenchmarkRecord(
            schema_version="1.0.0",
            experiment_id="exp_test_01",
            run_id="exp_test_01_p1_iter1",
            timestamp_utc="2026-10-28T12:00:00Z",
            run_type="measured",
            source_category="measured_own_pc",
            execution_location="local_ubuntu",
            hardware=HardwareTelemetry(
                host_os="Ubuntu 24.04",
                host_cpu="Intel Core i5",
                sys_ram_used_mb=4096.0,
                sys_ram_available_mb=12288.0,
                cpu_util_pct=15.2,
                gpu_name="NVIDIA GeForce GTX 1650",
                gpu_driver_version="596.49",
                gpu_vram_total_mb=4096.0,
                gpu_vram_used_mb=180.0,
                gpu_util_pct=8.0,
                gpu_temp_c=74.0,
                peak_gpu_vram_used_mb=1200.0,
                peak_gpu_util_pct=45.0,
                peak_gpu_temp_c=76.0,
            ),
            model=ModelIdentity(
                model_tag="qwen2.5:1.5b",
                digest_sha256="183715c43589",
                family="qwen2",
                parameter_size="1.5B",
                quantization_level="Q4_K_M",
                runtime_name="ollama",
                runtime_version="0.34.4",
            ),
            generation=GenerationConfig(
                temperature=0.0,
                top_p=1.0,
                seed=42,
                num_ctx=2048,
            ),
            metrics=PerformanceMetrics(
                load_duration_ms=45.2,
                ttft_client_ms=120.5,
                e2e_client_ms=650.0,
                prompt_tokens=18,
                prompt_eval_duration_ms=25.0,
                prompt_tps=720.0,
                response_tokens=35,
                decode_duration_ms=580.0,
                decode_tps=60.34,
            ),
            quality=QualityEvaluation(
                prompt_id="short_factual_01",
                category="short_factual",
                quality_passed=True,
                quality_notes="Passed all checks",
                response_text="Carbon",
            ),
            status="success",
        )

        json_str = record.model_dump_json()
        assert "exp_test_01" in json_str
        assert "qwen2.5:1.5b" in json_str

        csv_dict = record.to_csv_dict()
        assert csv_dict["experiment_id"] == "exp_test_01"
        assert csv_dict["decode_tps"] == 60.34
        assert csv_dict["quality_passed"] is True

    def test_null_metric_handling(self):
        """Ensure unavailable metrics are stored as None / null, never 0."""
        record = BenchmarkRecord(
            schema_version="1.0.0",
            experiment_id="exp_test_null",
            run_id="run_null_01",
            timestamp_utc="2026-10-28T12:00:00Z",
            run_type="cold_start",
            hardware=HardwareTelemetry(
                host_os="Ubuntu",
                host_cpu="CPU",
                gpu_name=None,
                gpu_vram_used_mb=None,
            ),
            model=ModelIdentity(model_tag="qwen2.5:1.5b"),
            generation=GenerationConfig(),
            metrics=PerformanceMetrics(
                ttft_client_ms=None,
                decode_tps=None,
            ),
            quality=QualityEvaluation(
                prompt_id="test_01",
                category="test",
                quality_passed=False,
                response_text="",
            ),
        )

        dumped = record.model_dump()
        assert dumped["hardware"]["gpu_name"] is None
        assert dumped["hardware"]["gpu_vram_used_mb"] is None
        assert dumped["metrics"]["ttft_client_ms"] is None


class TestTelemetryAndStats:
    """Test hardware info retrieval and statistical calculations."""

    def test_hardware_telemetry_capture(self):
        telem = capture_hardware_telemetry()
        assert telem.host_os != ""
        assert telem.host_cpu != ""
        assert telem.sys_ram_available_mb is not None
        assert telem.sys_ram_available_mb > 0

    def test_compute_stats_accuracy(self):
        data = [10.0, 20.0, 30.0, 40.0, 50.0]
        stats = compute_stats(data)
        assert stats["mean"] == 30.0
        assert stats["median"] == 30.0
        assert stats["p90"] == 50.0
        assert stats["min"] == 10.0
        assert stats["max"] == 50.0
        assert stats["stdev"] == pytest.approx(15.81, rel=1e-2)

    def test_wilson_confidence_intervals(self):
        # 5 out of 5 successes should show uncertainty, not a blanket 100%
        center, low, high = compute_wilson_score_interval(5, 5, confidence=0.95)
        assert center == 100.0
        assert low < 100.0  # Wilson interval properly reports lower bound for n=5
        assert high == 100.0

        # 0 out of 5
        center, low, high = compute_wilson_score_interval(0, 5, confidence=0.95)
        assert center == 0.0
        assert low == 0.0
        assert high > 0.0  # Upper bound accounts for small sample uncertainty

        # Zero sample safety
        assert compute_wilson_score_interval(0, 0) == (0.0, 0.0, 0.0)

    def test_linux_pressure_stall_info(self):
        mem_psi = read_linux_pressure("memory")
        assert isinstance(mem_psi, dict)
        assert "some_avg10" in mem_psi

    def test_metrics_cache_hit_and_network_overhead(self):
        metrics = PerformanceMetrics(
            ttft_client_ms=45.0,
            prompt_eval_duration_ms=4.0,
            load_duration_ms=1.0,
            prompt_tokens=150,
            prompt_cache_hit=True,
            server_total_duration_ms=350.0,
            network_overhead_ms=40.0,
        )
        assert metrics.prompt_cache_hit is True
        assert metrics.network_overhead_ms == 40.0
