# Dataset Card — CNC Machining Drift Detection

- **Objective:** detect CNC machining drift from spindle-load, x_axis_error, and vibration signals
  and emit `drift_score` (0..1, alert threshold 0.7) and `drift_class` (e.g. `tool_wear`) for the
  edge device on PWT-LINE-3 (powertrain CNC line).
- **Task family:** `--timeseries` (multivariate drift / anomaly detection over sensor windows)
- **Use case:** `neuroedge/industries/manufacturing/cnc-machine-performance-drift-leading-to-production-loss/`
- **Date:** 2026-09-15
- **Stage:** sourcing only. No download, labeling, synthesis, or training has run.
- **Required channels:** `spindle_load`, `x_axis_error` (commanded − actual axis position), `vibration_rms`

> **Verification:** licenses below were read on 2026-09-15 from the primary record where one
> exists (KITopen, Bosch GitHub, data.gov, Kaggle API metadata). Licenses churn — re-check at
> download time. This is not legal review.

## Ranked candidates

| Rank | Source / id | Units / size | Channels (load · x-err · vib) | Labels | License → commercial verdict | Split feasibility | Recommendation |
|---|---|---|---|---|---|---|---|
| **1** | **KIT multimodal CNC milling dataset** — Ströbel et al. 2025, "A Multimodal Dataset for Process Monitoring and Anomaly Detection in Industrial CNC Milling". KITopen <https://publikationen.bibliothek.kit.edu/1000182633>, DOI `10.35097/hvvwn1kfwf7qt48z`; paper <https://pmc.ncbi.nlm.nih.gov/articles/PMC12621317/> | 33 experiments on the KITopen record (the paper says 32; 15 with anomalies), ~6 h, 1 industrial machine (DMG DMC 60 H), 3 component types | ✓ spindle load %, current, power, torque · ✓ per-axis control position and encoder position, plus axis current/load (500 Hz controller) · ✓ tri-axial acceleration (10 kHz) | 8 anomaly types (incl. tool wear, chatter, built-up edge, overload, material defect, irregular stock allowance) at the experiment level | **CC BY 4.0** (KITopen record) → ✅ commercial use OK with attribution | Per experiment (GroupKFold), stratified by component type | **PICK** — the only real set with all three channels, real industrial machine, drift-like anomaly labels, clean license |
| 2 | **Bosch CNC machining vibration** — Tnani, Feil, Diepold. <https://github.com/boschresearch/CNC_Machining> | 3 machines × 15 processes, 6 time frames (Oct 2018 – Aug 2021) | ✗ · ✗ · ✓ tri-axial accel @ 2 kHz | good / bad per recording (counts not stated in README — TBD) | Data **CC BY 4.0**, code BSD-3 → ✅ | **Per machine** and **chronological** (time frames) — the best cross-machine / cross-time hold-out available | Secondary: real cross-machine hold-out for the vibration branch only |
| 3 | **CNC Mill Tool Wear** (U. Michigan SMART lab) — <https://www.kaggle.com/datasets/shasun/tool-wear-detection-in-cnc-mill> | 18 experiments, 463–2,333 rows each @ 100 ms, wax workpieces | ✓ S1 current/power · ✓ `X1_CommandPosition` − `X1_ActualPosition` · ✗ | Per-experiment `tool_condition` (worn/unworn), visual-inspection pass | **CC0** as declared by the uploader (Kaggle API `licenseNameNullable`) → ✅, but uploader-asserted, no separate U-Mich license page found | Per experiment (18 units — thin) | Tertiary: x-axis-error sanity check only; wax + 10 Hz is far from a powertrain line |
| 4 | **NASA PCoE Milling** (Agogino & Goebel) — <https://catalog.data.gov/dataset/milling-wear> | 16 cases, multiple runs, measured flank wear VB | ✓ spindle motor current · ✗ · ✓ table/spindle vibration | Continuous flank wear per run | **U.S. Government Works** (data.gov) → ✅ | Per case (tool) | Optional: real wear-progression curve for calibrating `drift_score`; no axis channel |
| 5 | **PHM Society 2010** CNC milling — <https://phmsociety.org/phm_competition/2010-phm-society-conference-data-challenge/> | 6 cutters × ~315 cuts, force/vib/AE @ 50 kHz | ~ force, not spindle load · ✗ · ✓ | Flank wear per cut | Challenge data, informal terms; Kaggle "CC0" mirrors are not the rights holder → ⚠️ **unverified — blocked** | Per cutter (6 units) | Excluded until PHM Society terms are confirmed |
| 6 | UCI #447 Hydraulic / CWRU bearing | — | ✗ domain mismatch | — | usable / free | — | Excluded on task fit |
| — | 🔴 Paderborn KAt | — | vib only | — | **CC BY-NC 4.0** | — | Poison pill — never in a product build |
| — | 🔴 MIMII / ToyADMOS2 / DCASE task-2 | — | audio | — | **CC BY-NC-SA** | — | Poison pill — never in a product build |

