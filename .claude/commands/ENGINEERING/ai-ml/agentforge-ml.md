---
description: Orchestrate the ML model lifecycle — record the portal's offline inputs and lock the use case, dataset scout, acquire/verify, label, synth, model proposal, model build, external training wait, held-out eval, offline return to the platform, simulator data, model card — with a human gate at every data and model decision, a use-case alignment audit at four checkpoints, and state persisted to <dest>/run.json after every transition (ADR-0022, ADR-0025). Only the use case is a required input; the device capability manifest and the portal training scaffold are optional and advisory (ADR-0027).
argument-hint: "<objective>" [--use-case <file>] [--capability-manifest <file>] [--dest <folder>] [--stage <id>] | handoff [--dest <folder>] | --status | --resume | --dry-run
---

## Arguments

`$ARGUMENTS` — one of:
- `"<objective>"` — the ML objective for a new or continuing run, e.g. `"detect CNC machining drift from
  spindle-load, x_axis_error and vibration signals"`. If blank, ask for one before doing anything else.
- `--use-case <file>` — the use-case YAML **the human downloaded from the portal** (NeuroEdge-Web ADR-0008 L-1,
  ADR-0025 D-1). Optional: the usual way is to drop it into `<dest>/from-neuroedge/`; either way a new run does
  not proceed without it. It is the source of truth for channels, rate, window, classes and
  head; M0 records it as `<dest>/inputs/use_case.yaml` and locks it into `<dest>/use_case.lock.json`, and every
  later stage reads the lock.
- `--capability-manifest <file>` — a target device's `capability_manifest.json` (the device's
  `ne-device-agent assess` output, the file uploaded in portal Step 2 · Target Device). **Optional and advisory
  (ADR-0027 D-2):** with one, `/usecase-audit` reports how the use case fits that device, as WARNs. Without one the
  run goes on, and the device is assessed at deployment. It can be dropped in, swapped (Jetson → test laptop/VM →
  Jetson) or left out at any time; it has no gate and re-opens nothing.
- `--dest <folder>` — the model folder. Given → used as-is. Omitted → derived and confirmed **once** at the
  `destination` stage (`ml-artifact-destination`), then passed to every stage and agent. **No later stage asks.**
- `--stage <id>` — join the pipeline at an already-wired stage (a user who has a dataset starts at `verify` or
  `model-select`; one who has a trained package starts at `eval`). Valid ids are the `ml` sequence below. Earlier
  stages are marked *supplied outside this run*, never fabricated, and their gates are not demanded.
- `--status` — print stage, gates owed, blocker and owner, then stop.
- `--resume` — restore stage and gate state from `<dest>/run.json` + `gates.json` after a session break or an
  external training run, with no transcript replay, then continue if nothing blocks.
- `--dry-run` — print the remaining stages and which command/agent each would use; write nothing, spawn nothing.
- `handoff [--dest <folder>]` — what to carry to and from the portal next, for **this project's runner**
  (ADR-0031 D-4). Stage what is ready, then show the walk-through, then stop:
  `python -m agentforge.src.ml_contract.handoff stage --dest <dest>` and `… handoff show --dest <dest>`. Relay the
  walk-through as printed: this project's route, numbered in upload order, then the other routes, greyed. When
  the human reports an upload, record it with `… handoff sent --dest <dest> --artifact <NN> --registration
  "<the portal's id, or its refusal, verbatim>"`. Before telling anyone to upload, run `… handoff verify --dest
  <dest>`: a `STALE` copy is re-staged first, never uploaded.

## You run in the main session — never as a subagent

Do not delegate this command to an agent (D1, same as `/agentforge`): it spawns agents and asks the user through
`AskUserQuestion`; a subagent can do neither.

## No network seam to the portal (ADR-0025 D-1)

The model project never calls the portal API. The use case (required), and the capability manifest and the
training scaffold (both optional), arrive as **files the human downloaded**, recorded with a hash by
`python -m agentforge.src.ml_contract.intake record --dest <dest> --kind
<use_case|capability_manifest|scaffold|model_recommendation> --file <downloaded file>`. A model trained off the portal leaves the same way: M11 builds an upload zip, and the human uploads
it in the portal. A portal-trained model is already there, and M11 uploads nothing (ADR-0033). Never fetch a portal file, and never read one from a portal repo's working tree.

