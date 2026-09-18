---
description: Orchestrate the ML model lifecycle — record the portal's offline inputs and lock the use case, dataset scout, acquire/verify, label, synth, model proposal, model build, external training wait, held-out eval, offline return to the platform, simulator data, model card — with a human gate at every data and model decision, a use-case alignment audit at four checkpoints, and state persisted to <dest>/run.json after every transition (ADR-0022, ADR-0025).
argument-hint: "<objective>" [--use-case <file>] [--capability-manifest <file>] [--dest <folder>] [--stage <id>] | --status | --resume | --dry-run
---

## Arguments

`$ARGUMENTS` — one of:
- `"<objective>"` — the ML objective for a new or continuing run, e.g. `"detect CNC machining drift from
  spindle-load, x_axis_error and vibration signals"`. If blank, ask for one before doing anything else.
- `--use-case <file>` — the use-case YAML **the human downloaded from the portal** (NeuroEdge-Web ADR-0008 L-1,
  ADR-0025 D-1). Optional: the usual way is to drop it into `<dest>/inputs/incoming/`; either way a new run does
  not proceed without it. It is the source of truth for channels, rate, window, classes and
  head; M0 records it as `<dest>/inputs/use_case.yaml` and locks it into `<dest>/use_case.lock.json`, and every
  later stage reads the lock.
- `--capability-manifest <file>` — the target device's `capability_manifest.json` (the device's
  `ne-device-agent assess` output, the file uploaded in portal Step 2 · Target Device). Optional in the same way:
  drop it into `<dest>/inputs/incoming/`. M0 records it as `<dest>/inputs/capability_manifest.json`.
- `--dest <folder>` — the model folder. Given → used as-is. Omitted → derived and confirmed **once** at the
  `destination` stage (`ml-artifact-destination`), then passed to every stage and agent. **No later stage asks.**
- `--stage <id>` — join the pipeline at an already-wired stage (a user who has a dataset starts at `verify` or
  `model-select`; one who has a trained package starts at `eval`). Valid ids are the `ml` sequence below. Earlier
  stages are marked *supplied outside this run*, never fabricated, and their gates are not demanded.
- `--status` — print stage, gates owed, blocker and owner, then stop.
- `--resume` — restore stage and gate state from `<dest>/run.json` + `gates.json` after a session break or an
  external training run, with no transcript replay, then continue if nothing blocks.
- `--dry-run` — print the remaining stages and which command/agent each would use; write nothing, spawn nothing.

## You run in the main session — never as a subagent

Do not delegate this command to an agent (D1, same as `/agentforge`): it spawns agents and asks the user through
`AskUserQuestion`; a subagent can do neither.

## No network seam to the portal (ADR-0025 D-1)

The model project never calls the portal API. The use case, the capability manifest and the training scaffold
arrive as **files the human downloaded**, recorded with a hash by
`python -m agentforge.src.ml_contract.intake record --dest <dest> --kind <use_case|capability_manifest|scaffold>
--file <downloaded file>`. The model package leaves the same way: M11 builds an upload zip, and the human uploads
it in the portal. Never fetch a portal file, and never read one from a portal repo's working tree.

**The drop folder (ADR-0025 D-1a).** Every model folder has `<dest>/inputs/incoming/` with a README saying what to
drop there and where each file comes from:

| Drop | Needed from | Where it comes from |
|---|---|---|
| `<use-case-id>.yaml` | M0 | portal Step 1 · Edge Use Case Design → validate → **Download use_case.yaml** |
| `capability_manifest.json` | M0 | the device's `ne-device-agent assess` output (uploaded in portal Step 2 · Target Device) |
| `neuroedge_train_<id>.py` | M8 | portal Step 3 · Model Strategy → **Build my own** → **Script (.py)** |

`python -m agentforge.src.ml_contract.intake check --dest <dest> --need <kinds>` records what was dropped (by
content, not by name), opens each file's gate, and **exits 3 naming every file still missing**. On exit 3, print
its lines (the folder and where each file comes from) and **stop the session**. Do not continue, guess or fetch.
`--resume` runs the same check again. Two files of one kind exit 1: ask which to keep.

## Stage sequence (`run_state` sequence `ml`)

