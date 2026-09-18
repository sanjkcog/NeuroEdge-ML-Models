---
description: Export simulator data from the same split data a model was trained and evaluated on, stamped with its use-case lock, for device replay and the portal's Virtual Run (NeuroEdge-Web ADR-0008).
argument-hint: --dest <folder> [--acceptance]
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
4. Add the stage-log row to `<dest>/README.md`, with the replay settings: `csv_replay` at `target_fps` =
   `sample_rate_hz` (or faster, since the device counts rows), and `feature_order` = the manifest's.

## Do NOT

- Do not build simulator data from anything but the model folder's split data.
- Do not resample, rescale or rename channels here. That happens once, in `data/contract/` (ADR-0008 L-3).
- Do not export the test split for anything but acceptance, and never before M10.
- Do not hand-edit `sim/manifest.json`; its `lock_sha256` is what the device checks.