**Two folders name the boundary (ADR-0031 D-1).** At the top of every model folder:
`<dest>/from-neuroedge/` is what the portal (or the device) gives this run, and `<dest>/to-neuroedge/` is what
this run gives the portal. Each has a README. `from-neuroedge/` is the drop folder of ADR-0025 D-1a under a new
name. The old `inputs/incoming/` is still read for one release; `intake check` says so when it finds one.

| Drop in `from-neuroedge/` | Read at | Required? | Where it comes from |
|---|---|---|---|
| `<use-case-id>.yaml` | M0 | **required**, gated, locked | portal Step 1 · Edge Use Case Design → validate → **Download use_case.yaml** |
| `capability_manifest.json` | M0 | optional, advisory | the device's `ne-device-agent assess` output (uploaded in portal Step 2 · Target Device) |
| `neuroedge_train_<id>.py` | M8 | optional: used when provided, else the default template | portal Step 3 · Model Strategy → **Build my own** → **Script (.py)** |
| `model_recommendation.json` | M7 | optional, advisory: `/model-select` must answer it (ADR-0028 D-9) | portal Step 3 · Model Strategy: pick from the rated list, then export the recommendation |
| `<use-case-id>-model-package.zip` | M9 | required once asked for (portal runners) | portal Step 3 · Optimize → Downloads → **Download all as .zip** |
| the held-out result `*.json` | M10 | required once asked for (`portal-package`) | portal Step 3 · Train → Held-out evaluation → **Download result** |

**The two return kinds are unpacked by the run, never by hand (ADR-0031 D-2).** `intake check --need
model_package` reads the run id from the package's own `model_artifact.json` (`extras.package_run_id`, else
`extras.package_run.run_id`, else its `created_at` as `YYYYMMDDTHHMMSSZ`) and writes the four files to
`<arch>/runs/<run_id>/model-package/`. It refuses a package whose `lock_sha256` is not this project's lock,
naming both hashes. The file stays in `from-neuroedge/` and nothing is written. `--need held_out_result` matches
the result to that package by the sha256 of the `model.onnx` it evaluated, and writes it beside the package as
`portal_held_out.json`. **Never choose a run id, and never unzip a package yourself**: a run id chosen by hand
is provenance invented by hand.

**`to-neuroedge/` is a staging view, never a new home (ADR-0031 D-3).** `handoff stage` copies each artifact
from a path that does not move, numbered in upload order: `01-M8-training-package.zip`, `02-M9-test-bundle.zip`,
`03-M9-dataset-upload.zip` (fine-tune only), `04-M11-return-package.zip`, `05-M12-simulator-data.zip`,
`06-M12-demo-simulator-data.zip`. `handoff.json` records each source and its sha256, so `handoff verify`
catches a stale copy. Nothing reads from `to-neuroedge/`, and no tool learns a new path.

`python -m agentforge.src.ml_contract.intake check --dest <dest> --need <kinds>` records what was dropped (by
content, not by name). It opens a gate for the use case only, and **exits 3 only when the use case is missing**.
On exit 3, print its lines (the folder and where the file comes from) and **stop the session**. Do not continue,
guess or fetch. `--resume` runs the same check again. A missing optional file is reported as `[ABSENT]` with what
the run does without it: relay that line and **carry on**. Two files of one kind exit 1: ask which to keep.

## Stage sequence (`run_state` sequence `ml`)

