"""Automated tests for Pocket AI Lab Control Plane API."""
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


def test_upload_results_success(tmp_path):
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