| # | id | Command → agent | Produces (under `<dest>/`) | Gate (gate id in `gates.json`) |
|---|---|---|---|---|
| M0 | `destination` | this command | `README.md`, `run.json`, `inputs/{use_case.yaml, capability_manifest.json, inputs.json}`, **`use_case.lock.json`**, `audit/M0.md` | **human:** `inputs/use_case.yaml`, `inputs/capability_manifest.json` · **automatic:** the lock must build · `audit/M0` |
| M1 | `scout` | `/dataset-scout --dest <dest>` → `ml-data-engineer` | `data/dataset-card.md` | **automatic: licence** (opened on failure) |
| M2 | `plan` | `/dataset-download --dest <dest>` (phase 1) → `ml-data-engineer` | `data/archive-manifest.tsv`, `data/fetch-plan.json` | **human: scope** `data/fetch-plan.json` |
| M3 | `download` | `/dataset-download --dest <dest>` (phase 2) | `data/raw/**` (gitignored) | dependency-wait (resumable) |
| M4 | `verify` | `/dataset-verify --dest <dest>` → `ml-data-engineer` | `data/profile.json`, `data/splits/*.json` + `split_hash`, `data/contract/` (TS), `data/portal_upload.zip`, `audit/M4.md` | **automatic:** `audit/M4` · **human: data-verified** `data/profile.json` |
| M5 | `label` | `/auto-label --dest <dest>` (vision) / TS window rule, then **`review split`** | `data/label-manifest.md`, **`data/split-review.md`** | **human: split review** `data/split-review.md` |
| M6 | `synth` | `/synth-data --dest <dest>` when chosen, then **`review synth`** (or `review synth --skip-reason`) | `data/synthetic-recipe.md` + `data/synthetic/manifest.json`, **`data/synth-review.md`** | **human: synthetic review** `data/synth-review.md` (a skip is approved too) |
| M7 | `model-select` | `/model-select --dest <dest>` → `ml-modeler`, then **`review model`** | **`model_proposed.md`** (+ `model_proposed/v<N>.md` for superseded proposals) | **human: model proposal** `model_proposed.md` |
| M8 | `model-build` | intake the **scaffold**, `audit M8`, then `/model-build --dest <dest>` → `ml-modeler`, then `ml-eval-reviewer` | `inputs/scaffold/<file>`, `audit/M8.md`, `<arch>/train.py · eval.py · config.yaml · requirements · RUN_ON_GPU.md` | **human:** `inputs/scaffold` · **automatic:** `audit/M8` · **hard:** `eval-methodology` |
| M9 | `train` | **external** — laptop GPU / AWS VM / platform trainer | `<arch>/runs/<run_id>/model-package/` | dependency-wait |
| M10 | `eval` | this command runs `<arch>/eval.py` on `data/splits/test.json` | `metrics.json` (`eval_split: held_out_test`) | **hard: KPIs + `beats_baseline`** (opened on a miss) |
| M11 | `return` | `audit M11`, then build + validate the upload zip; **the human uploads it** | `audit/M11.md`, `<arch>/runs/<run_id>/return/upload.zip`, `return.json` | **automatic:** `audit/M11` · **human:** `return-upload` |
| M12 | `data-simulator` | `/data-simulator --dest <dest>` | `sim/<split>/…` + `sim/manifest.json` (stamped with the lock of the returned model) | none |
| M13 | `model-card` | `ml-modeler` | `model-card.md` | none |

State lives **inside the model folder**. Every `run_state.py` / `gate_state.py` call below uses:

```
RUN="<dest>/run.json"   GATES="<dest>/gates.json"
python agentforge/src/state/run_state.py  --path "$RUN" --gates-path "$GATES" <subcommand>
python agentforge/src/state/gate_state.py --path "$GATES" <subcommand>
```

**Gates are enforced by `run_state.py`, not by this prose (ADR-0025 D-4).** `complete <stage>` is refused until
every required gate of that stage is `approved` and no other hard gate of the stage is unresolved. `start
<stage>` is refused while an earlier stage is open or owes a gate. A refusal names each gate. Answer it: never
work around it, and never mark a stage complete by hand in `run.json`.

### How every human gate is asked