| # | id | Command → agent | Produces (under `<dest>/`) | Gate (gate id in `gates.json`) |
|---|---|---|---|---|
| M0 | `destination` | this command | `README.md`, `run.json`, `inputs/{use_case.yaml, inputs.json}` (+ `capability_manifest.json` when provided), **`use_case.lock.json`**, `audit/M0.md` | **human:** `inputs/use_case.yaml` · **automatic:** the lock must build · `audit/M0` |
| M1 | `scout` | `/dataset-scout --dest <dest>` → `ml-data-engineer` | `data/dataset-card.md` | **automatic: licence** (opened on failure) |
| M2 | `plan` | `/dataset-download --dest <dest>` (phase 1) → `ml-data-engineer` | `data/archive-manifest.tsv`, `data/fetch-plan.json` | **human: scope** `data/fetch-plan.json` |
| M3 | `download` | `/dataset-download --dest <dest>` (phase 2) | `data/raw/**` (gitignored) | dependency-wait (resumable) |
| M4 | `verify` | `/dataset-verify --dest <dest>` → `ml-data-engineer` | `data/profile.json`, `data/splits/*.json` + `split_hash`, `data/contract/` (TS), `data/portal_upload.zip`, `audit/M4.md` | **automatic:** `audit/M4` · **human: data-verified** `data/profile.json` |
| M5 | `label` | `/auto-label --dest <dest>` (vision) / TS window rule, then **`review split`** | `data/label-manifest.md`, **`data/split-review.md`** | **human: split review** `data/split-review.md` |
| M6 | `synth` | `/synth-data --dest <dest>` when chosen, then **`review synth`** (or `review synth --skip-reason`) | `data/synthetic-recipe.md` + `data/synthetic/manifest.json`, **`data/synth-review.md`** | **human: synthetic review** `data/synth-review.md` (a skip is approved too) |
| M7 | `model-select` | pick up a **model recommendation** if one was dropped, `/model-select --dest <dest>` → `ml-modeler`, **`/model-fetch`** when the proposal names a pretrained base, then **`review model`** | **`model_proposed.md`** (+ `model_proposed/v<N>.md` for superseded proposals), `model/base/{loader.json, base-model-card.json, base-model-card.md}` (weights git-ignored) | **human: model proposal** `model_proposed.md` · **hard: base-model licence** `model/base-model-card.md` (opened only when the licence needs a human) |
| M8 | `model-build` | pick up a **scaffold** if one was dropped, `audit M8`, then `/model-build --dest <dest>` → `ml-modeler`, then `ml-eval-reviewer`. **Fine-tune path: no code is generated** | `inputs/scaffold/<file>` (when provided), `audit/M8.md`, `<arch>/train.py · eval.py · config.yaml · requirements · RUN_ON_GPU.md`, `<arch>/training-package.zip` | **automatic:** `audit/M8` · **hard:** `eval-methodology` |
| M9 | `train` | **external**: the runner approved at M7 (`portal-finetune` · `portal-package` · `offline`) | `<arch>/runs/<run_id>/model-package/` | dependency-wait |
| M10 | `eval` | this command runs `<arch>/eval.py` on `data/splits/test.json`, or accepts the portal's held-out result | `metrics.json` (`eval_split: held_out_test`), `<arch>/baseline_check.json` | **hard: KPIs on every path; `beats_baseline` only when a baseline is declared** (opened on a miss) |
| M11 | `return` | `audit M11`, then **`returns check`**: portal-trained → recorded, nothing uploaded; offline → build + validate the upload zip, **the human uploads it**; unclear → ask (ADR-0033) | `audit/M11.md`, `<arch>/runs/<run_id>/return.json` (+ `return/upload.zip` offline only) | **automatic:** `audit/M11` · `return-upload` (**automatic** on the portal route, **human** offline or when asked) |
| M12 | `data-simulator` | `/data-simulator --dest <dest>` | `sim/<split>/…` + `sim/manifest.json` (stamped with the lock of the returned model) | none |
| M13 | `model-card` | `ml-modeler` | `model-card.md` | none |

### The three paths (ADR-0028 D-1, D-4)

The runner is proposed at M7 and approved with the proposal. It decides what M8 and M9 do. A runner executes what
it is given and changes none of it.

| Stage | `portal-package` (training package) | `portal-finetune` (fine-tune) | `offline` |
|---|---|---|---|
| M0–M6 data | as written below | the same | the same |
| M7 | proposal + runner | proposal + runner + `/model-fetch` + the licence gate | proposal + runner |
| M8 | code, eval-methodology gate, `training-package.zip` | **no code is generated.** The eval-methodology gate reviews the data and the split only. The handoff is the dataset zip, the weights and `base-model-card.json` | code or vendor specs, plus a driver the user runs |
| M9 | wait; **the human uploads the package** to the portal, which runs it | wait; **the human uploads the dataset and the weights**; the portal's own trainer fine-tunes | wait; **the human runs the driver** on their own machine |
| M10 | on the package the human downloads from the portal | the same; `baseline: not_applicable` | on the local package |
| M11 | **no upload**: the portal trained it and already holds it; `returns portal` records the gate, the human promotes the run in Compare Runs | the same | build the return zip; it is how the model enters the portal at all |

