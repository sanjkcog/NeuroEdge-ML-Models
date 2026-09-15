# /model-build — Generate the model + training code and assemble the cloud-GPU handoff package

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /model-build · Skills: model-codegen, model-architectures, time-series-ml`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/model-codegen.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/model-architectures.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/time-series-ml.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Arguments

`$ARGUMENTS` — the `model-select` spec (or objective + dataset + framework). Optional
`--pytorch` / `--tf` to force the framework.

## What this does

The `ai-ml` pack's **headline deliverable** (ADR-0014): from the chosen architecture and prepared
dataset, generate a **runnable model and training script** — `.py` (PyTorch) or `.tf`/Keras — and
assemble a **training-ready handoff package** the user carries to a cloud GPU to train. **This command
does NOT run training** and assumes no local GPU. Spawns `ml-modeler` (applies `model-codegen`), then
`ml-eval-reviewer` for a pre-handoff review.

## Procedure

1. Spawn **`ml-modeler`** to generate the handoff package into `<objective-slug>/`:
   ```
   model.py|model_tf.py · train.py|train_tf.py · eval.py · config.yaml ·
   requirements.txt/environment.yml · data/README.md · RUN_ON_GPU.md
   ```
   honoring the framework choice and reusing `skills/SOFTWARE/pytorch/pytorch-patterns.md` idioms.
2. **Verify the invariants** (device-agnostic · seed-reproducible · **leakage-safe** · checkpoint+export
   to the target format · config-driven, no hardcoded hyperparameters/seed · **task-correct metrics**,
   ranking metrics for recommenders).
3. Spawn **`ml-eval-reviewer`** on the generated code. A **leakage** or **wrong-metric** finding is a
   blocker — loop back to `ml-modeler` to fix before handoff.
4. Present the package path + `RUN_ON_GPU.md` summary. **AgentForge stops here** — the user provisions
   a cloud GPU, installs `requirements.txt`, fetches the dataset (id/URL or synthetic recipe), runs
   `train.py`, and collects `checkpoint` + `metrics.json`.

## Boundary (explicit)

Everything up to the training run is in-session: data, architecture, and **model + training code
generation**. Only the **training run is external** (cloud GPU). The returned `metrics.json` later
feeds the phase-2 eval gate; do not run, upload, or provision here.
