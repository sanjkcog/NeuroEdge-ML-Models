# Label manifest — cnc_drift_1dcnn-timeseries

- **Decided:** 2026-09-17, by sanjkcog, at M4 `verify`, before any model was built
- **split_hash:** `bca8a336e7edcef703dbe5865c6f8518f6ec6757e9fb665dd0ba10b0c1b286c4` (method in each `splits/*.json`)
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

## Excluded (10 experiments), and why

| Units | What they are | Why excluded |
|---|---|---|
| TF-01-A01, TF-02-A01, TF-03-A01, TF-03-A02, IM-01F-A01, IM-02F-A01 | Commanded setting changes: feed +20%, overload +30%/+60%, altered cutting speed, chatter settings, irregular stock allowance | **Leakage.** The change shows up directly in torque and following error, so a model learns "this program was set differently". On a production line the program doesn't change, so that model would score well in eval and catch nothing in production |
| IMP-01-A01…A04 | Workpiece defects (cavities, cracks, chipped edge); settings byte-identical to IMP-01 | **Different use case** (quality escape, not machine drift). Not used as `normal` either: the defects change how the tool engages the part |

Nothing is deleted. These trials stay in `data/raw/` and can serve a separate objective.

## Splits

| Split | normal | tool_wear | IM-01R segment |
|---|---|---|---|
| train | IMP-BASE, IMP-01…04, 06, 07, 08, 10, 11, TF-01, TF-03 + IM-01R head | A01, A02, A05 | CYCLE [3210956, 3570511), 719.1 s |
| val | IMP-09, IMP-12, IM-01F + IM-01R middle | A04 | CYCLE [3573011, 3691196), 236.4 s |
| test (withheld) | IMP-05, TF-02 + IM-01R tail | A03 | CYCLE [3693696, 3814382), 241.4 s |

Bounds are measured on the rows present in both `hfdata.csv` and `interim/IM-01R_sensor.parquet`,
with a 2500-tick (5 s) gap at each boundary.

### Deviation from `time-series-ml`: one run spans train and test

IM-01R is the only normal run of the program the worn tools cut. It is split **by time** across
all three splits, which the skill forbids by default ("never let one physical unit span train and
test").
- **Why:** without it, val and test would compare the worn trial against other programs' normal
  runs, which rewards a shortcut: "IM-01R-style signal = worn".
- **Risk:** the test-normal segment is the tail of a run whose head was trained on, and the test
  segment covers a later part of the toolpath than the worn trial's full run. Both can flatter
  specificity.
- **Controls:** the window length chosen at M7 must be ≤ 2500 ticks (5 s), so no window crosses a
  gap. `ml-eval-reviewer` must check this at M8. Report metrics for the IM-01R segment against
  A03 separately from the cross-program normals.

## Known limits

- **Five worn experiments, one part type, one material** (injection mold, S235JR, roughing). A
  model trained here has seen tool wear on one program only. Say so in the model card.
- **Labels are states, not progression** (DATA_README §8). `drift_score` is a wear probability,
  not a measured degree of wear.
- **Thin positive class.** This probably makes M6 `/synth-data` necessary. It also argues for
  deciding at M7 on a model trained on `normal` only, with `tool_wear` used for validation and test.