Who owns what: on `portal-package` and `offline`, this run owns the method (architecture, recipe, training code,
evaluation). On `portal-finetune` it owns the inputs (the dataset, the split, the base-model choice and its
licence), and the portal's built-in recipe is accepted as it is. `portal-finetune` is allowed for loader
`ultralytics`, `torchvision` and `timm` only. `tao` is `offline` only. The `tao` template is not built yet
(ADR-0028 O-1).

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
4. **Record the offline inputs (ADR-0025 D-1, D-1a, D-2; ADR-0027).** `intake init --dest <dest>` creates the drop
   folder. When `--use-case` / `--capability-manifest` were given, record them directly (`intake record --kind
   use_case --file <path>`, `--kind capability_manifest`). Then **always** run `intake check --dest <dest> --need
   use_case,capability_manifest`. **Exit 3 → stop here** (the use case is missing), showing the drop folder; the
   run resumes with `--resume` once it is dropped. Present the use case's intake summary (file, sha256,
   generated-at, findings) and ask the human to confirm it is the right, current download. Record the decision. A
   FAIL in the summary is shown, and the human decides: re-download or approve with a reason.
   **The capability manifest has no gate.** When one was provided, show its summary for information. When none
   was, relay the `[ABSENT]` line and continue. Never stop or ask for it.
5. **Lock the use case (ADR-0008 L-1, L-2)** from the recorded copy:
   `python -m agentforge.src.ml_contract.lock build --use-case <dest>/inputs/use_case.yaml --dest <dest>
   [--expect-channels a,b,c] [--definitions <json>]`. Pass the signals the objective names as
   `--expect-channels`, so an objective that disagrees with the use case is caught here and not at the device.
   **A refusal stops the run**: show every listed problem and send the user to fix the use case (portal Step 1),
   then re-download and re-record it. Do not edit the lock, and do not work around a refusal. `--definitions` is
   only for per-sample definitions the portal schema cannot hold yet (ADR-0008 W2); the lock records that they came
   from the run. Then `run_state.py record-lock <dest>/use_case.lock.json`.
6. **Audit checkpoint M0:** `python -m agentforge.src.ml_contract.audit --dest <dest> --checkpoint M0` (the use
   case against its lock, plus use case ↔ device when a manifest was provided). No FAIL → its gate is approved
   automatically; show the WARNs anyway. **Every device finding is a WARN (ADR-0027 D-2):** the model is built to
   the lock, so a manifest from a test laptop or VM, or none at all, never blocks. Say plainly what the WARNs mean
   for deployment (for example "the use case asks for `ep-tensorrt`; this device offers only `ort-cpu`"). A FAIL
   here is about the use case itself → the human fixes and re-downloads it, or approves a documented deviation.
7. `complete destination --artifact README.md --artifact inputs/inputs.json --artifact use_case.lock.json
   --artifact audit/M0.md`.

**Every later stage reads the lock and never re-derives it**: channels, order, units, per-sample definition, rate,
window, stride, classes, head, `at_fpr`. After the lock the dataset and model are not redone, so only a
**model-contract** edit needs a re-lock (ADR-0030): a unit, the effective `at_fpr`, the class names or their order,
the head shape, the target metric (`recall` ≡ `recall_at_fpr`), or the channel names/order, `reduce`, rate, window
or stride. That is a FAIL naming the field, the locked value and the current value: re-lock (`--force`) and rebuild
the package, or revert the edit. Any other edit (target device, egress, `min_value`, definitions, business text)
changes the file hash only; it is a WARN, "the use case changed outside the contract; the lock still holds", and
the run goes on. `lock verify --dest <dest> --use-case <dest>/inputs/use_case.yaml` runs the same comparison.

### Stage loop (M1–M13)
For each stage not yet `complete`, in order: `start <id>` **before** the spawn → run the stage's command with
`--dest <dest>` (the command spawns its agent; pass the absolute path through) → generate the stage's pack and
ask its gate → `complete <id> --artifact <path>…` only after the artifact exists and the gates are through, or
`fail <id>` (two consecutive failures escalate to you).

**On every stage transition** (after each `start`, `complete` and `fail`), regenerate the index:
`python -m agentforge.src.ml_contract.handoff index --dest <dest>`. It writes `<dest>/00-START-HERE.md`: the
M0–M13 table with each milestone's status (done · gated · awaiting you · not started) and the folder its output
landed in (ADR-0031 D-5). The folders keep their names, because code reads them; this page is the map. **After
`complete` of M8, M11 and M12**, also run `handoff stage --dest <dest>`, so what goes to the portal is waiting in
`to-neuroedge/` without anyone zipping by hand.

