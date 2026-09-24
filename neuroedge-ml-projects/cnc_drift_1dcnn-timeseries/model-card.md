# Model Card — CNC Drift 1D-CNN (`cnc_drift_1dcnn-timeseries`)

> **Status: BELOW TARGET — demo/internal use only.** This model does not meet its recall target on
> held-out data (see §Held-out result). To use it in the portal, promote run `bd19c981a17d` in
> **Step 3 · Prepare Model → Compare Runs**.

## 1. What this model is

- **Use case:** `cnc-drift-on-powertrain-shop-for-car-prduction` — detect CNC machining drift
  (tool wear) on the powertrain shop floor from three sensor channels, faster than a manual
  operator (`1DCNN/runs/bd19c981a17d/model-package/model_artifact.json` → `extras.business_requirement`).
- **Architecture:** 1D-CNN (small dilated conv stack, ~11.4k params), classes `normal` /
  `tool_wear`, scalar sigmoid head (`meta.json`, `use_case.lock.json` → `head`).
- **Inputs:** 3 channels in order `spindle_load` (Nm), `x_axis_error` (µm), `vibration_rms` (g),
  window 64 samples @ 10 Hz (6.4 s), stride 10, layout `[1, features, window]`, normalization and
  the terminal Sigmoid folded into the ONNX graph (`meta.json`).
- **Target:** ONNX opset 13, NVIDIA Jetson Orin Nano / TensorRT execution provider
  (`model_artifact.json` → `extras.target`).

## 2. Dataset, licence, attribution

Source: `data/dataset-card.md` and `model_artifact.json` → `extras`.

- **Dataset id:** `kit-cnc-milling-multimodal`
- **Licence:** CC BY 4.0 — commercial use permitted, independently confirmed from two locations in
  the rights holder's own RADAR record (`data/dataset-card.md` §4 Verification log).
- **Attribution:** Stroebel, R. et al. (2025). *A Multimodal Dataset for Process Monitoring and
  Anomaly Detection in Industrial CNC Milling.* Karlsruhe Institute of Technology.
  DOI: 10.35097/hvvwn1kfwf7qt48z.
- Trained on real data + synthetic augmentation (`extras.trained_on`: `"real_train+synthetic"`);
  the synthetic generator and its provenance are recorded in `data/synthetic-recipe.md` and
  `data/synthetic/manifest.json` (not reproduced here).
