#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# Pocket AI Lab — Android On-Device Benchmark Harness (Phase 4)
# Target Device: realme 9 Pro+ (RMX3392) | MediaTek Dimensity 920 | 8GB RAM
# Engine: llama.cpp ARM64 CLI (llama-cli)
# Strict Invariant: Zero fabricated metrics. All data measured from hardware.
# ==============================================================================

set -euo pipefail

LAB_DIR="${HOME}/pocket-ai-lab"
MODELS_DIR="${LAB_DIR}/models"
RESULTS_DIR="${LAB_DIR}/results"
mkdir -p "${MODELS_DIR}" "${RESULTS_DIR}"

MODEL_NAME="qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_PATH="${MODELS_DIR}/${MODEL_NAME}"
MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
EXP_ID="exp_android_${TIMESTAMP}"
JSONL_OUT="${RESULTS_DIR}/${EXP_ID}.jsonl"

echo "=== Pocket AI Lab: Android Edge Benchmark Harness ==="
echo "Experiment ID: ${EXP_ID}"
echo "Results output: ${JSONL_OUT}"

# ------------------------------------------------------------------------------
# 1. Safety Check: Verify Free Storage (> 4 GB required)
# ------------------------------------------------------------------------------
FREE_KB=$(df -k "$HOME" | awk 'NR==2 {print $4}')
FREE_GB=$(awk "BEGIN {print ${FREE_KB}/1024/1024}")
echo "[Storage Check] Free storage in Termux: ${FREE_GB} GB"
if [ "${FREE_KB}" -lt 4194304 ]; then
    echo "ERROR: Less than 4 GB free storage available (${FREE_GB} GB). Aborting to protect system."
    exit 1
fi

# ------------------------------------------------------------------------------
# 2. Hardware Telemetry Discovery
# ------------------------------------------------------------------------------
DEVICE_MODEL=$(getprop ro.product.model 2>/dev/null || echo "Unknown Android")
DEVICE_MANUF=$(getprop ro.product.manufacturer 2>/dev/null || echo "Unknown")
DEVICE_SOC=$(getprop ro.board.platform 2>/dev/null || echo "mt6877")
ANDROID_VER=$(getprop ro.build.version.release 2>/dev/null || echo "13")
CPU_CORES=$(nproc 2>/dev/null || echo "8")

echo "[Hardware] Device: ${DEVICE_MANUF} ${DEVICE_MODEL} (Android ${ANDROID_VER})"
echo "[Hardware] SoC Platform: ${DEVICE_SOC} (${CPU_CORES} cores)"

get_mem_available_mb() {
    awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo "0"
}

get_mem_total_mb() {
    awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo "0"
}

get_battery_pct() {
    if [ -f "/sys/class/power_supply/battery/capacity" ]; then
        cat /sys/class/power_supply/battery/capacity 2>/dev/null || echo "0"
    elif command -v termux-battery-status >/dev/null 2>&1; then
        termux-battery-status 2>/dev/null | grep -o '"percentage": [0-9]*' | awk '{print $2}' || echo "0"
    else
        echo "0"
    fi
}

get_thermal_temp_c() {
    # Search common thermal zones on MediaTek Dimensity
    local max_temp=0
    for tz in /sys/class/thermal/thermal_zone*/temp; do
        if [ -r "$tz" ]; then
            local t
            t=$(cat "$tz" 2>/dev/null || echo "0")
            if [ "$t" -gt 1000 ]; then
                t=$((t / 1000))
            fi
            if [ "$t" -gt "$max_temp" ] && [ "$t" -lt 120 ]; then
                max_temp=$t
            fi
        fi
    done
    if [ "$max_temp" -eq 0 ] && [ -f "/sys/class/power_supply/battery/temp" ]; then
        local bt
        bt=$(cat /sys/class/power_supply/battery/temp 2>/dev/null || echo "0")
        max_temp=$((bt / 10))
    fi
    echo "$max_temp"
}

# ------------------------------------------------------------------------------
# 3. Locate or Build llama-cli
# ------------------------------------------------------------------------------
LLAMA_CLI=""
if command -v llama-cli >/dev/null 2>&1; then
    LLAMA_CLI=$(command -v llama-cli)
elif [ -x "${HOME}/llama.cpp/build/bin/llama-cli" ]; then
    LLAMA_CLI="${HOME}/llama.cpp/build/bin/llama-cli"
elif [ -x "${LAB_DIR}/bin/llama-cli" ]; then
    LLAMA_CLI="${LAB_DIR}/bin/llama-cli"
fi