**The guides (ADR-0031 D-6).** After `complete verify` (M4), `complete model-build` (M8) and
`complete data-simulator` (M12), spawn `ml-docs-writer` with `--dest <dest>` and the guide it owes:
`guides/dataset.md`, `guides/model.md` and `guides/demo.md`. It writes a draft and places it with
`handoff guide --dest <dest> --name <guide> --file <draft>`. A guide a person has edited is never overwritten:
the draft lands beside it as `<name>.proposed.md`. Relay that line, and let the human merge.

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
- **M7 model recommendation pick-up (no gate, ADR-0028 D-9):** before `/model-select`, run `intake check --dest
  <dest> --need model_recommendation`. It always exits 0 when the file is missing: relay the `[ABSENT]` line and
  carry on, exactly as before. When one was dropped, show its findings (all WARN at most) and
  `python -m agentforge.src.ml_contract.recommendation show --dest <dest>`.
- **M7 base model (ADR-0028 D-2, D-3):** when the proposal names a pretrained base, run `/model-fetch --dest <dest>`
  before the gate. It pins the revision, hashes the weights and writes `model/base/`. **Exit 3 = the hard licence
  gate `model/base-model-card.md` is open:** show the card, ask for one of the three outcomes (**approved**,
  **approved, internal and demo use only**, **rejected**), record it with `gate_state.py decide`, then
  `model_fetch licence --dest <dest> --outcome <…>`. An AGPL-3.0 (Ultralytics) model does **not** open the gate:
  it is recorded as approved for internal and demo use, with `distribution: internal_only` as information that
  travels and is shown. For the MVP nothing refuses on that flag. Say so once. Never guess a licence.
- **M7 the portal's "does not fit" is binding:** `recommendation check --dest <dest> --model-id <id>` exits 3 when
  the proposal picks a candidate the portal marked `does_not_fit`. Show the portal's reasons and ask the human.
  Only their decision lifts it: `recommendation check … --override "<their words>" --identity <user>`. It is
  recorded in `model/recommendation-override.json`, and you repeat it in the M7 gate's reason. `unverified` binds
  nothing. The human sees both opinions at the gate and decides. **Exit 4** means a recommendation was recorded
  but cannot be read: its ratings are unknown, which is not the same as "no file". Show the WARN and ask the human
  to export it again and drop it in `from-neuroedge/`. Do not go on as if nothing bound.
- **M7 model proposal (human):** `/model-select` writes `model_proposed.md`. Then `review model --dest <dest>` checks
  it covers architecture (with the reasoning for each size), framing, synthetic use, augmentation, baseline,
  evaluation, export, runner and **alternatives considered**, and opens the gate. Present the architecture table,
  the framing and the alternatives, and ask. `changes_requested` with an alternative (another framing,
  architecture or recipe) → `review model --dest <dest> --archive "<the human's reason>"` (moves the proposal to
  `model_proposed/v<N>.md`), `run_state.py reopen model-select`, and re-run `/model-select` with the reason as a
  **binding constraint**. Repeat until approved.
- **M8 scaffold pick-up (no gate — ADR-0027 D-3):** before generating anything, `intake check --dest <dest> --need
  scaffold`. It always exits 0 for a missing scaffold. Do not stop and do not ask.
  - **A scaffold was dropped** → it is recorded; show its findings for information. No FAIL → `/model-build` uses
    it (context, return writer, MLflow naming). A FAIL means it was generated from another use case: say so,
    **build from the default template instead**, and mention that a fresh download (portal **Step 3 · Model
    Strategy → Build my own → Script (.py)**) would be used on a re-run. The WARNs list what the lock overrides.
  - **`[ABSENT]`** → build from the default template, and say so in one line.

  `python -c "from agentforge.src.ml_contract.intake import usable_scaffold; print(usable_scaffold(r'<dest>'))"`
  prints the scaffold to use, or `None` for the default template.
- **M8 on the fine-tune path (`portal-finetune`):** generate **no code** and build **no package**. The scaffold
  pick-up is skipped. `ml-eval-reviewer` still runs, on the data and the split only (leakage, grouping, class
  balance), and its report is the `eval-methodology` gate. The handoff is `data/portal_upload.zip`, the weights in
  `model/base/weights/` and `model/base/base-model-card.json`.
- **M8 stored template:** for loader `transformers` with a classification head, start from
  `python -m agentforge.src.ml_contract.template write --dest <dest> --arch <Arch> --template
  transformers-classification`, then let `ml-modeler` adapt the recipe. Its `RUN_ON_GPU.md` says what is
  unverified. Repeat that to the human; do not soften it.
- **M8 audit checkpoint:** `audit --dest <dest> --checkpoint M8` (+ scaffold, advisory: WARN at most). Once a
  `training-package.zip` exists, the audit also checks its `package.json` against the lock.
