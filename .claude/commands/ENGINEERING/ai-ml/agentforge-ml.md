---
description: Orchestrate the ML model lifecycle — dataset scout, acquire/verify, label, synth, model select, model build, external training wait, held-out eval, return to the platform, model card — sequencing the existing ai-ml commands and agents, resolving the model folder once, and persisting state to <dest>/run.json after every transition (ADR-0022).
argument-hint: "<objective>" [--dest <folder>] [--stage <id>] | --status | --resume | --dry-run
---

## Arguments

`$ARGUMENTS` — one of:
- `"<objective>"` — the ML objective for a new or continuing run, e.g. `"detect CNC machining drift from
  spindle-load, x_axis_error and vibration signals"`. If blank, ask for one before doing anything else.
- `--dest <folder>` — the model folder. Given → used as-is. Omitted → derived and confirmed **once** at the
  `destination` stage (`ml-artifact-destination`), then passed to every stage and agent. **No later stage asks.**
- `--stage <id>` — join the pipeline at an already-wired stage (a user who has a dataset starts at `verify` or
  `model-select`; one who has a trained package starts at `eval`). Valid ids are the `ml` sequence below. Earlier
  stages are marked *supplied outside this run*, never fabricated.
- `--status` — print stage, gate, blocker and owner, then stop.
- `--resume` — restore stage and gate state from `<dest>/run.json` + `gates.json` after a session break or an
  external training run, with no transcript replay, then continue if nothing blocks.
- `--dry-run` — print the remaining stages and which command/agent each would use; write nothing, spawn nothing.

## You run in the main session — never as a subagent

Do not delegate this command to an agent (D1, same as `/agentforge`): it spawns agents and asks the user through
`AskUserQuestion`; a subagent can do neither.

## Stage sequence (`run_state` sequence `ml`)

| # | id | Command → agent | Produces (under `<dest>/`) | Gate |
|---|---|---|---|---|
| M0 | `destination` | this command | `README.md`, `run.json`, `gates.json` | none |
| M1 | `scout` | `/dataset-scout --dest <dest>` → `ml-data-engineer` | `data/dataset-card.md` | **hard, automatic: licence** |
| M2 | `plan` | `/dataset-download --dest <dest>` (phase 1) → `ml-data-engineer` | `data/archive-manifest.tsv`, `data/fetch-plan.json` | **hard, human: scope** |
| M3 | `download` | `/dataset-download --dest <dest>` (phase 2) | `data/raw/**` (gitignored) | dependency-wait (resumable) |
| M4 | `verify` | `/dataset-verify --dest <dest>` → `ml-data-engineer` | `data/profile.json`, `data/splits/*.json` + `split_hash`, `data/portal_upload.zip` | **hard, human: data-verified** |
| M5 | `label` | `/auto-label --dest <dest>` (vision) / TS window rule | `data/label-manifest.md` | hard for vision; soft for TS |
| M6 | `synth` | `/synth-data --dest <dest>` — only if M4 said *accept as hold-out* or a class is rare | `data/synthetic-recipe.md` | none |
| M7 | `model-select` | `/model-select --dest <dest>` → `ml-modeler` | `model-select.md` | none |
| M8 | `model-build` | `/model-build --dest <dest>` → `ml-modeler`, then `ml-eval-reviewer` | `<arch>/train.py · eval.py · config.yaml · requirements · RUN_ON_GPU.md` | **hard: eval-methodology** |
| M9 | `train` | **external** — laptop GPU / AWS VM / platform trainer | `<arch>/runs/<run_id>/model-package/` | dependency-wait |
| M10 | `eval` | this command runs `<arch>/eval.py` on `data/splits/test.json` | `metrics.json` (`eval_split: held_out_test`) | **hard: KPIs + `beats_baseline`** |
| M11 | `return` | `POST /models/{use_case_id}/upload-return-package` | registration response saved to `<arch>/runs/<run_id>/return.json` | none |
| M12 | `model-card` | `ml-modeler` | `model-card.md` | none |

State lives **inside the model folder**. Every `run_state.py` / `gate_state.py` call below uses:

```
RUN="<dest>/run.json"   GATES="<dest>/gates.json"
python agentforge/src/state/run_state.py  --path "$RUN" --gates-path "$GATES" <subcommand>
python agentforge/src/state/gate_state.py --path "$GATES" <subcommand>
```

## Procedure

### `destination` (M0)
1. Resolve `<dest>` per `ml-artifact-destination`: `--dest`, else derive `<intent>-<modality>` from the objective,
   resolve `ML_ROOT` (`NEUROEDGE_ML_ROOT` → `<git root>/neuroedge-ml-projects/` → ask), list existing folders that
   look like the same objective, and **ask once** — showing the full path and where the root came from.
