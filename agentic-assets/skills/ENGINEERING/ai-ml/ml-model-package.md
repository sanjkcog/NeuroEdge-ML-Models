---
name: ml-model-package
description: The model-package contract for the ai-ml discipline (ADR-0022) — the one folder a trained model is exchanged in: model.onnx, meta.json, model_artifact.json, metrics.json, calibration/. Defines what each file must carry (channel order, normalisation, head shape and range, decision threshold, output schema, provenance, eval_split, baseline) so a model built by /model-build, trained on any machine, can be validated at upload and deployed without anyone re-deriving its contract. Use when generating train.py/eval.py, when writing the return step, and when reviewing a package.
origin: ADR-0022
---

# ML Model Package

A trained model travels as **one folder**. Whoever trained it — a generated `train.py` on a laptop GPU, an AWS
VM, or a platform's own trainer — the folder is the same, and a consumer validates the folder, never the
toolchain that produced it. This is the `ai-ml` counterpart of the SDLC "artifact" idea: the contract is about
what the model *is*, not where it came from.

## When to Activate

- `/model-build` generating the training and evaluation code (the package is what `train.py` must end by writing)
- `/agentforge-ml` at the `eval` and `return` stages
- `ml-eval-reviewer` checking a package before it is handed to a platform
- Any platform integration that receives external models (NeuroEdge-Web: the *Finished training return package*
  upload, done by a human with the zip `/agentforge-ml` M11 builds; the model project never calls the platform's
  API, ADR-0025 D-1)

## The folder

```
model-package/
  model.onnx            the deployable artifact — ONNX, pinned opset, self-describing (see "In the graph")
  meta.json             the input/output contract the runtime reads
  model_artifact.json   the consuming platform's artifact record + provenance extras
  metrics.json          task-appropriate metrics, with the split they were measured on
  calibration/          optional — 50-200 train-split samples for INT8 calibration
```

**ONNX is the only deployable format.** A model that cannot export to ONNX (MiniRocket / ROCKET family, some
time-series foundation models) may be built and measured as the **baseline** and recorded in `model_artifact.json`,
but it is never `model.onnx`. Raw framework weights (`.pt`, `.h5`) may ride along for provenance; a consumer must
**never load them** — `torch.load` on an untrusted pickle executes code.

## `meta.json` — what the runtime needs and nothing it can guess

| Field | Why |
|---|---|
| `feature_order` (TS) / `input.layout` + `input.resolution` + `color_order` (vision) | Channel order is part of the contract; a sorted map on the device puts `sensor_10` before `sensor_2` and accuracy collapses silently |
| `window`, `stride` (TS) | Windowing is runtime behaviour, not model behaviour |
| `sample_rate_hz` (TS) | The device counts **rows**, not seconds, so the same window means a different time span at another rate. Without this field a rate mismatch is undetectable anywhere (NeuroEdge-Web ADR-0008 L-4) |
| `reduce` per channel (TS): `last` \| `mean` \| `rms` | Copied from the lock. It tells the device how to build one timestep from the samples inside it, the way training built it. **Absent, the device keeps the last sample:** a model trained on 100 ms means is then fed point samples, silently |
| `units` + `definitions` per channel (TS) | What one sample *is* (`100 ms mean of spindle torque, Nm`). The device never reads units; the contract must carry them so the field gateway can be checked against them |
| `lock_sha256` | The `use_case.lock.json` the model was built on. Upload compares the package with the use case through it, and a simulator file with a different lock hash is refused on the device |
| `normalization: {mean, std, applied: "in_graph" \| "runtime"}` | Statistics fitted on the **train split only**. Default is `in_graph` — folded into the exported graph so they cannot drift from the weights; the values are kept here for provenance and for foreign toolchains |
| `head: {shape: "scalar" \| "multiclass", classes: [...], range, activation}` | A scalar anomaly head with `argmax` over a length-1 output always reports class 0. `scalar` ⇒ two class names and a threshold; `multiclass` ⇒ `len(classes) == output_length`. Exporters validate this against the real output length |
| `output_schema` | What the output tensor *means*: `anomaly_score`, `class_logits`, `yolo_boxes_v8`, … Runtimes pick a post-processor by this key instead of assuming |
| `decision_threshold` | Chosen on the **validation** split (never test) for the target recall at the fixed FPR, and shipped with the model. A threshold typed into a config by hand is not calibrated |
| `at_fpr` | The false-alarm rate the threshold was calibrated at — the use case's `performance_targets.accuracy.at_fpr` (default `0.05`), captured at `/model-build`. `eval.py` reads it from here and reports the measured `fpr` in `metrics.json`; the platform compares the two as information, never as a gate (Web ADR-0007 T-6) |
| `class_names` (ordered) | Must be identical — order included — to the dataset labels and the use case |
| `opset`, `framework_versions` | Reproducibility and runtime compatibility |

