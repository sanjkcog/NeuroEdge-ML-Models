# model-select — cnc_drift_1dcnn-timeseries (M7)

- **Decided:** 2026-09-18, `/model-select --pytorch --target edge`
- **Contract locked at:** `use_case.lock.json` (`lock_sha256 b7a3765f48f6c07e73e553928f8ff40371d87286824e85d8dad48cb401d15f0d`)
- **Split locked at:** `split_hash 47871db08ccc16d34f4947407ec731a9988afdfb00ac890baf645df45f07baad`
- Generates no code and runs no training. Input to `/model-build` (M8).

## 1. Deployable pick — small 1D-CNN, plain conv stack (not InceptionTime)

**Architecture** (PyTorch, `channels-first (batch, 3, 64)`):

| Layer | In→Out ch | Kernel | Dilation | Padding | Notes |
|---|---|---|---|---|---|
| Conv1d + BN + ReLU | 3→16 | 5 | 1 | 2 | local texture, receptive field 5 |
| Conv1d + BN + ReLU | 16→32 | 5 | 2 | 4 | receptive field 13 |
| Conv1d + BN + ReLU | 32→64 | 3 | 4 | 4 | receptive field 21 |
| GlobalAvgPool1d (over the 64-step time axis) | 64→64 | — | — | — | collapses time; keeps per-channel activation *statistics* over the window |
| Linear + ReLU + Dropout(0.3) | 64→32 | — | — | — | head |
| Linear | 32→1 | — | — | — | scalar logit; Sigmoid folded in at export (§9), not during training loss |

