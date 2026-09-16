---
name: time-series-ml
description: Time-series / sensor ML for the ai-ml discipline (ADR-0015) — anomaly detection, fault classification, and RUL on multivariate sensor windows. Architecture ladder (ROCKET family → 1D-CNN/InceptionTime → TS foundation models), PdM datasets with license verdicts, leakage-safe splitting (chronological / per-unit), rare-event metrics, and signal-mode synthetic data. Use for any objective over sensor, vibration, or process time series.
origin: NeuroEdge AgentForge
---

# Time-Series / Sensor ML

Facts below are as-of **2026-08-31** (ADR-0015 research pass). Licenses and tool status churn —
**verify before a product decision**; do not treat this file as legal review.

## When to Activate

- The objective is over sensor/process time series: anomaly detection, fault classification,
  forecasting, RUL (e.g. "detect CNC machining drift", "predict bearing failure")
- `/dataset-scout --timeseries`, `/synth-data` signal mode, `/model-select`, `/model-build` for a
  TS task; `ml-eval-reviewer` reviewing TS training code

## Architecture ladder — in the order to try

| Rung | What | Why / when | Where |
|---|---|---|---|
| 1 | **MiniRocket / MultiRocket / Hydra + ridge** | Trains in seconds, no hyperparameters, routinely beats deep nets on modest data. **The honesty floor**: any deep model must beat it. Tiny deployable head — attractive for edge. Not a CNN: **no pretrained weights, nothing to fine-tune** — fixed non-trainable kernels + a linear head. Classification/regression only | `aeon` (BSD-3). 🔴 **Install from `aeon`/`sktime`, NOT `angus924/minirocket` — the original reference implementation is GPL-3.0.** The aeon/sktime reimplementations are BSD-3-Clause (adapted with the author's permission); vendoring the GPL original into a product triggers copyleft |
| 2 | **1D-CNN / InceptionTime** | The deep-learning control arm. Channels-first `(batch, features, window)` input; exports cleanly to ONNX (`Conv` with one spatial dim — TensorRT-safe). TCN / LSTM-FCN are the alternatives | `aeon` / `tsai` (check `tsai` maintenance — slowed since ~2024) |
| 3 | **Frozen TS foundation-model encoder + head** | Only when labels are scarce. **MOMENT (MIT)** is the one TSFM natively covering classification/AD/imputation; Chronos-Bolt, TimesFM, TinyTimeMixers, Lag-Llama are Apache-2.0 but **forecasting-only** (AD only via forecast-residual). 🔴 **Moirai weights are CC BY-NC — no commercial use** | HF |

🔴 **ROCKET-family scope.** MiniRocket/MultiRocket/Hydra do **classification and regression over
fixed-length windows** — nothing else. They are not generative and produce no reconstructed signal,
so they do not do denoising, filtering, imputation, or forecasting-as-generation. They also have **no
edge-deployment path in this stack**: the transform emits ~10k features per sample into a linear
head, not the `{1, C, W}` ONNX Conv graph the device runtime loads. Baseline and gate — never the
shipped edge artifact.

Library status: `aeon` (best-maintained TSC/TSAD home), `sktime` (broadest API), `darts`
(forecasting + PyOD-backed AD), `PyOD` (active). Avoid: Merlion (dormant), TODS (unmaintained).
`anomalib` is **image** AD — do not conflate. Nixtla's TimeGPT is a **paid API**, not a library.

## PdM datasets — with license verdicts

| Dataset | What | License verdict |
|---|---|---|
| **NASA PCoE** (milling, C-MAPSS, FEMTO, IMS bearings) | Run-to-failure + degradation labels | US-government work — generally clean; portal metadata inconsistent, verify per set |
| **PHM Society 2010** CNC milling | 315 cuts/cutter, force+vibration+AE at 50 kHz, measured flank wear | ⚠️ Informal (challenge data, research-use custom); **Kaggle "CC0" mirrors are not authoritative** |
| **CWRU bearing** | The classic benchmark | Free, but 🔴 **split by physical bearing** — the standard splits leak bearing identity and near-100% accuracies are memorization |
| **UCI #447 Hydraulic** | 2,205 cycle-shaped multivariate samples, graded condition labels | CC-BY-class — usable; best cycle-window proxy |
| **UCR/UEA archives** | Canonical TSC benchmarks | Research-informal — benchmark only, verify before redistribution |
| 🔴 **Paderborn KAt** | Real bearing damage | **CC BY-NC 4.0 — non-commercial only.** Every tutorial recommends it; keep it out of product builds |
| 🔴 **MIMII / ToyADMOS2 / DCASE task-2** | Machine-sound AD | **CC BY-NC-SA — non-commercial + share-alike.** Benchmark only |

License-fit stays the **blocking gate** (dataset-sourcing gate 2, ADR-0014 OQ-2).

## Leakage-safe splitting — the #1 TS failure mode

1. **Split first, window second.** Sliding windows with overlap (stride < window) are
   near-duplicates; a random split over windows puts the same signal on both sides. This exact
   defect shipped in a real preprocessor (50 % overlap + `random.shuffle`).
2. **Split chronologically or per unit** (`GroupKFold`; unit = bearing / cutter / machine / cycle).
   Never let one physical unit span train and test.
3. **Fit normalization stats on train folds only**; persist mean/std with the model so edge
   inference reproduces them.
4. **RUL label cap** (C-MAPSS convention, 115–130): record the cap in `config.yaml` — RMSE across
   different caps is not comparable.
5. **Channel order is part of the contract**: name channels so serialization order matches training
   order (a `std::map` sorts `sensor_10` before `sensor_2` — silent accuracy loss on device).

## Metrics for rare-event anomaly detection

- **PR-AUC primary** (ROC-AUC secondary — inflated by abundant negatives on imbalanced data).
- **Recall @ fixed FPR** — the operational plant framing: nuisance alerts per shift at the recall
  the use case demands (report both numbers).
- **Event-level F1** over anomaly *events*, plus PATE / affiliation metrics for interval tasks.
- 🔴 **Point-adjust F1 is broken** — random scores can beat SOTA under PA; never report it alone.
- `eval.py` emits all of the above into `metrics.json`; the published number is measured on a
  held-out split obeying the rules above, or it is not published.

## Signal-mode synthetic data (`/synth-data`)

Parametric waveform + noise + seeded anomalies: base signal (sinusoid/trend per channel) +
Gaussian noise + injected excursions with labeled onset — the NeuroEdge simulator's
`agentforge_simulator/gen_input.py --profile cyclic_multichannel` is the worked example: correlated
channels, a repeating work-cycle envelope, and a `--drift` fault magnitude that progresses across
cycles, labelled per cycle by a recorded severity threshold. Its `--profile sensor` is a single
channel with per-row glitch spikes and no cycles or progression — fit for a single-channel
point-glitch task or pipeline plumbing, not a drift/wear objective
([`synthetic-data`](synthetic-data.md) signal mode has the full rules).
Rules mirror the vision skill: synthesize the **rare class**, keep a **real hold-out**, emit a
reproducible `synthetic-recipe` (generator + params + seed), never validate on synthetic only.

## Labeling time series

`/auto-label`'s zero-shot pipeline is **vision-only**. For TS: labels come from the dataset's own
ground truth (wear measurements, run-to-failure timelines), threshold/rule weak supervision
reviewed by a human, or controlled seeding (synthetic anomalies carry free labels). Label the
**window** by an explicit rule (e.g. majority vote or any-anomaly) and record the rule in the
`label-manifest`.

## Deployment shape

Export ONNX with a **pinned opset** (repo-wide — mixed opsets across trainer/profiler/device is a
recorded field failure; for NeuroEdge it is **13**, the value the device runtime is proven against —
Web ADR-0001 W-3); input `(1, n_features, window)`, channels-first, **static feature dimension**;
fold train-split normalisation and a scalar head's `Sigmoid` **into the graph** so they cannot drift
from the weights (W-4, ADR-0003 B-3); persist `meta.json` (feature order, window, stride, mean/std for
provenance, head shape + range, decision threshold chosen on validation, class names) beside the
model — device parity depends on it. The full folder contract is [`ml-model-package`](ml-model-package.md). A model of this class runs on an MCU (~tens of KB); Jetson-class hardware is oversized but
fine when already owned.

## Do NOT

- Do not random-shuffle overlapping windows across splits, ever — chronological or per-unit only.
- Do not fit scalers on the full dataset before splitting.
- Do not train on Paderborn / MIMII / DCASE data (non-commercial) for anything shipped.
- Do not report point-adjust F1 alone, or accuracy on heavily imbalanced anomaly data.
- Do not skip the MiniRocket floor — a deep net that cannot beat it is not earning its inference cost.