## In the graph, not in a note

Two transformations are folded into `model.onnx` at export rather than documented for the consumer to apply:
**normalisation** (leading `Sub`/`Div` nodes over the feature dimension) and, for a scalar head, a terminal
**`Sigmoid`** so the score is bounded in (0, 1). A transformation carried as metadata drifts from the weights the
first time someone re-exports; one in the graph cannot. Export **refuses** when a scalar head's observed range on
a sample batch is not inside (0, 1).

Time-series graphs are **rank-3, channels-first `[1, features, window]`** with a **static** feature dimension
(the runtime validates channel count against it); batch and window may be dynamic. Opset is a **single pinned
constant** shared with the consuming runtime — for NeuroEdge it is **13** (Web ADR-0001 W-3), chosen because that
is what the device runtime is proven against, not on merit. Raising it is a joint change.

## `metrics.json` — the number and how it was obtained

- **Provenance first:** `eval_split: "held_out_test" | "self_reported_val"` and `split_hash`. A number without a
  split is not a result.
- **Rare-event detection (TS anomaly / drift):** `pr_auc` primary, `recall_at_fpr` with the `fpr` it was fixed at,
  `event_f1`, the confusion matrix and operating threshold; `auroc` secondary, never alone; never accuracy; never
  point-adjust F1 alone.
- **Detection / segmentation:** `map50`, `map50_95`, `precision`, `recall`. **Classification:** top-1 (in `map50`
  for the NeuroEdge schema), per-class recall. **Recommenders:** Recall@K / nDCG / MAP.
- Common fields: `epochs_completed`, `best_epoch`, `train_loss`, `val_loss`, `training_duration_s`.

## `model_artifact.json` — the platform record plus provenance

Use the consuming platform's schema (NeuroEdge: `ModelArtifact` — `use_case_id`, `model_name`, `framework`,
`format`, `uri`, `metrics`, `metrics_type`, `class_names`, `input_shape`, `created_at`, `extras`). In `extras`,
always:

- `dataset_id`, `dataset_license`, `attribution` — a CC BY licence is only satisfied if the attribution reaches
  the model card and the product NOTICE
- `split_hash`, `seed`, `code_commit`, `eval_split`
- `lock_sha256`, `use_case_id` — the use-case lock the model was built on (NeuroEdge-Web ADR-0008)
- TS: `sample_rate_hz`, `stride`, and per-channel `units`, `definitions`, `reduce`, copied from the lock. The
  portal lifts them into the device's input contract (`model.input_contract.json`)
- `baseline: {name, metrics, beats_baseline}` — the cheap reference (MiniRocket for TS) measured on the **same
  splits and metrics**; a deep model that does not beat it is reported as such, not hidden
- `onnx_uri`, `meta_uri`, `calibration_data_uri`, `source: "custom_return" | "portal_trained"`

## Validation a consumer performs at upload (and the package author performs before)

1. `onnx.checker` passes; opset equals the pinned constant.
2. Input rank/layout and static feature dimension match `meta.json` and `input_shape`.
3. `head.shape` is consistent with the real output length; one ORT-CPU forward pass on calibration (or a
   synthetic batch) lands inside `head.range` for a scalar head.
4. `class_names` identical, in order, across `meta.json`, `model_artifact.json` and the use case.
4a. **Consistent with the use case, not just internally** (ADR-0008 L-4): `feature_order`, window, `sample_rate_hz`
    and head match the use case the package names. A mismatch is a package-integrity refusal (NeuroEdge: 422).
5. `metrics.json` carries `eval_split` and `split_hash`; `model_artifact.json` carries `baseline`.
6. No framework pickle is opened. Ever.

## Do NOT

- Do not ship a raw `.pt` as the deployable artifact or expect a consumer to load it.
- Do not hand-type a threshold; derive it on validation and record it.
- Do not report validation metrics as if they were held-out results — label the split.
- Do not fit normalisation on the full dataset, and do not carry it *only* as metadata.
- Do not omit the baseline because it beat the model.