**Param count:** conv 256 + 2,592 + 6,208 = 9,056; BatchNorm affine 2×(16+32+64) = 224; head
64×32+32 + 32×1+1 = 2,113. **Total ≈ 11.4k parameters** — well inside edge budget (KB-scale
weights at fp32/int8), matches the deployment shape in `time-series-ml` ("a model of this class
runs on an MCU; Jetson-class hardware is oversized but fine when already owned").

**Why a plain dilated conv stack, not InceptionTime:** the fitted wear signature
(`data/synthetic-recipe.md` §"Fitted wear signature") is a **single, consistent scale change** —
`x_axis_error` std ×1.20–1.32, `spindle_load` std ×1.03–1.10, `vibration_rms` std ×0.78–0.85 — not
a mix of temporal patterns at different frequencies/durations. InceptionTime's value is multi-branch
multi-kernel-size parallelism to catch *heterogeneous* motifs across many classes/datasets; here
there is one motif family (variance change) on a 64-sample (6.4 s) window with only 3 independent
real worn train units. A multi-branch net would add parameters and overfitting surface without a
matching diversity of patterns to justify it. The dilated stack (receptive field 5→13→21, covering
about a third of the window by the last block) plus **BatchNorm3+GlobalAvgPool** is intentional:
BatchNorm's normalization statistics and a stack of ReLU-conv layers are variance-sensitive by
construction (a rectified combination of shifted/scaled convolutions responds to local dispersion,
not just local mean), and global average pooling aggregates that response over the whole window
into the scalar the head reads. This is a standard, well-fit choice for a texture/variance-type
univariate-per-channel signature, not a level-shift signature that would want mean-pooling of raw
values.

**Fits 64-step windows:** all three receptive fields stay well under 64, so the network can look at
several distinct sub-regions of the window rather than being forced to a single global receptive
field on the first layer.

## 2. Pretrained / transfer — none; train from scratch, small

No pretrained TS backbone is worth adopting here. **MOMENT** (MIT, the one TSFM in `time-series-ml`
natively covering AD/classification) is a transformer encoder in the tens of millions of parameters
— orders of magnitude over the edge budget in §1, and it would need an adapter to accept this
3-channel/64-step/10 Hz contract cleanly. Chronos-Bolt/TimesFM/TinyTimeMixers/Lag-Llama are
forecasting-only (AD only via forecast residual, which is the wrong framing when we already have
direct wear labels) and Moirai is CC BY-NC (blocked outright). None of this data problem is
label-scarce in the way that motivates rung 3 of the ladder: we have 4,491 real normal windows,
3,588 real worn windows across 3 independent worn units, plus the synthetic mix in §5. Rung 3 is
for when labels are too thin even for rung 2 — that is not the case here. **Verdict: train the
architecture in §1 from scratch**, matching `time-series-ml`'s ladder rung 2 and the objective's
explicit "1D-CNN" request in `README.md`.

## 3. Training framing — two-class supervised (BCE), not one-class

**Recommend:** a two-class supervised scalar head trained with `BCEWithLogitsLoss` against
`{normal: 0, tool_wear: 1}`, over the one-class/reconstruction alternative the label-manifest
flags as a fallback ("thin positive class... argues for a model trained on normal only").

**Reason:** the label-manifest's caution was written before M6 synth landed. We now have genuine
contrastive signal — 3 real independent worn units plus 30 synthetic worn units matched 1:1 against
30 synthetic normal units generated under identical domain randomization (§5) — which a
discriminative model can use directly to shape a decision boundary tuned to the KPI (**recall ≥
0.90 at FPR 0.01**, `use_case.lock.json`). A one-class/reconstruction model trained on `normal`
only would have to learn "reconstructs the IM-01R program" from a single program and would have no
mechanism to be tuned toward the false-positive-rate operating point the KPI demands; it also risks
a strictly harder generalization ask (reconstruction anomaly scores are typically noisier at fixed
FPR than a directly supervised head) given we do have positive examples to spend. Two-class
supervised is the better fit for the stated metric.

- **Loss:** `BCEWithLogitsLoss(pos_weight=...)` — `pos_weight` set from the **effective** class
  balance of the assembled train set (real + capped synthetic, §5), computed in `train.py` from the
  loaded split, not hardcoded.
- **Optimizer / schedule:** AdamW, weight decay 1e-4, base LR 1e-3, cosine decay with a short linear
  warmup (5% of steps) — values live in `config.yaml`, not the code.
- **Early stopping / model selection:** on **real val only** (never synthetic), tracked per-unit
  (§7's per-unit aggregation, not per-window), monitoring metric = **recall @ FPR 0.01** with PR-AUC
  as tie-break; patience default 15 epochs, max epochs default 100 — all config-driven.
- **Seed:** a single seed threaded through torch/numpy/python, its value living in `config.yaml`
  (default suggested: `20260918`, matching the synth seed for this project's traceability, but a
  free config field — never hardcoded in `model.py`/`train.py`).

## 4. Augmentation (train-only, real windows) — ranges bounded to protect the variance signature

The wear signal is mostly a **1.03×–1.32× std ratio**, not a mean shift (§synthetic-recipe fitted
signature). Every augmentation range below is deliberately tight so it cannot wash out that ratio:

| Augmentation | Range | Why this range |
|---|---|---|
| Jitter (additive Gaussian noise, per channel) | std = 1–3% of that channel's **train** std | Large enough to regularize, small enough that it cannot itself manufacture a 20–30% std inflation and confuse the label |
| Per-window gain (multiplicative, per channel, per window) | 0.97–1.03× | Deliberately tighter than a generic vision-style gain aug — a wider gain range directly perturbs the exact variance ratio the model must learn to detect |
| Time-shift | ±5 samples (≤ 8% of the 64-sample window), applied within the unit's split bounds only | Preserves local texture; no interpolation/warping that would compress or stretch the variance structure |

Explicitly **not** used: time-warping/stretching (would distort the std ratio nonlinearly),
mixup/cutmix across classes (label-manifest confirms each window carries a single unambiguous
per-unit label — mixing labels here has no principled meaning), and no augmentation is ever applied
to val/test.

## 5. Synthetic mix — adopt the recipe's cap, plus the required ablation

Adopt `data/synthetic-recipe.md`'s recommendation as-is: cap synthetic `tool_wear` at **≤ 50% of
real tool_wear train windows** (≤ ~1,794 of 35,719 synthetic worn windows — subsample uniformly
across the 30 synthetic worn units, not by picking whole units, to keep the realisation diversity
that was the point of synthesizing), matched 1:1 by an equal count of synthetic `normal` windows
drawn the same way. Final assembled train set: 4,491 real normal + up to ~1,794 synthetic normal,
3,588 real worn + up to ~1,794 synthetic worn (exact counts config-driven, capped by the rule
above).

**Required M8 output — the ablation:** train the §1 architecture twice, real-only and
real+capped-synthetic, same seed, same splits, same hyperparameters; compare **only on real val**
(§3's per-unit recall@FPR0.01 / PR-AUC). Never validate on synthetic. Both runs and the delta go
into the handoff package.

**Guarding against a "syntheticness" shortcut** (real spindle_load/vibration_rms std run ~10–19%
low against real, per the recipe's fidelity table — a leak surface if the model could learn
"low-dispersion synthetic block-bootstrap texture" instead of "worn"):
1. **Matched synthetic normals.** The generator applies identical domain randomization (gain,
   baseline offset, noise) to synthetic `normal` and `tool_wear` runs and differs them *only* by the
   fitted wear delta — so any "this is synthetic" texture is present equally in both synthetic
   classes and cannot by itself carry the label.
2. **The ablation is judged on real val only** — if real+synth training were teaching the model a
   synthetic-vs-real cue instead of normal-vs-worn, that cue is absent from real val and the
   ablation would show real+synth losing to real-only. The ablation is the actual falsification
   test for this shortcut, not a side note.
3. 🔴 **Do not use per-window standardization as a guard.** The lock's `scaling: in_graph` is a
   **global** normalization (subtract/divide by **train-fold** mean/std, fixed at export) — not
   per-window standardization. Per-window standardization would force every window to unit
   variance and **destroy the exact signal this task depends on** (the wear signature is a
   window-to-window variance change). Keep normalization global-train-stats only, matching the
   already-locked contract; do not let M8 substitute a per-window normalizer to try to fight the
   synthetic-fidelity gap — that would defeat the objective outright.

## 6. Baseline — MiniRocket + Ridge (`aeon`, BSD-3)

MiniRocket (via `aeon`, **not** `angus924/minirocket`, which is GPL-3.0 — see `time-series-ml`)
transform → `RidgeClassifierCV` (or `RidgeClassifier` with a fixed alpha grid), on the **same
windows and the same `split_hash 47871db0` splits** as the CNN, same per-unit evaluation protocol
(§7). MiniRocket's convolutional kernels are fixed/random (no fitting needed for the kernels
themselves), but the **PPV/max feature-selection and the ridge classifier are fit on train windows
only** — fit MiniRocket's transform on the train split, then transform val/test with the frozen
transform, exactly mirroring the leakage-safety rule already applied to the CNN's normalization
stats. This is the honesty floor — the CNN in §1 must beat it on real val (and is only reported as
`beats_baseline: true` if it does) per `model-codegen` invariant 9. **Baseline-only: no ONNX/edge
export** — `time-series-ml` is explicit that MiniRocket has no edge deployment path in this stack
(transform emits ~10k features into a linear head, not the `{1, C, W}` ONNX Conv graph the device
runtime loads).

## 7. Evaluation protocol (binding on M8's `eval.py`)

- **Per-unit aggregation, never per-window.** For each experiment/segment, compute the maximum and
  the mean `drift_score` (post-sigmoid, bounded 0–1) over that unit's windows; both are reported.
  Overlapping windows within one unit are near-duplicates (stride 10 vs window 64 = 84% overlap) —
  per-window metrics would overstate confidence.
- **Threshold:** calibrated on **real val** at the KPI's operating point, **FPR 0.01**
  (`use_case.lock.json: target.at_fpr`), never on test. Persisted in `meta.json` (§9).
- **Primary metrics:** recall @ FPR 0.01 (the KPI metric), PR-AUC (primary per `time-series-ml`),
  event/unit-level F1, full confusion matrix at the calibrated threshold. ROC-AUC reported
  secondary only. Never accuracy alone, never point-adjust F1 alone.
- **Segmentation of results, all required:**
  - **A01/A02 reported separately from A03/A04/A05** — A01/A02 carry seeded blowholes layered on
    top of tool wear (label-manifest §Taxonomy); a per-trial metric mixing them with pure-wear
    units is not a clean tool-wear number.
  - **IM-01R segment vs A03 reported separately from the cross-program normals** — per
    label-manifest's documented split deviation (IM-01R is the only normal run of the worn tools'
    program, and spans train/val/test by time). Report test recall on A03 against the IM-01R test
    tail *and* against the cross-program normals (IMP-05, TF-02) separately, so the
    same-program-vs-different-program risk noted in label-manifest is visible, not averaged away.
  - **Test is one worn trial.** `use_case.lock.json`'s test split holds exactly one worn unit
    (A03). State plainly in `metrics.json`/the model card that the reported test recall is a
    **single-trial pass/fail**, not a population estimate.
- **Leave-one-worn-unit-out CV, required, train+val worn units only.** Over the 4 worn units
  available outside test (A01, A02, A05 from train, A04 from val — never A03), run 4 folds each
  holding one worn unit out for validation and training on the rest (plus all normal units,
  respecting split-hash provenance — this is a spread estimate over train+val data, computed
  independently of, and never touching, the official test split). Report the per-fold recall@FPR0.01
  spread (min/max/mean) as an uncertainty band around the single test-trial number. This does not
  replace the official train/val/test protocol; it is an additional robustness read required by this
  spec.

## 8. Runner — `package`

`portal` is disallowed for this objective: the portal's `ts_preprocessor.py` windows across files
and splits randomly (confirmed in `data/README.md`'s stage log, M4 gate note, and restated in
`data/label-manifest.md`'s binding M7/M8 requirement #2 — "the portal's `ts_preprocessor.py` does
the opposite [of split-then-window], so it must not be used for this dataset"). NeuroEdge-Web
ADR-0002 V-1/V-2 (portal-side TS windowing fix) has not landed. **M8 generates a training package
the user runs on their own GPU/VM** (`RUN_ON_GPU.md`), reading windows from `data/contract/` inside
each unit's split bounds per `data/splits/*.json`.

## 9. Export — ONNX opset 13, edge-static shape

- **Opset 13**, pinned (per `use_case.lock.json`'s deployment target — Jetson Orin class, the value
  named explicitly here, not left to the exporter default).
- **Input:** `[1, 3, 64]` — static feature dim (3, fixed by the channel contract) and static window
  (64, fixed by the lock), **dynamic batch dimension** for offline batch scoring convenience; the
  device runtime feeds batch=1.
- **In-graph ops:** `Sub`/`Div` by train-fold mean/std (global, per §5 guard #3 — not per-window),
  then the §1 conv stack, then a terminal **Sigmoid** folded into the graph so the exported scalar
  output is bounded (0, 1) and directly comparable to the persisted threshold (`model-codegen`
  invariant 8) — training itself uses `BCEWithLogitsLoss` on the pre-sigmoid logit for numerical
  stability, with the sigmoid appended only in the exported graph.
- **`meta.json`** (beside the checkpoint/ONNX export), fields per lock + `model-codegen` invariant 7:
  - `feature_order`: `["spindle_load", "x_axis_error", "vibration_rms"]`
  - `window`: 64, `stride`: 10, `sample_rate_hz`: 10.0
  - `reduce`: `{"spindle_load": "mean", "x_axis_error": "mean", "vibration_rms": "rms"}` (from the
    lock's per-channel `reduce`)
  - `units`: `{"spindle_load": "Nm", "x_axis_error": "um", "vibration_rms": "g"}`
  - `definitions`: copied verbatim from `use_case.lock.json.timeseries.channels[*].definition`
  - `lock_sha256`: `b7a3765f48f6c07e73e553928f8ff40371d87286824e85d8dad48cb401d15f0d`
  - `head`: `"scalar"`; `output_schema`: `"anomaly_score"` (bounded 0–1, post-sigmoid)
  - `decision_threshold`: the value calibrated per §7, `at_fpr`: 0.01
  - `class_names`: `["normal", "tool_wear"]`
  - normalization stats (train-fold mean/std per channel) actually baked into the graph, recorded
    here too for auditability

## 10. Window guard — confirmed, not re-opened

64 samples at 10 Hz = **6.4 s**, under the **10 s** (5,000-tick) split-boundary gap that
`data/label-manifest.md` widened specifically for this contract window (2026-09-18, ADR-0008 M3).
`data/contract/manifest.json` and the M0 re-lock stage-log entries confirm the contract dataset was
rebuilt against this gap. No window can cross a split boundary under this guard — `train.py` must
still assert it at load time (label-manifest's binding requirement #2), but the geometry itself is
sound. No contract concern to raise on window/rate (see §"Contract concerns" below for the one item
that *is* raised).

## 11. Subfolder names for M8

- **CNN (deployable):** `1DCNN/` (matches `README.md`'s architecture-carrying folder-name
  convention already set at M0) — contains `model.py`, `train.py`, `config.yaml`, `eval.py`,
  `requirements.txt`, `RUN_ON_GPU.md`, exported `model.onnx` + `meta.json` after the user trains.
- **Baseline:** `MiniRocket/` — same `split_hash 47871db0`, contains its own `train.py`/`eval.py`
  pair (features fit train-only) and `metrics.json`; no ONNX export (§6).

## 12. Dataset facts used, and source

| Fact | Source |
|---|---|
| 3 channels, order, units, definitions, 10 Hz, window 64, stride 10, classes, scalar head, threshold calibrated on val, recall ≥0.90 @ FPR 0.01, layout, in-graph scaling | `use_case.lock.json` |
| Real train counts (13 normal / 4,491 windows; 3 worn A01/A02/A05 / 3,588 windows), val (4 normal / A04), test (3 normal / A03), 5 independent worn units total, one program IM-01R, one material | `data/label-manifest.md` (Splits, Known limits), `data/contract/manifest.json` (per-unit row counts) |
| A01/A02 blowhole confound; A03/A04/A05 pure tool wear | `data/label-manifest.md` (Taxonomy) |
| Wear signature (std ratios, direction, magnitude) | `data/synthetic-recipe.md` §"Fitted wear signature" |
| Synthetic counts, 50% cap recommendation, real:synthetic ratio ≈1:9.96, ablation requirement, never-in-val/test rule | `data/synthetic-recipe.md` §"Counts and mix" |
| Synthetic fidelity gap (std ~81–91% / ~10–19% low vs real on spindle_load/vibration_rms) | `data/synthetic-recipe.md` §"Fidelity table" |
| Matched domain randomization for synth normal/worn pairs | `data/synthetic-recipe.md` §"Generation approach" step 2 |
| Portal `ts_preprocessor.py` disallowed for this dataset | `data/label-manifest.md` binding requirement #2; `README.md` M4 gate stage-log row |
| 10 s split gap sized for the 6.4 s contract window | `data/label-manifest.md` (Splits table note, ADR-0008 M3) |
| IM-01R spans train/val/test by time, documented deviation | `data/label-manifest.md` §"Deviation from time-series-ml" |
| Per-unit / segment evaluation, recall @ stated FPR, MiniRocket baseline required, A01/A02 vs A03/A04/A05 split | `data/label-manifest.md` §"Requirements carried into M7/M8" |
| Edge target: Jetson Orin class, ONNX opset 13 | `README.md` (Architecture requested), this run's `--target edge` flag |
| MiniRocket license (aeon BSD-3 vs angus924 GPL-3.0), architecture ladder, deployment shape, metrics rules | `agentic-assets/skills/ENGINEERING/ai-ml/time-series-ml.md` |

## Contract concerns

None on window/rate — §10 confirms the geometry is sound as locked, so this section records a
**process** observation instead, not a request to change the lock: `README.md`'s M4 gate stage-log
row notes the portal use case *separately* declared `[spindle_load %, vibration g, coolant_temp,
feed_rate]` at 100 Hz / 512-sample window, and that this was flagged "must be reconciled... before
M7/M8." The current `use_case.lock.json` (`b7a3765f`) is the reconciled, authoritative 3-channel/10
Hz/64-window contract this spec builds against — confirming that reconciliation is closed is worth
a one-line check by the user before M8, since the lock file itself doesn't narrate that it
superseded the portal's earlier 4-channel/100 Hz declaration.

## Open question for the user

None blocking M8. One judgment call made here that the user should sanity-check: choosing
**two-class supervised BCE over one-class/normal-only training** (§3) reverses the label-manifest's
provisional lean toward normal-only, on the grounds that M6 synth now supplies matched worn/normal
pairs. If there's a reason to keep the one-class framing regardless (e.g. a product requirement to
work even without any worn-unit training signal on a *different* future program), say so before M8
generates `train.py`.
