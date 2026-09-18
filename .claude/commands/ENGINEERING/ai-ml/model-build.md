# /model-build — Generate the model + training code and assemble the cloud-GPU handoff package

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /model-build · Skills: ml-model-package, model-codegen, model-architectures, time-series-ml, ml-artifact-destination`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/ml-model-package.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/model-codegen.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/model-architectures.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/time-series-ml.md`
> - `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`
<!-- neuroedge-assets-patched source-version=4cf4279 -->

## Arguments

`$ARGUMENTS` — the `model-select` spec (or objective + dataset + framework). Optional
`--pytorch` / `--tf` to force the framework.

`--dest <folder>` — where this command writes its artifacts. If omitted, the command proposes `<ML_ROOT>/<intent>-<modality>` and asks before writing (`agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`).

## What this does

The `ai-ml` pack's **headline deliverable** (ADR-0014): from the chosen architecture and prepared
dataset, generate a **runnable model and training script** — `.py` (PyTorch) or `.tf`/Keras — and
assemble a **training-ready handoff package** the user carries to a cloud GPU to train. **This command
does NOT run training** and assumes no local GPU. Spawns `ml-modeler` (applies `model-codegen`), then
`ml-eval-reviewer` for a pre-handoff review.

## Procedure

0. **Resolve the destination** — apply `ml-artifact-destination`: use `--dest`, or propose `<ML_ROOT>/<intent>-<modality>` and **ask the user to confirm before writing anything**. Call the confirmed absolute path `<dest>` and pass it to every spawned agent. Inside an `/agentforge-ml` run `--dest` is always passed — **do not ask**; the orchestrator already confirmed it (ADR-0022 D-2).
1. Spawn **`ml-modeler`** to generate the handoff package into `<dest>/<architecture>/` — one subfolder per
   architecture, e.g. `1DCNN/`. Take the architecture, framing, synthetic use and evaluation protocol from the
   **approved** `<dest>/model_proposed.md` when it exists (inside `/agentforge-ml` it always does, and its gate is
   approved). **Otherwise** take them from `$ARGUMENTS` or ask the user, and record the choice in
   `<dest>/model_proposed.md` as you go (never require a `/model-select` run that did not happen):
   ```
   model.py|model_tf.py · train.py|train_tf.py · eval.py · config.yaml ·
   requirements.txt/environment.yml · data/README.md · RUN_ON_GPU.md
   ```
   honoring the framework choice and reusing `agentic-assets/skills/SOFTWARE/pytorch/pytorch-patterns.md` idioms.
   `train.py` reads the split from `<dest>/data/splits/{train,val}.json` — **never `test.json`** — and ends by
   writing the **model-package** (`ml-model-package`): `model.onnx` at the pinned opset with normalisation and,
   for a scalar head, the `Sigmoid` folded in; `meta.json`; `model_artifact.json` with the `baseline` block;
   `metrics.json` labelled `eval_split: self_reported_val`; optional `calibration/` from the train split.
   **Operating point (Web ADR-0007 T-6):** `meta.json` carries `at_fpr` (the false-alarm rate the use case
   agreed, `performance_targets.accuracy.at_fpr`; default `0.05`) and the `decision_threshold` calibrated on
   the validation split at that rate. `eval.py` reads the operating point **from `meta.json`** — never from
   the Web schema — and records the `fpr` it actually measured at in `metrics.json`. The platform compares
   that `fpr` with the use case's `at_fpr` as **information** (a `not_comparable` row), never as a gate.
   `eval.py --package <pkg> --split <dest>/data/splits/test.json` produces the held-out `metrics.json`.
   **The platform's scaffold is an offline input (ADR-0025 D-1, D-5).** When the platform publishes one
   (NeuroEdge: portal Step 3 · Model Strategy → *Build my own* → Script (.py)), the human downloads it and it is recorded as
   `<dest>/inputs/scaffold/<file>` (`python -m agentforge.src.ml_contract.intake record --kind scaffold`, with a
   human gate). Never fetch it. Use exactly two things from it: its `NEUROEDGE_CONTEXT` (ids, target device, KPIs,
   contract version, carried into `model_artifact.json` extras) and its return helper
   (`neuroedge_return.write_return_package`), installed from a local path or wheel and never fetched during
   training. **Its training body is never used.** Data loading, windowing, split, model, loss, metrics and
   export come from the lock and `model_proposed.md`. Where the scaffold context disagrees with the lock
   (vision defaults on a time-series use case, `at_fpr` only in notes), the lock wins; the intake findings list
   each case.
   **The lock drives the build (NeuroEdge-Web ADR-0008).** Inside `/agentforge-ml`:
   - Read `<dest>/use_case.lock.json` and take from it the channel order, window, stride, rate, head and class
     order. For time series, `train.py` reads **`<dest>/data/contract/`** (already at the lock's rate and units)
     and builds windows inside each unit's split bounds, keyed on the tick column, never by row position.
   - `config.yaml` **refuses** a window that differs from the lock, or that is longer than the smallest
     time-split gap. Scaling is fitted on train only and folded in-graph.
   - The package records `lock_sha256`, `sample_rate_hz`, `stride`, and per-channel `unit`, `definition` and
     **`reduce`**, in `meta.json` and in `model_artifact.json` `extras` (`ml-model-package`). Without `reduce`
     the device point-samples each timestep and upload refuses the package. Nothing here resamples or converts
     units.
2. **Verify the invariants** (device-agnostic · seed-reproducible · **leakage-safe** · checkpoint+export
   to the target format · config-driven, no hardcoded hyperparameters/seed · **task-correct metrics**,
   ranking metrics for recommenders · **package-complete**: every `ml-model-package` field present, threshold
   chosen on validation, baseline emitted with `beats_baseline`, class order identical everywhere).
3. Spawn **`ml-eval-reviewer`** on the generated code. A **leakage** or **wrong-metric** finding is a
   blocker — loop back to `ml-modeler` to fix before handoff.
4. Present the package path + `RUN_ON_GPU.md` summary. **This command stops here** — the user runs `train.py`
   on their GPU (laptop / VM) and collects `<arch>/runs/<run_id>/model-package/`. Inside `/agentforge-ml` the
   orchestrator then waits at `train`, runs `eval.py` on the withheld test split at `eval`, and at `return` builds
   the upload zip for **the human** to upload in the portal (ADR-0025 D-1).

## Boundary (explicit)

Everything up to the training run is in-session: data, architecture, and **model + training code
generation**. Only the **training run is external** (cloud GPU). The returned `metrics.json` later
feeds the phase-2 eval gate; do not run, upload, or provision here.
