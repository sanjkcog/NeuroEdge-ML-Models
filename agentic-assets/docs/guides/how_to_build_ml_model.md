# How to build an ML model with AgentForge

**Applies to:** any supervised model AgentForge's `ai-ml` discipline covers — vision (classification,
detection, segmentation), time series (classification, anomaly detection, forecasting), tabular, and
recommenders.

AgentForge takes you from *"I need a model for X"* to a **training-ready handoff package**: model
code, training script, eval script, pinned dependencies, and a run-on-GPU note. It deliberately
**does not run training** — that happens on your own GPU box — and it makes no GPU assumption. The
deliverable you carry out is generated `.py` code plus a dataset, not a weights file.

Every step below has a **Verify** block. Run it. The failure mode this discipline exists to prevent
is a pipeline that produces a confident, wrong number, and the only defence is checking each stage
before the next one builds on it.

**Contents**

- [The pipeline at a glance](#the-pipeline-at-a-glance)
- [Before you start](#before-you-start)
- [Step 1 — Source a dataset](#step-1--source-a-dataset)
- [Step 2 — Label, or synthesize](#step-2--label-or-synthesize)
- [Step 3 — Establish a cheap baseline](#step-3--establish-a-cheap-baseline)
- [Step 4 — Select an architecture](#step-4--select-an-architecture)
- [Step 5 — Generate the handoff package](#step-5--generate-the-handoff-package)
- [Step 6 — Adversarial review](#step-6--adversarial-review-before-any-gpu-spend)
- [Step 7 — Train on your GPU](#step-7--train-on-your-gpu)
- [Step 8 — Judge the result](#step-8--judge-the-result)
- [Worked example — 1D-CNN for CNC drift](#worked-example--1d-cnn-for-cnc-drift)
- [Failure modes](#failure-modes-worth-knowing-before-they-cost-you-a-run)

---

## The pipeline at a glance

| Step | Command or agent | Produces | Skips when |
|---|---|---|---|
| 1 | `/dataset-scout` | ranked candidates + license verdicts | you already have data |
| 2a | `/auto-label` | labeled set + review queue | data is labeled, or is not vision |
| 2b | `/synth-data` | synthetic set + `synthetic-recipe` | real data is sufficient |
| 3 | (manual) | a baseline score | never — see Step 3 |
| 4 | `/model-select` | architecture + transfer recipe | architecture is already fixed |
| 5 | `/model-build` | the handoff package (`ml-modeler`, then an `ml-eval-reviewer` pass) | — |
| 6 | `ml-eval-reviewer` | a methodology verdict | never — see Step 6 |
| 7 | your GPU, per `RUN_ON_GPU.md` | checkpoint, metrics, export | — |
| 8 | (manual) | ship / do-not-ship | — |

Three hooks back this up automatically: `post:edit:ml-leakage` flags classic footguns when you edit
training code, `pre:bash:ml-artifact` blocks a `git commit` that stages weight/dataset extensions
(`.pt`, `.onnx`, `.ckpt`, `.npy`, …) or any file over 25 MB, and `stop:eval-gate-reminder` blocks the
first stop after ML training code changed and requires an `ml-eval-reviewer` pass (once per edit
batch — it delivers the requirement, it cannot prove the review ran).

In an installed project the underlying skills live at `agentic-assets/skills/ENGINEERING/ai-ml/`
(source: `skills/ENGINEERING/ai-ml/` in the Assets repo) — `dataset-sourcing`, `data-labeling`,
`synthetic-data`, `pretrained-and-transfer`, `model-architectures`, `model-codegen`, and
`time-series-ml`, plus the pack's `manifest.md`. Read `model-codegen.md` if you want the full
invariant list; the checks in Step 5 below are its practical form.

---

## Before you start

Declare the discipline so the `/agentforge` orchestrator loads the pack's manifest. Per
`agentic-assets/skills/ENGINEERING/_mechanism/discipline-realization.md` the field sits on your
plugin manifest, beside `requires_subjects`:

```json
// agentforge_custom_plugin/<your-plugin>/plugin.json
"active_disciplines": ["ai-ml"]
```

The declaration scopes orchestrator context only. The five commands, three agents, and three hooks
above are installed into every project and work whether or not you declare it.

**Verify**

```bash
python health_check/cli.py --verbose        # Windows: PYTHONIOENCODING=utf-8 python health_check/cli.py --verbose
ls .claude/agents/ml-*.md .claude/commands/ENGINEERING/ai-ml/
```

✅ Hooks, skills, agents, and memory report PASS. ✅ `ml-data-engineer.md`, `ml-eval-reviewer.md`,
`ml-modeler.md` and the five command files are listed — the health check counts agents but does not
name the `ai-ml` ones. If they are missing, AgentForge is not installed in this project — run
`setup_agentforge_claude_project.py` first ([how_to_install_agentforge.md](how_to_install_agentforge.md)).

---

## Step 1 — Source a dataset

Pick the mode flag that matches your data: `--vision`, `--timeseries`, `--tabular`, or `--reco`.

```text
/dataset-scout --timeseries "<task, sensors/inputs, deployment target,
                             and whether the use is commercial>"
```

Say **commercial** explicitly if it is. License fit is the blocking gate, and the single most
common way a promising dataset turns out to be unusable months later.

**Verify**

- ✅ Output is a **ranked table** with a **license verdict per row**, not a list of links.
- ✅ Every candidate you would actually use has a named, checkable license (CC BY 4.0, Apache-2.0,
  MIT, BSD-3). Treat "informal", "research use", "challenge terms", or a Kaggle mirror's CC0 claim
  as **unresolved** — a permissive label on a derivative of informally-licensed data does not
  launder the original.
- 🔴 **Reject on sight:** CC BY-**NC** (no commercial use) and paid-API-only models. These are
  common in tutorials and will fail a product review.
- ✅ The set has **more than one physical unit** (machine, patient, bearing, site, subject). This
  is not optional — see Step 5, check 1. A single-unit run-to-failure set cannot be split validly
  at all.

Download from the authoritative record, not a mirror.

---

## Step 2 — Label, or synthesize

### 2a. Auto-label (vision only)

```text
/auto-label "<class names and what distinguishes them>"
```

`/auto-label` is **vision-only** and says so. For time series, label with weak supervision or
threshold rules instead — `time-series-ml.md` covers the patterns.

**Verify:** ✅ A human review queue exists and you actually sampled it. Zero-shot pre-labels are a
starting point, not ground truth.

### 2b. Synthesize the rare class

```text
/synth-data --signal "<signal shape, channels, rate, and the phenomenon to inject>"
```

Use `--signal` for time series, `--render` for 3D/vision, `--augment` for diffusion augmentation.

Four rules, and they are not negotiable:

1. Synthesize the **rare class only** — never the whole dataset.
2. Keep a **real hold-out**. Never validate on synthetic alone.
3. Emit a reproducible `synthetic-recipe` (generator + params + seed).
4. Never present synthetic samples as real in the dataset card.

**Verify**

- ✅ A recipe sidecar exists and a rerun with the same seed reproduces the data.
- ✅ Your hold-out set contains **no** synthetic rows.
- ✅ The positive rate is what you intended — check it, do not assume it.

---

## Step 3 — Establish a cheap baseline

**Do this before any deep learning.** Fit the cheapest reasonable estimator on the *same splits* with
the *same metrics*, and write the number down.

| Task | Cheap baseline | Backed by |
|---|---|---|
| Time-series classification | MiniRocket / MultiRocket + ridge (`aeon`, BSD-3) | `time-series-ml.md` — the floor `/model-build` emits (`model-codegen.md` invariant 9) |
| Tabular | gradient boosting (LightGBM / XGBoost) | general practice — `model-architectures.md` notes boosted trees often beat an MLP, but names no baseline |
| Vision | a small pretrained backbone, linear probe only | general practice — no AgentForge skill names a vision baseline |
| Anything | majority-class / stratified random — the true floor | general practice |

Only the time-series floor is specified by an AgentForge skill. For other families
`model-codegen.md` invariant 9 defers to "the cheap reference estimator the architecture skill names"
and none is named yet, so state the baseline you want in the `/model-build` prompt.

This number is what makes the trained model's score *mean* something. Without it you cannot tell a
good model from a leaky one, because both look impressive.

> 🔴 If you install MiniRocket, take it from `aeon` or `sktime` (BSD-3). The original
> `angus924/minirocket` repository is **GPL-3.0** — do not vendor it into a product.

**Verify:** ✅ You have a written baseline score, produced on the **same split** the model will use.
A baseline computed on a different split is worse than none, because it invites a false comparison.

---

## Step 4 — Select an architecture

```text
/model-select "<task>

  Input:    <exact tensor shape and layout, e.g. (1, 3, 64) channels-first>
  Features: <feature/channel names IN ORDER — this order is a contract>
  Head:     <output length and activation, e.g. scalar, Sigmoid-bounded>
  Target:   <hardware, runtime, export format + opset, latency budget>
  Split:    <the grouping unit — per machine/patient/site>
  Metrics:  <primary metric first>
  Baseline to beat: <your Step 3 number>"
```

Add `--pytorch` or `--tf` to force a framework.

**Verify**

- ✅ The recommendation matches your **data modality**. If you asked for time series and got a
  `timm`/`torchvision` vision backbone, the agent took the vision branch — redirect it to
  `time-series-ml.md`'s architecture ladder.
- ✅ For time series, expect a ladder — a cheap convolution-kernel method first, a from-scratch
  1D-CNN or InceptionTime as the shipped model, and a foundation model only if labels are scarce.
  **There is no ImageNet-equivalent for multivariate sensor data.** Channel count, sample rate,
  units, and physics differ per deployment, so a backbone pretrained on someone else's sensor rig
  transfers poorly. Do not spend days hunting for one; for a model this small, the search costs
  more than the training.
- ✅ The proposed export shape is the one your deployment target actually consumes.

---

## Step 5 — Generate the handoff package

```text
/model-build
```

`/model-build` spawns `ml-modeler`, which emits the package per `model-codegen.md`, then spawns
`ml-eval-reviewer` on it — a leakage or wrong-metric finding loops back to `ml-modeler` before
handoff:

```text
<objective-slug>/
  model.py          architecture (or model_tf.py)
  train.py          loaders, loss, optimizer, schedule, checkpoint, export (or train_tf.py)
  eval.py           held-out eval -> metrics.json
  config.yaml       hyperparameters, paths, seed, splits
  requirements.txt  pinned deps (or environment.yml)
  data/README.md    how to FETCH the dataset — never the data itself
  RUN_ON_GPU.md     provision -> install -> fetch -> train -> collect metrics
```

### State what the generator cannot infer

`model-codegen.md` requires a named opset, a bounded head when a score is thresholded, and a baseline
emitted beside the model (invariants 7–9), but it cannot know your values. Deployment contracts live
in your project, not in the skill. Put them in the prompt:

- the **exact export format and opset**, pinned to one value repo-wide;
- the **head's activation and output length**, if anything downstream compares the score to a
  threshold;
- **fit the baseline** on the same splits and metrics;
- **fail loudly if the test split holds only one class**.

### Verify the package — before spending GPU money

Seven checks. The first three catch the defects that invalidate a run entirely:

```text
 1. Split is per physical unit (GroupKFold), or chronological WITH a gap of at least
    one window — never a random shuffle over overlapping windows
 2. Normalization statistics are fit on the TRAIN fold only, and persisted
 3. The test split contains more than one class
 4. Metrics match the task — for rare events: PR-AUC, recall at a fixed false-positive
    rate, event-level F1. Never accuracy alone; never point-adjust F1 alone
 5. A single seed is set across framework + numpy + python
 6. Export shape and layout match the deployment contract, with static dims where required
 7. The metadata sidecar carries feature order, window, stride, train-fold mean/std,
    and class names
```

**Verify**

```bash
grep -rn "GroupKFold\|groups=" train.py        # check 1
grep -rn "fit_transform\|StandardScaler" train.py   # check 2 — must be train-fold only
grep -n "seed" config.yaml                          # check 5 — the seed lives in config (no fixed key name)
grep -n "manual_seed\|np.random.seed\|random.seed\|set_seed\|set_random_seed" train.py   # check 5 — every RNG seeded from it
```

✅ All seven pass. ✅ `data/README.md` describes how to fetch data and contains none.

> **Why check 2 matters more than it looks.** Computing mean/std over the full matrix before
> splitting leaks test-set statistics into training. The model scores well, ships, and degrades in
> production — and nothing raises an error at any point.

---

## Step 6 — Adversarial review (before any GPU spend)

```text
Use the ml-eval-reviewer agent to review the generated training and eval code for
train/test leakage, split integrity, metric appropriateness, and reproducibility.
Pay particular attention to: the split is grouped by physical unit and not random;
normalization is fit on the training fold only; the test split contains both classes;
the exported head matches the deployment contract.
```

`/model-build` already ran this agent once. Run it again yourself, with your contract in the prompt,
after any hand edit to the package.

**Verify:** ✅ The agent returns a verdict, and you fixed anything CRITICAL or HIGH before training.

Do not skip this. A leaked split costs a full training run plus the hours spent disbelieving the
result. A leaked split that *looks good* costs far more, because nobody disbelieves it.

---

## Step 7 — Train on your GPU

Follow the generated `RUN_ON_GPU.md`. AgentForge's loop completes at package assembly — it does not
provision, upload, or train.

**Verify**

- ✅ Training loss decreases and validation loss is tracked separately.
- ✅ The run is reproducible from the recorded seed.
- ✅ You collected: checkpoint, exported model, metrics file, and metadata sidecar.
- 🔴 A validation score that is perfect or near-perfect is a **leakage signal**, not a success
  signal. Return to Step 5 check 1.

If `train.py` or `eval.py` crashes instead, see
[When the generated training code crashes](#when-the-generated-training-code-crashes).

---

## Step 8 — Judge the result

```text
model score  >  baseline score   -> the model earns its inference cost; proceed
model score <=  baseline score   -> common at MVP data volumes. NOT automatically a failure.
                                    It means the model is under-trained or the data is thin.
                                    Ship it only if you need its deployment shape — and record
                                    beats_baseline: false. Do not quote the number as validated.
```

**Verify:** ✅ Both numbers are written down, on the same split, with the same metric. ✅ The model
card states whether the baseline was beaten.

---

## Worked example — 1D-CNN for CNC drift

Detect tool-wear drift on a CNC machine from three controller channels, deployed to an edge device.
This is the concrete form of every step above. Commands marked ✅ were executed while writing this
guide; those marked ▶ follow the documented contract.

**Contract for this example** — every downstream step depends on these:

| Item | Value |
|---|---|
| Input shape | `(1, 3, 64)` channels-first, feature dim static |
| Channel order | `c00_spindle_load`, `c01_x_axis_err`, `c02_vibration_rms` |
| Head | scalar, length 1, `Sigmoid` — so a `score > 0.7` threshold means something |
| Target | edge GPU, ONNX **opset 13**, ≤ 1 s per machining cycle |
| Split | per cutter/experiment |
| Metrics | PR-AUC primary, recall @ fixed FPR, event-level F1 |

### E1 — Source the dataset ▶

```text
/dataset-scout --timeseries "CNC machining drift / tool wear detection from spindle load,
                             axis error and vibration; edge deployment;
                             commercial product — license must permit commercial use"
```

**Verify:** ✅ Ranked table with license verdicts. ✅ At least one candidate is cleanly licensed for
commercial use *and* has multiple cutters. 🔴 Reject CC BY-NC bearing/audio sets — they dominate
tutorials and fail product review. Prefer a controller-channel dataset: those channels are the ones a
real customer PLC can actually provide.

### E2 — Generate synthetic drift cycles ✅

Real CNC data is usually scarce at MVP time. AgentForge installs its data-source simulator into your
project at `agentforge_simulator/` (source: `simulator/` in the Assets repo); its stdlib-only
`gen_input.py` has a cycle-shaped multi-channel profile:

```bash
cd agentforge_simulator
python gen_input.py --profile cyclic_multichannel \
  --rows 800 --rows-per-cycle 80 \
  --channel-names c00_spindle_load,c01_x_axis_err,c02_vibration_rms \
  --drift ramp-recover \
  --seed 20260914 --start-ts 2026-01-01T00:00:00Z \
  --recipe --out sim_input/cnc.csv
```

**Verify — actual observed output:**

```text
[gen] wrote 800 cyclic_multichannel record(s) to sim_input/cnc.csv (csv)
[gen] 10 cycle(s) of 80 rows, drift=ramp-recover, channels=['c00_spindle_load', ...]
[gen] wrote synthetic-recipe to sim_input/cnc.csv.recipe.json
```

- ✅ Columns are `ts, cycle_index, row_in_cycle, <channels…>, severity, label` — wide-CSV, and the
  column order is the feature order you train and serve with.
- ✅ Whole cycles only: 800 rows ÷ 80 = **10 complete cycles**. A partial trailing cycle would never
  leave its entry ramp — a fragment that looks like a cycle but is not one.
- ✅ Drift progresses *across* cycles, which is the phenomenon itself rather than a per-row coin
  flip. Observed severity by cycle with `ramp-recover` (rounded to 2 dp):
  `[0.0, 0.16, 0.32, 0.48, 0.63, 0.79, 0.95, 0.1, 0.1, 0.1]` — degradation to a peak, then a
  maintenance recovery. Use `--drift ramp` for monotonic wear, `step` for an abrupt fault, `none`
  for a clean control set.
- ✅ Label balance is sane — this run gives 240/800 positive (30 %). Check it; do not assume it.
- ✅ **Reproducibility:** pin `--start-ts` alongside `--seed`, then two runs are byte-identical
  (verified). With `--seed` alone the values repeat but the `ts` column is wall clock, so files
  differ — the tool prints a note saying so (and a WARNING if `--seed` is missing too).

```bash
diff sim_input/run1.csv sim_input/run2.csv && echo "byte-identical"
```

🔴 This is synthetic. It develops the pipeline; it does not validate the model. Keep a **real**
hold-out.

### E3 — MiniRocket floor ▶

This is code you write in your own project. AgentForge ships no baseline script, and `aeon` is not
one of its dependencies.

```bash
python -m venv .venv-ml && . .venv-ml/Scripts/activate    # Windows: Scripts, not bin
pip install "aeon>=1.0" scikit-learn numpy pandas
```

```python
import numpy as np
from aeon.classification.convolution_based import MiniRocketClassifier   # check against your aeon version
from sklearn.metrics import average_precision_score
# X: (n_cases, n_channels, n_timepoints) — channels-first, same layout as the device
# Split per cutter BEFORE windowing. Never random over overlapping windows.
clf = MiniRocketClassifier().fit(X_train, y_train)
scores = clf.predict_proba(X_test)[:, 1]
assert np.unique(scores).size > 2, "hard 0/1 votes, not scores: PR-AUC would be degenerate"
print("PR-AUC floor:", average_precision_score(y_test, scores))
```

> 🔴 **PR-AUC needs a continuous score, not a class vote.** This snippet was not executed while
> writing the guide, and `aeon`'s module layout and classifier arguments change between releases —
> confirm the import and API against the version you installed. MiniRocket's classic head is a ridge
> classifier, which has no native probabilities; if your version's `predict_proba` returns only 0/1,
> the assert fires. Then score with the ridge head's `decision_function`, or fit a probabilistic head
> (e.g. logistic regression) on the MiniRocket features.

**Verify:** ✅ You recorded the PR-AUC. ✅ It came from a per-cutter split. ✅ The scores were
continuous (the assert passed). ✅ `X` is channels-first `(n_cases, n_channels, n_timepoints)`. A
transposed array trains fine and is silently wrong.

MiniRocket is the honesty floor: fixed non-trainable kernels plus ridge, seconds to fit, no
hyperparameters, and it routinely beats deep nets on modest data. If the 1D-CNN cannot beat it, the
CNN is not earning its inference cost. It is **not** a candidate for shipping here — it has no ONNX
path and a different deployment shape.

### E4 — Select the architecture ▶

```text
/model-select "1D-CNN anomaly detector for CNC machining drift.

  Input:    (1, 3, 64) channels-first — feature dim STATIC, batch/window may be dynamic
  Channels: c00_spindle_load, c01_x_axis_err, c02_vibration_rms  (this order IS the contract)
  Head:     scalar, length 1, ending in Sigmoid so the output is bounded (0,1)
  Target:   edge GPU, ONNX opset 13, <=1s per machining cycle
  Split:    per cutter — the data has multiple physical units
  Metrics:  PR-AUC primary, recall @ fixed FPR, event-level F1
  Baseline to beat: MiniRocket PR-AUC = <your E3 number>"
```

**Verify:** ✅ You get the time-series ladder, not a vision backbone. ✅ The architecture is small —
a from-scratch 1D-CNN here is roughly 60 lines. **The work is in the data pipeline, not the
architecture.**

### E5 — Build and check the package ▶

```text
/model-build
```

Then run the seven checks from Step 5, with these concrete values:

```text
 1. GroupKFold by cutter id                                         <- not a random shuffle
 2. Scaler fit on the train fold only, persisted to meta.json
 3. Test split contains both classes                                <- a chronological cut on
                                                                       monotonic wear can yield
                                                                       a trivially perfect PR-AUC
 4. Export is channels-first (1, 3, 64), feature dim STATIC
 5. opset_version == 13                                             <- pinned, not "latest"
 6. Graph ends in Sigmoid; a sample forward pass lands inside (0,1)
 7. meta.json has feature_order, window, stride, mean, std, class_names
```

Checks 1–3 read the generated code, so run them before the GPU spend. The package holds no weights:
`model.onnx` and `meta.json` come back from the training run (Step 7), so run this script, and
checks 4–7, on what that run returns.

```bash
python -c "
import onnx, onnxruntime as ort, numpy as np
m = onnx.load('model.onnx')
print('opset:', m.opset_import[0].version)                       # expect 13
print('input:', [d.dim_value or d.dim_param for d in
      m.graph.input[0].type.tensor_type.shape.dim])              # expect [1, 3, 64]
print('last op:', m.graph.node[-1].op_type)                      # expect Sigmoid
s = ort.InferenceSession('model.onnx')
out = s.run(None, {s.get_inputs()[0].name: np.zeros((1,3,64), np.float32)})[0]
print('output:', out.shape, float(out.ravel()[0]))               # expect (1,1) and 0<v<1
"
```

**Verify:** ✅ opset is exactly 13. ✅ input is `[1, 3, 64]`. ✅ last op is `Sigmoid` and the sample
output lies strictly inside (0, 1). ✅ `meta.json` feature order matches E2's column order exactly.

### E6 — Review, train, judge ▶

Run the Step 6 review, then train per `RUN_ON_GPU.md`, then compare against the E3 floor.

🔴 **The normalization trap.** If you train with normalization, the scaler must reach inference. The
safe MVP route is to **fold the z-score into the exported graph** as leading `Sub`/`Div` nodes before
the first `Conv`, so the model arrives self-normalizing and the device applies nothing. The
alternative — train without normalization and accept the accuracy cost — is also honest.

What you must not do is train *with* normalization and export *without* folding it in. The model then
runs on raw engineering units, and **nothing, anywhere, raises an error.** Verify by pushing a known
window through both the checkpoint and the exported model and comparing scores:

```bash
python -c "print('checkpoint vs onnx score delta must be < 1e-4')"
```

---

## Failure modes worth knowing before they cost you a run

| Symptom | Almost always | Fix |
|---|---|---|
| Validation score near-perfect | Leakage | Step 5 checks 1–2 |
| Great offline, poor in production | Scaler fit before the split, or not shipped with the model | Step 5 check 2; fold into export |
| Model loses to the cheap baseline | Thin data or under-training — **not** automatically a bug | Step 8 — record it honestly |
| Score compared to a threshold behaves oddly | Unbounded head | E5 check 6 (`model-codegen` invariant 8) |
| Runs locally, fails on device | Opset or layout drift | Step 5 check 6; E5 checks 4–5 |
| Rare-event model looks strong | Accuracy on an imbalanced set is meaningless | Step 5 check 4 |
| Cannot reproduce a result | Unseeded, or wall-clock in the data | Step 5 check 5; pin `--start-ts` |
| `train.py` / `eval.py` crashes (shape, device, DataLoader, AMP, CUDA OOM) | A code defect in the generated PyTorch package, not a methodology one | `pytorch-build-resolver` — see below |

### When the generated training code crashes

AgentForge does not run training, so a crash surfaces on your GPU box, after handoff. Bring the full
traceback back to the project and hand it to `pytorch-build-resolver` (installed to `.claude/agents/`
with the rest; it applies `pytorch-patterns.md`):

```text
Use the pytorch-build-resolver agent on this traceback from train.py:
<the traceback, the command you ran, and — for CUDA errors — nvidia-smi and pip list from the GPU box>
```

It makes a minimal-diff fix for shape, device, gradient, DataLoader, and mixed-precision errors. It
does not judge methodology, so run `ml-eval-reviewer` on the fixed files (Step 6) and re-run the Step 5
checks before paying for another run. PyTorch only — there is no TensorFlow/Keras counterpart, so a
`train_tf.py` crash is ordinary debugging.

**The one-line summary:** the architecture is the easy part. Every expensive failure in this pipeline
is a **data-handling** failure — how you split, what you normalize, and what you measure.