1. Generate the pack (the `review` / `intake` / `audit` command named in the table). It opens the gate.
2. Show the human the pack's key content inline: tables, not just a path. Then ask with `AskUserQuestion`,
   offering **approve** and **changes requested** (and **reject** where the table names it). Put the recommended
   option first.
3. Record exactly what they chose:
   `gate_state.py decide <gate id> <approved|changes_requested|rejected> --identity <user> --reason "<their words>"`.
   Never record a decision the human did not make, and never pick an outcome for them.
4. `changes_requested` / `rejected` → do what the stage section says (re-run, re-enter an earlier stage), then
   regenerate the pack, which re-opens the same gate with its history kept.

## Procedure

### `destination` (M0)
1. Resolve `<dest>` per `ml-artifact-destination`: `--dest`, else derive `<intent>-<modality>` from the objective,
   resolve `ML_ROOT` (`NEUROEDGE_ML_ROOT` → `<git root>/neuroedge-ml-projects/` → ask), list existing folders that
   look like the same objective, and **ask once** — showing the full path and where the root came from.
2. Create `<dest>/README.md` (objective, modality, stage log) if missing.
3. `run_state.py --path "$RUN" init --objective "<objective>" --sequence ml [--start-stage <id>]`. If `run.json`
   exists, ask before `--force`; a decline means `--resume`. Then `start destination`.
4. **Record the offline inputs (ADR-0025 D-1, D-1a, D-2).** `intake init --dest <dest>` creates the drop folder.
   When `--use-case` / `--capability-manifest` were given, record them directly (`intake record --kind use_case
   --file <path>`, `--kind capability_manifest`). Then **always** run `intake check --dest <dest> --need
   use_case,capability_manifest`. **Exit 3 → stop here**, showing the missing files and the drop folder; the run
   resumes with `--resume` once they are dropped. Present both intake summaries (file, sha256, generated-at, findings) and ask the human to confirm each one is
   the right, current download. Record both decisions. A FAIL in a summary is shown, and the human decides:
   re-download or approve with a reason.
5. **Lock the use case (ADR-0008 L-1, L-2)** from the recorded copy:
   `python -m agentforge.src.ml_contract.lock build --use-case <dest>/inputs/use_case.yaml --dest <dest>
   [--expect-channels a,b,c] [--definitions <json>]`. Pass the signals the objective names as
   `--expect-channels`, so an objective that disagrees with the use case is caught here and not at the device.
   **A refusal stops the run**: show every listed problem and send the user to fix the use case (portal Step 1),
   then re-download and re-record it. Do not edit the lock, and do not work around a refusal. `--definitions` is
   only for per-sample definitions the portal schema cannot hold yet (ADR-0008 W2); the lock records that they came
   from the run. Then `run_state.py record-lock <dest>/use_case.lock.json`.
6. **Audit checkpoint M0:** `python -m agentforge.src.ml_contract.audit --dest <dest> --checkpoint M0` (use case
   ↔ device). No FAIL → its gate is approved automatically; show the WARNs anyway. A FAIL → present the findings;
   the human fixes the use case or picks another device (re-download, re-record, re-run the audit), or approves a
   documented deviation.
7. `complete destination --artifact README.md --artifact inputs/inputs.json --artifact use_case.lock.json
   --artifact audit/M0.md`.

**Every later stage reads the lock and never re-derives it**: channels, order, units, per-sample definition, rate,
window, stride, classes, head, `at_fpr`. If the use case changes, re-record it, re-lock (`--force`) and re-run
every stage from the first one the change affects. `lock verify --dest <dest> --use-case <dest>/inputs/use_case.yaml`
tells you whether it changed.

### Stage loop (M1–M13)
For each stage not yet `complete`, in order: `start <id>` **before** the spawn → run the stage's command with
`--dest <dest>` (the command spawns its agent; pass the absolute path through) → generate the stage's pack and
ask its gate → `complete <id> --artifact <path>…` only after the artifact exists and the gates are through, or
`fail <id>` (two consecutive failures escalate to you).

Gate handling, in stage order:
- **M1 licence (automatic):** the card's pick must carry a licence compatible with the product. `unverifiable` or
  non-commercial ⇒ `gate_state.py open data/dataset-card.md --stage scout --type hard` and stop; the run does not
  proceed on a guess (ADR-0014 OQ-2 — hard).
