# Synthetic data review — M6 (human gate `data/synth-review.md`)

Generated 2026-09-18T22:52:03+00:00 by `ml_contract.review synth`.

- **Lock** `b7a3765f48f6` · **split_hash** `47871db08ccc` · **seed** 20260918
- **Recipe** `data/synthetic-recipe.md`

## Real train + synthetic, per class (synthetic capped at 50% of real windows per class)

| Class | Real units | Real windows | Synthetic units | Synthetic windows | Real : synthetic | Synthetic windows used (cap) | Share synthetic after cap |
|---|---|---|---|---|---|---|---|
| normal | 13 | 4,491 | 30 | 35,867 | 1 : 7.99 | 2,245 | 33% |
| tool_wear | 3 | 3,588 | 30 | 35,719 | 1 : 9.96 | 1,794 | 33% |

### From `data/synthetic-recipe.md` — Fidelity

| Channel | Real normal (IM-01R train head) | Synth normal | Real worn (A05, pure) | Synth worn |
|---|---|---|---|---|
| `spindle_load` (Nm) | -2.3695 / 1.6759 | -2.3615 / 1.4160 | -2.4270 / 1.8351 | -2.3001 / 1.4864 |
| `x_axis_error` (um) | 0.0001 / 26.924 | 0.0625 / 27.477 | 0.0000 / 34.536 | 0.0448 / 32.827 |
| `vibration_rms` (g) | 5.7736 / 0.9321 | 5.7701 / 0.7854 | 5.4693 / 0.7501 | 5.6741 / 0.6823 |

Means match closely throughout (within ~0.1–0.3 of the real value on all channels). Stds are close
for `x_axis_error` (102% of real normal, 95% of real worn) and reasonable but somewhat low for
`spindle_load` (84–81%) and `vibration_rms` (84–91%) — attributable to the block-bootstrap steady-state
pool having slightly lower dispersion than the full real pool once the (now-anchored) startup
transient is excluded from it. This is disclosed, not hidden, below.

### From `data/synthetic-recipe.md` — Known limits

- **Sim-to-real gap.** Block-bootstrapped real data, not a physics simulation — captures the real
  marginal/short-range structure but not necessarily longer-range process dynamics beyond one block
  (150–400 rows / 15–40 s).
- **One program, one material.** Every synthetic run is derived from the IM-01R program (injection
  mold, S235JR, roughing) — same limitation already recorded in `label-manifest.md`'s Known limits for
  the real data; synthesis does not add program diversity, only within-program realisation diversity.
- **Wear signature derived largely from one pure-wear unit (A05).** A01/A02 confirm the
  `x_axis_error`/`vibration_rms` direction and rough magnitude but carry a blowhole confound; the
  `spindle_load` std increase and the correlation nudge are the least certain parts of the signature
  as a result. Randomization ranges are bounded by 3 units, not a large population — a narrower true
  diversity than the sampled ranges might suggest.
- **Std slightly below real** on `spindle_load` and `vibration_rms` (see fidelity table) — the
  steady-state pool (real pool with the anchored transient excluded) has somewhat lower dispersion
  than the raw real pool; magnitude of the shortfall is disclosed above, not corrected further at M6.
- **No cross-channel physics model** beyond the linear correlation nudge — real wear-vibration-torque
  coupling may be more structured (e.g., frequency-domain) than a shared-noise term captures.
- **Block seams have no crossfade** — consecutive bootstrap blocks are concatenated directly, so a
  block boundary can show a small discontinuity not present in a truly continuous real recording.

## How it is used

| Split | Synthetic |
|---|---|
| train | Mixed in, capped as above; every synthetic row keeps `source=synthetic` |
| val | **Never.** The threshold is calibrated here, on real data only |
| test | **Never.** It measures the real result, including the synthetic-to-real gap |

M8 must train a real-only model and a real + synthetic model and compare them on **real val**. The synthetic data is kept only if it improves real-val recall at the target FPR.

## Decision

- **approve** — use the synthetic set as above; M7 is next.
- **changes_requested** with the reason — re-run `/synth-data` (other cap, recipe or seed) or skip M6.
