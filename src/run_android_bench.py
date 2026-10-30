"""Pocket AI Lab — Automated Remote Android Benchmark Runner.

Connects to the attached Android edge device (realme 9 Pro+) over Tailscale SSH,
triggers the on-device `llama.cpp` ARM64 benchmark suite on the Dimensity 920,
downloads the resulting telemetry JSONL, and updates the local dashboard.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from typing import Optional


def run_remote_android_benchmark(
    phone_ip: Optional[str] = None,
    port: int = 8022,
) -> str:
    """Execute benchmark suite remotely on Android device over SSH."""
    if phone_ip is None:
        phone_ip = os.environ.get("POCKET_PHONE_HOST", "100.x.y.z")
    print(f"\n========================================================")
    print(f" POCKET AI LAB — REMOTE ANDROID BENCHMARK DISPATCHER")
    print(f" Target Device : realme 9 Pro+ (MediaTek Dimensity 920)")
    print(f" Connection    : {phone_ip}:{port} over Tailscale Ed25519")
    print(f"========================================================\n")

    # 1. Verify reachability
    print(f"[1/4] Verifying SSH reachability on {phone_ip}:{port}...")
    check_cmd = [
        "ssh", "-p", str(port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        phone_ip,
        "echo 'ONLINE' && getprop ro.product.model",
    ]
    try:
        res = subprocess.run(check_cmd, capture_output=True, text=True, check=True)
        device_name = res.stdout.strip().split("\n")[-1]
        print(f"✔ Device connected: {device_name}")
    except Exception as exc:
        print(f"❌ Failed to reach Android device at {phone_ip}:{port}: {exc}")
        print("  Ensure Termux is open and `sshd` is running on the phone.")
        sys.exit(1)

    # 2. Deploy latest android_bench.sh
    print(f"[2/4] Syncing latest benchmark harness to device...")
    scp_cmd = [
        "scp", "-P", str(port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        "scripts/android_bench.sh",
        f"{phone_ip}:~/pocket-ai-lab/android_bench.sh",
    ]
    subprocess.run(scp_cmd, check=True)

    # 3. Trigger benchmark execution on phone
    print(f"[3/4] Launching on-device inference passes on Dimensity 920...")
    exec_cmd = [
        "ssh", "-p", str(port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        phone_ip,
        "bash ~/pocket-ai-lab/android_bench.sh",
    ]
    proc = subprocess.Popen(exec_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    latest_jsonl = ""
    for line in iter(proc.stdout.readline, ""):
        print("  " + line, end="", flush=True)
        if "Results output:" in line:
            latest_jsonl = line.split("Results output:")[-1].strip()
    proc.wait()

    if proc.returncode != 0:
        print(f"❌ Benchmark failed on phone with exit code {proc.returncode}")
        sys.exit(proc.returncode)

    # 4. Fetch results back to PC
    print(f"\n[4/4] Retrieving benchmark JSONL telemetry to Ubuntu PC...")
    results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
    os.makedirs(results_dir, exist_ok=True)

    if not latest_jsonl:
        # Fallback to finding latest remote jsonl
        find_cmd = [
            "ssh", "-p", str(port),
            "-o", "StrictHostKeyChecking=no",
            "-o", "BatchMode=yes",
            phone_ip,
            "ls -t ~/pocket-ai-lab/results/exp_android_*.jsonl | head -n1",
        ]
        latest_jsonl = subprocess.check_output(find_cmd, text=True).strip()

    local_filename = os.path.basename(latest_jsonl)
    local_path = os.path.join(results_dir, local_filename)

    pull_cmd = [
        "scp", "-P", str(port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "BatchMode=yes",
        f"{phone_ip}:{latest_jsonl}",
        local_path,
    ]
    subprocess.run(pull_cmd, check=True)
    print(f"✔ Benchmark records saved to: {local_path}")

    # Re-export static distribution bundle
    from scripts.export_static_site import export_static_site
    export_static_site()

    print("\n---------------------------------------------------------")
    print(f" Android On-Device Benchmark Successfully Completed!")
    print(f" Local Telemetry Artifact : {local_path}")
    print(f" Web Dashboard Updated    : http://127.0.0.1:8000")
    print("---------------------------------------------------------\n")
    return local_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run on-device benchmark on Android phone")
    parser.add_argument("--phone-ip", type=str, default=os.environ.get("POCKET_PHONE_HOST", "100.x.y.z"), help="Phone Tailscale IP")
    parser.add_argument("--port", type=int, default=8022, help="Termux SSH port")
    args = parser.parse_args()

    run_remote_android_benchmark(phone_ip=args.phone_ip, port=args.port)
