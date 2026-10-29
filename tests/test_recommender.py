"""Tests for Deployment Recommendation Engine."""
import pytest
from src.recommender import (
    DeploymentTarget,
    HARDWARE_BUDGETS,
    evaluate_deployment_recommendation,
)


class TestRecommenderEngine:
    """Test deployment suitability recommendations and constraint verification."""

    def test_hardware_budgets_integrity(self):
        assert "realme_9_pro_plus" in HARDWARE_BUDGETS
        assert "ubuntu_gtx_1650" in HARDWARE_BUDGETS
        assert HARDWARE_BUDGETS["realme_9_pro_plus"]["max_safe_model_ram_mb"] < 4000.0

    def test_recommended_fit_mobile_1_5b(self):
        target = DeploymentTarget(
            device_id="realme_9_pro_plus",
            model_tag="qwen2.5:1.5b",
            quantization="Q4_K_M",
            runtime="llama.cpp",
            target_task="coding",
        )
        res = evaluate_deployment_recommendation(target)
        assert res.verdict in ["RECOMMENDED", "PROCEED_WITH_CAUTION"]
        assert res.hardware_headroom["available_headroom_mb"] > 0
        assert len(res.reproduction_command) > 0

    def test_oom_risk_detection(self):
        # Requesting massive context on phone exceeding safe budget
        target = DeploymentTarget(
            device_id="realme_9_pro_plus",
            model_tag="qwen2.5:3b",
            quantization="Q8_0",
            runtime="llama.cpp",
            context_tokens=16384,  # Huge KV cache
            target_task="general",
        )
        res = evaluate_deployment_recommendation(target)
        assert res.verdict in ["INCOMPATIBLE_OOM_RISK", "PROCEED_WITH_CAUTION"]
        assert any("memory" in lim.lower() or "budget" in lim.lower() for lim in res.known_limitations)

    def test_reasoning_deficit_warning_0_5b(self):
        target = DeploymentTarget(
            device_id="ubuntu_gtx_1650",
            model_tag="qwen2.5:0.5b",
            quantization="Q4_K_M",
            runtime="ollama",
            target_task="reasoning",
        )
        res = evaluate_deployment_recommendation(target)
        assert res.task_suitability["suitability_score_pct"] < 50.0
        assert any("causality deficit" in lim.lower() or "alfworld" in lim.lower() for lim in res.known_limitations)

    def test_retrieval_model_recommendation(self):
        target_emb = DeploymentTarget(
            device_id="ubuntu_gtx_1650",
            model_tag="nomic-embed-text",
            quantization="F16",
            runtime="ollama",
            target_task="retrieval",
        )
        res_emb = evaluate_deployment_recommendation(target_emb)
        assert res_emb.task_suitability["suitability_score_pct"] == 100.0
