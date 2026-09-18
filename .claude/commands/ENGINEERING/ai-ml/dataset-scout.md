# /dataset-scout — Find and evaluate a training dataset for an ML objective

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /dataset-scout · Skills: dataset-sourcing, time-series-ml, dataset-acquisition, ml-artifact-destination`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/dataset-sourcing.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/time-series-ml.md`
> - `agentic-assets/skills/ENGINEERING/_mechanism/dataset-acquisition.md`
> - `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`
<!-- neuroedge-assets-patched source-version=b5f0180 -->

## Arguments

`$ARGUMENTS` — the ML objective in plain language (e.g. `"detect cracked castings on a conveyor"`,
`"detect CNC machining drift from spindle-load and vibration signals"`). Optional `--vision` /
`--timeseries` / `--tabular` / `--reco` to hint the task family; inferred from the objective
otherwise (sensor/vibration/telemetry/drift/RUL wording ⇒ `--timeseries`).

`--dest <folder>` — where this command writes its artifacts. If omitted, the command proposes `<ML_ROOT>/<intent>-<modality>` and asks before writing (`agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`).

## What this does

Turns the objective into a **ranked shortlist of candidate datasets** with a defensible pick — the
first step of the `ai-ml` pipeline (ADR-0014). Spawns the `ml-data-engineer` agent, which applies the
`dataset-sourcing` skill. Produces the `dataset-card` artifact downstream stages cite.

## Procedure

0. **Resolve the destination** — apply `ml-artifact-destination`: use `--dest`, or propose `<ML_ROOT>/<intent>-<modality>` and **ask the user to confirm before writing anything**. Call the confirmed absolute path `<dest>` and pass it to every spawned agent. Inside an `/agentforge-ml` run `--dest` is always passed — **do not ask**; the orchestrator already confirmed it (ADR-0022 D-2).
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
3. Write the `dataset-card` to `<dest>/data/dataset-card.md` and add a stage-log row to `<dest>/README.md`
   (reference datasets by id/URL — never download blobs into the repo). The card opens with a **YAML front
   matter** that later stages parse — `id`, `url`, `license`, `license_verdict`, `modality`, `units` (the
   physical-unit key: experiment / cutter / machine / recording), `required_channels` or `classes`,
   `split_rule` (`grouped` | `chronological`), `expected_counts`, and `keys_required` (none | kaggle |
   roboflow | hf-gated | manual). Prose below it is for humans. End by printing the path.

4. **Capture the archive's index** for the picked dataset, and only its index (ADR-0024 D-1). Scouting already
   reads public metadata; the index costs kilobytes more and makes every later scoping question free — on the
   reference run a 64 KB index priced a 44.58 GB archive and answered every re-scope with no further requests.
   Write it to `<dest>/data/archive-manifest.tsv` via
   `agentforge/src/acquisition/archive_index.py` (`read_zip_index` / `find_tar_member` → `write_manifest`),
   capturing the CRC where the format carries one, and cite it from the card's front matter as `manifest`.
   Skip this only when the source ships a client that handles transfer itself (Hugging Face, Kaggle, Roboflow,
   TFDS) — see `dataset-acquisition`. **Still no payload: an index is not a download.**

## Next step

- Suitable dataset found → `/dataset-download` (price the transfer, scope gate, fetch), then `/dataset-verify`
  (measure, split per unit, withhold test, human gate), then `/auto-label` if labels are missing, then
  `/model-select`.
- No suitable dataset → `/synth-data`.
- Inside `/agentforge-ml` the orchestrator sequences these; the licence verdict is its hard M1 gate.
