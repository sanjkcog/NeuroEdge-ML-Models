# GPU Model Fit Matrix

VRAM requirements for YOLO models at 640×640 input, single image (batch=1), fp16 precision.
Used by `write_hw_manifest.py` to populate `yolo_variant_fit` and `recommended_variant`.

---

## YOLO Variant Requirements

| Model | Params (M) | VRAM min (GB) | VRAM comfortable (GB) | Recommended max batch (8 GB GPU) |
|-------|-----------|--------------|----------------------|----------------------------------|
| YOLOv8n | 3.2 | 1.5 | 2 | 32 |
| YOLOv8s | 11.2 | 2.5 | 3 | 16 |
| YOLOv8m | 25.9 | 4.0 | 5 | 8 |
| YOLOv8l | 43.7 | 6.5 | 8 | 4 |
| YOLOv8x | 68.2 | 10.0 | 12 | 2 |
| YOLOv10n | 2.3 | 1.5 | 2 | 32 |
| YOLOv10s | 7.2 | 2.0 | 3 | 16 |
| YOLOv10m | 15.4 | 3.5 | 5 | 8 |
| YOLOv10l | 24.4 | 5.5 | 7 | 4 |
| YOLOv10x | 29.5 | 7.0 | 9 | 4 |
| YOLOv11n | 2.6 | 1.5 | 2 | 32 |
| YOLOv11s | 9.4 | 2.5 | 3 | 16 |
| YOLOv11m | 20.1 | 3.5 | 5 | 8 |
| YOLOv11l | 25.3 | 5.5 | 7 | 4 |
| YOLOv11x | 56.9 | 9.0 | 12 | 2 |

> "VRAM min" = minimum to run inference, may OOM during training at larger batches.
> "VRAM comfortable" = stable training at batch=8 with image augmentation headroom.

---

## Common GPU Quick Reference

| GPU | VRAM | Largest comfortable YOLO | Notes |
|-----|------|--------------------------|-------|
| RTX 4090 | 24 GB | YOLOv8x / YOLOv11x (batch 8+) | Best for research |
| RTX 4080 | 16 GB | YOLOv8x (batch 4), YOLOv8l (batch 8) | Excellent for training |
| RTX 4070 Ti | 12 GB | YOLOv8l (batch 8), YOLOv8x (batch 2) | Strong all-rounder |
| RTX 4070 Laptop | 8 GB | YOLOv8l (batch 4), YOLOv8m (batch 8) | Good for local dev |
| RTX 4060 | 8 GB | YOLOv8l (batch 4), YOLOv8m (batch 8) | Budget option |
| RTX 3090 | 24 GB | YOLOv8x (batch 8+) | Equivalent to 4080 |
| RTX 3080 | 10 GB | YOLOv8l (batch 4) | Good training GPU |
| RTX 3070 | 8 GB | YOLOv8l (batch 4) | Same as 4060/4070 Laptop |
| RTX 3060 | 12 GB | YOLOv8l (batch 8) | VRAM-rich mid-range |
| GTX 1660 | 6 GB | YOLOv8m (batch 4) | Older; fp16 limited |
| T4 (cloud) | 16 GB | YOLOv8x (batch 4) | Colab / cloud training |

---

## Batch Size vs Training Time (RTX 4070 Laptop, 8 GB, YOLOv8m, 640px)

| Batch size | VRAM used | Time per epoch (1000 imgs) | Notes |
|-----------|-----------|---------------------------|-------|
| 1 | ~2.5 GB | ~4 min | Safe but slow |
| 4 | ~4.0 GB | ~2 min | Recommended minimum |
| 8 | ~6.5 GB | ~80 sec | Good default |
| 16 | ~OOM | — | OOM on 8 GB for YOLOv8m |

Use `--batch -1` in Ultralytics to auto-select the largest safe batch size.

---

## Inference Speed Reference (fp16, batch=1, 640×640)

| GPU | YOLOv8n (ms) | YOLOv8s (ms) | YOLOv8m (ms) | YOLOv8l (ms) |
|-----|-------------|-------------|-------------|-------------|
| RTX 4090 | 1.8 | 2.5 | 4.1 | 6.3 |
| RTX 4080 | 2.1 | 3.0 | 5.0 | 7.8 |
| RTX 4070 (desktop) | 2.5 | 3.5 | 6.2 | 10.1 |
| RTX 4070 Laptop | 3.2 | 4.8 | 8.5 | 14.2 |
| RTX 3080 | 3.0 | 4.5 | 7.5 | 12.0 |
| RTX 3060 | 4.5 | 6.5 | 11.0 | 18.5 |

> Values are approximate. Run `benchmark_gpu.py` for exact numbers on your machine.

---

## Training Recommendations by GPU

### RTX 4070 Laptop (8 GB VRAM) — Recommended settings

```bash
# Safe default
yolo train model=yolov8m data=dataset.yaml epochs=100 batch=8 imgsz=640 device=0

# Max performance (auto batch)
yolo train model=yolov8m data=dataset.yaml epochs=100 batch=-1 imgsz=640 device=0

# Large model, reduced batch
yolo train model=yolov8l data=dataset.yaml epochs=100 batch=4 imgsz=640 device=0
```

### RTX 4090 / RTX 3090 (24 GB VRAM) — Recommended settings

```bash
yolo train model=yolov8x data=dataset.yaml epochs=100 batch=32 imgsz=640 device=0
```

---

## Mixed Precision Notes

All RTX 30xx and 40xx GPUs support fp16 (Tensor Cores). Always enable:

```python
# In Ultralytics training
yolo train ... half=True   # fp16 training — halves VRAM, same accuracy
```

For TensorRT export:
- fp16: ~2× speed over fp32, negligible accuracy loss
- int8: ~4× speed over fp32, requires calibration dataset, small accuracy loss