- **M2 scope (human, ADR-0024 D-3a):** `/dataset-download` phase 1 prices the transfer from the archive's
  index and transfers nothing; you record the scope decision — **approve** a scope, **narrow** it, or
  **reject** and re-enter M1 with the reason as a constraint. **No run may enter M3 `download` without a
  recorded scope decision** — an unbounded transfer is the failure this gate exists to prevent.
- **M4 contract (TS):** built by `python -m agentforge.src.ml_contract.ts_contract --dest <dest>` from the lock plus
  `data/contract_sources.json`. That step refuses sources in the wrong unit, and any time-split segment gap shorter
  than one window, and records each unit's label per split (`unit_labels`) so M5 never has to open the test split.
- **M4 audit checkpoint:** `audit --dest <dest> --checkpoint M4` (+ dataset ↔ lock) **before** the data-verified
  gate is presented; its findings are part of what the human sees.
- **M4 data-verified (human):** `/dataset-verify` opens the gate; you record the decision it presents:
  `approve` → continue; `reject` with reason → re-enter M1 with the reason as a constraint (second real candidate
  at most) or M6 if the user chooses synthetic; `accept-as-hold-out` → M6 is mandatory.
- **M5 split review (human, ADR-0025 D-3):** after the label step, `python -m agentforge.src.ml_contract.review
  split --dest <dest>` writes `data/split-review.md`: units, rows, windows and hours per split × class; the window
  rule; the split method, every recorded deviation and the leakage controls. Present the split × class table and
  the rationale, and ask. `changes_requested` → back to M4 (re-split) or M5 (re-label) as the reason says.
- **M6 synthetic review (human):** first ask whether to run `/synth-data`. Recommend it when M4 said
  *accept-as-hold-out* or a class is rare by windows, and say why either way. **Run** → `/synth-data`, then
  `review synth --dest <dest> [--cap-fraction <f>]`: real train and synthetic aggregated per class, the ratio
  before and after the cap, the fidelity table, and how each split uses it. **Skip** → `review synth --dest <dest>
  --skip-reason "<the human's reason>"`. Either way the gate is asked and recorded. A skip is never implied.
- **M7 model proposal (human):** `/model-select` writes `model_proposed.md`. Then `review model --dest <dest>` checks
  it covers architecture (with the reasoning for each size), framing, synthetic use, augmentation, baseline,
  evaluation, export, runner and **alternatives considered**, and opens the gate. Present the architecture table,
  the framing and the alternatives, and ask. `changes_requested` with an alternative (another framing,
  architecture or recipe) → `review model --dest <dest> --archive "<the human's reason>"` (moves the proposal to
  `model_proposed/v<N>.md`), `run_state.py reopen model-select`, and re-run `/model-select` with the reason as a
  **binding constraint**. Repeat until approved.
- **M8 scaffold intake (human):** before generating anything, `intake check --dest <dest> --need scaffold`.
  **Exit 3 → stop the session**, telling the human to download the training scaffold (portal **Step 3 · Model
  Strategy → Build my own → Script (.py)**) into `<dest>/inputs/incoming/`; `--resume` picks it up. Present the findings: a FAIL means it was generated from another use case (re-download it). The
  WARNs list what the lock overrides. Ask, and record.
