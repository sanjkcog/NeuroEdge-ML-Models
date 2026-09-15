# DEPLOY-TARGETS / nvidia-jetson

Platform skill for Nvidia Jetson edge devices (Orin, Xavier, Nano).

## Scope

Knowledge for deploying and optimizing AI/ML models on Jetson via JetPack SDK and TensorRT.

## Skill Files

| File | Contents |
|------|---------|
| `jetson-deployment.md` | JetPack setup, container runtime, DeepStream |
| `tensorrt-optimization.md` | TRT model conversion, INT8 calibration, engine serialization |
| `cuda-patterns.md` | CUDA kernel patterns, unified memory, stream parallelism |

## Runtime Agent

Planned — `JetsonAgent(BaseHardwareAgent)` in `src/agents/hardware/nvidia_jetson_agent.py`.

Use pattern mirrors the implemented `NvidiaGpuAgent`:
- `detect()` — query Jetson model, JetPack version, GPU memory
- `check_deps()` — TensorRT, onnxruntime-gpu, jetson-stats
- `benchmark()` — TRT-accelerated YOLO inference (FPS, latency, power)
- `build_manifest()` — hw_target: `"jetson-orin"` / `"jetson-nano"` / `"jetson-xavier"`

## Activate When

- User mentions "Jetson", "Orin", "Xavier", "JetPack", "DeepStream", or "edge GPU"
- Deploying YOLO or transformer models to Nvidia embedded hardware
- Optimizing for INT8 / FP16 inference via TensorRT

## See Also

- `skills/DEPLOY-TARGETS/Capabilities/nvidia_gpu/` — local GPU skill (analogous; implemented)
- `src/agents/hardware/base_hardware.py` — `BaseHardwareAgent` ABC
