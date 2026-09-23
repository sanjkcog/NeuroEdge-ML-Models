---
description: Export simulator data from the same split data a model was trained and evaluated on, stamped with its use-case lock, for device replay and the portal's Virtual Run (NeuroEdge-Web ADR-0008).
argument-hint: --dest <folder> [--acceptance] | --dest <folder> --profile demo [--event-share <r>] [--minutes <m>]
---

# /data-simulator — Simulator data from the model's own split data (M12 of `/agentforge-ml`)

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /data-simulator · Skills: ml-model-package, time-series-ml, vision-ml, ml-artifact-destination`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/ml-model-package.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/time-series-ml.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/vision-ml.md`
> - `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`

## Arguments

`$ARGUMENTS` — `--dest <folder>` (always passed inside `/agentforge-ml`; standalone it is resolved once per
`ml-artifact-destination`), and `--acceptance` to also export the test split for final on-device acceptance.

`--profile demo [--event-share 0.7] [--minutes 5] [--splits val]` adds a **demo replay** in `sim-demo/` (ADR-0031
D-7). It is an addition to the export above, never a replacement.

## What this does

A simulator is only useful if it feeds the device **exactly** what the model was trained on. This command builds
simulator data from the model folder's own split data, never from a separate or hand-made set, and stamps it with the
`use_case.lock.json` hash of the model registered at M11. A device (or the portal's Virtual Run) can then refuse a
simulator file built for a different model (ADR-0008 D6).

It is generic. The lock's `modality` decides the format:

| Modality | Source | Output |
|---|---|---|
| `timeseries` | `data/contract/<unit>.parquet` (M4) | `sim/<split>/<unit>.csv`: `timestamp`, the lock's channels in lock order, `label`; rows `1/sample_rate_hz` apart |
| `vision`, `vision_anomaly` | the files each split lists (`units[].files`) | `sim/<split>/<unit>/` image folders |
| other | — | refused |

## Procedure

1. Run `python -m agentforge.src.ml_contract.data_simulator --dest <dest> [--acceptance]`. For time series, run it
   in the data-prep environment:
   `uv run --no-project --with-requirements agentforge/src/requirements-sensor.txt python -m …`.
2. It refuses rather than guesses when:
   - the lock was edited
   - `data/contract/` was built under a different lock
   - a split lists no files (vision)
   - `--acceptance` was passed before M10 `eval` is complete
3. Present `sim/manifest.json`: every file with its split, row or image count, labels and **purpose**:
   - `train` → `smoke_only`. The model has seen it, so scores prove nothing about accuracy.
   - `val` → `debug_and_parity`. Device debugging and threshold checks; the device score must equal `eval.py`'s.
   - `test` → `acceptance_only`. Final on-device acceptance. Never used to tune a threshold or choose a model.
4. **The demo replay (ADR-0031 D-7, D-8), when asked for.** Run
   `python -m agentforge.src.ml_contract.data_simulator --dest <dest> --profile demo [--event-share 0.7] [--minutes 5]`.
   It refuses until `sim/manifest.json` exists under the current lock, because a demo is an addition, never a
   replacement. It composes a replay from the same split rows (`val` by default; `test` only after M10):
   - **The event class** is the lock's non-nominal class. Where several classes are non-nominal, or no nominal
     class is declared, it is the minority class by window count. It is never named per use case.
   - **The unit of composition** is the modality's own: windows for time series, images for vision. The share is
     a share of those units, not of files or bytes.
   - **The order is interleaved:** nominal first, so the score is seen sitting low, then the crossing, spread
     through the replay rather than piled at the end.

   It writes `sim-demo/demo.csv` (time series) or `sim-demo/images/` (vision) and `sim-demo/manifest.json`, whose
   files are all `purpose: demo_only`. The manifest's `demo` block records the event class, the requested and
   achieved share, the minutes, `first_event_at_s`, and every stretch it used (unit, split, `block_start`). A
   class too small to fill the replay is repeated, and `repeated_classes` names it. Present that block and the
   caveat. **Every rate measured on the demo (false alarms, precision, recall) is meaningless as a measurement of
   the model.** `sim/` is untouched and stays the evidence; the audit never accepts a `demo_only` export as M12.
   The portal replays it labelled as a demonstration, and refuses it as acceptance evidence. Upload it from
   `to-neuroedge/06-M12-demo-simulator-data.zip` (`handoff stage`). Uploading it replaces the portal's current
   export for this use case, so re-upload `05-M12-simulator-data.zip` after the demo.
5. Add the stage-log row to `<dest>/README.md`, with the replay settings: `csv_replay` at `target_fps` =
   `sample_rate_hz` (or faster, since the device counts rows), and `feature_order` = the manifest's.

## Do NOT

- Do not build simulator data from anything but the model folder's split data.
- Do not resample, rescale or rename channels here. That happens once, in `data/contract/` (ADR-0008 L-3).
- Do not export the test split for anything but acceptance, and never before M10.
- Do not hand-edit `sim/manifest.json`; its `lock_sha256` is what the device checks.
- Do not write a demo into `sim/`, do not complete M12 with one, and never quote a number measured on it.
- Do not synthesise demo data. A demo that shows the model responding to data it never saw is a demo of the
  simulator; the demo is composed from the split, and the lock still stamps it.
