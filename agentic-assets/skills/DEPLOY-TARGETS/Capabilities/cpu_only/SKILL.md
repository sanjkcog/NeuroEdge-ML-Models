---
name: hw_cpu_only
description: >
  Use this skill when the user wants to run, test, benchmark, or profile AI/ML models
  on CPU-only (no GPU acceleration). Activate when the user mentions "CPU only", "CPU inference",
  "no GPU", "run on CPU", "benchmark on CPU", "CPU performance", "test without GPU",
  "my machine has no GPU", or "inference on CPU". Use this when NVIDIA GPU is not available
  or the user explicitly wants CPU-only execution.
version: 1.0.0
allowed-tools: [Read, Bash, Write, Edit]
---

# hw_cpu_only

Detects, validates, and benchmarks CPU performance for AI/ML workloads without GPU acceleration.
Produces `hw_capture_manifest.json` with the CPU's capability profile so downstream software
skills can configure training, export, and deployment correctly for CPU-only targets.

## When This Skill Applies

- User wants to test or benchmark AI/ML models on CPU without GPU
- User has no NVIDIA GPU and wants to know which YOLO variant runs on CPU
- User wants to benchmark inference speed on CPU
- User wants to confirm CPU readiness before running inference
- User wants to run models on machines without CUDA/GPU support

## When NOT to Use

- NVIDIA GPU is available → use `hw_nvidia_local_gpu`
- Target device is Jetson Nano/Orin → use `hw-jetson-nano` or `hw-jetson-orin`
- Production deployment target is a cloud server → use `sw-deployment-package` directly

---

## What This Skill Does

### Step 1 — CPU Detection
Run `scripts/detect_cpu.py` to discover CPU cores, threads, processor type,
available RAM, and system specifications.

### Step 2 — Dependency Check
Run `scripts/check_dependencies.py` to verify PyTorch (CPU build), Ultralytics,
and other required packages are installed. Reports any missing or misconfigured packages.

### Step 3 — YOLO Model Fit Analysis
Read `references/cpu_model_matrix.md` to determine which YOLO variants
(YOLOv8n/s/m/l/x) run on CPU at acceptable speed with available RAM.

### Step 4 — Inference Benchmark (optional)
Run `scripts/benchmark_cpu.py` to measure:
- FPS and ms/frame for a dummy inference at 640×640
- CPU utilisation % during inference
- Peak RAM used during inference
- Sustained throughput over 100 iterations (warmup + benchmark)

### Step 5 — Write Manifest
Run `scripts/write_hw_manifest.py` to write `hw_capture_manifest.json`
to `data/output/manifests/`. This file is the handoff to all software skills.

---

## Output: hw_capture_manifest.json

Written to: `data/output/manifests/hw_capture_manifest.json`

Key fields set by this skill:

```json
{
  "hw_target": "cpu-only",
  "cpu_name": "Intel Core i7-12700K",
  "cpu_cores": 12,
  "cpu_threads": 20,
  "constraints": {
    "compute_backend": "CPU",
    "supported_export_formats": ["onnx", "pytorch"],
    "max_model_size_mb": 2000,
    "ram_gb": 32,
    "processor_type": "x86_64"
  }
}
```

---

## Reference Files

- `references/cpu_model_matrix.md` — Inference speed and RAM requirements per YOLO variant on CPU
- `references/cpu_setup_guide.md` — CPU-optimized PyTorch installation on Windows/Linux

---

## Handoff to Software Skills

After this skill completes successfully:

- `sw-model-training` reads `hw_capture_manifest.json` to set `device: cpu` and
  select the smallest YOLO variant that trains in reasonable time on CPU
- `sw-model-export` reads `constraints.supported_export_formats` to select
  `onnx` as the export target for CPU inference
- `sw-model-evaluation` reads the manifest to benchmark inference on CPU
- `sw-model-optimization` uses manifest to apply quantization for CPU performance
