# /dataset-scout — Find and evaluate a training dataset for an ML objective

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /dataset-scout · Skills: dataset-sourcing, time-series-ml`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/dataset-sourcing.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/time-series-ml.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Arguments

`$ARGUMENTS` — the ML objective in plain language (e.g. `"detect cracked castings on a conveyor"`,
`"detect CNC machining drift from spindle-load and vibration signals"`). Optional `--vision` /
`--timeseries` / `--tabular` / `--reco` to hint the task family; inferred from the objective
otherwise (sensor/vibration/telemetry/drift/RUL wording ⇒ `--timeseries`).

## What this does

Turns the objective into a **ranked shortlist of candidate datasets** with a defensible pick — the
first step of the `ai-ml` pipeline (ADR-0014). Spawns the `ml-data-engineer` agent, which applies the
`dataset-sourcing` skill. Produces the `dataset-card` artifact downstream stages cite.

## Procedure

1. Spawn **`ml-data-engineer`** with the objective and the task-family hint. Instruct it to:
   - Search **Hugging Face Datasets**, **Roboflow Universe**, **Kaggle**, and **TFDS** for candidates.
     For `--timeseries`, search the PdM sources instead — **NASA PCoE**, **PHM Society challenges**,
     **UCI**, **UCR/UEA** — per the dataset-sourcing skill's time-series section (and its
     non-commercial poison-pill list: Paderborn, MIMII/DCASE).
   - Score each against the four gates: **task-fit**, **license compatibility**, **class-balance/size**,
     **label-quality** (for time series, label-quality includes: is a chronological / per-unit split
     even possible from the metadata provided).
   - Return a ranked table + a single **picked** dataset, or the finding **"no suitable real dataset —
     recommend `/synth-data`"** with the reason.
2. Present the ranked report to the user. **License is blocking**: if the picked dataset's license is
   incompatible or unverifiable, say so and do not present it as usable (ADR-0014 OQ-2).
3. Write the `dataset-card` to the objective's data folder (reference datasets by id/URL — never
   download blobs into the repo).

## Next step

- Suitable dataset found → `/auto-label` (if labels are missing) then `/model-select`.
- No suitable dataset → `/synth-data`.
