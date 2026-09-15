---
name: pretrained-and-transfer
description: Choose a pretrained backbone and a transfer-learning recipe instead of training from scratch — timm, torchvision, TF Hub / Keras applications, Hugging Face Hub, NVIDIA TAO, ONNX Model Zoo — matched to the task and the deployment target. Use during model selection, before generating model code.
origin: NeuroEdge AgentForge
---

# Pretrained Models & Transfer Learning

Almost no product should train a vision/DL model from scratch. Pick a **pretrained backbone** and
**fine-tune** it — far less data, far less compute, better accuracy. This skill picks the backbone and
the transfer recipe; [`model-codegen`](model-codegen.md) then emits the actual code.

## When to Activate

- `/model-select` is invoked
- After the dataset is known, before `/model-build`
- The deployment target (edge vs cloud) constrains the model size

## Model sources

| Source | Framework | Best for |
|---|---|---|
| **timm** (PyTorch Image Models) | PyTorch | huge CNN/ViT zoo — ResNet, EfficientNet(V2), ConvNeXt, ViT — one API, pretrained weights |
| **torchvision.models** | PyTorch | canonical, well-documented, detection/segmentation heads |
| **Keras Applications / TF Hub** | TensorFlow | when the objective mandates a `.tf`/Keras deliverable |
| **Hugging Face Hub** | both | `config.json` + weights, timm-compatible, model cards |
| **NVIDIA TAO Toolkit** | export→TensorRT | fine-tune NVIDIA pretrained nets and export for edge (Jetson) inference |
| **ONNX Model Zoo** | framework-neutral | when you need an ONNX starting point for cross-EP deployment |

## Choosing a backbone (the trade-off)

Match three things: **task** (classification / detection / segmentation head), **data size** (less
data ⇒ lean harder on a strong pretrained backbone, freeze more layers), and **deployment target**:

- **Edge / on-device** (Jetson, Qualcomm, Raspberry Pi — see `skills/DEPLOY-TARGETS/*`) ⇒ MobileNetV3,
  EfficientNet-Lite, small ConvNeXt; plan the export (TensorRT / QNN / ONNX) at selection time.
- **Cloud inference** ⇒ larger EfficientNetV2 / ConvNeXt / ViT are fine.

## Transfer-learning recipe (what `/model-select` outputs)

1. **Freeze vs fine-tune** — small data: freeze the backbone, train the head; more data: unfreeze the
   top blocks; lots of data: full fine-tune with a low LR.
2. **Learning-rate strategy** — discriminative LRs (lower for backbone, higher for head), warmup,
   cosine decay.
3. **Augmentation** — task-appropriate (flips/crops/color for natural images; be careful with
   defect orientation).
4. **Data budget** — a rough samples-per-class expectation given the freeze depth.

## Output

A `model-select` recommendation: chosen framework (`.py`/`.tf`), backbone + weights id, head, the
freeze/LR/augmentation recipe, and the deployment-target export path. This is the direct input to
[`model-codegen`](model-codegen.md) / `/model-build`.

## Do NOT

- Do not recommend a cloud-scale backbone for an edge target — check the DEPLOY-TARGETS constraints
  first.
- Do not pick weights whose license/usage terms conflict with the product (same license discipline as
  dataset sourcing).
