# DEPLOY-TARGETS / qualcomm

Platform skill for Qualcomm AI platforms (AIM01, RB3 Gen 2, Snapdragon Edge AI).

## Scope

Knowledge for exporting and running models on Qualcomm's HTP (Hexagon Tensor Processor)
via the SNPE 2.x and QNN SDK.

## Skill Files

| File | Contents |
|------|---------|
| `qualcomm-ai-hub.md` | AI Hub model export, profiling, and benchmarking |
| `snpe-patterns.md` | SNPE runtime, DLC model format, quantization |
| `qnn-deployment.md` | QNN SDK, HTP delegate, OnnxRuntime-QNN integration |

## Runtime Agent

Stub — `QualcommEdgeAgent(BaseHardwareAgent)` in `src/agents/hardware/qualcomm_edge/qualcomm_agent.py`.

Implement in order:
1. `detect()` — SoC model, HTP version, LPDDR capacity
2. `check_deps()` — onnxruntime-qnn, qnn-onnx-provider, numpy, Pillow
3. `benchmark()` — HTP NPU inference via QNN delegate
4. `build_manifest()` — hw_target: `"qualcomm-aim01"`, compute_backend: `"NPU"`, export_formats: `["qnn", "onnx"]`

Source scripts can be adapted from any Qualcomm hardware skills library that implements
the SNPE/QNN pattern — see `src/agents/hardware/qualcomm_edge/qualcomm_agent.py` for the
`NotImplementedError` stubs that mark what needs to be implemented.

## Activate When

- User mentions "Qualcomm", "AIM01", "Snapdragon", "HTP", "QNN", "SNPE", or "NPU"
- Deploying models to Windows on ARM or Qualcomm-based Linux edge devices
- Comparing CPU vs NPU inference performance

## See Also

- `src/agents/hardware/qualcomm_edge/qualcomm_agent.py` — stub agent class
- `src/agents/hardware/base_hardware.py` — `BaseHardwareAgent` ABC
