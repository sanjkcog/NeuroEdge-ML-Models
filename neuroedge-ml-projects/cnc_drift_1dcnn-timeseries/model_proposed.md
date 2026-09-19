# model-select — cnc_drift_1dcnn-timeseries (M7, v2)

- **Decided:** 2026-09-18, `/model-select --pytorch --target edge`
- **Supersedes:** `model_proposed/v1.md` (archived — missing the ADR-0025 required section
  headings; refused by `ml_contract.review model`). v1's technical decisions are carried forward
  as prior context only; none of them were approved, and every one is re-justified below against
  the evidence in `data/`.
- **Contract locked at:** `use_case.lock.json` (`lock_sha256 b7a3765f48f6c07e73e553928f8ff40371d87286824e85d8dad48cb401d15f0d`)
- **Split locked at:** `split_hash 47871db08ccc16d34f4947407ec731a9988afdfb00ac890baf645df45f07baad`
- Generates no code and runs no training. Input to `/model-build` (M8).

## Architecture

**Family and rung:** `time-series-ml`'s architecture ladder, rung 2 (1D-CNN trained from scratch)
— matching the objective's explicit request ("cnc drift 1D CNN model with 3 sensors",
`README.md`) and the data volume available (4,491 real normal / 3,588 real worn train windows,
plus the M6 synthetic mix). Rung 1 (MiniRocket+ridge) is retained as the required honesty-floor
baseline, not the deployable model (§Baseline). Rung 3 (frozen TSFM encoder) is rejected — see
§Alternatives considered.

**Proposed network** (PyTorch, `channels-first`, input `(batch, 3, 64)`):

| Layer | In→Out ch | Kernel | Dilation | Padding | Receptive field | Why this size |
|---|---|---|---|---|---|---|
| Conv1d + BN + ReLU | 3→16 | 5 | 1 | 2 | 5 | 16 channels is the smallest width that lets 3 input channels each get several independent learned combinations (≈5:1 expansion) without the first layer being the network's parameter bottleneck; kernel 5 covers 0.5 s at 10 Hz, enough to see a few raw samples of local dispersion per channel, matching the "texture, not shape" signature below |
| Conv1d + BN + ReLU | 16→32 | 5 | 2 | 4 | 13 | doubling width (16→32) is the standard doubling-per-block convention that keeps parameter growth log-linear with depth; dilation 2 (not a second kernel-5 pass at dilation 1) grows the receptive field to 13 samples (1.3 s) without adding parameters relative to a wider kernel — appropriate because the wear signature (below) is a *dispersion* feature over an extended span, not a fine edge that needs dense sampling |
| Conv1d + BN + ReLU | 32→64 | 3 | 4 | 4 | 21 | kernel shrinks to 3 and dilation grows to 4 so the third block keeps extending the receptive field (13→21 samples, 2.1 s, ≈33% of the 6.4 s window) with the same or fewer per-layer parameters than block 2, rather than paying for a still-wider kernel at this depth; 64 channels caps the deepest, most expressive layer at a width still small enough to keep the whole network in the low tens of thousands of parameters |
| GlobalAvgPool1d over the time axis | 64→64 | — | — | — | window (64) | collapses the time axis into one activation-**statistic** per channel-64 feature — appropriate because, per the fitted wear signature, the label is carried by a *window-wide* variance change, not a moment-in-time event, so a pooling operator that must attend to a specific time step (e.g. max-pool or attention) would be solving the wrong problem |
| Linear + ReLU + Dropout(0.3) | 64→32 | — | — | — | — | a single 32-wide hidden layer is enough head capacity to combine 64 pooled features into a decision surface without adding meaningful overfitting risk on top of a conv trunk this small; dropout 0.3 sized for a train set with effectively only 3–8 independent worn realizations (real + capped synthetic) once per-unit correlation is accounted for |
| Linear | 32→1 | — | — | — | — | scalar logit per `use_case.lock.json`'s `head.shape: scalar`; sigmoid is folded in only at export (§Export), not during training (numerically stable `BCEWithLogitsLoss` on the raw logit) |

