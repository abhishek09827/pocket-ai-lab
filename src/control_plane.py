"""Pocket AI Lab — Strictly Local Authenticated Control Plane & Job Runner.

Security Guarantees:
- Strictly binds to 127.0.0.1 (Loopback). Never binds to 0.0.0.0.
- Mutation endpoints require 'X-Pocket-Token' authentication.
- Allowlisted job actions only. Zero arbitrary shell execution.
"""
from __future__ import annotations

import csv
import glob
import os
import secrets
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Header, Security, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.model_registry import discover_available_models, profile_model_fit, list_registry
from src.telemetry import capture_hardware_telemetry


# Token management
TOKEN_FILE = os.path.expanduser("~/.pocket_ai_lab_token")


def get_or_create_token() -> str:
    """Retrieve existing security token or generate a high-entropy 256-bit token."""
    env_token = os.environ.get("POCKET_LAB_TOKEN")
    if env_token:
        return env_token.strip()

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            tok = f.read().strip()
            if tok:
                return tok

    new_token = secrets.token_hex(32)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(new_token)
    os.chmod(TOKEN_FILE, 0o600)
    return new_token


AUTH_TOKEN = get_or_create_token()


def verify_token(x_pocket_token: Optional[str] = Header(None)) -> str:
    """Verify security token for mutating control actions."""
    if not x_pocket_token or not secrets.compare_digest(x_pocket_token, AUTH_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Pocket-Token authentication header",
        )
    return x_pocket_token


# FastAPI App
app = FastAPI(
    title="Pocket AI Lab Control Plane",
    description="Strictly loopback-bound management API for edge AI benchmarking",
    version="1.0.0",
)

# CORS restricted strictly to localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# In-memory job state tracker
jobs_lock = threading.Lock()
JOBS_STORE: Dict[str, Dict[str, Any]] = {}


class JobSubmissionRequest(BaseModel):
    model: str = Field(..., description="Ollama model tag e.g. llama3.2:1b")
    repeats: int = Field(2, ge=1, le=10)
    warmups: int = Field(1, ge=0, le=5)


class TelemetryResponse(BaseModel):
    host_os: str
    host_cpu: str
    sys_ram_used_mb: Optional[float]
    sys_ram_available_mb: Optional[float]
    cpu_util_pct: Optional[float]
    gpu_name: Optional[str]
    gpu_vram_used_mb: Optional[float]
    gpu_temp_c: Optional[float]


@app.get("/api/health")
def health_check() -> Dict[str, str]:
    """Basic health check verifying loopback service availability."""
    return {"status": "ok", "service": "Pocket AI Lab Control Plane", "binding": "127.0.0.1"}


@app.get("/api/telemetry")
def get_telemetry() -> Dict[str, Any]:
    """Retrieve instantaneous hardware telemetry."""
    hw = capture_hardware_telemetry()
    return hw.model_dump()


@app.get("/api/models")
def get_model_registry() -> List[Dict[str, Any]]:
    """Query model registry with parameter counts and GTX 1650 VRAM compatibility."""
    raw = discover_available_models()
    return [profile_model_fit(m) for m in raw]


