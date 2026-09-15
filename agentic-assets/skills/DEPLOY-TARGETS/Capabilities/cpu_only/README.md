# hw_cpu_only

Skill for detecting, validating, and benchmarking CPU-only inference performance
(Intel, AMD, ARM64) before running AI/ML workloads without a GPU.

---

## What It Does

1. Detects CPU cores, threads, processor type, clock speed, and available RAM
2. Checks that all required Python packages (CPU build) are installed
3. Recommends which YOLO variant runs acceptably on this CPU
4. Optionally benchmarks inference speed (FPS, latency ms, peak RAM)
5. Writes `hw_capture_manifest.json` for downstream skills to consume

---

## NeuroEdge Location

```
skills/DEPLOY-TARGETS/Capabilities/cpu_only/   ← this skill (knowledge docs)
src/agents/hardware/cpu_only/            ← runtime implementation
  ├── cpu_agent.py                       ← CpuOnlyAgent(BaseHardwareAgent)
  ├── detect_cpu.py                      ← CLI: detect CPU
  ├── check_dependencies.py              ← CLI: audit packages
  ├── benchmark_cpu.py                   ← CLI: benchmark YOLO on CPU
  ├── write_hw_manifest.py               ← CLI: run_workflow (MAIN ENTRY)
  └── validate_hw_manifest.py            ← CLI: validate manifest
```

---

## Prerequisites

| Requirement | Minimum version | Check command |
|-------------|----------------|---------------|
| Python | 3.11 | `python --version` |
| PyTorch (CPU build) | 2.1+ | `python -c "import torch; print(torch.__version__)"` |
| Ultralytics | 8.0+ | `pip show ultralytics` |
| psutil | 5.9+ | `pip show psutil` |

See `references/cpu_setup_guide.md` for full installation instructions on Windows and Linux.

---

## How to Use

### Option A — Programmatic (recommended for NeuroEdge)

```python
from src.agents.hardware.cpu_only.cpu_agent import CpuOnlyAgent

agent = CpuOnlyAgent()

# Full pipeline: detect → check_deps → benchmark → manifest → validate
manifest = agent.run_workflow(skip_benchmark=False, model="yolov8n")
print(manifest.recommended_variant)   # e.g. "yolov8m"
print(manifest.constraints["ram_gb"]) # e.g. 32.0

# Steps individually
info = agent.detect()
print(info.device_name)               # e.g. "Intel Core i7-13700K"

bench = agent.benchmark(model="yolov8n", runs=100)
print(bench.fps)                      # e.g. 22.4
```

### Option B — Makefile

```bash
make hw-detect       # detect CPU specs
make hw-check        # audit dependencies
make hw-benchmark    # benchmark YOLO on CPU
make hw-manifest     # full pipeline → hw_capture_manifest.json
make hw-validate     # validate manifest
make hw-full         # manifest + validate
```

### Option C — Scripts directly

```bash
# From project root
python src/agents/hardware/cpu_only/detect_cpu.py
python src/agents/hardware/cpu_only/check_dependencies.py
python src/agents/hardware/cpu_only/benchmark_cpu.py --model yolov8n --runs 100
python src/agents/hardware/cpu_only/write_hw_manifest.py
python src/agents/hardware/cpu_only/write_hw_manifest.py --skip-benchmark
python src/agents/hardware/cpu_only/validate_hw_manifest.py
```

---

## Output: hw_capture_manifest.json

Written to `data/output/manifests/hw_capture_manifest.json`.

Example (Intel Core i7-12700K, 32 GB RAM):

```json
{
  "hw_target": "cpu-only",
  "device_name": "Intel(R) Core(TM) i7-12700K",
  "cpu_cores": 8,
  "cpu_threads": 20,
  "capture_timestamp": "2026-05-11T10:30:00",
  "constraints": {
    "compute_backend": "CPU",
    "supported_export_formats": ["onnx", "pytorch"],
    "ram_gb": 32.0,
    "ram_available_gb": 28.5,
    "processor_type": "x86_64",
    "platform": "Windows"
  },
  "yolo_variant_fit": {
    "yolov8n": {"fits": true,  "latency_ms": 45.3},
    "yolov8s": {"fits": true,  "latency_ms": 88.1},
    "yolov8m": {"fits": true,  "latency_ms": 210.0},
    "yolov8l": {"fits": false, "reason": "Need 12+ threads, have 20 — latency 620ms > 500ms threshold"},
    "yolov8x": {"fits": false, "reason": "Latency 1240ms > threshold 2000ms"}
  },
  "recommended_variant": "yolov8m",
  "benchmark": {
    "model": "yolov8n",
    "latency_mean_ms": 45.3,
    "latency_p99_ms": 52.1,
    "fps": 22.1,
    "ram_peak_mb": 512.5,
    "num_threads_used": 20
  },
  "skill_name": "hw_cpu_only",
  "status": "success"
}
```

---

## Downstream Skill Handoff

| Skill | What it reads | How it uses it |
|-------|--------------|----------------|
| `sw-model-training` | `recommended_variant`, `constraints.compute_backend` | Sets `device=cpu`, picks model size |
| `sw-model-export` | `constraints.supported_export_formats` | Selects `onnx` for CPU runtime |
| `sw-model-evaluation` | `constraints.compute_backend`, `device_name` | Benchmarks on CPU, labels results |

---

## Reference Files

- `references/cpu_model_matrix.md` — YOLO performance tiers (Entry/Mid/High-performance CPU)
- `references/cpu_setup_guide.md` — PyTorch CPU / Ultralytics setup on Windows, macOS, Linux

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `psutil not installed` | `pip install psutil` |
| Low FPS / all variants fail | Reduce `--runs`, use `--skip-benchmark`, try `yolov8n` only |
| `Manifest not found` | Run `write_hw_manifest.py` before `validate_hw_manifest.py` |
| `StateManager` import error | Ignore — replaced by `CpuOnlyAgent` in NeuroEdge; scripts use the agent directly |
