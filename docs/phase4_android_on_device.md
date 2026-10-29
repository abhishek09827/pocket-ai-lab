# Phase 4 Runbook: Android On-Device Benchmarking (Termux + llama.cpp ARM64)

**Target Hardware:**
- **Device:** realme 9 Pro+ (`RMX3392`)
- **SoC:** MediaTek Dimensity 920 (2x Cortex-A78 @ 2.5 GHz + 6x Cortex-A55 @ 2.0 GHz)
- **RAM:** 8 GB LPDDR4X
- **Storage Status:** 19 GB free (**Verified Safe**: Model requires ~986 MB)
- **OS:** Android 13 / realme UI 4.0

---

## 1. Quick Answers & Exact Tunnel Parameters

When opening an SSH tunnel from your phone to access the Pocket AI Lab Control Plane and Ollama:

| Variable | Exact Value | Notes |
| :--- | :--- | :--- |
| `<UBUNTU_USER>` | `abhishek` | Ubuntu WSL2 username |
| `<UBUNTU_TAILSCALE_IP>` | `100.x.y.z` | See instructions below to check/install Tailscale |
| Security Token | `a51f4f610e21ae8430241c81fcbde2ec522f956221123af579fd318b245ab0f0` | Stored in `~/.pocket_ai_lab_token` |
| Web Dashboard Tunnel | `ssh -N -L 8000:127.0.0.1:8000 abhishek@<TAILSCALE_IP>` | Opens Web Dashboard at `http://127.0.0.1:8000` |
| Ollama API Tunnel | `ssh -N -L 11434:127.0.0.1:11434 abhishek@<TAILSCALE_IP>` | Loops Ollama inference to phone |

### How to obtain `<UBUNTU_TAILSCALE_IP>`:
- If Tailscale is installed on **Windows**:
  - Click the Tailscale tray icon -> Click **Copy IPv4 Address** (starts with `100.`).
  - Or in Windows PowerShell: `tailscale ip -4`
- If installing Tailscale directly inside **Ubuntu WSL2** (Recommended for direct tunneling):
  ```bash
  curl -fsSL https://tailscale.com/install.sh | sh
  sudo tailscale up
  tailscale ip -4
  ```

### Prerequisite: Enable SSH Server on Ubuntu WSL2:
Because `openssh-server` is not yet running on this Ubuntu instance, run this once:
```bash
sudo apt update && sudo apt install -y openssh-server
sudo service ssh start
```

---

## 2. Setting Up Termux on realme 9 Pro+

### Step 2.1: Install Termux & Storage Setup
Ensure Termux is installed from **F-Droid** or GitHub (do not use Google Play version as it is outdated).
Open Termux and run:
```bash
termux-setup-storage
pkg update && pkg install -y git clang cmake make curl jq bc
```

---

## 3. Native llama.cpp ARM64 Compilation on Dimensity 920

Compile `llama.cpp` directly on your Dimensity 920 (~2 minutes):
```bash
git clone --depth 1 https://github.com/ggerganov/llama.cpp.git $HOME/llama.cpp
cd $HOME/llama.cpp
cmake -B build -DGGML_OPENMP=OFF
cmake --build build --config Release -j$(nproc) --target llama-cli
```

Verify binary:
```bash
$HOME/llama.cpp/build/bin/llama-cli --version
```

---

## 4. Run the Automated Android Benchmark Harness

We have prepared the automated test script [`scripts/android_bench.sh`](file:///home/abhishek/projects/ai-lab/scripts/android_bench.sh).

You can copy `scripts/android_bench.sh` to your phone via SSH/SCP or run:
```bash
# In Termux on your realme 9 Pro+:
curl -sSL https://raw.githubusercontent.com/.../scripts/android_bench.sh -o android_bench.sh
# Or copy directly from this PC:
# scp abhishek@<TAILSCALE_IP>:~/projects/ai-lab/scripts/android_bench.sh .
chmod +x android_bench.sh
./android_bench.sh
```

### What `android_bench.sh` performs:
1. **Safety Assert:** Confirms > 4 GB free storage before downloading.
2. **Model Download:** Pulls `qwen2.5-1.5b-instruct-q4_k_m.gguf` (~986 MB).
3. **Telemetry Capture:** Reads `/proc/meminfo`, `/sys/class/thermal/thermal_zone*/temp`, and battery percentage.
4. **Standardized Prompt Execution:** Runs the 7 core benchmark prompts across warmups and measured runs on 4 threads (optimized for Cortex-A78 cores).
5. **JSONL Emission:** Produces `results/exp_android_<timestamp>.jsonl` adhering to schema v1.0.0.
6. **Automatic Ingestion:** If the SSH tunnel to port 8000 is active, uploads the results directly to the Control Plane leaderboard!

---

## 5. Uploading Benchmark Results to Control Plane

From Termux on your phone, once your SSH tunnel (`ssh -N -L 8000:127.0.0.1:8000 abhishek@<TAILSCALE_IP>`) is open:
```bash
curl -X POST \
  -H "X-Pocket-Token: a51f4f610e21ae8430241c81fcbde2ec522f956221123af579fd318b245ab0f0" \
  -F "file=@$HOME/pocket-ai-lab/results/exp_android_*.jsonl" \
  http://127.0.0.1:8000/api/upload-results
```

The Web Dashboard at `http://127.0.0.1:8000` will instantly reflect the realme 9 Pro+ on-device measurements alongside the GTX 1650 PC baseline!