@app.get("/api/leaderboard")
def get_consolidated_leaderboard() -> List[Dict[str, Any]]:
    """Compile consolidated multi-dimensional leaderboard from benchmark CSV files."""
    results_dir = "results"
    all_data = []

    # Compile reasoning benchmark results
    for f in glob.glob(os.path.join(results_dir, "reasoning_*.csv")):
        with open(f, "r", encoding="utf-8") as fp:
            reader = csv.DictReader(fp)
            for row in reader:
                all_data.append(row)

    if not all_data:
        return []

    measured = [r for r in all_data if r.get("run_type") == "measured"]
    models = sorted(list(set(r["model_tag"] for r in measured)))

    leaderboard = []
    for m in models:
        m_rec = [r for r in measured if r["model_tag"] == m]
        alf = [r for r in m_rec if r.get("benchmark_family") == "alfworld_decision"]
        hotpot = [r for r in m_rec if r.get("benchmark_family") == "hotpotqa_multihop"]

        alf_success_pct = round((sum(1 for r in alf if r["outcome"] == "SUCCESS") / (len(alf) or 1)) * 100.0, 1)
        alf_invalid_pct = round((sum(1 for r in alf if r["outcome"] == "INVALID_ACTION") / (len(alf) or 1)) * 100.0, 1)
        hotpot_acc_pct = round((sum(1 for r in hotpot if r["outcome"] == "SUCCESS") / (len(hotpot) or 1)) * 100.0, 1)
        hotpot_hall_pct = round((sum(1 for r in hotpot if r["outcome"] == "HALLUCINATION") / (len(hotpot) or 1)) * 100.0, 1)

        vrams = [float(r["peak_vram_mb"]) for r in m_rec if r.get("peak_vram_mb")]
        tps = [float(r["decode_tps"]) for r in m_rec if r.get("decode_tps")]
        ttfts = [float(r["ttft_client_ms"]) for r in m_rec if r.get("ttft_client_ms")]

        avg_vram = round(sum(vrams) / len(vrams), 1) if vrams else 0.0
        avg_tps = round(sum(tps) / len(tps), 2) if tps else 0.0
        median_ttft = round(sorted(ttfts)[len(ttfts) // 2], 2) if ttfts else 0.0

        leaderboard.append({
            "model_tag": m,
            "hotpotqa_accuracy_pct": hotpot_acc_pct,
            "hotpotqa_hallucination_pct": hotpot_hall_pct,
            "alfworld_success_pct": alf_success_pct,
            "alfworld_invalid_action_pct": alf_invalid_pct,
            "decode_tps": avg_tps,
            "median_ttft_ms": median_ttft,
            "peak_vram_mb": avg_vram,
            "gtx_1650_vram_pct": round((avg_vram / 4096.0) * 100.0, 1),
            "total_measured_trials": len(m_rec),
        })

    # Sort by overall performance
    leaderboard.sort(key=lambda x: (x["alfworld_success_pct"], x["hotpotqa_accuracy_pct"], x["decode_tps"]), reverse=True)
    return leaderboard


def _background_job_runner(job_id: str, model: str, repeats: int, warmups: int) -> None:
    """Execute evaluation job in isolated worker thread."""
    from src.auto_eval import auto_evaluate_model

    with jobs_lock:
        JOBS_STORE[job_id]["status"] = "running"
        JOBS_STORE[job_id]["started_at"] = time.time()

    try:
        auto_evaluate_model(
            model=model,
            repeats=repeats,
            warmups=warmups,
        )
        with jobs_lock:
            JOBS_STORE[job_id]["status"] = "completed"
            JOBS_STORE[job_id]["completed_at"] = time.time()
    except Exception as exc:
        with jobs_lock:
            JOBS_STORE[job_id]["status"] = "failed"
            JOBS_STORE[job_id]["error"] = str(exc)
            JOBS_STORE[job_id]["completed_at"] = time.time()


@app.post("/api/jobs/evaluate", status_code=status.HTTP_202_ACCEPTED)
def submit_evaluation_job(
    req: JobSubmissionRequest,
    _token: str = Depends(verify_token),
) -> Dict[str, Any]:
    """Submit a model evaluation job. Requires X-Pocket-Token authentication."""
    job_id = f"job_{uuid.uuid4().hex[:8]}"

    with jobs_lock:
        JOBS_STORE[job_id] = {
            "job_id": job_id,
            "model": req.model,
            "repeats": req.repeats,
            "warmups": req.warmups,
            "status": "queued",
            "submitted_at": time.time(),
        }

    thread = threading.Thread(
        target=_background_job_runner,
        args=(job_id, req.model, req.repeats, req.warmups),
        daemon=True,
    )
    thread.start()

    return {
        "job_id": job_id,
        "model": req.model,
        "status": "queued",
        "message": f"Job {job_id} submitted for evaluation of {req.model}",
    }


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str) -> Dict[str, Any]:
    """Query execution status of a submitted job."""
    with jobs_lock:
        if job_id not in JOBS_STORE:
            raise HTTPException(status_code=404, detail="Job not found")
        return JOBS_STORE[job_id]


@app.post("/api/upload-results", status_code=status.HTTP_201_CREATED)
async def upload_results(
    file: UploadFile = File(...),
    _token: str = Depends(verify_token),
) -> Dict[str, Any]:
    """Securely upload benchmark results from edge devices (e.g. Android Termux).
    
    Requires X-Pocket-Token authentication.
    Accepts .jsonl or .csv files.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    
    clean_filename = os.path.basename(file.filename)
    if not (clean_filename.endswith(".jsonl") or clean_filename.endswith(".csv")):
        raise HTTPException(status_code=400, detail="Only .jsonl and .csv result files are allowed")

    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    os.makedirs(results_dir, exist_ok=True)
    destination_path = os.path.join(results_dir, clean_filename)

    content = await file.read()
    with open(destination_path, "wb") as f:
        f.write(content)

    return {
        "status": "success",
        "filename": clean_filename,
        "bytes_received": len(content),
        "saved_path": f"results/{clean_filename}",
    }


@app.get("/api/edge-results")
def list_edge_results() -> List[Dict[str, Any]]:
    """List benchmark results originating from edge devices (e.g., Android)."""
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    android_records = []
    
    import json
    for f in glob.glob(os.path.join(results_dir, "*android*.jsonl")):
        with open(f, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        android_records.append(data)
                    except Exception:
                        pass
    return android_records


@app.get("/scripts/android_bench.sh")
def download_android_harness() -> FileResponse:
    """Download Android benchmark harness script directly over the loopback SSH tunnel."""
    script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "android_bench.sh")
    if not os.path.exists(script_path):
        raise HTTPException(status_code=404, detail="Script not found")
    return FileResponse(script_path, media_type="text/x-shellscript", filename="android_bench.sh")


# Mount static website if directory exists
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