- **M8 eval-methodology:** `ml-eval-reviewer`'s report is the gate (`gate_state.py open eval-methodology --stage
  model-build`); any **leakage** or **wrong-metric** finding loops back to `ml-modeler` before the stage completes.
- **M8 training package (ADR-0028 D-5):** once the eval-methodology gate is approved, zip what was built, so every
  runner executes the same thing: `python -m agentforge.src.ml_contract.package build --dest <dest> --arch <arch>
  [--baseline <dir>] [--data in-package|local|s3://bucket/prefix] [--catalogue-id <id>]`. Pass `--catalogue-id`
  when the proposal adopted a portal catalogue entry. **A time-series run always passes `--baseline`**: the build
  refuses without it, because M10's `beats_baseline` gate could otherwise never open (D-11). Ask the human once where the heavy files travel:
  **in-package** for small data, **local** when the runner is on this machine, **s3://…** for a runner on AWS. For
  s3 it prints an `aws s3 sync` command; **the human runs it**. Nothing here uploads. The test split is withheld
  from the package, and the command's output says which files. A refusal (an edited lock, a missing entry script,
  a secret-looking file) names the problem: fix it and rebuild, never pack around it. Add
  `--artifact <arch>/training-package.zip` to `complete model-build`. The zip can hold the dataset, so keep it out
  of git: `git check-ignore <arch>/training-package.zip`, and when it is not ignored, tell the human the one rule
  to add (`neuroedge-ml-projects/*/*/training-package.zip`). The project owns its `.gitignore`. The same build
  writes the **sealed test bundle** `data/portal_test.zip` (ADR-0028 D-12): the withheld test split, for the
  portal's Evaluate step only. It IS the test data, so it is kept out of git the same way
  (`neuroedge-ml-projects/*/data/portal_test.zip`) and is never sent to a trainer.
- **M10 KPIs (ADR-0028 D-11):** compare `metrics.json` to the use case's targets (recall at the fixed FPR / mAP /
  …) on **every** path. A miss opens the hard gate (`kpi`, stage `eval`) with the numbers side by side.
  **`beats_baseline` is required only when a baseline is declared.** Run
  `python -m agentforge.src.ml_contract.kpi baseline --dest <dest> --arch <arch> --model-package <pkg>`: it writes
  `<arch>/baseline_check.json`, and exit 1 means the same `kpi` gate opens (the model does not beat its declared
  baseline, or the flag is missing). **The verdict says which split the comparison was measured on.** It prefers
  the held-out comparison (`eval.py` scored the model and its baseline on the test split, or the portal's accepted
  result carries it). `beats_baseline_val_only` means only the training script's own validation comparison exists:
  that is not a clean pass. Repeat its caveat in the KPI gate's text and in the model card. On the fine-tune path there is no training package and no baseline: it
  records `baseline: not_applicable`, and that is not a miss. Never evaluate the pretrained model as it is and
  call it a baseline: its classes differ, so it proves nothing. The user may accept a documented miss; the
  acceptance is recorded, never implied.

### `train` (M9) — the external wait
1. `start train`, then write `<dest>/<arch>/HANDOFF.md`. It names **the runner approved at M7** and says who
   does what. Nothing here uploads, and nothing here trains.
   - **`portal-package`: the portal is the runner.** The human uploads `<arch>/training-package.zip` (its sha256
     included) in the portal (Step 3 · Model Strategy → Custom development → **Training package**). The portal
     executes it and changes none of it. They upload `data/portal_test.zip` in the portal's Evaluate step only.
     Running the same zip yourself per `RUN_ON_GPU.md` stays possible as a fallback; its result enters the portal
     as a return package.
   - **`portal-finetune`: the portal is the runner, with its own recipe.** The human uploads
     `data/portal_upload.zip`, the weights file from `model/base/weights/` and `model/base/base-model-card.json`.
     The portal matches the weights against the card by sha256. **Not built in the portal yet** (NeuroEdge-Web
     ADR-0011 S-4 and S-5 are designed, not built, as read at Web `456850c`): until they are, say so in
     `HANDOFF.md`, and offer `portal-package` or `offline` instead.
   - **`offline`: the human's machine is the runner.** Give the exact command from `RUN_ON_GPU.md`. Say which
     hardware it needs.

   In every case end with the output of `handoff stage` and `handoff show` (ADR-0031 D-4): what is staged in
   `to-neuroedge/`, which portal screen each file goes to, and what is awaited back in `from-neuroedge/`. Set
   `run.json` gate `{pending: true, stage: train, reason: waiting_external}` and **stop the session cleanly** — do
   not poll.
