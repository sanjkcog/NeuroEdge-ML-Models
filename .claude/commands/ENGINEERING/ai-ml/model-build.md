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

## The runner decides what is built (ADR-0028 D-1, D-4)

Read §Runner in the approved `model_proposed.md` first.

- **`portal-package`** or **`offline`** → the procedure below.
- **`portal-finetune`** → **generate no code.** The portal's built-in trainer owns the recipe. Spawn
  `ml-eval-reviewer` on the **data and the split only**, then stop. The handoff is `data/portal_upload.zip`, the
  weights in `model/base/weights/` and `model/base/base-model-card.json`. There is no baseline on this path, and
  M10 records `baseline: not_applicable` (ADR-0028 D-11).

**A stored template (ADR-0028 D-6).** For loader `transformers` with a classification head, do not write the code
from nothing:

```
python -m agentforge.src.ml_contract.template write --dest <dest> --arch <Arch> --template transformers-classification
```

It needs the base model `/model-fetch` wrote, and a multiclass vision lock. It writes `train.py` (fine-tune over
the local snapshot with no network, a linear-probe baseline, ONNX export through `optimum` at opset 13 with the
normalisation in the graph, `output_schema: class_logits`), `eval.py`, `tf_common.py`, `config.yaml` filled from the
lock, pinned `requirements.txt` and `RUN_ON_GPU.md`. `ml-modeler` then adapts the recipe in `config.yaml`. It does
not change the `contract` block. **`RUN_ON_GPU.md` lists what is unverified** (the scripts have never been run;
a transformer may not export at opset 13). Repeat that to the human. Do not soften it. The `tao` template is not
built yet (ADR-0028 O-1).

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
   **The platform's scaffold is an optional offline input (ADR-0025 D-1, D-5; ADR-0027 D-3).** When the platform
   publishes one (NeuroEdge: portal Step 3 · Model Strategy → *Build my own* → Script (.py)) and the human dropped
   it, it is recorded as `<dest>/inputs/scaffold/<file>` (`python -m agentforge.src.ml_contract.intake record
   --kind scaffold`). It has no gate, and its absence never stops the build. Never fetch it.
   `intake.usable_scaffold(<dest>)` returns the file to use, or `None` when there is none **or** when it
   disagrees with the lock (it was generated from another use case): then build from the default template below
   and say so. Use exactly two things from a usable scaffold: its `NEUROEDGE_CONTEXT` (ids, target device, KPIs,
   contract version, carried into `model_artifact.json` extras) and its return helper
   (`neuroedge_return.write_return_package`), installed from a local path or wheel and never fetched during
   training. **Its training body is never used.** Data loading, windowing, split, model, loss, metrics and
   export come from the lock and `model_proposed.md`. Where the scaffold context disagrees with the lock
   (vision defaults on a time-series use case, `at_fpr` only in notes), the lock wins; the intake findings list
   each case.
   **No usable scaffold → the default template (ADR-0027 D-3).** Nothing is asked and nothing is recorded. `train.py` writes the whole
   model-package itself, exactly as `ml-model-package` specifies: `model.onnx`, `meta.json`, `metrics.json`, and
   `model_artifact.json` in the consuming platform's `ModelArtifact` schema (`use_case_id`, `model_name`,
   `framework`, `format`, `uri`, `metrics`, `metrics_type`, `class_names`, `input_shape`, `created_at`, `extras`),
   with the **`baseline` block `{name, metrics, beats_baseline}` in `extras`**, which is as mandatory here as
   on the scaffold path.
   When `neuroedge_return` is installed locally, it also runs `neuroedge_return.validate_package` on the result.
   Both paths produce the same folder.
   **Training KPIs in MLflow, both paths.** `train.py` logs to MLflow when it is importable:
   - params: arch, window, stride, lr, epochs, seed, `split_hash`, `lock_sha256`
   - per-epoch metrics: train/val loss, val PR-AUC, val recall at `at_fpr`
   - artifacts: `model.onnx` and `meta.json`

   The tracking URI comes from `MLFLOW_TRACKING_URI`. Point it at the portal's MLflow server to see the run on the
   portal's *Prepare Model* page; otherwise it logs to a local `./mlruns`. Without MLflow, training still runs and
   says so. When a scaffold is provided, reuse **only** its MLflow run naming and tag *string literals*, so runs
   line up with the portal's. Never reuse its `log_metric`/`log_param` calls or any value its (unused) training
   body computes. Every logged metric comes from this `train.py`'s own train/val computation, never from test.
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
   Also run `python -m agentforge.src.ml_contract.package check-env --dest <model folder> --arch <Arch>
   [--baseline <Dir>]`: every step's `requirements.txt` must install TOGETHER on the runner (one environment,
   Linux / Python 3.11, wheels only). A set that does not install is a blocker — loop back to `ml-modeler`.
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
