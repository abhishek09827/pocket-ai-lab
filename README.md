# Pocket AI Lab 🔬📱💻

[![CI & GitHub Pages Deployment](https://github.com/abhishek09827/pocket-ai-lab/actions/workflows/deploy.yml/badge.svg)](https://github.com/abhishek09827/pocket-ai-lab/actions/workflows/deploy.yml)
[![Live Research Dashboard](https://img.shields.io/badge/Live_Research_Dashboard-GitHub_Pages-38bdf8?style=flat&logo=github)](https://abhishek09827.github.io/pocket-ai-lab/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776ab.svg?style=flat&logo=python)](https://python.org)
[![Tests Passing](https://img.shields.io/badge/Pytest-68%20passed-34d399.svg?style=flat&logo=pytest)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)

> **Empirical Edge AI Benchmarking & Dual-Hardware SLM Research Testbed**  
> Physical kernel counters. Real thermal degradation curves. Sandboxed code execution. Zero fabricated benchmarks.

---

## 🌟 Live Interactive Dashboard

Explore the full 11-tab interactive research portal deployed live at:  
👉 **[https://abhishek09827.github.io/pocket-ai-lab/](https://abhishek09827.github.io/pocket-ai-lab/)**

Features:
- **⚔️ Hardware Duel:** Head-to-head metrics comparing NVIDIA GTX 1650 vs realme 9 Pro+ (Dimensity 920).
- **🏆 Model Leaderboard:** Multi-facet filters (model scale, architecture) & side-by-side comparison modal.
- **🎯 Deployment Recommender:** Empirical decision engine answering *"Can I run this model on my device?"* with memory headroom meters.
- **📱 realme 9 Pro+ Profile:** Detailed SoC specs, 10-pass sustained thermal test telemetry, and degradation curve.
- **🧪 Application AI Evaluations:** Sandboxed Python code execution (10/10), strict JSON schemas (9/10), and offline semantic retrieval (100% Recall@1).
- **📊 Visual Gallery:** 10 publication-quality charts.
- **📦 Raw Data Explorer:** Direct downloads for raw JSONL and CSV telemetry ledgers.

---

## 🔬 Key Empirical Research Findings

### 1. The Energy Inversion (Tokens-per-Watt)
While the laptop GPU (GTX 1650) is 4.4x faster in token throughput (46.4 TPS vs 10.6 TPS), it draws ~50W. The MediaTek Dimensity 920 on the realme 9 Pro+ draws ~4W:
$$\text{Phone Efficiency} = \frac{10.64\text{ TPS}}{4\text{ W}} = \mathbf{2.66\text{ Tokens/Watt}}$$
$$\text{Laptop GPU Efficiency} = \frac{46.41\text{ TPS}}{50\text{ W}} = \mathbf{0.93\text{ Tokens/Watt}}$$
👉 **Smartphone CPUs are 2.89x more energy-efficient than discrete laptop GPUs for edge token generation.**

### 2. Prefill vs Decode Asymmetry
- **Prompt Evaluation (Prefill):** The GPU is **22.0x faster** (354.2 vs 16.1 TPS) thanks to 896 CUDA cores parallelizing matrix multiplication.
- **Autoregressive Generation (Decode):** The gap collapses to only **4.4x** (46.4 vs 10.6 TPS) because token decoding is memory-bandwidth bound rather than compute bound.

### 3. The Embodied Causality Deficit & Coder Anchor
- General models $<3$B parameters (`qwen2.5:1.5b` and `llama3.2:1b`) suffered a **0% success rate on ALFWorld sequential planning**, with 40% of failures caused by invalid actions (e.g., trying to take an item from a closed container).
- In contrast, `qwen2.5-coder:1.5b` achieved **46.7% success** and `qwen2.5-coder:3b` reached **60% success** (0% invalid actions). Syntax trees, variable scoping, and control-flow pre-training act as a cognitive anchor for causal state tracking!

### 4. Sustained Mobile Thermal Throttling (-29.43%)
Across a 10-pass continuous inference benchmark on the realme 9 Pro+ (200.4 seconds of continuous execution):
- **Cold-Start Speed:** 6.82 TPS
- **Peak Warm Speed:** 7.61 TPS (Pass 4)
- **Sustained Tail Speed:** 5.37 TPS (Pass 9)
- **Measured Thermal Throttling:** **-29.43% degradation** as passive vapor chamber cooling saturates.
- **Memory Stability:** 3,878 MB average RAM RSS with **0 OOM events**.

### 5. Offline Semantic Retrieval (RAG)
`nomic-embed-text:latest` (137M nomic-bert, 768-dim) achieved:
- **100% Recall@1, 100% Recall@5, and 1.0 MRR**
- Memory footprint: **323.0 MB VRAM** (8.4% of 4GB GTX 1650 budget)
- Dedicated compact embedding models are 10x faster and 75% more memory-efficient than using generative LLMs for dense retrieval.

---

## 💻 Dual-Hardware Testbed Specifications

| Specification Metric | Host PC Baseline (Workstation) | Edge Mobile Target (Phone) |
| :--- | :--- | :--- |
| **Device Model** | Lenovo IdeaPad Gaming (WSL2 / Ubuntu 24.04) | realme 9 Pro+ 5G (RMX3392) |
| **Processor / SoC** | Intel Core i5-10300H (4C/8T @ 4.5 GHz) | MediaTek Dimensity 920 5G (TSMC 6nm) |
| **Core Architecture** | x86_64 AVX2 | 2x Cortex-A78 (2.5 GHz) + 6x Cortex-A55 (2.0 GHz) |
| **Accelerator** | NVIDIA GeForce GTX 1650 (4GB GDDR6, TU117) | ARM Mali-G68 MC4 |
| **System Memory** | 16 GB DDR4 (Dual-channel) | 8 GB Unified LPDDR4X (7,553 MB accessible) |
| **Safe Model Memory** | 3,800 MB Safe VRAM Limit | ~3,200 MB Safe RAM (Leaves ~4.3 GB for Android OS) |
| **Runtime Engine** | Ollama v0.34.4 (CUDA cuBLAS) | `llama.cpp` ARM64 CLI (NEON CPU vectorization) |
| **Power Envelope** | ~50W TDP under load | ~4W TDP under load |
| **Network Perimeter** | Loopback `127.0.0.1:8000` | Tailscale WireGuard Mesh (`100.84.51.84:8022`) |

---

## 📊 Physical Leaderboard

| Model Tag | ALFWorld Planning | ALFWorld Invalid | HotpotQA Accuracy | HotpotQA Hallucination | Decode Speed | Median TTFT | Peak VRAM |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **qwen2.5-coder:3b** | **60.0%** | **0.0%** | 60.0% | 40.0% | 21.40 TPS | 41.12 ms | 2,227 MB (54.4%) |
| **qwen2.5-coder:1.5b** | **46.7%** | **6.7%** | 93.3% | 6.7% | 43.40 TPS | 32.12 ms | 1,378 MB (33.6%) |
| **qwen2.5:3b** | 20.0% | 0.0% | **100.0%** | **0.0%** | 19.44 TPS | 46.75 ms | 2,228 MB (54.4%) |
| **qwen2.5:1.5b** | 0.0% | 26.7% | **100.0%** | **0.0%** | 48.39 TPS | 63.49 ms | 1,314 MB (32.1%) |
| **deepseek-r1:1.5b** | 0.0% | 20.0% | 66.7% | 13.3% | 37.44 TPS | 11,159 ms | 1,872 MB (45.7%) |
| **qwen2.5:0.5b-instruct-q8_0** | 0.0% | 0.0% | 73.3% | 13.3% | 108.74 TPS | 181.09 ms | 2,014 MB (49.2%) |
| **qwen2.5:0.5b (Q4_K_M)** | 0.0% | 0.0% | **100.0%** | **0.0%** | **142.58 TPS** | **18.83 ms** | **764 MB (18.7%)** |
| **llama3.2:1b** | 0.0% | 40.0% | 40.0% | 60.0% | 43.91 TPS | 25.03 ms | 1,622 MB (39.6%) |

*(Statistical confidence: All scores report Wilson 95% binomial confidence intervals in raw ledgers).*

---

## 🚀 Quickstart & Developer Runbook

### 1. Installation
```bash
git clone https://github.com/abhishek09827/pocket-ai-lab.git
cd pocket-ai-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run Test Suite (68 Tests)
```bash
PYTHONPATH=. pytest -v
```

### 3. Run Benchmark Suite with Linux PSI Telemetry
```bash
PYTHONPATH=. python3 -m src.benchmark --model qwen2.5-coder:1.5b --warmups 1 --repeats 3
```

### 4. Run Application-Level AI Evaluators
```bash
# Python Coding in Sandboxed Execution Environment
PYTHONPATH=. python3 -m src.run_application_eval --suite coding --model qwen2.5-coder:1.5b

# Strict JSON Schema & Negative Controls
PYTHONPATH=. python3 -m src.run_application_eval --suite structured --model qwen2.5-coder:1.5b

# Dense Semantic Retrieval (Offline RAG)
PYTHONPATH=. python3 -m src.run_application_eval --suite retrieval --model nomic-embed-text:latest
```

### 5. Launch Authenticated Control Plane & Dashboard
```bash
PYTHONPATH=. uvicorn src.control_plane:app --host 127.0.0.1 --port 8000
# Open in browser: http://127.0.0.1:8000
```

### 6. Build Static Distribution Bundle
```bash
PYTHONPATH=. python3 scripts/export_static_site.py
# Output generated in dist/
```

---

## 🔒 Security & Measurement Invariants

1. **Strict Loopback Binding:** Local servers bind exclusively to `127.0.0.1`. Binding to `0.0.0.0` is blocked by unit tests (`tests/test_benchmark.py`).
2. **Encrypted WireGuard Mesh:** Phone access operates through private Tailscale mesh IPs (`100.x.y.z`) over SSH tunnels.
3. **Zero Synthetic Generation:** Telemetry samplers read directly from `/proc/pressure/memory`, `/proc/pressure/cpu`, NVML CUDA counters, and Android sysfs.
4. **Energy Disclaimers:** Battery percentage deltas are recorded as coarse device state indicators, not calibrated laboratory Joules.

---

## 📄 License & Attribution

Distributed under the MIT License. Developed by Abhishek Kaushik & Antigravity.
All benchmark data, charts, and prompts are openly reproducible.