2. On `--resume`, by runner:
   - **`portal-package` / `portal-finetune`:** `intake check --dest <dest> --need model_package`. It unpacks a
     dropped package to `<arch>/runs/<run_id>/model-package/`, with the run id read from the package (ADR-0031 D-2).
     Exit 0 → `complete train --artifact <arch>/runs/<run_id>/model-package` and continue to M10. Exit 3 → relay
     the `[MISSING]` line (where to download it in the portal) and stop. Exit 1 `[REFUSED]` → relay every problem.
     A lock mismatch means the portal trained another use case's package, or one from before a re-lock: re-upload
     `to-neuroedge/01-M8-training-package.zip`. Never unpack it by hand to get past a refusal.
   - **`offline`:** look for `<arch>/runs/*/model-package/{model.onnx, meta.json, model_artifact.json,
     metrics.json}`, which the driver in `RUN_ON_GPU.md` writes. Found → complete as above. Not found → print what
     is awaited and stop.

   Nothing here fetches a package.

### `eval` (M10)
Run `<arch>/eval.py --package <pkg> --split <dest>/data/splits/test.json` (CPU is fine). It writes
`metrics.json` with `eval_split: held_out_test` and the `split_hash`, and it never reads train or val. Then the KPI
gate above.

**When the portal already evaluated it** (runner `portal-package`; ADR-0028 D-12): the portal ran this same
`eval.py` on the sealed `data/portal_test.zip`. The human downloads that result from the portal (Train → Held-out
evaluation → *Download result*) and drops it in `from-neuroedge/`. `intake check --dest <dest> --need
held_out_result` places it beside the package it scored, as `<arch>/runs/<run_id>/portal_held_out.json`,
matched by the model's sha256, never by a run id someone typed (ADR-0031 D-2). Then this command checks it,
offline:
`python -m agentforge.src.ml_contract.heldout accept --dest <dest> --arch <arch> --evidence
<arch>/runs/<run_id>/portal_held_out.json`. It is
accepted only when it is about THIS run: `held_out_test`, this run's lock, this run's test files by sha256, and the
training package in this folder. Accepted → use its metrics for the KPI gate, and repeat its caveats (a unit whose
file the training package also carried; a test set evaluated on more than once) in the gate's text. Refused → run
`eval.py` locally as above; never argue a refused result into the gate. Either way the KPI gate is opened here.

### `return` (M11) — only a model trained off the portal is uploaded (ADR-0025 D-1, ADR-0033)
1. `audit --dest <dest> --checkpoint M11`: the package's `meta.json` against the lock and the simulator export
   (and the device, as WARNs, when a manifest was provided). A FAIL here is a defect in M8/M10 to fix, not a
   deviation to approve lightly.
2. **Where was it trained?** `python -m agentforge.src.ml_contract.returns check --dest <dest>` prints the route
   and its evidence. A portal-trained model is already registered in the portal by the run that trained it, and
   uploading it back creates a duplicate run that becomes the portal's "latest" model (NeuroEdge-Web
   `return_package_service.py`, read at `9eed61b`). So:
   - **exit 0, `portal`** (the package came in through `from-neuroedge/` and its `model_artifact.json` names a
     portal runner, or none on a portal M7 runner) → `returns portal --dest <dest>`. It records `return-upload`
     automatically, writes `return.json` (`route: portal`), builds no zip and withdraws any unsent staged `04`.
     Tell the human, as information and not a gate: **promote that run** in portal *Step 3 · Prepare Model →
     Compare Runs → Promote*, so every later step (Optimize, Prepare Device, Virtual Run, Deploy) uses it. Go
     straight on to M12.
   - **exit 2, `offline`** → `returns build --dest <dest>`: it zips `model.onnx`, `meta.json`,
     `model_artifact.json`, `metrics.json` (+ `calibration/`) into `<arch>/runs/<run_id>/return/upload.zip`, runs
     `neuroedge_return.validate_package` when it is installed (from a local path or wheel, never fetched),
     records both in `return.json`, and opens the `return-upload` gate. Then step 3.
   - **exit 3, `ask`** → show the evidence and ask with `AskUserQuestion`: *trained on the portal* or *trained
     offline*. Record their answer as theirs: `returns portal --dest <dest> --identity <user> --reason "<their
     words>"`, or `returns build … --identity <user> --reason "…"` and then step 3. Never guess.