**Parameter count, computed, not guessed:**
- Conv1: 3×16×5 + 16 = 256; BN1 affine: 2×16 = 32
- Conv2: 16×32×5 + 32 = 2,592; BN2 affine: 2×32 = 64
- Conv3: 32×64×3 + 64 = 6,208; BN3 affine: 2×64 = 128
- Head: (64×32 + 32) + (32×1 + 1) = 2,080 + 33 = 2,113
- **Total ≈ 11,393 parameters** (conv 9,056 + BN 224 + head 2,113) — KB-scale at fp32, comfortably
  inside `time-series-ml`'s edge guidance ("a model of this class runs on an MCU; Jetson-class
  hardware is oversized but fine when already owned" — the `--target edge` flag here maps to a
  Jetson Orin Nano, so headroom is intentional rather than needed).

**Why the receptive-field/pooling combination fits the actual signal, not a generic default:**
the fitted wear signature (`data/synthetic-recipe.md` §"Fitted wear signature", measured on real
train data only) is a **consistent per-channel standard-deviation change** across all three real
worn units — `x_axis_error` std ×1.20–1.32, `spindle_load` std ×1.03–1.10, `vibration_rms` std
×0.78–0.85 — with mean shifts that are negligible to small by comparison. A stack of
BatchNorm+ReLU convolutions is variance-sensitive by construction (a rectified, scaled/shifted
convolution responds to local dispersion around a learned reference, not only to local mean), and
global average pooling aggregates that dispersion response over the whole 6.4 s window into the
scalar the head reads — matching a *texture/variance*-type signature rather than a level-shift or
short-transient signature that would instead want mean-pooling of raw values or a
sharper/localized receptive field.

**No pretrained backbone — architecture is trained from scratch.** This is a `time-series-ml`
sensor/process objective, not vision or NLP: there is no timm/torchvision/TF-Hub backbone to
transfer from, and the `pretrained-and-transfer` skill's advice does not apply here (it governs
CNN/DNN objectives with an image or text pretraining corpus, which this is not). The only
transfer-eligible options in this domain are time-series foundation models, evaluated and rejected
in §Alternatives considered.

## Framing

