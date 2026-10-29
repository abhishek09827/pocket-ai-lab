"""Automated tests for Pocket AI Lab Control Plane API."""
import os
import pytest
from fastapi.testclient import TestClient

from src.control_plane import app, AUTH_TOKEN

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["binding"] == "127.0.0.1"


def test_telemetry_endpoint():
    resp = client.get("/api/telemetry")
    assert resp.status_code == 200
    data = resp.json()
    assert "host_os" in data
    assert "host_cpu" in data


def test_leaderboard_endpoint():
    resp = client.get("/api/leaderboard")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if len(data) > 0:
        first = data[0]
        assert "model_tag" in first
        assert "alfworld_success_pct" in first
        assert "hotpotqa_accuracy_pct" in first


def test_job_submission_requires_token():
    # Without token header -> 401
    resp = client.post("/api/jobs/evaluate", json={"model": "qwen2.5:1.5b", "repeats": 1})
    assert resp.status_code == 401

    # With invalid token -> 401
    resp = client.post(
        "/api/jobs/evaluate",
        json={"model": "qwen2.5:1.5b", "repeats": 1},
        headers={"X-Pocket-Token": "invalid_token_123"},
    )
    assert resp.status_code == 401


def test_job_submission_with_valid_token():
    # With valid token -> 202 Accepted
    resp = client.post(
        "/api/jobs/evaluate",
        json={"model": "qwen2.5:1.5b", "repeats": 1, "warmups": 0},
        headers={"X-Pocket-Token": AUTH_TOKEN},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"

    job_id = data["job_id"]
    # Poll status
    poll_resp = client.get(f"/api/jobs/{job_id}")
    assert poll_resp.status_code == 200
    poll_data = poll_resp.json()
    assert poll_data["job_id"] == job_id


def test_upload_results_requires_token():
    resp = client.post(
        "/api/upload-results",
        files={"file": ("test_android.jsonl", b'{"test": 1}\n')},
    )
    assert resp.status_code == 401


def test_upload_results_rejects_invalid_extension():
    resp = client.post(
        "/api/upload-results",
        files={"file": ("malicious.exe", b'malicious payload')},
        headers={"X-Pocket-Token": AUTH_TOKEN},
    )
    assert resp.status_code == 400


def test_upload_results_success():
    sample_jsonl = b'{"schema_version": "1.0.0", "execution_location": "local_android"}\n'
    resp = client.post(
        "/api/upload-results",
        files={"file": ("android_test_mock.jsonl", sample_jsonl)},
        headers={"X-Pocket-Token": AUTH_TOKEN},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "success"
    assert data["filename"] == "android_test_mock.jsonl"
    # Clean up mock file created by test
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    mock_file = os.path.join(results_dir, "android_test_mock.jsonl")
    if os.path.exists(mock_file):
        os.remove(mock_file)


def test_deployment_recommendation_endpoint():
    req = {
        "device_id": "realme_9_pro_plus",
        "model_tag": "qwen2.5:1.5b",
        "quantization": "Q4_K_M",
        "runtime": "llama.cpp",
        "context_tokens": 2048,
        "target_task": "coding",
    }
    resp = client.post("/api/recommend", json=req)
    assert resp.status_code == 200
    data = resp.json()
    assert "verdict" in data
    assert "observed_metrics" in data
    assert "hardware_headroom" in data


def test_job_cancellation():
    # Submit job
    submit_resp = client.post(
        "/api/jobs/evaluate",
        json={"model": "qwen2.5:0.5b", "repeats": 1, "warmups": 0},
        headers={"X-Pocket-Token": AUTH_TOKEN},
    )
    job_id = submit_resp.json()["job_id"]

    # Cancel without token -> 401
    cancel_no_tok = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel_no_tok.status_code == 401

    # Cancel with token -> 200
    cancel_ok = client.post(
        f"/api/jobs/{job_id}/cancel",
        headers={"X-Pocket-Token": AUTH_TOKEN},
    )
    assert cancel_ok.status_code == 200
    assert cancel_ok.json()["status"] in ["cancelled", "completed", "failed"]


def test_regression_comparison():
    # Find existing csv files
    import glob, os
    files = glob.glob("results/reasoning_*.csv")
    if len(files) >= 2:
        f1 = os.path.basename(files[0])
        f2 = os.path.basename(files[1])
        resp = client.get(f"/api/regression/compare?run1={f1}&run2={f2}")
        assert resp.status_code == 200
        data = resp.json()
        assert "deltas" in data
        assert "verdict" in data
