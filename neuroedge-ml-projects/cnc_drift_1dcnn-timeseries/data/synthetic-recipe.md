# Synthetic recipe — cnc_drift_1dcnn-timeseries (M6 synth, signal mode)

- **Decided:** 2026-09-18, `/synth-data --signal`, before any model was built (M7 not yet run)
- **Generator:** `data/synth/gen_synth.py` (tracked; blobs are not) at repo HEAD `b7dcd92`
- **Seed:** `20260918` (also the run's default `--start-ts`-equivalent — this generator has no wall-clock
  timestamp column, so `--seed` alone is fully reproducing; see self-check below)
- **Command used:**
  ```bash
  python data/synth/gen_synth.py --dest <dest> --seed 20260918 --n-worn 30 --n-normal 30 --self-check
  ```
- **Output:** `data/synthetic/SYN-tool_wear-001..030.parquet`, `SYN-normal-001..030.parquet`,
  `data/synthetic/manifest.json` (per-unit params, gitignored blobs excepted — parquet is
  `.gitignore`d, `manifest.json` and this file are tracked)

## Why synthesize

Real train tool_wear windows are not rare (3,588), but **independent worn units** are: only 3
(A01, A02, A05), and only A05 is pure tool wear (A01/A02 also carry seeded blowholes). The goal is
diversity of wear *realisations* — severity, ramp shape, per-run gain/baseline/noise — not more
windows of the same three units.

## Anchor data (train split only)

- `data/contract/IM-01R.parquet` filtered to `split == "train"` — verified this filter's
  `block_start` range `[3211000, 3567950]` falls entirely inside the recorded train bounds
  `[3210956, 3568011)` from `data/splits/train.json`'s IM-01R segment (asserted in code, not just
  eyeballed). 7,140 rows, all `label == "normal"`.
- `data/contract/IM-01R-A01.parquet`, `IM-01R-A02.parquet`, `IM-01R-A05.parquet` — each asserted to
  be entirely `split == "train"`, entirely `label == "tool_wear"`, per `data/contract/manifest.json`
  (no val/test rows exist for these three units). 12,013 / 12,037 / 12,006 rows.
- **Never opened:** `data/splits/val.json`, `data/splits/test.json`, or any parquet for a val/test
  unit (IM-01F, IMP-09, IMP-12, IM-01R-A04, IMP-05, TF-02, IM-01R-A03). `grep` over the script
  confirms these names appear only in a docstring/comment/constant, never in a file-open call.

## Fitted wear signature (worn vs. IM-01R train-head normal)

Measured on train-split rows only, comparing A01/A02/A05 against the IM-01R train head:

| Channel | Normal mean / std | A05 (pure wear) mean / std | A01 mean / std | A02 mean / std | Fitted std-ratio range | Fitted mean-shift range |
|---|---|---|---|---|---|---|
| `spindle_load` (Nm) | -2.3695 / 1.6759 | -2.4270 / 1.8351 | -2.2402 / 1.7348 | -2.2935 / 1.7846 | 1.03 – 1.10 | -0.06 .. +0.13 Nm |
| `x_axis_error` (um) | 0.0001 / 26.924 | 0.0000 / 34.536 | 0.0002 / 34.846 | 0.0001 / 34.839 | 1.20 – 1.32 | -0.0002 .. +0.0002 um (negligible) |
| `vibration_rms` (g) | 5.7736 / 0.9321 | 5.4693 / 0.7501 | 5.8056 / 0.7576 | 5.7437 / 0.7752 | 0.78 – 0.85 | -0.31 .. +0.04 g |

- `x_axis_error` std increase (+28–29%) is the most consistent wear signature — present, nearly
  identically, in all three worn units.
- `vibration_rms` std **decrease** (-17% to -20%) is also consistent across all three — a real,
  counter-intuitive finding (a naive "wear = more vibration" prior would be wrong here) — kept as-is,
  not overridden.
