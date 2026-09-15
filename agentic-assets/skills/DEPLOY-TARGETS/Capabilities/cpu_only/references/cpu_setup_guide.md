# CPU-Only PyTorch & Ultralytics Setup Guide

Complete setup instructions for running AI/ML models on CPU without GPU/CUDA.

---

## Quick Start (Recommended)

Use `uv` (fast Python package manager):

```bash
# CPU-only PyTorch + Ultralytics
uv add "torch==2.5.1+cpu" ultralytics opencv-python --index-strategy unsafe-best-match

# Verify CPU build
python -c "import torch; print(f'CPU available: {torch.backends.cpu.is_available()}')"
python -c "from ultralytics import YOLO; print('Ultralytics ready')"
```

---

## Detailed Setup by OS

### Windows 10/11

#### 1. Install Python 3.11+

Download from https://www.python.org/downloads/ (or via `choco install python3.11`)

Verify:
```bash
python --version  # Should output 3.11.x or later
```

#### 2. Create Virtual Environment (recommended)

```bash
python -m venv venv
venv\Scripts\activate
```

#### 3. Install PyTorch (CPU-only)

```bash
uv add "torch==2.5.1+cpu" --index-strategy unsafe-best-match
```

Or with pip:
```bash
pip install torch==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu
```

Verify PyTorch is CPU-only:
```bash
python -c "import torch; print(torch.device('cpu')); print(f'CUDA: {torch.cuda.is_available()}')"
```

Expected output:
```
cpu
CUDA: False
```

#### 4. Install Ultralytics and Dependencies

```bash
uv add ultralytics opencv-python pillow numpy
```

Or with pip:
```bash
pip install ultralytics opencv-python pillow numpy
```

#### 5. Test Inference

```bash
yolo detect predict model=yolov8n.pt source=https://ultralytics.com/images/bus.jpg device=cpu
```

Expected: Image saved with detections (takes 10-30 seconds on typical CPU).

---

### macOS (Intel/Apple Silicon)

#### 1. Install Python 3.11+

Via Homebrew:
```bash
brew install python@3.11
```

Or download from https://www.python.org/downloads/

#### 2. Create Virtual Environment

```bash
python3.11 -m venv venv
source venv/bin/activate
```

#### 3. Install PyTorch (CPU-only)

**Intel Mac:**
```bash
uv add "torch==2.5.1+cpu" --index-strategy unsafe-best-match
```

**Apple Silicon (M1/M2/M3):**
```bash
uv add torch torchvision torchaudio --index-strategy unsafe-best-match
```

Note: Apple Silicon PyTorch defaults to CPU (Metal acceleration is GPU, not CUDA).

#### 4. Install Ultralytics and Dependencies

```bash
uv add ultralytics opencv-python pillow numpy
```

#### 5. Test Inference

```bash
yolo detect predict model=yolov8n.pt source=https://ultralytics.com/images/bus.jpg device=cpu
```

---

### Linux (Ubuntu 20.04+, Fedora, etc.)

#### 1. Install Python 3.11+

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv
```

**Fedora/RHEL:**
```bash
sudo dnf install -y python3.11 python3.11-devel
```

#### 2. Create Virtual Environment

```bash
python3.11 -m venv venv
source venv/bin/activate
```

#### 3. Install PyTorch (CPU-only)

```bash
uv add "torch==2.5.1+cpu" --index-strategy unsafe-best-match
```

Or with pip:
```bash
pip install torch==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu
```

#### 4. Install Ultralytics and Dependencies

```bash
uv add ultralytics opencv-python pillow numpy
```

**Note for some Linux distros:** OpenCV may require additional system libraries:
```bash
sudo apt-get install -y libgl1-mesa-glx libsm6 libxext6 libxrender-dev
```

#### 5. Test Inference

```bash
yolo detect predict model=yolov8n.pt source=https://ultralytics.com/images/bus.jpg device=cpu
```

---

## Verify Installation

Run this script to check all components:

```python
import sys
import platform

print(f"Python: {sys.version}")
print(f"Platform: {platform.platform()}")

