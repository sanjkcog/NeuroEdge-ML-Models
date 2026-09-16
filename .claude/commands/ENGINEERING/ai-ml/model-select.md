# /model-select — Recommend an architecture, pretrained backbone, and transfer recipe

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /model-select · Skills: pretrained-and-transfer, model-architectures, time-series-ml, ml-artifact-destination`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/pretrained-and-transfer.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/model-architectures.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/time-series-ml.md`
> - `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`
<!-- neuroedge-assets-patched source-version=8acd6bf -->

## Arguments

`$ARGUMENTS` — the objective + prepared dataset reference, and optionally the deployment target
(e.g. `--target jetson` / `--target cloud`) and framework (`--pytorch` / `--tf`).

`--dest <folder>` — where this command writes its artifacts. If omitted, the command proposes `<ML_ROOT>/<intent>-<modality>` and asks before writing (`agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`).

## What this does

Chooses **what model to build** before code is generated (ADR-0014). Spawns `ml-modeler`, which applies
`pretrained-and-transfer` + `model-architectures`. Output is the direct input to `/model-build`.

## Procedure

0. **Resolve the destination** — apply `ml-artifact-destination`: use `--dest`, or propose `<ML_ROOT>/<intent>-<modality>` and **ask the user to confirm before writing anything**. Call the confirmed absolute path `<dest>` and pass it to every spawned agent. Inside an `/agentforge-ml` run `--dest` is always passed — **do not ask**; the orchestrator already confirmed it (ADR-0022 D-2).
1. Spawn **`ml-modeler`** with the dataset facts and target. Read `<dest>/data/dataset-card.md` and
   `label-manifest.md` if they exist; **if they do not** (the user arrived with their own dataset rather
   than via `/dataset-scout`), ask for the dataset's source, license, size, class balance and split, and
   write them to `<dest>/data/dataset-card.md` before continuing. Instruct it to decide:
   - **Family** — CNN (vision), DNN/MLP (tabular/general — note the gradient-boosted-tree alternative
     for pure tabular), or recommender (name the **ranking metric set**: Recall@K/nDCG/MAP).
   - **Backbone + weights** — timm/torchvision (PyTorch) or TF Hub/Keras (TensorFlow), sized to the
     data **and** the deployment target (edge → MobileNetV3/EfficientNet-Lite; cloud → larger).
   - **Transfer recipe** — freeze depth, discriminative LR + schedule, task-valid augmentation, data
     budget.
   - **Export path** — **ONNX is the deployable format** (`ml-model-package`); TensorRT / QNN / TF are derived from
     it downstream (ties to `agentic-assets/skills/DEPLOY-TARGETS/*`). A family that cannot export to ONNX
     (MiniRocket / ROCKET, some TS foundation models) may be the **baseline** but not the deployable pick.
   - **Baseline** — name the cheap reference the deep model must beat on the same splits and metrics
     (TS: MiniRocket + ridge; tabular: gradient-boosted trees; vision: a linear probe on a frozen backbone).
   - **Runner** — `package` (the generated `train.py` on the user's GPU / VM) or `portal` (the consuming
     platform's own trainer, only when the family is one it supports **and** its split integrity is proven —
     for NeuroEdge time series that is disallowed until Web ADR-0002 V-1/V-2 land; ADR-0022 Q-2).
2. Present the recommendation; confirm framework (`.py` vs `.tf`) and target with the user if not given.
3. Record it as the `model-select` spec at `<dest>/model-select.md`, naming the dataset facts it was
   based on and where they came from.

## Next step

`/model-build` — generate the `.py`/`.tf` model + training script from this spec.