3. Offline only: `handoff stage --dest <dest>` copies the zip to `to-neuroedge/04-M11-return-package.zip`. Tell the
   human what to upload and where (portal **Step 3 · Prepare Model → Bring a trained model → Finished training
   return package**). Ask them to confirm the upload and paste the registration id or the portal's refusal. Record
   it: `approved` with the id in the reason, or `changes_requested` with the refusal, **and** `handoff sent --dest
   <dest> --artifact 04 --registration "<the same words>"`. A portal refusal (422) is a defect in M8/M10 to fix,
   not a second opinion to argue with. "Not uploaded yet" leaves the gate open and stops the session.
4. `complete return --artifact audit/M11.md --artifact <arch>/runs/<run_id>/return.json`.

### `data-simulator` (M12)
`/data-simulator --dest <dest>` exports simulator data from the **same split data** the model was trained and
evaluated on, stamped with the lock of the model M11 returned. Train and val are exported by default. Test is
exported only when the user asks for on-device acceptance, and is marked acceptance-only in `sim/manifest.json`.
It is generic: the lock's modality decides the format (time series → CSV at the contract rate; vision → an image
folder per split). Complete with `--artifact sim/manifest.json`. `/usecase-audit --dest <dest>` (standalone)
confirms the export against the lock.

**Then offer the demo replay (ADR-0031 D-7, D-8).** `/data-simulator --dest <dest> --profile demo
[--event-share 0.7] [--minutes 5]` composes a short replay from the same val rows, weighted toward the lock's
non-nominal class and interleaved, so the event is seen within the first minute. It is written to its own
`sim-demo/`, with its own manifest, and every file in it is `purpose: demo_only`. **It is an addition, never a
replacement.** `sim/` is untouched, stays the export the audit reads, and stays M12's artifact. Any rate
measured on the demo is meaningless as a measurement of the model. Say that whenever you mention the demo, and
never quote a number from it. The portal replays it labelled as a demonstration, and refuses it as acceptance
evidence.

### `model-card` (M13)
`ml-modeler` writes `<dest>/model-card.md`: dataset id + licence + attribution, split hash, seed, commit, baseline vs
model, threshold, known caveats, the offline inputs' hashes (`inputs/inputs.json`) and every gate decision that
approved a deviation. Add the stage-log row to `README.md`. The run is complete; Part 3 → device is the platform's.

## Flags

- `--status`: `run_state.py status` (prints the gates the next stage is owed) + `gate_state.py audit`, one screen,
  stop.
- `--resume`: `run_state.py resume` (exits 3 and names every owed gate when one blocks), then the stage loop from
  the first non-complete stage (train handled above). Resuming at M0, M7 or M8 re-runs `intake check` for that
  stage's files first, so files dropped since the stop are picked up. A run started before ADR-0025 will be owed the M0
  use-case gate, the M4 audit, and the M5/M6/M7 reviews. Record them in order, as above; each one is a real
  decision. A run started before ADR-0027 may still hold a pending `inputs/capability_manifest.json` or
  `inputs/scaffold` gate: it no longer guards anything, so ask the human once and record their answer to close it.
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
- Do not start a run past M0 without the use case recorded (`intake check` exit 0), and do not continue past a
  lock refusal.
- Do not stop, ask, or open a gate for a missing capability manifest or scaffold, and do not treat a device or
  scaffold WARN as a blocker (ADR-0027). Every other human gate (M2, M4, M5, M6, M7, M10, M11) is unchanged.
- Do not resample, rescale or convert units anywhere except the contract dataset (ADR-0008 L-3).
- Do not state what the portal, the device or another repo does unless you read it there. Name the file and the
  commit you read it at. A claim you could not check is written as `unverified`, never as a fact (ADR-0028 D-8).
- Do not download a model anywhere but `/model-fetch`, never at `latest` or a branch, and never write a key.
- Do not choose a model the portal marked `does_not_fit` without the human's recorded override.
- Do not generate training code on the fine-tune path, and do not require `beats_baseline` where no baseline is
  declared.
- Do not use the scaffold's training body. Only its context, its return writer and its MLflow tracking
  conventions are used (ADR-0025 D-5, ADR-0027 D-3).
- Do not choose a `<run_id>`, and do not unzip a portal package by hand. `intake check --need model_package`
  reads the run id from the package (ADR-0031 D-2).
- Do not make `to-neuroedge/` a path anything reads, and do not rename a load-bearing folder to match the
  milestone numbers. `00-START-HERE.md` is the navigation (ADR-0031 D-3, D-5).
- Do not cite, compare or gate on a number measured on a `demo_only` export, and do not complete M12 with one
  (ADR-0031 D-8).

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
