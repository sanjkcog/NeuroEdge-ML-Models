# /model-select — Recommend an architecture, pretrained backbone, and transfer recipe

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /model-select · Skills: pretrained-and-transfer, model-architectures, time-series-ml`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/pretrained-and-transfer.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/model-architectures.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/time-series-ml.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Arguments

`$ARGUMENTS` — the objective + prepared dataset reference, and optionally the deployment target
(e.g. `--target jetson` / `--target cloud`) and framework (`--pytorch` / `--tf`).

## What this does

Chooses **what model to build** before code is generated (ADR-0014). Spawns `ml-modeler`, which applies
`pretrained-and-transfer` + `model-architectures`. Output is the direct input to `/model-build`.

## Procedure

1. Spawn **`ml-modeler`** with the `dataset-card`/`label-manifest` and target. Instruct it to decide:
   - **Family** — CNN (vision), DNN/MLP (tabular/general — note the gradient-boosted-tree alternative
     for pure tabular), or recommender (name the **ranking metric set**: Recall@K/nDCG/MAP).
   - **Backbone + weights** — timm/torchvision (PyTorch) or TF Hub/Keras (TensorFlow), sized to the
     data **and** the deployment target (edge → MobileNetV3/EfficientNet-Lite; cloud → larger).
   - **Transfer recipe** — freeze depth, discriminative LR + schedule, task-valid augmentation, data
     budget.
   - **Export path** — ONNX / TensorRT / TF SavedModel for the target (ties to `skills/DEPLOY-TARGETS/*`).
2. Present the recommendation; confirm framework (`.py` vs `.tf`) and target with the user if not given.
3. Record it as the `model-select` spec.

## Next step

`/model-build` — generate the `.py`/`.tf` model + training script from this spec.