- **Caveat carried from `data/dataset-card.md`:** all real training data comes from one physical
  machine (KIT's DMC 60 H) — the single biggest external-validity risk for this model, only
  partially mitigated by the (unused-in-training) Bosch cross-machine hold-out.

## 3. Reproducibility identifiers

- **Lock:** `use_case.lock.json` → `use_case_sha256 = 1db4afbe8113ba7398dd3a7a7ca78bdf87498f1164502fbea70a75c91fb51396`,
  `lock_sha256 = b7a3765f48f6c07e73e553928f8ff40371d87286824e85d8dad48cb401d15f0d`.
- **Split hash — two values, same split, read plainly:**
  - `data/splits/*.json` record `split_hash = 47871db08ccc16d34f4947407ec731a9988afdfb00ac890baf645df45f07baad`
    — this is M4's split_hash, computed as `sha256(json.dumps([train.units, val.units, test.units], sort_keys=True, separators=(",",":")))`
    over the split **files** (per `data/splits/test.json` → `split_hash_method`).
  - The training code (`common/ts_data.split_hash_of('train','val')`) and everything downstream of
    it — `meta.json`, `model_artifact.json`, `metrics.json`, `portal_held_out.json` — record
    `split_hash = e89654ee2568fea26e68382555b8e71146ed44d1442284111f1c5611000b4b83`, which is the
    sha256 of the **train+val unit lists only** (a different input to the same hash function, over
    the same underlying split).
  - **Both refer to the same train/val/test split** — they are not two different splits, just two
    different things hashed (all three splits' unit lists as files, vs. only train+val's unit
    lists as computed at train time).
- **Seed:** `20260918` (`model_artifact.json` → `extras.seed`).
- **Code commit:** `null` — `model_artifact.json` → `extras.code_commit` was not recorded by the
  training run. Not fabricated here.
- **Runner:** `portal-package` (`extras.package_run.runner`).
- **Portal run id:** `bd19c981a17d` (`extras.package_run.run_id`).
- **model.onnx sha256:** `24d3a85af18ebfcab4bc709e44e0cf92cb40d1a10b01ac0322c86824295f9caa`
  (`meta.json` is not the source of this hash; confirmed identical across
  `model_artifact.json` → `extras.upload_checksums.onnx_model` and
  `extras.package_run` / `extras.evidence.held_out_test.model_onnx_sha256`).
- **Decision threshold:** `0.7765876650810243` (`meta.json` → `decision_threshold`).
- **ONNX opset:** 13. **Input shape:** `[1, 3, 64]`, `channels_first` (`meta.json`).

## 4. Held-out result (`1DCNN/portal_held_out.json`, `eval_split: held_out_test`)

| Metric | Value | Target | Result |
|---|---|---|---|
| recall @ FPR 0.01 | **0.318** (`0.3176865046102263`) | 0.90 | **MISS** |
| FPR | 0.0090 (`0.00903225806451613`) | ≤ 0.01 | met |
| PR-AUC | 0.939 (`0.9391306544817768`) | — | for reference |
| AUROC | 0.918 (`0.9175621231376578`) | — | for reference |

All four numbers above are read at `eval_split: "held_out_test"`
(`1DCNN/portal_held_out.json` → `evidence.headline` / `metrics`). The model **misses its recall
target by a wide margin** while meeting its FPR bound.

## 5. LOWO cross-validation spread (leave-one-worn-unit-out, from the package `metrics.json`)

Source: `1DCNN/runs/bd19c981a17d/model-package/metrics.json` → `cross_validation`.

| Held-out worn unit | recall @ FPR 0.01 | PR-AUC |
|---|---|---|
| IM-01R-A01 | 0.239 | 0.894 |
| IM-01R-A02 | 0.318 | 0.899 |
| IM-01R-A05 | 0.284 | 0.879 |
| IM-01R-A04 | 0.373 | 0.923 |

**Range: 0.24–0.37, mean 0.30** (`recall_at_fpr_min`/`_max`/`_mean` = `0.2393`/`0.3729`/`0.3035`).
This is real-data-only cross-validation over train+val worn units — it never touches A03 (the test
unit) — and gives an additive uncertainty band around the single-trial held-out number in §4.

## 6. Baseline comparison

Source: `1DCNN/baseline_check.json`.

- **Result:** `beats_baseline_val_only` — the 1D-CNN beats its declared MiniRocket+ridge baseline,
  **on validation only**.
- **Caveat, verbatim from the file:** *"the comparison was measured on validation only, the split
  that also picked the best epoch, and the training script reported it about itself: it is not a
  held-out result."*
- **`opens_gate`: `false`** — this comparison does not, by itself, satisfy any gate.

## 7. Caveats (stated plainly, no softening)

- **Headline rests on one worn unit.** The held-out `recall_at_fpr` (§4) is a single-trial
  pass/fail on `IM-01R-A03` — not a population estimate
  (`model_artifact.json` → `extras.evidence.held_out_test.headline.headline_single_trial_caveat`;
  same wording on the val-side headline names `IM-01R-A04` instead, per `metrics.json`).
- **`IM-01R` spans train/val/test by time** — a documented deviation from "never let one unit span
  train and test." Its test segment is the tail of a run whose head was trained on, which can
  flatter specificity (`data/splits/test.json` → `deviation`; same note repeated verbatim in
  `portal_held_out.json` → `evidence.headline.im01r_deviation_note`).
- **The test set has been evaluated 2–3 times.** `1DCNN/portal_held_out.json`
  (`evaluation_run_id 1c7097d874a8`, 2026-09-21) recorded `times_this_test_set_was_used: 2`; the
  later `model_artifact.json` evidence block (`evaluation_run_id 3d4f0fbc33a4`, 2026-09-23) records
  `times_this_test_set_was_used: 3`. Per both files' own caveat text: *"a number chosen after
  looking at earlier ones is no longer a clean held-out result."*

## 8. Gate decisions

### `kpi` gate — approved as a documented miss

Source: `gates.json` → `gates.kpi`. Status: `approved`.

> **sanjkcog**, 2026-09-23: *"Accept documented miss: held_out_test recall@FPR0.01 = 0.318 vs
> target 0.90 (miss); FPR 0.0090 <= 0.01 (met); PR-AUC 0.939. LOWO-CV recall 0.24-0.37 (mean
> 0.30). Baseline: beats_baseline_val_only (self_reported_val, not held-out). Caveats: single worn
> test unit IM-01R-A03; IM-01R spans train/test by time; test set evaluated 2-3 times. Model is
> below target, demo/internal use."*

### `return-upload` gate — approved automatically (ADR-0033)

Source: `gates.json` → `gates.return-upload`. Status: `approved`.

> **agentforge-ml return route (automatic)**, 2026-09-23: *"route portal (portal run
> bd19c981a17d): the portal trained this model and already holds it; a return upload would
> duplicate the run."*

## 9. Offline input hashes (`inputs/inputs.json`)

| Input | sha256 |
|---|---|
| `inputs/use_case.yaml` | `1db4afbe8113ba7398dd3a7a7ca78bdf87498f1164502fbea70a75c91fb51396` |
| `inputs/capability_manifest.json` | `455d98666972fe6b77e8190b19aed3484a627559d07027495bd28f09fd6bc340` |
| `inputs/scaffold/neuroedge_train_cnc-drift-on-powertrain-shop-for-car-prduction.py` | `f2325f0715e868a5f24fae15e17de9b59d80550a2a7770646827da2d5e800fb3` |
| `1DCNN/runs/bd19c981a17d/model-package` (zip) | `9a880fc4bc6f177687e741eeb698d159d0f1b4c378354b6d6474e8e8c03338e6` |
| — `model.onnx` (inside the package) | `24d3a85af18ebfcab4bc709e44e0cf92cb40d1a10b01ac0322c86824295f9caa` |
| — `meta.json` (inside the package) | `6708ed1dd7b11937d74e25ba52747117d73e2a62b7ec93f7f68d3e628475961e` |
| — `model_artifact.json` (inside the package) | `68fed2877977fc45bf391c8a8bf6a8cabc267f7fc9cb32f2db7d2a2014beaea6` |
| — `metrics.json` (inside the package) | `2b0f9b47185afe1941be806d38ade7966d7e974a2e16c21e4d67b31b07d579e4` |

## 10. Bottom line

This is a real, trained, ONNX-exported 1D-CNN that beats a MiniRocket baseline on validation, but
**misses its held-out recall target (0.318 vs 0.90) by a wide margin**, has a wide LOWO
cross-validation spread (0.24–0.37), rests its headline on a single worn test unit, carries a
documented train/test time-leakage deviation on one unit, and has had its test set looked at more
than once. It was approved as a **documented miss for demo/internal use only** — not for a
production recall claim. To use this model in the portal, promote run `bd19c981a17d` in
**Step 3 · Prepare Model → Compare Runs**.