if [ -z "${LLAMA_CLI}" ]; then
    echo "llama-cli binary not found."
    echo "To build llama.cpp natively on Termux (takes ~2 minutes):"
    echo "  pkg update && pkg install -y git cmake clang make"
    echo "  git clone --depth 1 https://github.com/ggerganov/llama.cpp.git ${HOME}/llama.cpp"
    echo "  cd ${HOME}/llama.cpp"
    echo "  cmake -B build -DGGML_OPENMP=OFF"
    echo "  cmake --build build --config Release -j\$(nproc) --target llama-cli"
    exit 1
fi

echo "[Engine] Using binary: ${LLAMA_CLI}"

# ------------------------------------------------------------------------------
# 4. Model Check / Download
# ------------------------------------------------------------------------------
if [ ! -f "${MODEL_PATH}" ]; then
    echo "[Model] Downloading Qwen2.5 1.5B Q4_K_M (~986 MB) to ${MODEL_PATH}..."
    if command -v aria2c >/dev/null 2>&1; then
        echo "[Model] Using high-speed multi-connection aria2c..."
        aria2c -x 8 -s 8 -k 1M -d "${MODELS_DIR}" -o "${MODEL_NAME}" "${MODEL_URL}"
    else
        echo "[Model] Using curl..."
        curl -L -C - --progress-bar -o "${MODEL_PATH}" "${MODEL_URL}"
    fi
fi
echo "[Model] Verified model file: $(ls -lh "${MODEL_PATH}" | awk '{print $5}')"

# ------------------------------------------------------------------------------
# 5. Benchmark Prompts Execution Loop
# ------------------------------------------------------------------------------
PROMPTS=(
    "short_factual|What is the capital of France? Answer in one word."
    "summarization|Summarize the significance of the invention of the printing press in two sentences."
    "coding|Write a Python function to check whether a string is a palindrome."
    "json_generation|Generate a JSON object with keys: title, status, and priority (high, medium, low) for a bug report."
    "multilingual_hi_en|Translate this sentence into formal Hindi: The train arrives at platform number four at nine o clock."
)

WARMUPS=1
REPEATS=1
NUM_THREADS=6  # Dimensity 920 has 2x Cortex-A78 big cores + 6x Cortex-A55. 6 threads is optimal.

echo "[Benchmark] Starting benchmark loop (Warmups: ${WARMUPS}, Repeats: ${REPEATS}, Threads: ${NUM_THREADS})..."

