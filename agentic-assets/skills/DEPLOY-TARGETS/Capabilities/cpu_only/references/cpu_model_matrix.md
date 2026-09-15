# CPU YOLO Model Performance Matrix

This table shows approximate inference latency and whether each YOLO variant is
practical on a modern CPU (Intel i5/i7, AMD Ryzen 5/7, or equivalent).

## Performance by CPU Tier

### Entry-Level CPU (Intel i3, AMD Ryzen 3, 4 cores/threads)

| Model | Latency (ms) | FPS | Practical? | Notes |
|-------|-------------|-----|-----------|-------|
| YOLOv8n | 150-200 | 5-7 | ✓ Yes | Real-time possible, single-threaded |
| YOLOv8s | 400-600 | 1-2 | ✗ No | Too slow for most use cases |
| YOLOv8m+ | >1000 | <1 | ✗ No | Not practical on entry-level |

### Mid-Range CPU (Intel i5/i7, AMD Ryzen 5/7, 6-8 cores)

| Model | Latency (ms) | FPS | Practical? | Notes |
|-------|-------------|-----|-----------|-------|
| YOLOv8n | 50-100 | 10-20 | ✓ Yes | Good real-time performance |
| YOLOv8s | 150-250 | 4-7 | ✓ Maybe | Acceptable for lower frame-rate apps |
| YOLOv8m | 400-700 | 1-3 | ✗ No | Borderline; only for batch processing |
| YOLOv8l+ | >1000 | <1 | ✗ No | Not practical |

### High-Performance CPU (Intel i9, AMD Ryzen 9, 12+ cores)

| Model | Latency (ms) | FPS | Practical? | Notes |
|-------|-------------|-----|-----------|-------|
| YOLOv8n | 30-50 | 20-33 | ✓ Yes | Excellent real-time |
| YOLOv8s | 80-150 | 7-13 | ✓ Yes | Good real-time performance |
| YOLOv8m | 200-400 | 2-5 | ✓ Maybe | Acceptable for lower frame rates |
| YOLOv8l | 600-1000 | 1-2 | ✗ No | Too slow |
| YOLOv8x | >1200 | <1 | ✗ No | Not practical |

---

## Model Sizes

For RAM budgeting (CPU inference at batch=1):

| Model | Size (MB) | Min RAM (GB) | Notes |
|-------|-----------|-------------|-------|
| YOLOv8n | ~3.2 | 4 | Nano — smallest, fastest |
| YOLOv8s | ~11.2 | 8 | Small — balanced |
| YOLOv8m | ~49.7 | 16 | Medium — larger weights |
| YOLOv8l | ~83.7 | 16 | Large — heavy |
| YOLOv8x | ~135.5 | 24 | XLarge — slowest |

---

## Threading Impact

PyTorch CPU uses OpenMP by default. Performance scales with thread count:

```
4 threads:   100% baseline
8 threads:   1.6–1.8× faster
12 threads:  2.0–2.2× faster
16+ threads: 2.2–2.4× faster (diminishing returns)
```

To set PyTorch thread count:
```python
import torch
torch.set_num_threads(12)  # Use 12 CPU threads
```

Or via environment variable:
```bash
export OMP_NUM_THREADS=12
```

---

## Quantization Impact

CPU inference is much faster with quantized models (INT8):

```
FP32 (baseline):    100% latency
INT8 quantized:     30–50% latency (3×–2× speedup)
```

Quantized models have slightly lower accuracy (~1-2%), but are 2–3× faster.

---

## Typical Recommendations

| User has... | Recommend | Notes |
|-------------|-----------|-------|
| Laptop (4 cores) | YOLOv8n only | Use quantization for better FPS |
| Desktop (8 cores) | YOLOv8n or YOLOv8s | YOLOv8s practical with low frame rate |
| Workstation (12+ cores) | YOLOv8s or YOLOv8m | Good balance of speed/accuracy |
| Development only | Any model | Speed is less critical during development |

---

## RAM During Inference

Peak memory usage during inference (batch=1):

| Model | Peak RAM (MB) | Headroom at 4GB | Headroom at 8GB |
|-------|---------------|-----------------|-----------------|
| YOLOv8n | ~500–800 | ✓ Safe | ✓ Safe |
| YOLOv8s | ~1000–1500 | ✓ Safe | ✓ Safe |
| YOLOv8m | ~2000–3000 | ✗ Risky | ✓ Safe |
| YOLOv8l | ~3500–4500 | ✗ No | ✗ Risky |
| YOLOv8x | ~5000–6000 | ✗ No | ✗ No |

Include OS, browser, other apps when planning RAM headroom.

---

## References

- Ultralytics YOLOv8 Docs: https://docs.ultralytics.com
- PyTorch CPU Optimization: https://pytorch.org/docs/stable/notes/cpu_threading_torchscript_inference.html
- OpenMP Threading: https://www.openmp.org/
