# CUDA Setup Guide — Local NVIDIA GPU (Windows & Linux)

Quick reference for setting up CUDA, cuDNN, PyTorch, and TensorRT
for AI/ML workloads on a local RTX GPU.

---

## Version Compatibility Matrix

| PyTorch | CUDA Toolkit | cuDNN | TensorRT | Python |
|---------|-------------|-------|----------|--------|
| 2.3.x | 12.1 / 11.8 | 8.9 | 8.6 | 3.9–3.12 |
| 2.2.x | 12.1 / 11.8 | 8.9 | 8.6 | 3.9–3.11 |
| 2.1.x | 12.1 / 11.8 | 8.7 | 8.5 | 3.8–3.11 |
| 2.0.x | 11.8 / 11.7 | 8.7 | 8.5 | 3.8–3.11 |

> For RTX 40xx: use CUDA 12.1 + PyTorch 2.2 or 2.3. CUDA 11.8 also works.
> For RTX 30xx: CUDA 11.8 and 12.1 both work.

---

## Windows Setup

### Step 1 — NVIDIA Driver

Download and install the latest Game Ready or Studio driver:
- Check current driver: `nvidia-smi` in cmd
- Minimum driver for CUDA 12.1: **530.xx** or later
- RTX 4070 Laptop minimum: driver **525.xx**

### Step 2 — CUDA Toolkit

Install CUDA Toolkit 12.1 (recommended for RTX 40xx):
- Installer type: **exe (local)** for offline install
- Components to install: Development + Runtime (skip VS integration if not needed)
- Default install path: `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1`

Add to system PATH (if installer didn't):
```
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\bin
C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.1\libnvvp
```

Verify: `nvcc --version`

### Step 3 — Python Environment

```powershell
# Using uv (recommended — already in this project)
uv venv --python 3.11
.venv\Scripts\activate

# Or using conda
conda create -n hw_skills python=3.11
conda activate hw_skills
```

### Step 4 — PyTorch with CUDA

```powershell
# Preferred — uv manages .venv and uv.lock automatically
# CUDA 12.1 (RTX 40xx recommended)
uv add "torch==2.5.1+cu121" "torchvision==0.20.1+cu121" `
  --extra-index-url https://download.pytorch.org/whl/cu121 `
  --index-strategy unsafe-best-match

# CUDA 11.8 (RTX 30xx / older 40xx)
uv add "torch==2.3.1+cu118" "torchvision==0.18.1+cu118" `
  --extra-index-url https://download.pytorch.org/whl/cu118 `
  --index-strategy unsafe-best-match

# Backup — if uv add fails (e.g. index not supported)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# Verify
python -c "import torch; print(torch.cuda.is_available(), torch.version.cuda)"
```

### Step 5 — ML Dependencies

```powershell
# Preferred
uv add ultralytics opencv-python numpy Pillow psutil gputil
uv add onnx onnxruntime   # optional, for ONNX export

# Backup
pip install ultralytics opencv-python numpy Pillow psutil gputil
pip install onnx onnxruntime-gpu   # optional, for ONNX export
```

### Step 6 — TensorRT (optional, RTX only)

TensorRT on Windows requires the zip package (not pip):
1. Download TensorRT 8.6 GA for CUDA 12.x from NVIDIA Developer
2. Extract to `C:\TensorRT-8.6.x`
3. Add `C:\TensorRT-8.6.x\lib` to system PATH
4. Install Python wheel:
   ```powershell
   pip install C:\TensorRT-8.6.x\python\tensorrt-8.6.x-cp311-none-win_amd64.whl
   ```
5. Verify: `python -c "import tensorrt; print(tensorrt.__version__)"`

---

## Linux Setup (Ubuntu 22.04 / WSL2)

### Step 1 — Driver (bare metal only; WSL2 uses Windows driver)

```bash
# Check if driver is already installed
nvidia-smi

# Install if missing (Ubuntu)
sudo apt install nvidia-driver-535
sudo reboot
```

### Step 2 — CUDA Toolkit (Linux / WSL2)

```bash
# Add NVIDIA package repo
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt update

# Install CUDA 12.1
sudo apt install cuda-toolkit-12-1

# Add to PATH (~/.bashrc)
echo 'export PATH=/usr/local/cuda-12.1/bin:$PATH' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=/usr/local/cuda-12.1/lib64:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc

# Verify
nvcc --version
```

### Step 3 — Python + PyTorch

```bash
# Preferred
uv add "torch==2.5.1+cu121" "torchvision==0.20.1+cu121" \
  --extra-index-url https://download.pytorch.org/whl/cu121 \
  --index-strategy unsafe-best-match
uv add ultralytics opencv-python numpy Pillow

# Backup
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install ultralytics opencv-python numpy Pillow
```

### Step 4 — TensorRT (Linux)

```bash
sudo apt install tensorrt
# Or via pip (simpler):
pip install tensorrt
```

---

## WSL2 Notes (Windows Subsystem for Linux)

- WSL2 uses the Windows NVIDIA driver directly — do NOT install a separate Linux driver inside WSL2
- CUDA toolkit must still be installed inside WSL2 (the toolkit, not the driver)
- `nvidia-smi` should work immediately in WSL2 if Windows driver is installed
- Performance is ~5–10% lower than bare metal; sufficient for development and testing

---

## Verify Everything Works

```python
import torch
print("PyTorch:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())
print("CUDA version:", torch.version.cuda)
print("cuDNN version:", torch.backends.cudnn.version())
print("GPU name:", torch.cuda.get_device_name(0))
print("VRAM (GB):", round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1))
```

Expected output for RTX 4070 Laptop:
```
PyTorch: 2.3.0+cu121
CUDA available: True
CUDA version: 12.1
cuDNN version: 8902
GPU name: NVIDIA GeForce RTX 4070 Laptop GPU
VRAM (GB): 8.0
```

---

## Common Issues and Fixes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `CUDA not available` after PyTorch install | CPU-only PyTorch wheel | Reinstall with `--index-url .../cu121` |
| `nvcc not found` | CUDA bin not in PATH | Add `C:\...\CUDA\v12.1\bin` to PATH |
| `OOM` during training | Batch size too large | Reduce batch or use `batch=-1` (auto) |
| TensorRT import error on Windows | Wheel not installed | Install `.whl` from TensorRT zip manually |
| `nvidia-smi` works but PyTorch CUDA fails | Driver/CUDA version mismatch | Match CUDA toolkit to driver version |
| Slow training despite GPU detected | `half=False` default | Add `half=True` to training args |

---

## Quick Diagnostic Commands

```bash
# Check GPU
nvidia-smi

# Check CUDA
nvcc --version

# Check PyTorch
python -c "import torch; print(torch.cuda.is_available())"

# Run skill detection script
python .claude/skills/Hardware\ skills/hw_nvidia_local_gpu/scripts/detect_gpu.py

# Run dependency check
python .claude/skills/Hardware\ skills/hw_nvidia_local_gpu/scripts/check_dependencies.py
```