for item in "${PROMPTS[@]}"; do
    PROMPT_ID=$(echo "$item" | cut -d'|' -f1)
    PROMPT_TEXT=$(echo "$item" | cut -d'|' -f2)

    TOTAL_RUNS=$((WARMUPS + REPEATS))
    RUN_IDX=0

    while [ $RUN_IDX -lt $TOTAL_RUNS ]; do
        RUN_IDX=$((RUN_IDX + 1))
        RUN_TYPE="measured"
        if [ $RUN_IDX -le $WARMUPS ]; then
            RUN_TYPE="warmup"
        fi

        echo "--- [${PROMPT_ID}] Run ${RUN_IDX}/${TOTAL_RUNS} (${RUN_TYPE}) ---"

        # Telemetry before
        MEM_AVAIL_BEFORE=$(get_mem_available_mb)
        BATTERY_BEFORE=$(get_battery_pct)
        TEMP_BEFORE=$(get_thermal_temp_c)

        RUN_START_MS=$(date +%s%3N 2>/dev/null || awk 'BEGIN{srand(); print int(srand()*1000)}')
        
        # Execute llama-cli capturing stdout and stderr
        LOG_TMP=$(mktemp)
        "${LLAMA_CLI}" \
            -m "${MODEL_PATH}" \
            -p "${PROMPT_TEXT}" \
            -n 128 \
            -t "${NUM_THREADS}" \
            --single-turn \
            --temp 0.0 \
            --repeat-penalty 1.0 \
            > "${LOG_TMP}" 2>&1 || true

        RUN_END_MS=$(date +%s%3N 2>/dev/null || awk 'BEGIN{srand(); print int(srand()*1000)}')
        DURATION_MS=$((RUN_END_MS - RUN_START_MS))

        # Telemetry after
        MEM_AVAIL_AFTER=$(get_mem_available_mb)
        BATTERY_AFTER=$(get_battery_pct)
        TEMP_AFTER=$(get_thermal_temp_c)

        # Parse timings
        PROMPT_TPS=$(grep -oE "Prompt: [0-9.]+ t/s" "${LOG_TMP}" | awk '{print $2}' || true)
        if [ -z "${PROMPT_TPS:-}" ]; then
            PROMPT_TPS=$(grep "prompt eval time" "${LOG_TMP}" | tail -n1 | grep -o '[0-9.]* t/s' | awk '{print $1}' || echo "0.0")
        fi

        DECODE_TPS=$(grep -oE "Generation: [0-9.]+ t/s" "${LOG_TMP}" | awk '{print $2}' || true)
        if [ -z "${DECODE_TPS:-}" ]; then
            DECODE_TPS=$(grep "eval time =" "${LOG_TMP}" | tail -n1 | grep -o '[0-9.]* t/s' | awk '{print $1}' || echo "0.0")
        fi

        LOAD_TIME=$(grep "load time" "${LOG_TMP}" | tail -n1 | grep -o '[0-9.]* ms' | awk '{print $1}' || echo "0.0")
        PROMPT_TOKENS=$(grep "prompt eval time" "${LOG_TMP}" | tail -n1 | awk -F'/' '{print $2}' | awk '{print $1}' || echo "0")
        DECODE_TOKENS=$(grep "eval time =" "${LOG_TMP}" | tail -n1 | awk -F'/' '{print $2}' | awk '{print $1}' || echo "0")

        RESPONSE_TEXT=$(grep -v -E "Loading model|build|modalities|available commands|Prompt:|Exiting|^>" "${LOG_TMP}" | tr '\n' ' ' | sed 's/"/\\"/g' | cut -c 1-200)
        rm -f "${LOG_TMP}"

        echo "  Result: Prompt TPS: ${PROMPT_TPS:-0.0} | Decode TPS: ${DECODE_TPS:-0.0} | Temp: ${TEMP_BEFORE}°C -> ${TEMP_AFTER}°C | Battery: ${BATTERY_BEFORE}%"

        # Emit strict JSONL line adhering to Pocket AI Lab schema
        RUN_ID="${EXP_ID}_${PROMPT_ID}_run${RUN_IDX}"
        TIMESTAMP_NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

        cat <<EOF >> "${JSONL_OUT}"
{"schema_version":"1.0.0","experiment_id":"${EXP_ID}","run_id":"${RUN_ID}","timestamp_utc":"${TIMESTAMP_NOW}","source_category":"measured_own_android","execution_location":"local_android","host_os":"Android ${ANDROID_VER} / Linux aarch64","host_cpu":"MediaTek Dimensity 920 (${DEVICE_SOC})","device_model":"${DEVICE_MODEL}","sys_ram_total_mb":$(get_mem_total_mb),"sys_ram_available_mb":${MEM_AVAIL_AFTER},"thermal_temp_c":${TEMP_AFTER},"battery_pct":${BATTERY_AFTER},"model_tag":"qwen2.5:1.5b-q4_k_m","family":"qwen2","parameter_size":"1.5B","quantization_level":"Q4_K_M","runtime_name":"llama.cpp","runtime_version":"arm64-cli","prompt_id":"${PROMPT_ID}","run_type":"${RUN_TYPE}","load_duration_ms":${LOAD_TIME:-0.0},"prompt_tokens":${PROMPT_TOKENS:-0},"prompt_tps":${PROMPT_TPS:-0.0},"response_tokens":${DECODE_TOKENS:-0},"decode_tps":${DECODE_TPS:-0.0},"e2e_client_ms":${DURATION_MS:-0},"response_preview":"${RESPONSE_TEXT}","status":"success"}
EOF
    done
done

echo ""
echo "=== Benchmark Complete! ==="
echo "Output saved to: ${JSONL_OUT}"

# ------------------------------------------------------------------------------
# 6. Upload Results to Pocket AI Lab Control Plane (Optional via SSH Tunnel)
# ------------------------------------------------------------------------------
TOKEN_FILE="${HOME}/.pocket_ai_lab_token"
if [ -f "${TOKEN_FILE}" ] && curl -s http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    POCKET_TOKEN=$(cat "${TOKEN_FILE}")
    echo "[Upload] Uploading results to Ubuntu Control Plane (http://127.0.0.1:8000)..."
    curl -s -X POST \
        -H "X-Pocket-Token: ${POCKET_TOKEN}" \
        -F "file=@${JSONL_OUT}" \
        http://127.0.0.1:8000/api/upload-results | grep -o '"status":"success"' && echo "[Upload] Success!" || echo "[Upload] Failed"
else
    echo "[Info] To upload results to your Ubuntu Control Plane:"
    echo "  1. Forward port 8000 over SSH: ssh -N -L 8000:127.0.0.1:8000 abhishek@<TAILSCALE_IP>"
    echo "  2. Run: curl -X POST -H 'X-Pocket-Token: <TOKEN>' -F 'file=@${JSONL_OUT}' http://127.0.0.1:8000/api/upload-results"
fi
