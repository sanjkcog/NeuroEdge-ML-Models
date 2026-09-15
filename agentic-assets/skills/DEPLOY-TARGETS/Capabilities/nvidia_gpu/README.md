# hw_nvidia_local_gpu

Skill for detecting, validating, and benchmarking a local NVIDIA GPU
(RTX 4070, RTX 4080, RTX 3090, or any CUDA-capable card) before running AI/ML workloads.

---

## What It Does

1. Detects GPU model, VRAM, CUDA version, driver, cuDNN, and TensorRT
2. Checks that all required Python packages are installed and CUDA-enabled
3. Recommends which YOLO variant fits within available VRAM
4. Optionally benchmarks inference speed (FPS, latency ms, peak VRAM)
5. Writes `hw_capture_manifest.json` for downstream skills to consume

---

## NeuroEdge Location

```
skills/DEPLOY-TARGETS/Capabilities/nvidia_gpu/   ← this skill (knowledge docs)
src/agents/hardware/nvidia_gpu/            ← runtime implementation
  ├── gpu_agent.py                         ← NvidiaGpuAgent(BaseHardwareAgent)
  ├── detect_gpu.py                        ← CLI: detect GPU via nvidia-smi + PyTorch
  ├── check_dependencies.py                ← CLI: audit packages (CUDA, TensorRT)
  ├── benchmark_gpu.py                     ← CLI: benchmark YOLO on CUDA
  ├── write_hw_manifest.py                 ← CLI: run_workflow (MAIN ENTRY)
  └── validate_hw_manifest.py              ← CLI: validate manifest
```

---

## Prerequisites

| Requirement | Minimum version | Check command |
|-------------|----------------|---------------|
| NVIDIA driver | 525.xx (RTX 40xx) | `nvidia-smi` |
| CUDA Toolkit | 11.8 or 12.1 | `nvcc --version` |
| Python | 3.11 | `python --version` |
| PyTorch (CUDA build) | 2.1+ | `python -c "import torch; print(torch.version.cuda)"` |
| Ultralytics | 8.0+ | `pip show ultralytics` |

See `references/cuda_setup_guide.md` for full installation instructions on Windows and Linux.

---

## How to Use

### Option A — Programmatic (recommended for NeuroEdge)

```python
from src.agents.hardware.nvidia_gpu.gpu_agent import NvidiaGpuAgent

agent = NvidiaGpuAgent()

# Full pipeline: detect → check_deps → benchmark → manifest → validate
manifest = agent.run_workflow(skip_benchmark=False, model="yolov8n", runs=200)
print(manifest.recommended_variant)           # e.g. "yolov8l"
print(manifest.constraints["vram_total_gb"])  # e.g. 8.0
print(manifest.constraints["supported_export_formats"])  # ["pytorch","onnx"] or ["tensorrt","pytorch","onnx"]

# Steps individually
info = agent.detect()
print(info.device_name)               # e.g. "NVIDIA GeForce RTX 4070 Laptop GPU"
print(info.metadata["gpu_count"])     # 1

bench = agent.benchmark(model="yolov8n", runs=200)
print(bench.fps)                      # e.g. 312.5
print(bench.memory_peak_mb)          # VRAM peak in MB
```

### Option B — Makefile

```bash
make gpu-detect      # detect GPU specs
make gpu-check       # audit dependencies (CUDA, TensorRT, etc.)
make gpu-benchmark   # benchmark YOLO on CUDA
make gpu-manifest    # full pipeline → hw_capture_manifest.json
make gpu-validate    # validate manifest
make gpu-full        # manifest + validate
```

### Option C — Scripts directly

```bash
# From project root
python src/agents/hardware/nvidia_gpu/detect_gpu.py
python src/agents/hardware/nvidia_gpu/check_dependencies.py
python src/agents/hardware/nvidia_gpu/benchmark_gpu.py --model yolov8n --runs 200
python src/agents/hardware/nvidia_gpu/write_hw_manifest.py
python src/agents/hardware/nvidia_gpu/write_hw_manifest.py --skip-benchmark
python src/agents/hardware/nvidia_gpu/validate_hw_manifest.py
```

---

## Output: hw_capture_manifest.json

Written to `data/output/manifests/hw_capture_manifest.json`.

Example (RTX 4070 Laptop, 8 GB VRAM):

```json
{
  "hw_target": "nvidia-local-gpu",
  "device_name": "NVIDIA GeForce RTX 4070 Laptop GPU",
  "gpu_count": 1,
  "capture_timestamp": "2026-05-11T10:30:00",
  "constraints": {
    "compute_backend": "CUDA",
    "supported_export_formats": ["pytorch", "onnx"],
    "max_model_size_mb": 6400,
    "vram_total_gb": 8.0,
    "vram_free_gb": 7.4,
    "cuda_version": "12.1",
    "cudnn_version": "8902",
    "tensorrt_version": null,
    "driver_version": "537.13",
    "compute_capability": "8.9"
  },
  "yolo_variant_fit": {
    "yolov8n": {"fits": true,  "max_batch": 26},
    "yolov8s": {"fits": true,  "max_batch": 13},
    "yolov8m": {"fits": true,  "max_batch": 6},
    "yolov8l": {"fits": true,  "max_batch": 4},
    "yolov8x": {"fits": false, "max_batch": 0, "reason": "Need 12.0 GB VRAM, have 8.0 GB"}
  },
  "recommended_variant": "yolov8l",
  "benchmark": {
    "model": "yolov8n",
    "device": "cuda",
    "latency_mean_ms": 3.2,
    "latency_p99_ms": 4.1,
    "fps": 312.5,
    "vram_peak_mb": 812.4
  },
  "skill_name": "hw_nvidia_local_gpu",
  "status": "success"
}
```

TensorRT note: if `tensorrt` Python package is installed, `supported_export_formats` gains `"tensorrt"` as the first entry.

---

## Downstream Skill Handoff

| Skill | What it reads | How it uses it |
|-------|--------------|----------------|
| `sw-model-training` | `recommended_variant`, `vram_total_gb`, `constraints.compute_backend` | Sets `device=cuda:0`, picks model size, sets batch |
| `sw-model-export` | `constraints.supported_export_formats`, `constraints.tensorrt_version` | Selects `tensorrt` if present, else `onnx` |
| `sw-model-evaluation` | `constraints.compute_backend`, `device_name` | Benchmarks on `cuda:0`, labels results with GPU name |
| `sw-deployment-package` | `hw_target`, `constraints.cuda_version` | Selects correct Docker base image |

---

## Reference Files

- `references/gpu_model_matrix.md` — VRAM requirements per YOLO variant and GPU quick reference
- `references/cuda_setup_guide.md` — CUDA / cuDNN / PyTorch / TensorRT setup (Windows + Linux)

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `No NVIDIA GPU detected` | Install driver, reboot, run `nvidia-smi` |
| `CUDA not available` in PyTorch | Reinstall: `pip install torch --index-url https://download.pytorch.org/whl/cu121` |
| OOM during benchmark | Use `--skip-benchmark` or try a smaller `--model` |
| TensorRT missing | Install from NVIDIA: see `references/cuda_setup_guide.md` |
| Manifest not found | Run `write_hw_manifest.py` before `validate_hw_manifest.py` |
