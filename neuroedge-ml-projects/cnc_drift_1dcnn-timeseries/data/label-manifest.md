# Label manifest — cnc_drift_1dcnn-timeseries

- **Decided:** 2026-09-17, by sanjkcog, at M4 `verify`, before any model was built
- **split_hash:** `47871db08ccc16d34f4947407ec731a9988afdfb00ac890baf645df45f07baad` (method in each `splits/*.json`)
- **Supersedes:** the M2-era splits (`split_hash 6e2049…`). Their single `anomaly` label mixed three
  different phenomena.

## Taxonomy

Two classes, one label per experiment (or per segment of IM-01R). Each window inherits the label
of the unit it came from.

| Label | Meaning | Units |
|---|---|---|
| `normal` | Healthy machine running its program as designed | the 18 normal experiments |
| `tool_wear` | Same program and settings as the normal run, cut with a worn tool | IM-01R-A01…A05 |

IM-01R-A01 and A02 also carry seeded blowholes (1 mm / 5 mm). They stay `tool_wear`, because the
tool is the worn one. But the blowholes are a workpiece effect layered on top, so a per-trial
metric on A01/A02 is not pure tool wear. A03, A04 and A05 are pure tool wear.

## Window rule (M5, recorded 2026-09-18 against lock `b7a3765f`)

- **Window:** 64 samples at 10 Hz (6.4 s) from `data/contract/`, stride 10, as the lock sets them.
- **Label:** a window takes its unit's label (`normal` or `tool_wear`). Labels are per unit, so
  every sample in a window carries the same label. Majority vote and any-anomaly therefore give the
  same answer, and no mixed-label window can exist.
- **Placement:** a window lies entirely inside one unit's `[cycle_start, cycle_end_exclusive)`
  split bounds. A window that would cross a bound is dropped, not truncated or padded.
- No gate: time-series labels come from the dataset's ground truth (`time-series-ml`), not from
  human review.

## Excluded (10 experiments), and why

| Units | What they are | Why excluded |
|---|---|---|
| TF-01-A01, TF-02-A01, TF-03-A01, TF-03-A02, IM-01F-A01, IM-02F-A01 | Commanded setting changes: feed +20%, overload +30%/+60%, altered cutting speed, chatter settings, irregular stock allowance | **Leakage.** The change shows up directly in torque and following error, so a model learns "this program was set differently". On a production line the program doesn't change, so that model would score well in eval and catch nothing in production |
| IMP-01-A01…A04 | Workpiece defects (cavities, cracks, chipped edge); settings byte-identical to IMP-01 | **Different use case** (quality escape, not machine drift). Not used as `normal` either: the defects change how the tool engages the part |

Nothing is deleted. These trials stay in `data/raw/` and can serve a separate objective.

## Splits

| Split | normal | tool_wear | IM-01R segment |
|---|---|---|---|
| train | IMP-BASE, IMP-01…04, 06, 07, 08, 10, 11, TF-01, TF-03 + IM-01R head | A01, A02, A05 | CYCLE [3210956, 3568011), 714.1 s |
| val | IMP-09, IMP-12, IM-01F + IM-01R middle | A04 | CYCLE [3573011, 3688696), 231.4 s |
| test (withheld) | IMP-05, TF-02 + IM-01R tail | A03 | CYCLE [3693696, 3814382), 241.4 s |

Bounds are measured on the rows present in both `hfdata.csv` and `interim/IM-01R_sensor.parquet`,
with a 5000-tick (10 s) gap at each boundary (widened 2026-09-18 from 5 s, so a 6.4 s contract window fits; ADR-0008 M3).

### Deviation from `time-series-ml`: one run spans train and test

IM-01R is the only normal run of the program the worn tools cut. It is split **by time** across
all three splits, which the skill forbids by default ("never let one physical unit span train and
test").
- **Why:** without it, val and test would compare the worn trial against other programs' normal
  runs, which rewards a shortcut: "IM-01R-style signal = worn".
- **Risk:** the test-normal segment is the tail of a run whose head was trained on, and the test
  segment covers a later part of the toolpath than the worn trial's full run. Both can flatter
  specificity.
- **Controls:** the window length chosen at M7 must be ≤ 5000 ticks (10 s), so no window crosses a
  gap. `ml-eval-reviewer` must check this at M8. Report metrics for the IM-01R segment against
  A03 separately from the cross-program normals.

## Known limits

- **Five worn experiments, one part type, one material** (injection mold, S235JR, roughing). A
  model trained here has seen tool wear on one program only. Say so in the model card.
- **Labels are states, not progression** (DATA_README §8). `drift_score` is a wear probability,
  not a measured degree of wear.
- **Thin positive class.** This probably makes M6 `/synth-data` necessary. It also argues for
  deciding at M7 on a model trained on `normal` only, with `tool_wear` used for validation and test.

## Requirements carried into M7/M8 (ml-eval-reviewer, 2026-09-18)

These are binding on `/model-build` and are checked by `ml-eval-reviewer` at M8:

1. **Window guard, hard fail.** `config.yaml` must refuse a window over 5000 ticks (10 s at
   500 Hz), or over the gap at whatever rate the use-case contract settles on. Re-derive the gap
   if the rate changes.
   The locked contract (`use_case.lock.json`, 2026-09-18) is 64 samples at 10 Hz = 6.4 s = 3200 ticks,
   inside the 10 s gap.
2. **Windows come from the split files.** Build windows inside each unit's
   `[cycle_start, cycle_end_exclusive)` bounds from `splits/*.json`, keyed on `CYCLE`/`tick`,
   never by row position, and never window first and split afterwards. Assert at load time that
   no window crosses a split boundary. *(Corrected 2026-09-19: this line said the portal's
   `ts_preprocessor.py` "does the opposite". The portal fixed that on 2026-09-18, NeuroEdge-Web
   `1197d27`. The portal is still not used for this dataset, because it cannot take these split
   files: see `model_proposed.md` §Runner.)*
3. **Centring is already train-only.** IM-01R's channel means come from its train segment
   (`interim/alignment.json` records `centre_ticks` and `channel_means`). Any later scaling in
   `train.py` must also be fitted on the train split only and exported in-graph.
4. **An honest evaluation protocol.**
   - Report metrics per experiment (or per segment for IM-01R): one score per unit, such as the
     maximum or mean `drift_score`. Don't report per window: overlapping windows from one trial
     are near-duplicates.
   - Report recall at a stated FPR, not only AUC, and a MiniRocket baseline on the same splits.
   - There are 5 independent positive units. Test holds one worn trial (A03), so the test recall
     is a single-trial pass/fail; say that plainly.
   - Report A01/A02 (tool wear plus blowholes) separately from A03/A04/A05 (pure tool wear).