2. Create `<dest>/README.md` (objective, modality, stage log) if missing.
3. `run_state.py --path "$RUN" init --objective "<objective>" --sequence ml [--start-stage <id>]`. If `run.json`
   exists, ask before `--force`; a decline means `--resume`.
4. `run_state.py start destination` → `complete destination --artifact README.md`.

### Stage loop (M1–M12)
For each stage not yet `complete`, in order: `start <id>` **before** the spawn → run the stage's command with
`--dest <dest>` (the command spawns its agent; pass the absolute path through) → check the stage's gate → `complete
<id> --artifact <path>…` only after the artifact exists, or `fail <id>` (two consecutive failures escalate to you).

Gate handling, in stage order:
- **M1 licence (automatic):** the card's pick must carry a licence compatible with the product. `unverifiable` or
  non-commercial ⇒ `gate_state.py open dataset-card --stage scout --type hard` and stop; the run does not proceed
  on a guess (ADR-0014 OQ-2 — hard).
- **M2 scope (human, ADR-0024 D-3a):** `/dataset-download` phase 1 prices the transfer from the archive's
  index and transfers nothing; you record the scope decision — **approve** a scope, **narrow** it, or
  **reject** and re-enter M1 with the reason as a constraint. **No run may enter M3 `download` without a
  recorded scope decision** — an unbounded transfer is the failure this gate exists to prevent.
- **M4 data-verified (human):** `/dataset-verify` opens the gate; you record the decision it presents:
  `approve` → continue; `reject` with reason → re-enter M1 with the reason as a constraint (second real candidate
  at most) or M6 if the user chooses synthetic; `accept-as-hold-out` → M6 is mandatory.
- **M5:** vision — human review is the gate; TS — the window rule is recorded, no gate.
- **M8 eval-methodology:** `ml-eval-reviewer`'s report is the gate; any **leakage** or **wrong-metric** finding
  loops back to `ml-modeler` before the stage completes.
- **M10 KPIs:** compare `metrics.json` to the use case's targets (recall at the fixed FPR / mAP / …) and require
  `beats_baseline: true`; either failing opens a hard gate with the numbers side by side. The user may accept a
  documented miss; the acceptance is recorded, never implied.

### `train` (M9) — the external wait
1. `start train`, then write `<dest>/<arch>/HANDOFF.md`: where the package will be expected
   (`<arch>/runs/<run_id>/model-package/`), the exact command from `RUN_ON_GPU.md`, and the runner recorded in
   `model-select.md` (`package` on laptop/VM, or `portal` when allowed). Set `run.json` gate
   `{pending: true, stage: train, reason: waiting_external}` and **stop the session cleanly** — do not poll.
2. On `--resume`: look for `<arch>/runs/*/model-package/{model.onnx, meta.json, model_artifact.json, metrics.json}`.
   Found → `complete train --artifact <package>` and continue to M10. Not found → print exactly what is awaited and
   stop. For `runner: portal`, fetch the run via the portal's `GET /use-cases/{id}/runs/{run_id}` and
   `download-model/raw|metadata` into the same folder first.

### `eval` (M10)
Run `<arch>/eval.py --package <pkg> --split <dest>/data/splits/test.json` (CPU is fine). It writes
`metrics.json` with `eval_split: held_out_test` and the `split_hash`, and it never reads train or val. Then the KPI
gate above.

### `return` (M11)
`POST /models/{use_case_id}/upload-return-package` with `model_artifact`, `metrics`, `onnx_model` (and
`calibration_data`); save the response. The platform re-validates (opset, head range, class order, baseline —
`ml-model-package`); a 422 here is a defect in M8/M10 to fix, not a second opinion to argue with.

### `model-card` (M12)
`ml-modeler` writes `<dest>/model-card.md`: dataset id + licence + attribution, split hash, seed, commit, baseline vs
model, threshold, known caveats. Add the stage-log row to `README.md`. The run is complete; Part 3 → device is the
platform's.

## Flags

- `--status`: `run_state.py status` + `gate_state.py audit`, one screen, stop.
- `--resume`: `run_state.py resume`, then the stage loop from the first non-complete stage (train handled above).
- `--dry-run`: print the remaining sequence with owners; never write `run.json`.

## Do NOT

- Do not ask for the destination inside a stage — it was answered at M0.
- Do not let any stage after M4 touch `data/splits/test.json` except `eval.py` — it does not exist until
  `verify` writes it.
- Do not transfer a byte before the M2 scope gate is recorded.
- Do not mark `train` complete without a package on disk; do not run training here.
- Do not present a metric without its `eval_split`; do not skip the baseline.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /agentforge-ml · Skills: ml-artifact-destination, dataset-sourcing, time-series-ml, ml-model-package`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/dataset-sourcing.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/time-series-ml.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/ml-model-package.md`
<!-- neuroedge-assets-patched source-version=4cf4279 -->
