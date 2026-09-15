# DEPLOY-TARGETS / cloud-aws

Platform skill for AWS cloud AI infrastructure (SageMaker, IoT Greengrass, EC2 GPU).

## Scope

Knowledge for training, serving, and edge-deploying models via AWS managed services.

## Skill Files

| File | Contents |
|------|---------|
| `sagemaker-patterns.md` | Training jobs, inference endpoints, model registry |
| `aws-iot-greengrass.md` | Edge deployment via Greengrass v2 components |
| `ec2-deployment.md` | GPU instance setup (p3, g4dn, g5), AMI patterns, spot instances |

## Runtime Agent

Planned — `CloudAgent(BaseHardwareAgent)` in `src/agents/hardware/cloud_infra_agent.py`.

Key fields in manifest:
- hw_target: `"aws-sagemaker"` / `"aws-greengrass"` / `"aws-ec2-gpu"`
- compute_backend: `"CUDA"` (EC2 GPU) or `"CPU"` (Greengrass edge)
- export_formats: `["pytorch", "onnx", "sagemaker-neo"]`

## Activate When

- User mentions "SageMaker", "Greengrass", "EC2", "AWS", or "cloud training"
- Deploying from a local or edge device to AWS cloud for scale-out
- Using Greengrass to push updated models to edge fleets

## See Also

- `skills/DEPLOY-TARGETS/cloud-azure/` — Azure IoT Edge + ML Studio equivalent
- `skills/DEPLOY-TARGETS/cloud-gcp/` — Vertex AI + Coral TPU equivalent
- `src/agents/hardware/base_hardware.py` — `BaseHardwareAgent` ABC