## Pick: KIT multimodal CNC milling dataset (rank 1)

Passes all four gates:

1. **Task fit** — real industrial 5-axis milling machine; all three device channels are recorded
   natively; anomaly types include tool wear (maps to `drift_class: tool_wear`) and process
   anomalies (chatter, overload) that are drift-adjacent.
2. **License** — CC BY 4.0 on the repository of record. Obligation: attribute Ströbel et al. 2025
   + DOI in the model card and product NOTICE.
3. **Size / balance** — ~6 h at 500 Hz / 10 kHz gives ample windows, but only **33 independent
   experiments** (15 anomalous, the rest normal). The anomalous experiments are split across 8 types,
   so any single type (e.g. tool wear) has only a few experiments. Per-class counts are TBD —
   read the metadata at download.
4. **Label quality** — labels are per experiment and anomaly type, not per timestamp, and there is
   no continuous drift score. A per-window labeling rule is needed (`label-manifest`).

## Channel mapping (KIT → device contract)

| Device channel | KIT source signal | Derivation |
|---|---|---|
| `spindle_load` | spindle load (%) — 500 Hz controller JSON/CSV | direct; resample to device window rate |
| `x_axis_error` | X control position − X encoder position | computed; confirm sign convention and units (mm) at download |
| `vibration_rms` | acceleration X/Y/Z (g) — 10 kHz `.mat` | RMS over each device window (magnitude or chosen axis — fix once, record in `meta.json`) |

Channel order in `meta.json`: `spindle_load, x_axis_error, vibration_rms` (explicit — never sorted).
Controller (500 Hz) and sensor (10 kHz) streams must be aligned via the dataset's synchronized
`.mat` files before windowing.

## Leakage-safe split rule

- **Split by experiment first, window second.** No experiment may appear in two splits.
  `GroupKFold(groups=experiment_id)`, stratified by component type so train and test both see all three
  part geometries.
- Hold out ≥ 1 anomalous experiment per anomaly type used as a target class. With so few units, use
  **leave-experiments-out CV** and report the spread across folds, not a single number.
- Fit normalization on train folds only; persist mean/std in `meta.json`.
- **Cross-domain hold-out:** evaluate the vibration branch on Bosch (rank 2), split per machine, to
  measure generalization beyond one KIT machine.

## Known caveats

- **Single machine.** Everything learned is from one DMC 60 H. It will not transfer to PWT-LINE-3
  unchanged — plan on on-line calibration with plant data, and treat Bosch cross-machine results as
  the honest generalization estimate.
- **Few anomaly examples per type.** Complement with `/synth-data` (`agentforge_simulator/gen_input.py
  --profile cyclic_multichannel --channel-names spindle_load,axis_err,vibration_rms --drift ramp-recover
  --label-threshold 0.5 --seed <fixed> --recipe`) for the rare drift class only, keeping **KIT
  experiments as the real validation set** — never validate on synthetic.
- **No continuous `drift_score` label.** Options: (a) train a normal-only anomaly model and calibrate the
  score to the 0.7 threshold on held-out anomalous experiments; (b) use NASA Milling wear curves to shape
  a progression-based score. Decide at `/model-select`.
- Experiment count differs between the KITopen record (33) and the paper (32) — reconcile at download.
- Size of the KITopen archive is not stated on the record — store it outside git (data dir / DVC).

## Next step

Labels exist (experiment-level anomaly type), so skip `/auto-label` (vision-only anyway). Define the
per-window labeling rule in a `label-manifest`, optionally run `/synth-data` for the rare drift
class, then run `/model-select` (MiniRocket floor → 1D-CNN/InceptionTime, per `time-series-ml`).
