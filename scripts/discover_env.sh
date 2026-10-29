#!/usr/bin/env bash
set -uo pipefail

echo "================================================================="
echo " Pocket AI Lab - Phase 0 Environment Discovery"
echo " Timestamp (UTC): $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "================================================================="

echo ""
echo "--- 1. OS & Kernel ---"
echo "Kernel: $(uname -srm)"
if [ -f /etc/os-release ]; then
    grep -E '^(NAME|VERSION|ID|VERSION_ID)=' /etc/os-release
else
    echo "/etc/os-release not found"
fi

echo ""
echo "--- 2. CPU Architecture & Features ---"
if command -v lscpu &>/dev/null; then
    lscpu | grep -E 'Model name|Architecture|CPU\(s\):|Thread\(s\) per core|Core\(s\) per socket|Socket\(s\):|CPU max MHz|CPU min MHz|Flags' | head -n 25
    echo -n "Key Vector Extensions: "
    lscpu | grep -o -E '\b(avx|avx2|avx512f|avx512vnni|vnni|fma)\b' | sort -u | tr '\n' ' '
    echo ""
else
    echo "lscpu command not found"
fi

echo ""
echo "--- 3. Memory & Storage ---"
echo ">> System Memory:"
free -h || true
echo ""
echo ">> Filesystem Usage:"
df -h / /home 2>/dev/null || df -h

echo ""
echo "--- 4. GPU & Acceleration ---"
echo ">> PCI Display Devices (lspci):"
if command -v lspci &>/dev/null; then
    lspci | grep -iE 'vga|3d|display|nvidia' || echo "No matching PCI devices found"
else
    echo "lspci not installed"
fi
echo ""
echo ">> NVIDIA System Management Interface (nvidia-smi):"
if command -v nvidia-smi &>/dev/null; then
    nvidia-smi --query-gpu=name,driver_version,memory.total,memory.free,memory.used,temperature.gpu,utilization.gpu,utilization.memory --format=csv,noheader || nvidia-smi
else
    echo "nvidia-smi not found or NVIDIA driver not loaded"
fi

echo ""
echo "--- 5. Network, SSH & Tailscale ---"
echo ">> Tailscale Status:"
if command -v tailscale &>/dev/null; then
    tailscale status 2>&1 || echo "Tailscale service not responding"
    tailscale ip -4 2>/dev/null && echo "Tailscale IPv4: $(tailscale ip -4 2>/dev/null)" || true
else
    echo "tailscale CLI not found"
fi
echo ""
echo ">> Active Listening Ports (Loopback & Network):"
if command -v ss &>/dev/null; then
    ss -tlnp 2>/dev/null || ss -tln
else
    echo "ss command not found"
fi
echo ""
echo ">> SSH Service Status:"
systemctl is-active ssh 2>/dev/null || systemctl is-active sshd 2>/dev/null || echo "systemctl check for ssh/sshd failed or inactive"

echo ""
echo "--- 6. Ollama Server Status ---"
if command -v ollama &>/dev/null; then
    echo "Ollama binary: $(command -v ollama)"
    ollama --version 2>/dev/null || echo "Unable to get ollama version"
    systemctl is-active ollama 2>/dev/null && echo "Ollama systemd service: active" || echo "Ollama systemd service: not active / not found"
else
    echo "Ollama binary not found in PATH"
fi
echo "Testing Ollama port 11434 via curl (loopback):"
curl -s --max-time 3 http://127.0.0.1:11434/api/version 2>&1 || echo "Connection to 127.0.0.1:11434 failed"
echo ""

echo ""
echo "--- 7. Android Device & ADB Connection ---"
if command -v adb &>/dev/null; then
    echo "ADB binary: $(command -v adb) ($(adb version | head -n 1))"
    echo ">> ADB Devices:"
    adb devices -l
    echo ""
    echo ">> Android Storage Check (if device is attached & authorized):"
    adb shell df -h /data 2>&1 || echo "ADB shell command failed or device unauthorized/unreachable"
else
    echo "adb not installed"
fi

echo ""
echo "--- 8. Python & Development Environment ---"
if command -v python3 &>/dev/null; then
    echo "Python 3: $(python3 --version) at $(which python3)"
else
    echo "python3 not found"
fi
if command -v pip &>/dev/null; then
    echo "Pip: $(pip --version)"
elif command -v pip3 &>/dev/null; then
    echo "Pip3: $(pip3 --version)"
else
    echo "pip/pip3 not found in standard PATH"
fi

echo ""
echo "================================================================="
echo " Discovery completed."
echo "================================================================="