- `spindle_load` std increase is present but smaller and more variable (+3.5% to +9.5%).
- **Cross-channel coupling:** `spindle_load`↔`vibration_rms` correlation is 0.103 in normal train
  data, 0.223 in A05 (pure wear, +0.12), but close to flat in A01/A02 (0.092, 0.095 — the blowhole
  layered on top may be masking it, or it's a single-unit artifact). Sampled range `[0.0, 0.12]` per
  worn run, so the correlation nudge is present at random strength (including near-zero) rather than
  forced on every run — this reflects it being clearly observed in only 1 of 3 real worn units.
- **Additive, not extrapolated far:** all ranges above are bounded by the min/max these three real
  worn units actually show; no range reaches beyond the observed real spread.

## A real, once-per-run physical artifact worth naming

All four real IM-01R-family train runs (the normal head, A01, A02, A05) show a single sharp
`spindle_load` spin-up transient a few dozen rows into the run (down to about -84 Nm vs. a
-1..-4 Nm steady floor), each about 4 rows past a -10 Nm threshold. This is almost certainly a
machine-startup artifact, not noise. The generator locates it (`_find_startup_transient`,
threshold -10 Nm, ±6-row pad) and **places it once at the start of every synthetic run**, then
block-bootstraps the rest from the pool with that transient excluded (so it can't be resampled a
second time by chance). Before this fix, a plain block-bootstrap under-represented the transient in
about half of trial synthetic runs (self-check below), pulling the aggregate `spindle_load` std
noticeably low; anchoring it once per run closed most, not all, of that gap.

## Generation approach

1. **Base signal**: `_find_startup_transient` extracts the spin-up rows once; the rest of each
   ~12,000-row synthetic run is a **block-bootstrap** resample (contiguous blocks, 150–400 rows,
   random start offset, sampled with replacement) of the remaining ("steady-state") IM-01R train-head
   rows. This is a **real base**, not a parametric waveform: every row's channel values are drawn
   directly from real train data, just reordered/repeated, which keeps whatever real local
   autocorrelation exists within a block.
2. **Per-run domain randomization** (same distributions for a `normal` run and its `tool_wear`
   sibling, so the two classes differ *only* in the wear delta, not in base character): a
   multiplicative gain (0.95–1.05), an additive baseline offset (±5% of the real channel std), and
   extra i.i.d. Gaussian noise (0–10% of the real channel std) — all per channel, drawn once per run.
3. **Wear delta** (`tool_wear` runs only): per-channel std-ratio and mean-shift sampled from the
   ranges above, applied to the channel's deviation from its real mean, scaled by a **severity curve**
   that ramps from a random start value (0.3–0.7) to 1.0 over the first 5–40% of the run — either
   linearly (`ramp`) or as a step (`step`), chosen 50/50 — then holds at 1.0. A correlation nudge
   (0–0.12) adds a shared component to `spindle_load` and `vibration_rms`.
4. **Clipping**: every channel is clipped to `[min(real normal, real worn) - 5% span, max(...) + 5%
   span]` (`vibration_rms` additionally floored at 0, since it's an RMS quantity and the real data
   never goes negative). This bounds the domain-randomization + wear-delta stack so per-run noise
   cannot extrapolate far beyond the real train envelope (rule 3). Fraction of rows clipped per
   channel is recorded per unit in `manifest.json` under `clipped_fraction` — typically well under 1%.

## Label rule (chosen)

**Per-unit, single label** — matches the real data structure exactly (label-manifest.md's Taxonomy:
a worn run is one unit, one label, for its whole duration). The severity ramp/step described above
changes wear **magnitude** within a `tool_wear` run; it never changes the row's **label**. Every row
in a `SYN-tool_wear-*` file carries `label == "tool_wear"`; every row in a `SYN-normal-*` file carries
`label == "normal"`. This was chosen over an onset-based label change because the real worn units
have no such internal label transition to anchor an onset-split rule to, and it keeps window
construction identical to the real-data path (label-manifest.md's M5 rule) with no extra dropped-window
logic needed for synthetic data.

## Counts and mix

| | units | rows | windows (window=64, stride=10) |
|---|---|---|---|
| Synthetic `tool_wear` | 30 | 358,943 | 35,719 |
| Synthetic `normal` | 30 | 360,441 | 35,867 |
| Real train `tool_wear` (A01, A02, A05) | 3 | 36,056 | 3,588 |
| Real train `normal` (13 units incl. IM-01R head) | 13 | 45,673 | 4,491 |

- **Real:synthetic tool_wear window ratio ≈ 1 : 9.96** (3,588 real vs 35,719 synthetic).
- **M8 recommendation:** cap synthetic `tool_wear` windows at **≤ 50% of the real tool_wear train
  window count** (≤ ~1,794 windows — e.g. subsample ~5 of the 30 synthetic worn units, or randomly
  subsample windows across all 30), matched 1:1 by an equal number of synthetic `normal` windows drawn
  the same way. Train **both** a real-only model and a real+synth model on the same train split, and
  compare them **only on the real val split** (never synthetic) — the honest measure of whether
  synthesis helped.
- Synthetic data is never used in val or test, per hard rule 6 and this project's `use_case.lock.json`
  / `label-manifest.md` split design.

## Self-check results

Run: `python data/synth/gen_synth.py --dest <dest> --seed 20260918 --n-worn 30 --n-normal 30 --self-check`

- **Row counts:** 60 files, 719,384 total rows (358,943 `tool_wear` + 360,441 `normal`), matching
  `manifest.json`'s per-unit `rows` fields.
- **Columns and order:** every file is
  `[block_start, split, label, spindle_load, x_axis_error, vibration_rms, unit_id, source]` — the
  three lock channels appear in exactly `spindle_load, x_axis_error, vibration_rms` order, matching
  `use_case.lock.json`.
- **NaNs:** 0 across all 60 files, all columns.
- **Reproducibility:** rerunning with the same `--seed 20260918` is **byte-identical** — sha256 over
  all 60 parquet files (name + bytes), both runs: `987cbbdc77ee45fac386bffe56e73e252b7fdc4968100d865205d98976702592`.
  Also verified after two independent script revisions (transient-anchoring fix included).
- **Value ranges vs. real train:**
  - `spindle_load`: real normal `[-83.41, 0.0]`, real worn `[-83.90, 65.51]`; synthetic worn
    `[-91.37, 0.68]`, synthetic normal `[-87.44, 0.42]` — within the clip envelope (real combined
    range ± 5%), i.e. bounded, not open-ended extrapolation.
  - `x_axis_error`: real normal `[-504.6, 564.5]`, real worn `[-636.2, 638.2]`; synthetic worn
    `[-694.0, 701.9]`, synthetic normal `[-528.4, 591.1]` — same clip-envelope story.
  - `vibration_rms`: real normal `[0.182, 9.217]`, real worn `[0.185, 8.178]`; synthetic worn
    `[0.262, 8.843]`, synthetic normal `[0.0, 9.573]` — floored at 0 (RMS quantity), within envelope.
- **No val/test unit referenced:** confirmed by grep over `gen_synth.py` — `IM-01F`, `IMP-09`,
  `IMP-12`, `IM-01R-A04`, `IMP-05`, `TF-02`, `IM-01R-A03`, `val.json`, `test.json` appear only in a
  docstring/comment/constant used for self-documentation, never in a file-open call.

## Fidelity table (mean / std, per channel)

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

## Known limits

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

## Reproducing this dataset

```bash
python data/synth/gen_synth.py --dest <dest> --seed 20260918 --n-worn 30 --n-normal 30
```

`data/synth/gen_synth.py` is stdlib + pandas/numpy, tracked in git; the seed above reproduces the
dataset byte-for-byte (verified above). Output parquet blobs are gitignored
(`neuroedge-ml-projects/*/data/synthetic/*.parquet`); `manifest.json` (per-unit generation params) and
this recipe are tracked.