- **M8 audit checkpoint:** `audit --dest <dest> --checkpoint M8` (+ scaffold).
- **M8 eval-methodology:** `ml-eval-reviewer`'s report is the gate (`gate_state.py open eval-methodology --stage
  model-build`); any **leakage** or **wrong-metric** finding loops back to `ml-modeler` before the stage completes.
- **M10 KPIs:** compare `metrics.json` to the use case's targets (recall at the fixed FPR / mAP / …) and require
  `beats_baseline: true`; either failing opens a hard gate (`kpi`, stage `eval`) with the numbers side by side.
  The user may accept a documented miss; the acceptance is recorded, never implied.

### `train` (M9) — the external wait
1. `start train`, then write `<dest>/<arch>/HANDOFF.md`: where the package will be expected
   (`<arch>/runs/<run_id>/model-package/`), the exact command from `RUN_ON_GPU.md`, and the runner recorded in
   `model_proposed.md` (`package` on laptop/VM, or `portal` when allowed). Set `run.json` gate
   `{pending: true, stage: train, reason: waiting_external}` and **stop the session cleanly** — do not poll.
2. On `--resume`: look for `<arch>/runs/*/model-package/{model.onnx, meta.json, model_artifact.json, metrics.json}`.
   Found → `complete train --artifact <package>` and continue to M10. Not found → print exactly what is awaited and
   stop. For `runner: portal`, **the human** downloads the portal run's package (raw model + metadata) into that
   folder. Nothing here fetches it.

### `eval` (M10)
Run `<arch>/eval.py --package <pkg> --split <dest>/data/splits/test.json` (CPU is fine). It writes
`metrics.json` with `eval_split: held_out_test` and the `split_hash`, and it never reads train or val. Then the KPI
gate above.

### `return` (M11) — offline (ADR-0025 D-1)
1. `audit --dest <dest> --checkpoint M11`: the package's `meta.json` against the lock, the device and the
   simulator export. A FAIL here is a defect in M8/M10 to fix, not a deviation to approve lightly.
2. Build `<arch>/runs/<run_id>/return/upload.zip` holding `model.onnx`, `meta.json`, `model_artifact.json`,
   `metrics.json` and `calibration/` when present. Run `neuroedge_return.validate_package` on it locally when the
   package is installed (from a local path or wheel, never fetched). Record its report in `return.json`, or record
   that it was not available.
3. Tell the human exactly what to upload and where (portal **Step 3 · Model Strategy → Finished training return package**). Open the
   gate: `gate_state.py open return-upload --stage return`. Ask them to confirm the upload and paste the
   registration id or the portal's refusal. Record it: `approved` with the id in the reason, or
   `changes_requested` with the refusal. A portal refusal (422) is a defect in M8/M10 to fix, not a second opinion
   to argue with.

### `data-simulator` (M12)
`/data-simulator --dest <dest>` exports simulator data from the **same split data** the model was trained and
evaluated on, stamped with the lock of the model M11 returned. Train and val are exported by default. Test is
exported only when the user asks for on-device acceptance, and is marked acceptance-only in `sim/manifest.json`.
It is generic: the lock's modality decides the format (time series → CSV at the contract rate; vision → an image
folder per split). Complete with `--artifact sim/manifest.json`. `/usecase-audit --dest <dest>` (standalone)
confirms the export against the lock.

### `model-card` (M13)
`ml-modeler` writes `<dest>/model-card.md`: dataset id + licence + attribution, split hash, seed, commit, baseline vs
model, threshold, known caveats, the offline inputs' hashes (`inputs/inputs.json`) and every gate decision that
approved a deviation. Add the stage-log row to `README.md`. The run is complete; Part 3 → device is the platform's.

## Flags

- `--status`: `run_state.py status` (prints the gates the next stage is owed) + `gate_state.py audit`, one screen,
  stop.
- `--resume`: `run_state.py resume` (exits 3 and names every owed gate when one blocks), then the stage loop from
  the first non-complete stage (train handled above). Resuming at M0 or M8 re-runs `intake check` for that stage's
  files first, so files dropped since the stop are picked up. A run started before ADR-0025 will be owed the M0 input
  gates, the M4 audit, and the M5/M6/M7 reviews. Record them in order, as above; each one is a real decision.
- `--dry-run`: print the remaining sequence with owners; never write `run.json`.

## Do NOT

- Do not call the portal API, and do not read portal files from a portal repo's working tree. Ask the human for
  the downloaded file.
- Do not ask for the destination inside a stage — it was answered at M0.
- Do not let any stage after M4 touch `data/splits/test.json` except `eval.py` — it does not exist until
  `verify` writes it.
- Do not transfer a byte before the M2 scope gate is recorded.
- Do not complete a stage over an unanswered gate, and do not answer a gate for the human.
- Do not mark `train` complete without a package on disk; do not run training here.
- Do not present a metric without its `eval_split`; do not skip the baseline.
- Do not start a run past M0 without the use case and capability manifest recorded (`intake check` exit 0), and do
  not continue past a lock refusal. Do not start M8 without the scaffold recorded.
- Do not resample, rescale or convert units anywhere except the contract dataset (ADR-0008 L-3).
- Do not use the scaffold's training body. Only its context and its return writer are used (ADR-0025 D-5).

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
