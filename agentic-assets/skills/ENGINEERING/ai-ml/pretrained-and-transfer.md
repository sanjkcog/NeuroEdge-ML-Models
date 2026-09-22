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

## Where the weights come from: `/model-fetch` only (ADR-0028 D-2)

`/model-fetch` is the only downloader. The portal downloads no model, and nothing calls the portal.

| Hub | How it resolves | Revision (always pinned, never `latest` or a branch) | Key |
|---|---|---|---|
| Hugging Face | `snapshot_download` of the named repo | a commit hash, or a tag | `HF_TOKEN`, for gated repos only |
| NVIDIA NGC | `ngc registry model download-version` | the version in `org/team/model:version` | `NGC_API_KEY` |
| GitHub | a named release asset | the release tag | none |
| Ultralytics | a release asset of `ultralytics/assets` | the release tag that holds the file | none |
| torchvision | the weights file from `download.pytorch.org` | the file name; its suffix is the start of its sha256, checked after download | none |
| Qualcomm AI Hub | **the upstream source, never the AI Hub download** | as the upstream hub requires | none |

**The AI Hub upstream rule.** What AI Hub gives you is a compiled inference artifact. It cannot be fine-tuned.
Look the model up in the open-source `qai_hub_models` package, read which upstream repo and weights it loads, and
fetch that. If you did not read it there, write the source as `unverified`.

A key is read from the environment. Its value is never written to a file or a log; only the variable's name is.

## Loader families and runners (ADR-0028 D-4)

`loader.json` names how the weights are loaded. The loader decides which runners are allowed.

| `loader` | Typical source | Runners allowed |
|---|---|---|
| `ultralytics` | an Ultralytics `.pt` | `portal-finetune` · `portal-package` · `offline` |
| `torchvision` | a torchvision model name and its weights file | `portal-finetune` · `portal-package` · `offline` |
| `timm` | a timm model name | `portal-finetune` · `portal-package` · `offline` |
| `transformers` | a Hugging Face snapshot folder | `portal-package` · `offline` (stored M8 template: `transformers-classification`) |
| `tao` | an NGC TAO model | `offline` only. The template is not built yet (ADR-0028 O-1) |
| `custom` | anything else a `pip` environment can load | `portal-package` · `offline` |
| `none` | trained from scratch, nothing to fetch | `portal-package` · `offline` |

## Licence (ADR-0028 D-3)

Read the licence at the source and record where you read it. **Never guess.** Permissive with evidence: approved.
AGPL-3.0 (every Ultralytics model): approved for internal and demo use without a gate (owner's MVP decision,
2026-09-21); `distribution: internal_only` travels as information and nothing refuses on it. Non-commercial,
unverifiable, missing, or per-model terms (NGC, AI Hub): the hard gate `model/base-model-card.md` opens at M7.

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
- Do not download weights outside `/model-fetch`, and do not fetch `latest` or a branch.
- Do not evaluate the pretrained model as it is and call that a baseline: its classes differ from the use case's,
  so it is beaten trivially and proves nothing (ADR-0028 D-11).
