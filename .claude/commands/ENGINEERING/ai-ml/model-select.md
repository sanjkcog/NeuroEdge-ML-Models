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
   - **The contract is not a choice here.** Inside `/agentforge-ml`, read `<dest>/use_case.lock.json`
     (NeuroEdge-Web ADR-0008). Its channels and order, rate, window, stride, classes and head are fixed inputs
     to the recommendation, never outputs of it. An architecture that cannot honour the lock's static window
     and head is not a candidate. If the evidence says the window or rate is wrong, stop and send the change
     back to the use case (re-lock), rather than choosing a different window here.
   - **Runner** — `package` (the generated `train.py` on the user's GPU / VM) or `portal` (the consuming
     platform's own trainer, only when the family is one it supports **and** its split integrity is proven —
     for NeuroEdge time series that is disallowed until Web ADR-0002 V-1/V-2 land; ADR-0022 Q-2).
   - **Framing** — for a scalar anomaly head: supervised two-class vs normal-only (one-class /
     reconstruction), with the loss, class weighting, optimiser, schedule, early-stopping metric (on real val,
     per unit) and seed.
   - **Synthetic use** — whether and how the M6 set enters training (cap, the real-only vs real+synthetic
     ablation), or why it does not.
2. **Write the proposal to `<dest>/model_proposed.md`** (ADR-0025 D-3). This is the page the human approves, so
   it explains as well as decides. It must have a heading for each of: **Architecture** (a layer table with
   channels, kernel, dilation, receptive field and parameter count, and **the reasoning for each size choice**),
   **Framing**, **Synthetic** data use, **Augmentation**, **Baseline**, **Evaluation** protocol, **Export**,
   **Runner**, and **Alternatives considered** (at least one real alternative per major choice, and why it lost).
   Name the dataset facts it is based on and the file each came from. `review model` refuses a proposal missing
   any of these headings.
3. **A re-run with an alternative** (the human asked for changes at the M7 gate): the orchestrator has archived
   the previous proposal to `<dest>/model_proposed/v<N>.md` and passes the human's reason. Treat that reason as a
   **binding constraint**. Read the archived versions so the new proposal says what changed from each and why,
   and does not silently repeat a rejected choice.
4. Present the proposal; confirm framework (`.py` vs `.tf`) and target with the user if not given. Inside
   `/agentforge-ml` the orchestrator then runs `python -m agentforge.src.ml_contract.review model --dest <dest>`
   and asks the gate. Nothing moves to `/model-build` until it is approved.

## Next step

`/model-build` — generate the `.py`/`.tf` model + training script from the approved `model_proposed.md`.
