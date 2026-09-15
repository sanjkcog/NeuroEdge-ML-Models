# DEPLOY-TARGETS / raspberry-pi

Platform skill for Raspberry Pi 5 and other ARM-based embedded boards.

## Scope

Knowledge for deploying AI/ML models on memory-constrained ARM hardware
via ONNX Runtime and optimized CPU inference.

## Skill Files

| File | Contents |
|------|---------|
| `rpi-deployment.md` | RPi OS setup, GPIO, Camera Stack (libcamera), Docker on ARM |
| `arm-optimization.md` | NEON SIMD, memory-constrained ML, ONNX Runtime ARM delegates |

## Runtime Agent

Planned — `RPiAgent(BaseHardwareAgent)` in `src/agents/hardware/raspberry_pi_agent.py`.

Key differences from `CpuOnlyAgent`:
- ARM architecture detection (aarch64)
- ONNX Runtime as primary backend (not PyTorch)
- Memory constraints: typically 4–8 GB LPDDR
- hw_target: `"raspberry-pi-5"` / `"raspberry-pi-4"`
- export_formats: `["onnx"]` only (no CUDA, no TensorRT)

## Activate When

- User mentions "Raspberry Pi", "RPi", "Pi 5", "Pi 4", "ARM edge", or "embedded ARM"
- Deploying lightweight models (YOLOv8n, MobileNet) to single-board computers
- Building a vision node for a low-power edge device

## See Also

- `skills/DEPLOY-TARGETS/Capabilities/cpu_only/` — CPU-only skill (closest analogue; implemented)
- `src/agents/hardware/base_hardware.py` — `BaseHardwareAgent` ABC
