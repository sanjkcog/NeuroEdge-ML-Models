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
   - **Loader** (ADR-0028 D-4) — one of `ultralytics` · `torchvision` · `timm` · `transformers` · `tao` · `custom` ·
     `none` (trained from scratch). It says how the base weights are loaded, and it decides which runners are allowed.
   - **Runner** (ADR-0028 D-4) — one of three. Take the proposal from
     `python -m agentforge.src.ml_contract.model_fetch runner --loader <loader> [--path <catalogue path>]`:

     | `runner` | Allowed for | What it means |
     |---|---|---|
     | `portal-finetune` | loader `ultralytics`, `torchvision`, `timm` only | the portal's built-in trainer fine-tunes the fetched weights on the prepared dataset, with its own recipe. M8 generates no code |
     | `portal-package` | any loader a `pip` environment can run | the portal executes `training-package.zip` and changes none of it. A user who wants their own recipe for a YOLO or timm model takes this runner |
     | `offline` | loader `tao`, and any work that needs a vendor toolchain | the user runs the generated driver on their own machine; the result enters the portal as a return package |

     Running a training package on a laptop outside the portal stays possible. It is a fallback, not the default.
     A TAO model needs an NVIDIA GPU machine with the container runtime: say so when you propose it. The `tao`
     template is not built yet (ADR-0028 O-1), so say that too.
   - **Refuse what cannot deploy** (ADR-0028 D-7) — refuse a proposal whose export cannot meet the pinned opset 13,
     or that has no `output_schema` the device runs (`anomaly_score`, `class_logits`, `yolo_boxes_v8`). Say which
     of the two it is. Whether a transformer exports at opset 13 is `unverified` until someone has exported it.
   - **Framing** — for a scalar anomaly head: supervised two-class vs normal-only (one-class /
     reconstruction), with the loss, class weighting, optimiser, schedule, early-stopping metric (on real val,
     per unit) and seed.
   - **Synthetic use** — whether and how the M6 set enters training (cap, the real-only vs real+synthetic
     ablation), or why it does not.
1a. **Answer the portal's recommendation, when there is one (ADR-0028 D-9).** It is an advisory input: a file the
   human exported from the portal and dropped in `inputs/incoming/`. Nothing here calls the portal, and **without
   the file this command runs exactly as before.** `python -m agentforge.src.ml_contract.recommendation show
   --dest <dest>` prints the pick and every rated candidate. The portal knows the device and its catalogue and
   never sees the data. You know the data and the task. So the two can disagree, and these rules reconcile them:
   1. §Alternatives considered **must address the portal's pick**: adopt it, or reject it with the reason.
   2. A candidate marked **`does_not_fit`** (memory, opset, licence: evidence) is **binding**. Do not choose it.
      `recommendation check --dest <dest> --model-id <id>` exits 3 for such a choice. Only the human can override
      it, at the M7 gate, and the override is recorded.
   3. A candidate marked **`unverified`** binds nothing.
   4. You may choose another catalogue entry, or a model outside the catalogue. The second reaches the portal as
      "unlisted".
   5. **The human decides at the M7 gate**, seeing both opinions. When your choice differs from the pick, the
      reason travels in `base-model-card.json` `selection_note` (`/model-fetch --selection-note`).
1b. **Fetch the base model (ADR-0028 D-2, D-3).** When the proposal names a pretrained base, run `/model-fetch
   --dest <dest>` (`--from-recommendation` when you adopt the pick). It pins the revision, hashes the weights, writes
   `model/base/` and gates the licence. Take the licence outcome and the allowed runners from
   `model/base/base-model-card.json` into the proposal. A model trained from scratch (`loader: none`) skips this.
1c. **A claim about another repo is verified there, or marked `unverified` (ADR-0028 D-8).** When the proposal
   rests on what the portal, the device or any other repo does (for example "the portal re-splits", "the device
   runs opset 13"), read the file in **that** repo. Cite the file and the commit you read it at, in the proposal.
   A claim you could not check is written as `unverified`, never as a fact. Do not verify such a claim inside the
   model folder: the answer is not there.
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

`/model-build` — generate the `.py`/`.tf` model + training script from the approved `model_proposed.md`. With
runner `portal-finetune` it generates no code: the handoff is the dataset zip, the weights and
`base-model-card.json`.
