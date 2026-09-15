---
name: model-codegen
description: Generate the model and training script as runnable PyTorch (.py) or TensorFlow/Keras code plus a training-ready handoff package (env spec, config, run-on-GPU note) — the deliverable the user carries to a cloud GPU to train. Framework-parametric, leakage-safe, reproducible. AgentForge stops at the handoff; it never runs training.
origin: NeuroEdge AgentForge
---

# Model Code Generation & Cloud-GPU Handoff

This is the pack's **headline deliverable**. From the chosen architecture + prepared dataset, emit a
**runnable model and training script** — `.py` (PyTorch) or `.tf`/Keras — and assemble a
**training-ready handoff package** the user runs on their own cloud GPU. **AgentForge builds the code;
the training run happens elsewhere.** No GPU is assumed here, and no training is launched.

## When to Activate

- `/model-build` is invoked (after `/model-select` and the dataset is prepared)
- `ml-modeler` is generating model + training code

## What gets generated (the handoff package)

```
<objective-slug>/
  model.py            (or model_tf.py)      # architecture, framework-parametric
  train.py            (or train_tf.py)      # data loaders, loss, optimizer, schedule, checkpoint, export
  config.yaml                               # hyperparameters, paths, seed, splits
  requirements.txt / environment.yml        # pinned deps (torch / tensorflow, etc.)
  data/README.md                            # how to fetch the dataset (id/URL or synthetic recipe) — NOT the data itself
  RUN_ON_GPU.md                             # step-by-step: provision, install, run train.py, where checkpoints/metrics land
  eval.py                                   # held-out eval → metrics.json (for the return eval gate)
```

## Framework selection

- Honor the objective's framework choice: **PyTorch** (`.py`, default; uses timm/torchvision) or
  **TensorFlow/Keras** (`.tf`/Keras applications). The architecture spec says which; generate that one.
- Reuse the PyTorch idioms in `skills/SOFTWARE/pytorch/pytorch-patterns.md` (device-agnostic code,
  seed control, explicit shapes) — reference, not re-owned.

## Correctness invariants the generated code MUST satisfy

1. **Device-agnostic** — `cuda if available else cpu`; the user's GPU box picks it up with no edit.
2. **Reproducible** — a single seed set across framework + numpy + python; deterministic where feasible.
3. **Leakage-safe** — train/val/test split is explicit and fixed; normalization stats fit on **train
   only**; no test data touches training or model selection. (The `post-edit-ml-leakage` hook + the
   `ml-eval-reviewer` verify this.) **Time series adds:** split **before** windowing, split
   chronologically or per physical unit (`GroupKFold`), never shuffle overlapping windows across
   splits, and record any RUL label cap in `config.yaml` ([`time-series-ml`](time-series-ml.md)).
4. **Checkpoint + export** — save best-by-val checkpoint; export to the deployment format the target
   needs (ONNX / TensorRT / TF SavedModel — tie to `skills/DEPLOY-TARGETS/*`).
5. **Config-driven, not hardcoded** — hyperparameters, paths, and the seed live in `config.yaml`, so
   the user tunes on the GPU box without editing code.
6. **Metrics match the task** — classification (accuracy/precision-recall/F1), detection/seg (mAP/IoU),
   **recommender (Recall@K / nDCG / MAP)**, **time-series anomaly detection (PR-AUC primary,
   recall @ fixed FPR, event-level F1 — never point-adjust F1 alone, never raw accuracy on
   imbalanced data)** — `eval.py` emits `metrics.json` for the return eval gate.
7. **TS deployment parity** — for time-series models: pinned ONNX opset (one value repo-wide),
   channels-first `(1, n_features, window)` export, and a `meta.json` beside the checkpoint
   carrying feature order, window, stride, train-fold mean/std, and class names — the device
   cannot reproduce inference without it ([`time-series-ml`](time-series-ml.md)).
   **Name the opset explicitly**, and take the value from the **deployment runtime it is proven
   against**, not from the library default and not from a majority vote across the codebase — the
   exporter, the profiler and the device must all import one constant. An unnamed opset is how three
   different values end up in three places.
8. **A thresholded score must be bounded, and say so.** If anything downstream compares the model's
   output against a threshold — an alarm rule, an alerting pipeline, a business trigger — the exported
   graph **ends in the squashing function** (`Sigmoid` for a scalar head, `Softmax` for multiclass)
   and the artifact declares the range. A threshold against an unbounded logit is not merely wrong, it
   is *meaningless*: it selects an arbitrary operating point that moves with every retrain, and
   nothing errors. Fold it into the graph rather than documenting it for the consumer to apply — a
   transformation carried as a note drifts from the weights it belongs to.
   **Where the threshold itself comes from:** calibrate it on the **validation** split (never test) at
   the target operating point, and record it in the artifact so consumers read it instead of
   hard-coding a literal.
9. **Emit the baseline alongside the model.** Fit the cheap reference estimator the architecture
   skill names for this family (for time series, the ROCKET-family floor in
   [`time-series-ml`](time-series-ml.md)) on the **same splits** with the **same metrics**, and write
   both results plus a `beats_baseline` flag into the artifact. Different splits or different metrics
   is not a comparison. Without a floor, a reported score cannot be sized — it may be excellent, or
   below what a linear model achieves in seconds, and nothing in the package says which.
10. **Match the consuming platform's artifact contract.** When the trained model is handed back to a
    portal, registry, or deployment service, the package must contain what that endpoint *requires* —
    typically a metrics file **and** a model-artifact descriptor (input shape, task type, class names,
    the head declaration from invariant 8). `eval.py`'s `metrics.json` alone is usually not enough.
    Check the receiving endpoint's contract when assembling the package; an artifact that trains
    perfectly and cannot be uploaded is not a deliverable.

## The handoff boundary (explicit)

`RUN_ON_GPU.md` tells the user exactly how to: provision the cloud GPU, install `requirements.txt`,
fetch the dataset (by id/URL or by re-running the synthetic recipe), run `train.py`, and collect
`checkpoint` + `metrics.json`. AgentForge's stage loop **completes at package assembly** — it does not
provision, does not upload, does not train. The returned `metrics.json` later feeds the (phase-2) eval
gate.

## Do NOT

- Do not run training, download weights-after-training, or assume a local GPU — the run is external.
- Do not bake the dataset into the package or git — reference it (id/URL/recipe); blobs are hook-blocked.
- Do not hardcode hyperparameters or the seed into the model/train code — they belong in `config.yaml`.
- Do not generate a training script with test data reachable from the training path (leakage).
- Do not leave the ONNX opset to the library default, or pick it by what most of the codebase happens
  to use — pin the value the deployment runtime is proven against.
- Do not export a raw logit for a score something downstream will threshold, and do not "document"
  the missing activation instead of folding it into the graph.
- Do not report a model's metrics with no baseline to size them against.
