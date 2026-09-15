---
name: hw_nvidia_local_gpu
description: >
  Use this skill when the user wants to run, test, benchmark, or profile AI/ML models
  on a local NVIDIA GPU (RTX 4070, RTX 4080, RTX 3090, RTX 3080, or any CUDA-capable
  laptop or desktop GPU). Activate when the user mentions "local GPU", "my laptop GPU",
  "RTX 4070", "RTX GPU", "CUDA local", "test on my machine", "run inference locally",
  "benchmark on GPU", "local training", "train on my GPU", or "profile GPU performance".
  Always use this skill before sw-model-training or sw-model-export when the target
  device is the user's own Windows or Linux workstation with an NVIDIA card.
version: 1.0.0
allowed-tools: [Read, Bash, Write, Edit]
---

# hw_nvidia_local_gpu

Detects, validates, and benchmarks a local NVIDIA GPU for AI/ML workloads.
Produces `hw_capture_manifest.json` with the GPU's full capability profile
so downstream software skills can configure training, export, and deployment correctly.

## When This Skill Applies

- User wants to test or benchmark their local NVIDIA GPU (RTX 4070 or similar)
- User is about to train a YOLO model and wants to confirm GPU readiness
- User wants to know which YOLO variant fits their GPU memory
- User wants to benchmark inference speed on their local machine
- User wants to run a quick sanity-check before a long training run

## When NOT to Use

- Target device is Jetson Nano/Orin → use `hw-jetson-nano` or `hw-jetson-orin`
- No GPU present and user wants CPU-only inference → skip hardware skills entirely
- Production deployment target is a cloud server → use `sw-deployment-package` directly

---

## What This Skill Does

### Step 1 — GPU Detection
Run `scripts/detect_gpu.py` to discover all NVIDIA GPUs, CUDA version,
driver version, cuDNN, and available VRAM per device.

### Step 2 — Dependency Check
Run `scripts/check_dependencies.py` to verify PyTorch, CUDA toolkit,
cuDNN, and Ultralytics are installed and CUDA-enabled. Reports any
missing or misconfigured packages.

### Step 3 — YOLO Model Fit Analysis
Read `references/gpu_model_matrix.md` to determine which YOLO variants
(YOLOv8n/s/m/l/x) fit within available VRAM at the desired batch size.

### Step 4 — Inference Benchmark (optional)
Run `scripts/benchmark_gpu.py` to measure:
- FPS and ms/frame for a dummy inference at 640×640
- GPU utilisation % during inference
- Peak VRAM used during inference
- Sustained throughput over 500 iterations (warmup + benchmark)

### Step 5 — Write Manifest
Run `scripts/write_hw_manifest.py` to write `hw_capture_manifest.json`
to `data/output/manifests/`. This file is the handoff to all software skills.

---

## Output: hw_capture_manifest.json

Written to: `data/output/manifests/hw_capture_manifest.json`

Key fields set by this skill:

```json
{
  "hw_target": "nvidia-local-gpu",
  "gpu_name": "NVIDIA GeForce RTX 4070 Laptop GPU",
  "constraints": {
    "compute_backend": "CUDA",
    "supported_export_formats": ["tensorrt", "onnx", "pytorch"],
    "max_model_size_mb": 8000,
    "vram_gb": 8,
    "cuda_version": "12.1",
    "tensorrt_version": "8.6"
  }
}
```

---

## Reference Files

- `references/gpu_model_matrix.md` — VRAM requirements per YOLO variant and batch size
- `references/cuda_setup_guide.md` — CUDA, cuDNN, PyTorch installation on Windows/Linux

---

## Handoff to Software Skills

After this skill completes successfully:

- `sw-model-training` reads `hw_capture_manifest.json` to set `device: cuda:0` and
  select the largest YOLO variant that fits in VRAM
- `sw-model-export` reads `constraints.supported_export_formats` to select
  `tensorrt` (if TensorRT is installed) or `onnx` as the export target
- `sw-model-evaluation` reads the manifest to benchmark inference on `cuda:0`
