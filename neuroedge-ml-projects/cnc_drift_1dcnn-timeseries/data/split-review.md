# Split review — M5 (human gate `data/split-review.md`)

Generated 2026-09-19T02:00:07+00:00 by `ml_contract.review split` from `data/contract/manifest.json` and `data/splits/{train,val}.json`. Test is summarised from the counts recorded at M4; `splits/test.json` was not opened.

- **Lock** `b7a3765f48f6` · **split_hash** `47871db08ccc`
- **Window** 64 samples at 10 Hz = 6.4 s · **stride** 10 (1 s; consecutive windows share 54 of 64 samples)
- **Classes** ['normal', 'tool_wear'] · **target** recall ≥ 0.9 at FPR 0.01

## Split × class

| Split | Class | Units | Rows | Hours | Windows | Share of split windows |
|---|---|---|---|---|---|---|
| train | normal | 13 | 45,673 | 1.27 | 4,491 | 56% |
| train | tool_wear | 3 | 36,056 | 1.00 | 3,588 | 44% |
| val | normal | 4 | 12,681 | 0.35 | 1,244 | 51% |
| val | tool_wear | 1 | 12,098 | 0.34 | 1,204 | 49% |
| test | normal | 3 | 7,928 | 0.22 | 775 | 39% |
| test | tool_wear | 1 | 11,991 | 0.33 | 1,193 | 61% |

## Per unit

| Unit | Split | Label | Rows | Windows |
|---|---|---|---|---|
| IM-01R | train | normal | 7,140 | 708 |
| IM-01R-A01 | train | tool_wear | 12,013 | 1,195 |
| IM-01R-A02 | train | tool_wear | 12,037 | 1,198 |
| IM-01R-A05 | train | tool_wear | 12,006 | 1,195 |
| IMP-01 | train | normal | 3,335 | 328 |
| IMP-02 | train | normal | 3,426 | 337 |
| IMP-03 | train | normal | 2,862 | 280 |
| IMP-04 | train | normal | 2,531 | 247 |
| IMP-06 | train | normal | 2,603 | 254 |
| IMP-07 | train | normal | 2,242 | 218 |
| IMP-08 | train | normal | 3,365 | 331 |
| IMP-10 | train | normal | 2,410 | 235 |
| IMP-11 | train | normal | 3,255 | 320 |
| IMP-BASE | train | normal | 7,458 | 740 |
| TF-01 | train | normal | 2,480 | 242 |
| TF-03 | train | normal | 2,566 | 251 |
| IM-01F | val | normal | 6,077 | 602 |
| IM-01R | val | normal | 2,312 | 225 |
| IM-01R-A04 | val | tool_wear | 12,098 | 1,204 |
| IMP-09 | val | normal | 2,400 | 234 |
| IMP-12 | val | normal | 1,892 | 183 |
| IM-01R | test | normal | 2,413 | 235 |
| IM-01R-A03 | test | tool_wear | 11,991 | 1,193 |
| IMP-05 | test | normal | 2,998 | 294 |
| TF-02 | test | normal | 2,517 | 246 |

## How the data was split, and why

- **Grouping:** experiment; IM-01R normal run split chronologically (see deviation)
- **Taxonomy:** normal vs tool_wear (label-manifest.md)
- **Recorded deviation:** IM-01R (the only normal run of the tool-wear program) spans train/val/test by time, against time-series-ml "never let one unit span train and test". Chosen so val and test each hold a same-program normal beside a worn trial; the alternative rewards a program-identity shortcut. Risk: test-normal is the tail of a run whose head was trained on, which can flatter specificity. Mitigation: 10 s gaps (re-split 2026-09-18 for the 6.4 s contract window); the window must be <= 5000 ticks; ml-eval-reviewer to check at M8.
- **Excluded units (10):** IM-01F-A01, IM-02F-A01, IMP-01-A01, IMP-01-A02, IMP-01-A03, IMP-01-A04, TF-01-A01, TF-02-A01, TF-03-A01, TF-03-A02 — reasons in `data/label-manifest.md`
- **Leakage controls:** windows are cut inside each unit's split bounds only; the M4 contract build refuses any time-split gap shorter than one window (6.4 s). Overlapping windows of one unit are near-duplicates, so metrics are reported per unit, not per window.

### From `data/label-manifest.md` — Window rule

- **Window:** 64 samples at 10 Hz (6.4 s) from `data/contract/`, stride 10, as the lock sets them.
- **Label:** a window takes its unit's label (`normal` or `tool_wear`). Labels are per unit, so
  every sample in a window carries the same label. Majority vote and any-anomaly therefore give the
  same answer, and no mixed-label window can exist.
- **Placement:** a window lies entirely inside one unit's `[cycle_start, cycle_end_exclusive)`
  split bounds. A window that would cross a bound is dropped, not truncated or padded.
- No gate: time-series labels come from the dataset's ground truth (`time-series-ml`), not from
  human review.

### From `data/label-manifest.md` — Known limits

- **Five worn experiments, one part type, one material** (injection mold, S235JR, roughing). A
  model trained here has seen tool wear on one program only. Say so in the model card.
- **Labels are states, not progression** (DATA_README §8). `drift_score` is a wear probability,
  not a measured degree of wear.
- **Thin positive class.** This probably makes M6 `/synth-data` necessary. It also argues for
  deciding at M7 on a model trained on `normal` only, with `tool_wear` used for validation and test.

## Decision

- **approve** — the split, the classes and the window rule are right; M6 (synthetic data) is next.
- **changes_requested** with the reason — back to M4 (`/dataset-verify`) to re-split, or M5 to re-label.

Nothing downstream reads the test split until M10 `eval`.