**Recommend:** two-class supervised, scalar head, `BCEWithLogitsLoss({normal: 0, tool_wear: 1})`,
over the one-class/reconstruction alternative that `data/label-manifest.md`'s "Known limits"
provisionally leaned toward ("thin positive class... argues for... a model trained on `normal`
only").

**Why the reversal is justified now, not asserted:** the label-manifest's lean predates M6. M6
landed genuine contrastive signal — 3 independent real worn units (A01, A02, A05) plus, per
`data/synthetic-recipe.md`, 30 synthetic worn units matched 1:1 against 30 synthetic normal units
generated under *identical* per-run domain randomization (gain, baseline offset, noise), differing
only in the fitted wear delta. A discriminative model can use that contrast directly to shape a
decision boundary tuned to the KPI operating point (**recall ≥ 0.90 at FPR 0.01**,
`use_case.lock.json`). A one-class/reconstruction model trained on `normal` only would learn
"reconstructs the IM-01R program" from a single program with no mechanism to tune toward a target
FPR, and reconstruction anomaly scores are typically noisier at a fixed FPR than a directly
supervised head — a strictly harder ask given that labeled positives now exist to spend. This
choice is flagged as the one open, non-blocking judgment call for the human (see end of document).

- **Loss:** `BCEWithLogitsLoss(pos_weight=...)`, `pos_weight` computed in `train.py` from the
  *effective* class balance of the assembled train set (real + capped synthetic, §Synthetic),
  never hardcoded.
- **Optimizer / schedule:** AdamW, weight decay 1e-4, base LR 1e-3, cosine decay with a 5%-of-steps
  linear warmup — all values live in `config.yaml`.
- **Model selection:** on **real val only** (never synthetic), aggregated **per unit** (§Evaluation),
  monitoring **recall @ FPR 0.01** with PR-AUC as tie-break; patience 15 / max epochs 100, both
  config-driven.
- **Seed:** one seed threaded through torch/numpy/python, value in `config.yaml` (suggested
  `20260918` to match the synth seed for traceability) — never hardcoded in `model.py`/`train.py`.

## Synthetic

Adopt `data/synthetic-recipe.md` and `data/synth-review.md`'s approved cap as-is: synthetic
windows capped at **≤ 50% of real train windows per class** — 2,245 synthetic normal (of 35,867
available) and 1,794 synthetic worn (of 35,719 available), subsampled uniformly across the 30
synthetic units per class (not by dropping whole units), preserving realisation diversity. Final
assembled train set: 4,491 real + ≤2,245 synthetic normal; 3,588 real + ≤1,794 synthetic worn
(exact counts config-driven, capped by the rule above, never exceeding the approved 33%
post-cap synthetic share recorded in `data/synth-review.md`).

**Required M8 output — the ablation.** Train the §Architecture network twice, real-only and
real+capped-synthetic, identical seed/splits/hyperparameters; compare **only on real val**
(§Evaluation's per-unit recall@FPR0.01 / PR-AUC). Per `data/synth-review.md`'s decision, the
synthetic data is kept in the deployable model **only if** real+synthetic beats real-only on that
comparison; both runs and the delta ship in the handoff package regardless of outcome.

**Guarding against a synthetic-texture shortcut.** `data/synthetic-recipe.md`'s fidelity table
shows real `spindle_load`/`vibration_rms` std running ~81–91% of real magnitude in the synthetic
set (block-bootstrap steady-state pool has slightly lower dispersion than the full real pool) —
a leak surface if the model could learn "low-dispersion synthetic texture" instead of "worn":
1. **Matched synthetic normals** — identical domain randomization is applied to synthetic
   `normal` and `tool_wear` runs, differing only by the fitted wear delta, so a "this is
   synthetic" cue is present equally in both synthetic classes and cannot by itself carry the
   label.
2. **The ablation is judged on real val only** — if real+synth training taught a
   synthetic-vs-real cue instead of normal-vs-worn, that cue is absent from real val and the
   ablation would show real+synth losing. This is the actual falsification test, not a side note.
3. 🔴 **No per-window standardization as a workaround.** The lock's `scaling: in_graph` is
   **global** (train-fold mean/std, fixed at export), never per-window. Per-window standardization
   would force every window to unit variance and destroy the exact signal this task depends on
   (a window-to-window variance change). M8 must not substitute a per-window normalizer to fight
   the synthetic-fidelity gap.
- Synthetic data is never used in val or test (`data/synth-review.md`'s "How it is used" table,
  hard rule 6).

## Augmentation

Train-only, real windows only (never applied to synthetic windows, val, or test). The wear signal
is mostly a 1.03×–1.32× std ratio, not a mean shift (`data/synthetic-recipe.md`'s fitted
signature), so every range below is deliberately tight — an augmentation strong enough to
manufacture a comparable std inflation would itself confuse the label:

| Augmentation | Range | Why this range |
|---|---|---|
| Jitter (additive Gaussian noise, per channel) | std = 1–3% of that channel's **train** std | Large enough to regularize against exact-sample memorization, small enough that it cannot itself produce a 20–30% std inflation |
| Per-window gain (multiplicative, per channel, per window) | 0.97–1.03× | Deliberately tighter than a generic vision-style gain aug — a wider range would directly perturb the exact variance ratio the model must detect |
| Time-shift | ±5 samples (≤8% of the 64-sample window), within the unit's split bounds only | Preserves local texture; no interpolation/warping that would compress or stretch the variance structure |

Explicitly **not** used: time-warping/stretching (would distort the std ratio nonlinearly),
mixup/cutmix across classes (`data/label-manifest.md` confirms each window carries one
unambiguous per-unit label — mixing labels has no principled meaning here).

## Baseline

**MiniRocket + Ridge**, via `aeon` (BSD-3) — **not** `angus924/minirocket` (GPL-3.0), per
`time-series-ml`'s license rule. Fit on the **same windows and the same `split_hash 47871db0`
splits** as the CNN, evaluated with the identical per-unit protocol (§Evaluation). MiniRocket's
random convolutional kernels need no fitting, but the PPV/max feature-selection and the ridge
classifier must be **fit on train windows only**, then applied frozen to val/test — mirroring the
leakage-safety rule already binding on the CNN's normalization stats.

This is the honesty floor (`model-codegen` invariant 9): the CNN in §Architecture is reported as
`beats_baseline: true` only if it beats MiniRocket+ridge on real val recall@FPR0.01. **Baseline
only — no ONNX/edge export**: `time-series-ml` is explicit that MiniRocket has no edge deployment
path in this stack (the transform emits ~10k features into a linear head, not the `{1, C, W}`
ONNX Conv graph the device runtime loads).

## Evaluation

Binding on M8's `eval.py`:

- **Per-unit aggregation, never per-window.** Max and mean `drift_score` (post-sigmoid, 0–1) per
  unit/segment, both reported. Stride 10 vs window 64 = 84% overlap, so per-window metrics would
  overstate confidence.
- **Threshold** calibrated on **real val only**, at the KPI operating point FPR 0.01
  (`use_case.lock.json: target.at_fpr`), never on test. Persisted in `meta.json` (§Export).
- **Primary metrics:** recall @ FPR 0.01 (the KPI metric), PR-AUC (primary per `time-series-ml`),
  event/unit-level F1, full confusion matrix at the calibrated threshold. ROC-AUC secondary only.
  Never accuracy alone, never point-adjust F1 alone.
- **Segmentation, all required:**
  - **A01/A02 reported separately from A03/A04/A05** — A01/A02 carry seeded blowholes on top of
    tool wear (`data/label-manifest.md` Taxonomy); mixing them into one metric with pure-wear
    units is not a clean tool-wear number.
  - **IM-01R segment vs A03 reported separately from the cross-program normals** — IM-01R is the
    only normal run of the worn tools' program and spans train/val/test by time
    (`data/label-manifest.md`'s documented split deviation). Report test recall on A03 against the
    IM-01R test tail *and* against the cross-program normals (IMP-05, TF-02) separately, so the
    same-program-vs-different-program risk stays visible rather than averaged away.
  - **Test is one worn trial** (A03 only). State plainly in `metrics.json`/the model card that the
    reported test recall is a single-trial pass/fail, not a population estimate.
- **Leave-one-worn-unit-out CV, required, train+val worn units only.** 4 folds over A01, A02, A05
  (train) and A04 (val) — never touching A03/test — each holding one worn unit out, training on
  the rest (plus all normal units, respecting split provenance). Report per-fold recall@FPR0.01
  spread (min/max/mean) as an uncertainty band around the single test-trial number. Additive to,
  never a replacement for, the official train/val/test protocol.

## Export

- **ONNX opset 13**, pinned to the deployment target (Jetson Orin Nano class, `--target edge`),
  not left to the exporter default.
- **Input `[1, 3, 64]`** — static feature dim (3, fixed by the channel contract), static window
  (64, fixed by the lock), dynamic batch dimension for offline batch-scoring convenience; the
  device runtime feeds batch=1.
- **In-graph ops:** `Sub`/`Div` by train-fold mean/std (global, per §Synthetic guard #3, never
  per-window) → the §Architecture conv stack → a terminal **Sigmoid** folded into the graph so the
  exported scalar is bounded (0, 1) and directly comparable to the persisted threshold
  (`model-codegen` invariant 8). Training uses `BCEWithLogitsLoss` on the pre-sigmoid logit for
  numerical stability; sigmoid is appended only in the exported graph.
- **`meta.json`** beside the checkpoint/ONNX export (`model-codegen` invariant 7):
  `feature_order: ["spindle_load", "x_axis_error", "vibration_rms"]`; `window: 64`, `stride: 10`,
  `sample_rate_hz: 10.0`; `reduce` per channel from the lock; `units` per channel from the lock;
  `definitions` copied verbatim from `use_case.lock.json`; `lock_sha256`; `head: "scalar"`,
  `output_schema: "anomaly_score"`; `decision_threshold` calibrated per §Evaluation with
  `at_fpr: 0.01`; `class_names: ["normal", "tool_wear"]`; and the baked-in normalization stats
  (train-fold mean/std per channel), recorded for auditability.

## Runner

**`package`.** The decision stands; its recorded reason was corrected on 2026-09-19.

> **Correction (2026-09-19, doc-only, after the M7 approval).** This section first said the
> portal's `ts_preprocessor.py` windows before it splits and that the fix had not landed. That was
> stale: the portal fixed it on 2026-09-18 (NeuroEdge-Web `1197d27`, Web ADR-0009). It now splits
> rows first, fits normalisation on training rows only, windows inside each split piece, and
> refuses a random split over overlapping windows. The claim was copied from
> `data/label-manifest.md` requirement #2, written before that fix, and was checked only against
> this folder, which could not show it.

`portal` is still not the runner for this objective, for reasons read from the portal's code
(`neuroedge_model_training/`, 2026-09-19):

- **It cannot take the approved split.** Its `per_unit` method shuffles units at random (fixed seed)
  into fractions. It is not class-aware, so with 5 worn units among about 30 it can leave val or
  test with no worn unit, and it cannot express the M5-approved assignment (A01/A02/A05 train, A04
  val, A03 test) or the recorded IM-01R chronological deviation.
- **It would not keep test withheld.** `data/portal_upload.zip` holds train + val only, so the portal
  would carve its own test set out of this run's val.
- **Its TS trainer does not train to the lock's target.** It is a fixed small net trained with
  multiclass cross-entropy and selected on accuracy: no scalar head, no threshold calibrated at
  `at_fpr`, no recall at a fixed FPR, no PR-AUC, no class weighting, no seed.
- **It produces no baseline**, so no `beats_baseline`, and no real-only vs real+synthetic ablation or
  leave-one-worn-unit-out CV (§Synthetic, §Baseline, §Evaluation).

`inputs/inputs.json`'s recorded scaffold WARN ("training body... NOT used; M8 generates them from
the lock and `model_proposed.md`") confirms the portal scaffold's training body is out of scope
regardless.

M8 therefore generates a training package the user runs on their own GPU/VM (`RUN_ON_GPU.md`),
reading windows from `data/contract/` inside each unit's split bounds per `data/splits/*.json`.
The recorded scaffold (`inputs/scaffold/neuroedge_train_cnc-drift-....py`) is reused only for its
context plumbing, return writer, and MLflow run naming/tags (per `inputs/inputs.json`'s PASS
findings on those two items) — never its training body.

Subfolders for M8: **`1DCNN/`** (deployable — `model.py`, `train.py`, `config.yaml`, `eval.py`,
`requirements.txt`, `RUN_ON_GPU.md`, exported `model.onnx` + `meta.json` after the user trains) and
**`MiniRocket/`** (baseline — its own `train.py`/`eval.py`, `metrics.json`, no ONNX export).

## Alternatives considered

**Architecture alternatives:**
- **InceptionTime** (multi-branch, multi-kernel-size) — rejected. Its value is catching
  *heterogeneous* motifs across many classes/datasets via parallel kernel sizes. Here the fitted
  wear signature is a **single, consistent scale change** (variance ratio) present near-identically
  across all three real worn units, not a mix of temporal patterns at different frequencies or
  durations. A multi-branch net would add parameters and overfitting surface — on only 3 real
  worn units — without a matching diversity of patterns to justify it.
- **Frozen TSFM encoder (MOMENT, MIT)** — rejected for this rung. MOMENT is the one TSFM in
  `time-series-ml` natively covering AD/classification, but it is a transformer encoder in the
  tens of millions of parameters, orders of magnitude over the edge budget (§Architecture's
  ~11.4k), and would need a custom adapter to accept this 3-channel/64-step/10 Hz contract.
  Rung 3 of the ladder is for objectives where labels are too thin even for rung 2 — not the case
  here (4,491 real normal + 3,588 real worn train windows across 3 independent worn units, plus
  the approved synthetic mix).
- **Other forecasting-only TSFMs (Chronos-Bolt, TimesFM, TinyTimeMixers, Lag-Llama)** — rejected.
  These support anomaly detection only via forecast residual, which is the wrong framing when
  direct wear labels already exist (see framing discussion below). **Moirai** is additionally
  blocked outright by its CC BY-NC license.

**Framing alternatives:**
- **One-class / reconstruction, trained on `normal` only** — the label-manifest's provisional
  lean, rejected here (§Framing) on the grounds that M6 now supplies matched real+synthetic
  worn/normal pairs, giving a discriminative model contrastive signal to tune a decision boundary
  directly to the KPI's FPR operating point — an operating point a reconstruction-only model has
  no direct mechanism to hit. Flagged as the one open judgment call for the human to override if a
  future-program generalization requirement outweighs this.
- **Forecast-residual anomaly scoring** — rejected together with the forecasting-only TSFMs above:
  it discards the direct wear labels this dataset actually has.

**Recipe / training alternatives:**
- **Wider augmentation ranges** (e.g. generic vision-style ±10–20% gain) — rejected (§Augmentation):
  the wear signal is itself a 3–32% std ratio change, so a loose gain/jitter range risks
  manufacturing or erasing the exact signal the label depends on.
- **Per-window standardization instead of global train-fold scaling** — rejected (§Synthetic guard
  #3, §Export): would force every window to unit variance and destroy the window-to-window
  variance signature this task depends on, even though it would superficially help mask the
  synthetic-fidelity gap.
- **Using the full synthetic set unmasked (1:9.96 real:synthetic ratio) instead of the 50% cap** —
  rejected; `data/synthetic-recipe.md`'s own recommendation and `data/synth-review.md`'s approval
  cap synthetic at 50% of real per class specifically so the assembled train set stays
  majority-real and the ablation in §Synthetic remains a meaningful test rather than training
  predominantly on block-bootstrapped data.
- **`portal` as the M8 runner** — rejected; see §Runner for the verified evidence.

## Contract concerns

None on window/rate. 64 samples at 10 Hz = 6.4 s, under the 10 s (5,000-tick) split-boundary gap
that `data/label-manifest.md` widened specifically for this contract window (ADR-0008 M3);
`data/contract/manifest.json` and the M0 re-lock stage-log entries confirm the contract dataset was
rebuilt against this gap. `train.py` must still assert the guard at load time
(`data/label-manifest.md`'s binding requirement #1), but the geometry itself is sound as locked.

One process observation, not a request to change the lock: `README.md`'s M4 gate stage-log row
notes the portal use case *separately* declared `[spindle_load %, vibration g, coolant_temp,
feed_rate]` at 100 Hz / 512-sample window, flagged "must be reconciled... before M7/M8." The
current `use_case.lock.json` (`b7a3765f`) is the reconciled, authoritative 3-channel/10 Hz/64-window
contract this proposal builds against — worth a one-line confirmation from the user before M8,
since the lock file itself doesn't narrate that it superseded the portal's earlier declaration.

## Open question for the user

None blocking M8. One judgment call the human should sanity-check: choosing **two-class supervised
BCE over one-class/normal-only training** (§Framing) reverses `data/label-manifest.md`'s
provisional lean, on the grounds that M6 synth now supplies matched worn/normal pairs. If there is
a reason to keep the one-class framing regardless — e.g. a product requirement to work even
without any worn-unit training signal on a *different* future program — say so before M8 generates
`train.py`.