import torch
print(f"PyTorch: {torch.__version__}")
print(f"CPU available: {torch.backends.cpu.is_available()}")
print(f"CUDA available: {torch.cuda.is_available()}")

from ultralytics import YOLO
print(f"Ultralytics: ready")

import cv2
print(f"OpenCV: {cv2.__version__}")

import numpy as np
print(f"NumPy: {np.__version__}")

print("\n✓ All CPU components ready!")
```

Save as `verify_cpu_setup.py` and run:
```bash
python verify_cpu_setup.py
```

Expected output:
```
Python: 3.11.x ...
Platform: Linux-5.15.0-x86_64 (or Windows-10, etc.)
PyTorch: 2.5.1+cpu
CPU available: True
CUDA available: False
Ultralytics: ready
OpenCV: 4.9.0
NumPy: 1.26.4

✓ All CPU components ready!
```

---

## Performance Tuning

### Optimize PyTorch for CPU

```python
import torch
import os

# Use all available CPU threads
torch.set_num_threads(os.cpu_count())

# Optional: disable unused features
torch.set_grad_enabled(False)  # For inference only
torch.backends.cudnn.enabled = False

# Run inference
model = YOLO('yolov8n.pt')
results = model(source, device='cpu')
```

### Enable OpenMP Threading

Set before running Python:

```bash
# Linux/macOS
export OMP_NUM_THREADS=8
export MKL_NUM_THREADS=8

# Windows (PowerShell)
$env:OMP_NUM_THREADS = 8
$env:MKL_NUM_THREADS = 8
```

### Quantize Model for Speed

```python
from ultralytics import YOLO

model = YOLO('yolov8n.pt')

# Export as INT8 quantized ONNX for 2–3× speed boost
model.export(format='onnx', int8=True, device='cpu')

# Run quantized model (faster inference)
results = model('image.jpg', device='cpu')
```

---

## Troubleshooting

### "PyTorch not found" or "ModuleNotFoundError: torch"

```bash
# Check installation
pip show torch

# If missing, reinstall
uv add "torch==2.5.1+cpu"

# Or with pip
pip install torch==2.5.1+cpu
```

### "CUDA is available" when it shouldn't be

You installed the CUDA build instead of CPU-only. Uninstall and reinstall:

```bash
pip uninstall torch torchvision torchaudio
uv add "torch==2.5.1+cpu" --index-strategy unsafe-best-match
```

Verify:
```bash
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"  # Should print False
```

### "ImportError: No module named 'cv2'"

Install OpenCV:

```bash
uv add opencv-python
```

### "YOLO model not found"

The model downloads on first use. Ensure internet connection, or download manually:

```bash
yolo detect predict model=yolov8n.pt source=image.jpg device=cpu --download
```

### Very slow inference on multi-core CPU

Ensure PyTorch uses all cores:

```python
import torch
import os

num_threads = os.cpu_count()
torch.set_num_threads(num_threads)
print(f"Using {num_threads} threads")
```

Also check:
- Are other apps consuming CPU?
- Is your model using GPU (check `device='cpu'`)?
- For batch inference, use `torch.inference_mode()` context manager

---

## Differences from CUDA/GPU Setup

| Aspect | CPU | GPU (CUDA) |
|--------|-----|-----------|
| PyTorch variant | `+cpu` | `+cu121`, `+cu118` |
| Inference latency | High (50–1000ms) | Low (2–10ms) |
| Training speed | Slow | Fast (5–100×) |
| Memory used | Lower (often <1GB) | Higher (4–24GB) |
| Model quantization | Recommended | Optional |
| Deployment complexity | Low | High |
| Cost | None | High (GPU) |

For real-time inference, CPU is only practical with YOLOv8n (nano) or quantized models.
For training, GPU is strongly recommended (CPU training is impractical for large datasets).

---

## Next Steps

After setup is verified:

1. Run the skill: `/hw_cpu_only` to generate `hw_capture_manifest.json`
2. For inference: Use `sw-model-evaluation` to benchmark your CPU
3. For training: Consider using a GPU server (even CPU inference still works)
4. For deployment: Export as ONNX for maximum compatibility
