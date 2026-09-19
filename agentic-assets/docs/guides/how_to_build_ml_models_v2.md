# How to build an ML model with AgentForge — v2: the `/agentforge-ml` orchestrated flow

**Applies to:** every model the `ai-ml` discipline covers — vision (classification, detection,
segmentation), time series (anomaly detection, fault classification, forecasting, RUL), tabular, and
recommenders — built as an **orchestrated run** that ends with a validated model registered in the
NeuroEdge Web portal.

**What changed from v1.** [how_to_build_ml_model.md](how_to_build_ml_model.md) walks the five standalone
commands by hand and stops at a handoff package. This guide supersedes it for day-to-day use:
`/agentforge-ml` sequences the same commands, resolves the model folder **once**, adds the missing
**verify** step (download, measure, split per unit, withhold test), suspends across your training run
and **resumes**, evaluates on a held-out split you control, and hands you an upload package that
**returns the model to the portal**, so Part 3 → Prepare Device → Virtual Run → Deploy continue
unchanged. v1 remains the deep reference for *why* each step is shaped the way it is; read it once.

**What changed on 2026-09-18 (ADR-0025, ADR-0026, ADR-0027):**

- **No calls to the portal.** The model project takes its inputs as **files you download and drop** into
  `<folder>\inputs\incoming\`. The model goes back as a zip **you upload**.
- **Only the use case is required (ADR-0027).** It is the contract between the portal, the device and the
  model, so it is confirmed at a gate and locked. The device's **capability manifest** and the portal's
  **training scaffold** are optional: drop one and it is used, leave it out and the run goes on. Neither
  has a gate. So you can build for the Jetson, try the model on a laptop or VM, and only then deploy,
  without re-answering anything.
- **You approve every decision that shapes the model:** the use case at M0, the transfer scope at M2, the
  verified data at M4, the train/val/test split at M5, synthetic data (or skipping it) at M6, the model
  proposal at M7, the KPI result at M10 and the upload at M11.
- **Gates are enforced in code.** A stage cannot complete, and a later one cannot start, while a gate is
  owed.
- **`/usecase-audit`** checks at M0, M4, M8 and M11 that the use case, the data, the scaffold, the
  simulator export, the package and the device all agree.

Decisions this guide implements: `docs/decisions/ADR-0021-ml-artifact-destination.md` (where artifacts
live), `docs/decisions/ADR-0022-agentforge-ml-orchestrator-and-model-package-contract.md` (the
orchestrator and the model-package contract), `ADR-0024` (priced, scoped dataset transfer),
`ADR-0025` (offline inputs, review gates, enforced gates, `/usecase-audit`), `ADR-0026` (portal inputs
now; the use-case hash ignores trailing newlines), `ADR-0027` (only the use case is required; the
capability manifest and the scaffold are optional and advisory), and NeuroEdge-Web
`docs/decisions/ADR-0005-*.md` / `ADR-0008-*.md` (the portal side and the use-case lock).

**Contents**

- [The pipeline at a glance](#the-pipeline-at-a-glance)
- [Before you start](#before-you-start)
- [Two ways to run it](#two-ways-to-run-it)
- [`/agentforge-ml` arguments](#agentforge-ml-arguments)
- [Where everything lives](#where-everything-lives)
- [Stage by stage](#stage-by-stage)
- [The training wait — and how to resume](#the-training-wait--and-how-to-resume)
- [Integration with the NeuroEdge Web portal](#integration-with-the-neuroedge-web-portal)
- [Gates, approvals, and working offline](#gates-approvals-and-working-offline)
- [Worked example — CNC drift, end to end](#worked-example--cnc-drift-end-to-end)
- [Failure modes and what they mean](#failure-modes-and-what-they-mean)
- [Reference](#reference)

---

## The pipeline at a glance

| # | Stage id | What runs | Produces (under the model folder) | Gate |
|---|---|---|---|---|
| M0 | `destination` | the orchestrator — resolves the folder, **records the downloaded use case** (and a capability manifest, if you dropped one), locks the use case, audits it (device fit is advisory) | `README.md`, `run.json`, `gates.json`, `inputs/`, `use_case.lock.json`, `audit/M0.md` | **human: the use case** · **automatic: the lock builds, `audit/M0`** |
| M1 | `scout` | `/dataset-scout` → `ml-data-engineer` | `data/dataset-card.md` | **hard, automatic: licence** |
| M2 | `plan` | `/dataset-download` phase 1 → `ml-data-engineer` | `data/archive-manifest.tsv`, `data/fetch-plan.json` | **hard, human: scope** |
| M3 | `download` | `/dataset-download` phase 2 | `data/raw/**` (gitignored) | waits — resumable |
| M4 | `verify` | `/dataset-verify` → `ml-data-engineer` | `data/profile.json`, `data/splits/{train,val,test}.json`, `data/contract/` (TS), `data/portal_upload.zip`, `audit/M4.md` | **automatic: `audit/M4`** · **hard, human: data verified** |
| M5 | `label` | `/auto-label` (vision zero-shot → review · TS window rule), then `review split` | `data/label-manifest.md`, `data/split-review.md` | **hard, human: split review** |
| M6 | `synth` | `/synth-data` when chosen, then `review synth` (or a recorded skip) | `data/synthetic-recipe.md`, `data/synth-review.md` | **hard, human: synthetic review (a skip too)** |
| M7 | `model-select` | `/model-select` → `ml-modeler`, then `review model` | `model_proposed.md` (+ `model_proposed/v<N>.md`) | **hard, human: model proposal — re-run with an alternative on request** |
| M8 | `model-build` | use the scaffold if you dropped one, else the default template; `audit M8`, `/model-build` → `ml-modeler`, then `ml-eval-reviewer` | `inputs/scaffold/` (when provided), `<arch>/train.py · eval.py · config.yaml · requirements · RUN_ON_GPU.md` | **automatic: `audit/M8`** · **hard: eval methodology** |
| M9 | `train` | **you**, on your GPU (laptop / AWS VM) or the portal's trainer | `<arch>/runs/<run_id>/model-package/` | waits for you |
| M10 | `eval` | the orchestrator runs `eval.py` on the **withheld test split** | `metrics.json` (`eval_split: held_out_test`) | **hard: KPIs + beats the baseline** |
| M11 | `return` | `audit M11`, build + validate the upload zip; **you upload it in the portal** | `return/upload.zip`, `return.json` | **automatic: `audit/M11`** · **human: upload confirmed** |
| M12 | `data-simulator` | `/data-simulator` | `sim/<split>/…`, `sim/manifest.json` | — |
| M13 | `model-card` | `ml-modeler` | `model-card.md` | — |

Four rules hold the whole thing together:

1. **The destination is asked once** (M0). Every later stage and agent receives it. If a stage asks you
   for a folder, something is wrong.
2. **Nothing is transferred before it is priced** (M2). The archive's own index is read first — kilobytes
   — and the transfer is scoped against it at a gate. On the run this was built from, that step found 88%
   of a 44.58 GB archive to be a derivable duplicate and a further 56% out of scope, before a payload byte
   moved. A download that starts without a recorded scope decision is the bug this prevents.
3. **The test split never leaves the model folder.** Trainers — yours or the portal's — only ever see
   train + val. The number you publish is measured at M10 on data no trainer touched.
4. **ONNX is the only deployable artifact.** A model that cannot export (MiniRocket, some TS foundation
   models) is your *baseline*, never the thing you ship.

---

## Before you start

**1. A model-development project with the assets installed.** The owner's convention is one repo for
all model work — `NeuroEdge-ML-Models` — with a `neuroedge-ml-projects/` folder at its root. Install or
update the assets there:

```powershell
python "<Assets>\update_agentforge_claude_project.py" --project C:\SanjeevE\NeuroEdge-ML-Models
python "<Assets>\install.py" --project C:\SanjeevE\NeuroEdge-ML-Models --verify   # expect: zero drift
```

**2. `NEUROEDGE_ML_ROOT`.** Set it in that project's `.env` (the AgentForge block already has the line):

```dotenv
NEUROEDGE_ML_ROOT=C:\SanjeevE\NeuroEdge-ML-Models\neuroedge-ml-projects
```

With it set, every run from **any** repo proposes its folder under that root. Without it, the
orchestrator falls back to `<git root>/neuroedge-ml-projects/` if it exists, else asks for a full path.

**3. Keys — only for some sources.** Scouting needs none. Downloading needs:

| Source | Key |
|---|---|
| KIT, NASA PCoE / data.gov, Bosch GitHub, UCI, TFDS | none |
| Kaggle | `KAGGLE_USERNAME`, `KAGGLE_KEY` |
| Roboflow | `ROBOFLOW_API_KEY` |
| Hugging Face (gated/private sets only) | `HF_TOKEN` |
| PHM Society | manual registration |

All optional; an unset key stops the download with its name — it never falls back to a mirror whose
licence is not the rights holder's.

**4. A GPU box for M9.** Laptop (RTX-class) today, an AWS VM later — the flow is identical. Training
never runs inside AgentForge.

**5. The NeuroEdge Web portal, for you, not for the run.** You use it to create and validate the use
case, to download files, and at M11 to upload the model. The model project never calls it, so it does
not need to be running while `/agentforge-ml` runs.

**6. The three portal files, dropped into `<folder>\inputs\incoming\`.** The folder is created at M0,
with a README listing what goes there. File names don't matter: each file is recognised by its content.

| File | Read at | Where you get it |
|---|---|---|
| the use case (`<use-case-id>.yaml`) — **required** | M0 | portal **Step 1 · Edge Use Case Design** → validate the spec → **Download use_case.yaml** |
| the device capability manifest — **optional, advisory** | M0 | the target device's assessment (`ne-device-agent assess --local` writes `capability_manifest.json`), the file uploaded in **Step 2 · Target Device**. The portal has no download for it yet |
| the training scaffold (`neuroedge_train_<id>.py`) — **optional** | M8 | **Step 3 · Prepare Model → Model Strategy → Build my own → Script (.py)**. Without it, M8 uses the default template |

If you drop a capability manifest, the M0 audit compares the use case's target device and runtime with
it and **warns** on a mismatch. It never blocks: the model is built to the use-case lock, so the same
model can be tried on a laptop or VM before the Jetson. Swap the manifest any time, or leave it out.

**7. Data directory.** Raw downloads land outside git: `$NEUROEDGE_ML_DATA` if set, else
`<model-folder>/../.data/<dataset-id>/`. Both are gitignored; the `pre-commit-ml-artifact` hook blocks
blobs anyway.

---

## Two ways to run it

### A. Automated — one command, gates pause it

```text
/agentforge-ml "detect CNC machining drift from spindle-load, x_axis_error and vibration signals"
```

The orchestrator asks two kinds of question and nothing else:

- **The destination at M0.** Accept the proposed `cnc_drift-timeseries` or type another.
- **The gates:**
  - M0: confirm each input file;
  - M1: the licence, if unclear;
  - M2: the transfer **scope**;
  - M4: data verified;
  - M5: the split review;
  - M6: synthetic data, or skip it;
  - M7: the model proposal;
  - M10: the KPI decision;
  - M11: confirm your upload.

An audit gate is answered automatically unless the audit finds a FAIL. Everything between gates runs
without you.

It **stops** in three places:

- when a portal file it needs is not yet in `inputs\incoming\`;
- at M9, to wait for your training run;
- at M11, to wait for your upload.

`--resume` continues from any of them.

### B. Step by step — the same commands, standalone

Every stage command works on its own; pass the folder explicitly so no stage asks:

```text
/dataset-scout    "<objective>" --timeseries --dest <folder>
/dataset-download --dest <folder>              # phase 1 prices it, you pick a scope, phase 2 fetches
/dataset-verify   --dest <folder>              # reads what is already on disk; transfers nothing
/auto-label     --dest <folder>              # vision, or the TS window rule
/synth-data     "<what and why>" --dest <folder>
/model-select   "<objective>" --target jetson --dest <folder>
/model-build    --dest <folder>
/usecase-audit  --dest <folder>              # any time: are use case, data, simulator and device aligned?
```

Standalone commands don't ask the gates for you. The review packs (`python -m
agentforge.src.ml_contract.review split|synth|model --dest <folder>`) and `gate_state.py decide` do the
same job by hand.

Use this when you want to inspect between steps, or to re-run one stage. The standalone commands still
write `dataset-card.md`, `profile.json`, etc. in the same places, so an orchestrated run can pick up
where you left off with `--stage`.

### C. Join in the middle — `--stage`

You rarely start at scouting. Pick the entry point that matches what you already have:

| You have… | Start with |
|---|---|
| Nothing but an objective | `/agentforge-ml "<objective>"` |
| A dataset already downloaded | `--stage verify` (it profiles and splits what you have; `--data-dir` points at it) |
| A dataset **and** labels, decided splits | `--stage model-select` (it writes `dataset-card.md` from what you state) |
| A generated package, training done | `--stage eval` (put the package at `<arch>/runs/<run_id>/model-package/`) |
| A model the portal trained | `--stage eval` with `runner: portal` recorded in `model_proposed.md` |

Stages before the entry point are marked *supplied outside this run* — never fabricated.

---

## `/agentforge-ml` arguments

```text
/agentforge-ml "<objective>" [--use-case <file>] [--capability-manifest <file>] [--dest <folder>] [--stage <id>]
/agentforge-ml --status | --resume | --dry-run
```

| Argument | Meaning |
|---|---|
| `"<objective>"` | Plain-language objective. Drives the derived folder name (`<intent>-<modality>`) and the task family. Blank ⇒ you are asked. |
| `--use-case <file>` | The use-case YAML you downloaded from the portal. **Optional:** the usual way is to drop it into `inputs\incoming\`. Either way M0 does not proceed without it, and it locks it (`use_case.lock.json`). Every later stage reads the lock for channels, rate, window, classes and head (NeuroEdge-Web ADR-0008). |
| `--capability-manifest <file>` | A target device's `capability_manifest.json`. **Optional and advisory:** with one, the audits warn when the use case doesn't fit that device. Without one the run goes on. You can also drop it into `inputs\incoming\`. |
| `--dest <folder>` | Use this folder as-is; **no question asked**. Omitted ⇒ derived from the objective and confirmed once. |
| `--stage <id>` | Join at `destination · scout · plan · download · verify · label · synth · model-select · model-build · train · eval · return · data-simulator · model-card`. |
| `--status` | One screen: stage, gate, blocker, owner. No changes. |
| `--resume` | Reload `run.json` + `gates.json` from the folder and continue. This is how you come back after training. |
| `--dry-run` | Print the remaining stages and their owners. Writes nothing, spawns nothing. |

`/agentforge-ml` must run in the **main session** (it spawns agents and asks questions); do not
delegate it to a subagent.

---

## Where everything lives

```
<NEUROEDGE_ML_ROOT>/<intent>-<modality>/          e.g. cnc_drift-timeseries/
  README.md                 objective · modality · stage log (one row per command run)
  run.json  gates.json      orchestrator state — the run resumes from these alone
  inputs/                   the portal's files, as you downloaded them (ADR-0025 D-1)
    incoming/               the drop folder; its README says what goes here and where it comes from
      recorded/             dropped files already recorded, time-stamped
    inputs.json             per input: path · sha256 · generated_at · findings
    use_case.yaml           M0 — required; the lock is built from this copy
    capability_manifest.json M0 — optional, advisory: a target device
    scaffold/<file>         M8 — optional; its context and return writer are used, never its training body
  use_case.lock.json        M0 — the input contract, locked from the use case (ADR-0008)
  audit/                    M0 · M4 · M8 · M11 — the /usecase-audit reports (.md for you, .json for tools)
  data/
    dataset-card.md         M1 — YAML front matter (id, url, licence, units, split_rule, keys_required) + prose
    archive-manifest.tsv    M1 — the source's own index: path · offset · compressed · uncompressed · crc
                                 (kilobytes; every later scoping question is answered from this, for free)
    fetch-plan.json         M2 — the chosen scope, its spans, wire vs disk budget, projected wall-clock
    raw/                    M3 — the payload. GITIGNORED — never committed, never in the repo
    profile.json            M4 — what actually arrived: units, channels, rates, counts (claimed vs measured)
    splits/                 M4 — train.json · val.json · test.json + split_hash   ← test never leaves here
    contract_sources.json   M4 — how each locked channel is produced from this dataset's raw columns (TS)
    contract/               M4 — the data at the lock's rate, names and units; everything below reads it (TS)
    portal_upload.zip       M4 — train + val only, in the portal's upload layout
    label-manifest.md       M5
    split-review.md         M5 — the review pack the split gate approves
    synthetic-recipe.md     M6
    synth-review.md         M6 — the review pack (or the recorded skip)
  model_proposed.md         M7 — architecture (with reasoning), framing, baseline, runner, export, alternatives
  model_proposed/v<N>.md    M7 — superseded proposals when M7 is re-run with an alternative
  <architecture>/           M8 — one folder per architecture, e.g. 1DCNN/, MiniRocket/
    train.py eval.py config.yaml requirements.txt RUN_ON_GPU.md HANDOFF.md
    runs/<run_id>/model-package/    M9 — model.onnx · meta.json · model_artifact.json · metrics.json · calibration/
    runs/<run_id>/return/upload.zip M11 — what you upload in the portal
    runs/<run_id>/return.json       M11 — the local validation report and the registration id you pasted
  sim/                      M12 — simulator data per split + manifest.json (lock hash, purpose per file)
  model-card.md             M13
```

Folder name = `<intent>-<modality>`, derived from the objective: intent is 1–3 `snake_case` words for
*what is judged* (`cnc_drift`, `casting_crack`, `bearing_rul`); modality is `vision · timeseries ·
tabular · reco · text · audio · multimodal · genai`. Architecture is **not** in the name — one
objective is usually built more than once (a baseline and a deep model).

---

## Stage by stage

### M0 — `destination`
You see: *"It will be created under `C:\…\neuroedge-ml-projects` (from `NEUROEDGE_ML_ROOT`):
**cnc_drift-timeseries** — accept, or give a different name or a full path."* Existing folders that look
like the same objective are offered first, so a second run reuses rather than duplicates.
Then, in order:

1. **Record the inputs.** `intake check --need use_case,capability_manifest` picks up what you dropped
   into `inputs\incoming\`, copies each file into `inputs\` with its hash, and moves the original to
   `incoming\recorded\`. If the **use case** is missing it says where to get it, and the run **stops**;
   `--resume` checks again. A missing capability manifest is only reported (`[ABSENT]`), and the run
   continues. Two files of the same kind stop it: keep one.
2. **Confirm the use case** at its gate. You see the file, its hash, when it was generated, and every
   finding. A capability manifest, when provided, is shown for information and has no gate.
3. **Lock the use case** from the recorded copy. `use_case.lock.json` holds the channels (name, unit,
   per-sample definition, order, reduce), rate, window, stride, classes, head and target. If the YAML is
   incomplete, or disagrees with the objective (for example it names signals you didn't), the run
   **stops** with every problem listed. Fix the use case in the portal's Step 1, download it again, and
   re-run. The lock ignores line endings, a BOM and trailing newlines, so the portal re-saving the same
   spec does not count as a change.
4. **Audit use case ↔ device** (`audit/M0.md`). This checks that the task is supported, that the device
   takes ONNX, that the use case's runtime profile is one the device offers, that `device_profile_id`
   matches, that the device's sensors cover the channels, and that the manifest is recent. A FAIL
   stops here: fix the use case or pick the right device, or approve a documented exception.

**Verify:** `README.md` names your objective; `run.json` says `"sequence": "ml"` and records
`use_case_lock`; `run_state.py status` shows no `Owed:` line for `destination`.

### M1 — `scout`
`ml-data-engineer` searches the right portals for the family (PdM sources for time series, HF / Roboflow
/ Kaggle / TFDS for vision) and scores candidates against four gates: task fit, **licence**, size /
balance, label quality (for TS: can it be split per unit at all?). Output: a ranked table and one pick.
**Gate:** an unverifiable or non-commercial licence stops the run — a guess here becomes a legal problem
three repos downstream.
**Verify:** the card's front matter has `license_verdict`, `units`, `split_rule`, `keys_required`.

### M2 — `plan`  (transfers nothing)
`ml-data-engineer` reads the archive's index — captured at M1, or read now — and **prices the transfer
before any of it happens**. It reports total size, size grouped by file type, size grouped by logical
unit, and two or more candidate scopes with their cost. Grouping alone is what does the work: on the run
this flow was built from it exposed that 88% of a 44.58 GB archive was a PCHIP-upsampled duplicate of
data present in two other formats, and that only 7 of 33 experiments served the objective.

If the source is Hugging Face, Kaggle, Roboflow or TFDS, this stage says so and **uses that client** —
they already do resumable ranged transfer, and hand-rolling against them is worse than what exists.

**Gate — three outcomes:** *approve* a scope; *narrow* it and re-plan; *reject* and return to M1 with the
reason as a constraint. **A run cannot enter M3 without a recorded scope decision** — an unbounded
transfer is precisely the failure this stage exists to prevent.
**Verify:** `fetch-plan.json` names the scope, both budgets (wire and disk are different numbers), and
the rate the estimate came from.

### M3 — `download`
Executes the approved plan and nothing else. Resumable by design: each pass skips entries already on
disk at their declared size, so an interrupted transfer costs one span, not the run — and a transfer
*will* outlive its session. `--resume` reads `fetch-plan.json` and the files present; it never replays a
transcript. Raw data lands in `data/raw/`, gitignored, verified with `git check-ignore` before the first
byte.
**Verify:** bytes fetched against the approved budget, and no size mismatch in the log.

### M4 — `verify` (the step v1 lacked)
**Measure** → split → withhold → package → **you decide**. It transfers nothing; M3 did that, and this stage reads what is already on disk. `profile.json` is measured from
disk, never copied from the card; the two are shown side by side and a discrepancy is the finding
(the KIT dataset says 33 experiments on the record page and 32 in the paper — you find out here, not
during training). The split is per physical unit (experiment / cutter / machine), or chronological with
a one-window gap; a split that leaves any set single-class fails. `portal_upload.zip` contains train +
val only. When the channels you need come from two recorders (controller + DAQ), align them here with
`sensor_align` (see [Joining a second recorder](#joining-a-second-recorder--sensor_align-used-at-m4))
before profiling. A channel you cannot align is a missing channel.

For time series, M4 also builds the **contract dataset** (`data/contract/`). It is at the lock's rate,
names and units, cut inside split bounds. Its manifest records each unit's label and contiguous
segments per split, which is what lets M5 count windows without opening the test split. Then
`/usecase-audit` runs at **M4** (dataset ↔ lock), and its findings are part of what you approve.

**Gate — three outcomes:**
- *approve*;
- *reject with a reason*. The reason picks the next move: a missing channel re-scouts with it as a hard
  constraint, and "too small" tries the next candidate (at most two real candidates before synthetic is
  offered);
- *accept as hold-out*: real but insufficient data is kept as validation/test, and M6 synthesises the
  rare class.

**Verify:** `data/splits/test.json` exists and its unit ids appear in neither train nor val.

### M5 — `label`
Vision: Autodistill (Grounding DINO boxes, SAM masks) → Label Studio review → FiftyOne QA → YOLO
export with class names identical to the use case. Time series: no annotation tool — a **window rule**
(`majority` · `any` · `unit`) applied by code over the fixed splits, or `training_labels: none` for
normal-only anomaly detection; you review sample plots.

Then **the split review**, `data/split-review.md`, which you approve. For each split and class it gives
units, rows, hours and windows, with windows counted per contiguous segment because a window never
crosses a gap. It also shows the window rule, how the data was split and why, every recorded deviation,
the leakage controls, and the known limits. *Changes requested* sends you back to M4 (re-split) or M5
(re-label).
**Verify:** `label-manifest.md` states the rule, per-split counts and the `split_hash`.

### M6 — `synth` (you decide, and the decision is recorded)
You are asked whether to add synthetic data. It is recommended after *accept as hold-out*, or when a
class is rare **by windows**. When too few *independent units* is the problem, synthetic data can't fix
it: a generator only adds the variety you model into it.
- **Run it:** `/synth-data` builds a reproducible set (generator, params, seed). Its statistics are
  fitted on the train split only, and it is **stamped with the lock and split hash**. An unstamped set is
  refused.
- **The review pack**, `data/synth-review.md`, shows real train and synthetic data per class, the
  real:synthetic ratio before and after the cap (default: synthetic ≤ 50% of the real windows per
  class), the fidelity table, and how each split uses it. Train only; val and test stay real. M8 must
  compare a real-only model with a real+synthetic one **on real val**.
- **Skip it:** the skip and your reason go into the same pack, and you approve it like any other gate.

### M7 — `model-select`
Decides family, backbone, transfer recipe, **baseline** (MiniRocket for TS, gradient-boosted trees for
tabular, a linear probe for vision), **runner** (`package` = your GPU; `portal` = the portal's own trainer,
only for families it supports **and** whose split integrity is proven — for NeuroEdge time series that is
disallowed until Web ADR-0002 V-1/V-2 land), and the export path (ONNX; TensorRT/QNN derived later).
It also decides the **framing** for an anomaly head: supervised two-class, or normal-only (one-class).
All of this goes into `model_proposed.md`, **the page you approve**. It must cover the architecture (a
layer table with the reasoning for every size), the framing, synthetic use, augmentation, baseline,
evaluation, export, runner, and the **alternatives considered**. If you want another approach, answer
*changes requested* with it. The proposal is archived to `model_proposed/v<N>.md`, and M7 re-runs with
your reason as a binding constraint. Repeat until you approve.
**Verify:** `model_proposed.md` names the baseline and the runner, explains every size choice, and lists
the alternatives considered.

### M8 — `model-build`
First the **scaffold**, which is optional and never asked about (ADR-0027 D-3):
- **You dropped the portal's scaffold:** it is recorded and checked against the lock, and it is used.
  The check compares use-case id, class order, channel order, rate, window, stride, per-channel
  unit/reduce, target metric, `min_value` and `at_fpr`. A mismatch means it was generated from another
  version of the use case: M8 then **ignores it, builds from the default template, and tells you**, so a
  stale download never stops the run. From a matching scaffold, M8 takes **only** the context (ids, device,
  KPIs), the `neuroedge_return` package writer, and MLflow run naming and tags. It **never** takes its
  data loading, split, model, loss or metrics.
- **You didn't:** M8 builds with the **default template**. Nothing is asked. The default
  `train.py` writes the whole model package itself, including the baseline block.

Then `/usecase-audit` runs at **M8**. Then `ml-modeler` generates the code from the lock and the
approved `model_proposed.md`:
- `train.py` reads only `data/splits/{train,val}.json`, and `eval.py` is the only code that opens
  `test.json`.
- `train.py` ends by writing the **model-package**.
- On both paths it logs parameters, per-epoch train/val loss, and validation PR-AUC and recall at the
  target FPR to **MLflow**. Set `MLFLOW_TRACKING_URI` to the portal's MLflow server to see the run there;
  otherwise it logs to `./mlruns`, which `mlflow ui` opens. Test-split numbers never go to MLflow.

Finally `ml-eval-reviewer` reviews the code. A leakage or wrong-metric finding blocks the stage until it
is fixed.
**Verify:** `RUN_ON_GPU.md` exists; `grep test.json <arch>/train.py` returns nothing.

### M9 — `train` — see the next section.

### M10 — `eval`
The orchestrator runs `<arch>/eval.py --package <pkg> --split data/splits/test.json` (CPU is fine) and
writes `metrics.json` with `eval_split: held_out_test` and the `split_hash`. Then the gate: metrics
against the use case's KPIs (recall at the fixed FPR / mAP / …) **and** `beats_baseline: true`. You may
accept a documented miss; the acceptance is recorded, never implied.

### M11 — `return` (you upload)
Nothing is posted for you. The model project never calls the portal.
1. `/usecase-audit` runs at **M11**: the package's `meta.json` against the lock, the device, and the
   simulator export.
2. `return/upload.zip` is built with `model.onnx`, `meta.json`, `model_artifact.json`, `metrics.json`
   and `calibration/` when present. It is validated locally with the portal's own
   `neuroedge_return.validate_package` when that is installed (from a local path, never fetched).
3. **You upload the zip** in the portal: Step 3 · Prepare Model → Model Strategy → *Finished training
   return package*. Then paste the registration id, or the portal's refusal, at the `return-upload` gate.

A 422 from the portal means a defect in M8/M10 to fix, not a second opinion to argue with.

### M12 — `data-simulator`
Exports simulator data from the **same split data** the model was trained and evaluated on, stamped with the lock
of the returned model:
- **Time series:** CSVs at the contract rate, with the lock's channel names, in order.
- **Vision:** image folders built from each split's file list.

Train is for smoke tests (the model has seen it), val for device debugging and score parity, and test only for final
on-device acceptance, and only after M10. The device refuses a simulator file whose lock hash isn't the deployed
model's. The whole chain is in NeuroEdge-Device `docs/reference/how_to_design_model_simulator_web_in_sync.md`.

### M13 — `model-card`
Dataset id, licence and **attribution** (CC BY is only satisfied if it reaches the card and the
product NOTICE), split hash, seed, commit, baseline vs model, threshold, caveats.

---

## What does the acquiring — the helper modules

`/dataset-download` is not a prompt asking an agent to improvise a transfer. It calls four modules that
ship with AgentForge into your project at `agentforge/src/acquisition/`, the same way `agentforge/src/state/`
does. They carry **no modality awareness** — a time-series tar, a vision zip and an offline-RL archive all
present the same problem to them — so the same code serves every family, and only the *selector* changes.

| Module | What it owns | Why it exists as code, not advice |
|---|---|---|
| `archive_index` | Read a remote container's table of contents without its payload — ZIP central directory incl. ZIP64, tar headers incl. GNU base-256 sizes, ZIP-nested-in-tar. Emits `(path, offset, compressed, uncompressed, method, crc)` and persists it as `archive-manifest.tsv` | This is the whole economic argument: 64 KB of index priced a 44.58 GB archive. An octal-only tar parser silently reads a >8 GB member as size 0 — the kind of detail that has to live in tested code |
| `ranged_fetch` | HTTP byte-range client with the transport injected (so it tests without a network): asserts **206**, asserts the response length, enforces a cumulative budget *before* each request, serves backoff, and records the rate and throttle penalty it observed | `raise_for_status()` passes on 200 — a host ignoring `Range` returns the entire object, and code that trusts it parses full-file bytes as the requested window, producing offsets that are wrong but plausible |
| `fetch_plan` | Group by file type and by unit (this is where the savings are found), merge selections into spans, and cost them — wire bytes and disk bytes as **separate** budgets, plus a wall-clock projection | The merge threshold is derived, not guessed: `gap = measured_rate x per_request_penalty`. Pay for wasted bytes exactly when they are cheaper than another throttled request |
| `archive_extract` | Inflate members from a fetched span and write them — path-safe against `../` escapes, and **size-verified before the write**, not after | A span one byte short truncates its last entry while every other entry in it extracts perfectly. Verifying after writing leaves a wrong file on disk counted as a success |

You will not normally call these yourself — the command does. They matter to you for two reasons: a
transfer that fails now fails *loudly and specifically* rather than leaving plausible-looking wrong data
on disk, and the observed rate/penalty they record is what makes the next estimate accurate rather than
a guess.

> `requests` is the one new dependency, and only for the *caller* — the modules keep it out of their
> imports so they remain testable offline.

### Joining a second recorder — `sensor_align` (used at M4)

Industrial datasets often come from **two recorders**: the machine controller (e.g. a SINUMERIK Edge
export at 500 Hz, keyed by a cycle counter) and a bolted-on DAQ (accelerometer, force platform at
10 kHz, keyed by its own sample number). The channels you want are split across them. On the KIT CNC
dataset, spindle load and following error are in `hfdata.csv`, but vibration exists **only** in
`raw_data/*.mat`. The two start at different moments and their clocks drift apart. `sensor_align`
(shipped to `agentforge/src/sensor_align/`) puts the DAQ stream on the controller's clock and writes
one feature row per controller tick.

| Trap | What happens | What `sensor_align` does |
|---|---|---|
| The `.mat` is a MATLAB `timetable` (an MCOS object) | `scipy.io.loadmat` returns an opaque handle. `pymatreader` returns only `_TypeSystem`/`_Class`/`_ObjectMetadata`, with no signal data. Neither raises an error | Reads it with `mat-io`, which decodes it to a DataFrame (MAT v5 and v7.3). Octave has no `timetable` class, so it isn't an option |
| The decoded time index is truncated to whole seconds (`timedelta64[s]`) | A 10 kHz recording collapses to one index value per second | Rebuilds time from sample number ÷ rate and ignores the index |
| "Row 0 = row 0" | Wrong by seconds: KIT offsets run from −9 s to +6 s | Anchors on the NC program's **dwell**. The sync-pulse channel (`Sync_Signal`, driven by `TAKTGEBER`) pauses for exactly one `G04 F2`, and `hfblockevent.csv` logs that block against the controller counter. The gap must match the logged dwell, or the trial is refused |
| A fixed offset | Wrong by up to 98 ms by the end of a 20-minute run: the DAQ clock runs 75–81 ppm fast | Measures the rate from the sync edges (each half-period = 8 controller ticks), with a straight-line fit and a spike debounce. At shutdown (`M5`/`M30`) the generator stretches one phase, so the fit stops there and the fitted rate covers the last few seconds |
| Cross-correlating vibration against spindle power | No usable peak (r ≤ 0.25 on real trials) | Not used |

```bash
# its own throwaway env: mat-io needs numpy>=2.2, the voice stack pins numpy<2 on Python < 3.13
uv run --no-project --with-requirements agentforge/src/requirements-sensor.txt \
  python -m agentforge.src.sensor_align.align --root <dest>/data/raw/Dataset \
    --mat-glob "*/*/raw_data/*.mat" \
    --events-template "{mat_dir}/../processed_data/{trial}_hfblockevent.csv" \
    --out-template "<dest>/data/interim/{trial}_sensor.parquet" \
    --diagnostics "<dest>/data/interim/alignment.json"
```

The output has a `tick` column (the same values as `hfdata.csv`'s `CYCLE`, so you join on it) plus the
per-axis RMS and the `vibration_rms` / `force_rms` magnitudes. Each channel's whole-run mean is removed
first, so DC offset and preload don't count as vibration. The defaults are the KIT rig: 10 kHz / 500 Hz
/ 8 ticks per half-period / `^G04`. Override every one of them for another rig.

**Accuracy (KIT, 33/33 aligned):** clock drift is fully removed. The anchor is good to about one sync
half-period, because the generator restarts on its own phase grid: vibration leaves baseline a median
8 ms before spindle current, range −14 to +8 ms. That's fine for RMS features over windows of 0.2 s or
more. It's too coarse for timing events shorter than ~20 ms.

> A vibration channel that comes from a bolted-on sensor is only a valid **model input** if the edge
> device will have that sensor. Settle that in the channel contract at M4, not after training.

---

## The skills behind it

Two skills were added, and one existing skill grew a section. The commands read them; you may want to
read them when a decision looks arbitrary.

- **`skills/ENGINEERING/_mechanism/dataset-acquisition.md`** — the cross-pack mechanism. Owns the
  *ordering*: index first, then group by type, then group by unit, then merge, then (carefully) prefix.
  That order is the whole product — skipping to "optimise the transfer" is what produces a strategy that
  fetches data you never needed. Also owns the transport invariants and the rule against hand-rolling
  when a source ships its own client.
- **`skills/ENGINEERING/ai-ml/vision-ml.md`** — new, the vision counterpart to `time-series-ml.md`. Its
  most important section is **leakage-safe splitting**, which previously had no home: vision's
  characteristic leak is augmented or near-duplicate variants of one source image landing in both train
  and validation, which is how portal exports routinely ship. It inflates mAP and shows no symptom. Also
  carries dataset licence verdicts (MVTec AD is CC BY-NC — the default choice in every tutorial, and
  unusable in a product) and metric guidance.
- **`skills/ENGINEERING/ai-ml/time-series-ml.md`** — gained an *Acquisition profile*: the unit is the
  experiment, prefix-fetching is allowed only when the labelled condition holds across the whole run,
  and the redundancy to look for is a pre-synchronised or resampled copy alongside the raw streams.

---

## The training wait — and how to resume

At M9 the orchestrator writes `<arch>/HANDOFF.md` (where the package is expected, the exact command,
the runner), sets `run.json` to `waiting_external`, and **stops the session cleanly**. It does not poll.
While it trains, `train.py` logs to MLflow (see M8), so you can watch the loss and validation KPIs
live.

**Run training yourself:**

```powershell
# from RUN_ON_GPU.md — laptop or AWS VM, identical
cd <folder>\1DCNN
pip install -r requirements.txt
python train.py --config config.yaml          # writes runs/<run_id>/model-package/
```

The package that comes out is the contract:

```
runs/<run_id>/model-package/
  model.onnx           opset 13 · normalisation and (scalar head) Sigmoid folded into the graph
  meta.json            feature_order · window · stride · head · output_schema · decision_threshold · class_names
  model_artifact.json  portal schema + provenance + baseline block
  metrics.json         self-reported validation metrics (eval_split: self_reported_val)
  calibration/         optional, train-split samples for INT8
```

**Come back:**

```text
/agentforge-ml --resume
```

`--resume` looks for `<arch>/runs/*/model-package/{model.onnx, meta.json, model_artifact.json,
metrics.json}`. Found ⇒ `train` completes and M10 runs. Not found ⇒ it prints exactly what it is waiting
for and stops again. For `runner: portal`, **you** download the portal run's model and metadata into
that folder. The model project never fetches it.

Session breaks at any other stage resume the same way — state is `run.json` + `gates.json`, never the
transcript. `--status` tells you where you are.

---

## Integration with the NeuroEdge Web portal

Everything crosses as a **file you move by hand**; neither side calls the other (ADR-0025 D-1).

| Portal step | What agentforge-ml gives it, or takes from it | Direction |
|---|---|---|
| 1 · Edge Use Case Design — *Download use_case.yaml* (shown once the spec validates) | M0 records it and locks it. The portal saves the spec first and downloads its own saved copy, so the file is exactly what the portal holds | you download |
| 2 · Target Device — the device's `capability_manifest.json` | **optional.** M0 records it and the audit warns where the use case doesn't fit it. It comes from the device's assessment; the portal has no download yet | you copy it |
| 3 · Dataset — *Upload labelled dataset* | `data/portal_upload.zip` — train + val only, YOLO layout with `data.yaml` (vision) or CSV/JSON with `label` + unit columns (TS); class names identical to the use case | you upload |
| 3 · Prepare Model → Model Strategy — *Build my own → Script (.py)* | **optional.** M8 records the scaffold and checks it against the lock. It uses the scaffold's **context**, its `neuroedge_return` writer and its MLflow naming, never its training body (ADR-0025 D-5, ADR-0027 D-3). Without it, or when it belongs to another version of the use case, M8 uses the default template | you download |
| 3 · Model Strategy — *Finished training return package* | M11 builds and validates `return/upload.zip`; **you upload it** and confirm the registration id at the `return-upload` gate | you upload |
| 3 · Optimize | `extras.source = custom_return` ⇒ the export step becomes **validate** (checker, ORT load, opset, shapes); *Re-export ONNX* reads *Re-validate*; FP16/INT8 and runtime-EP projection unchanged | portal |
| 4–6 · Prepare Device → Virtual Run → Deploy | unchanged — the package entered the same manifests location the portal's own trainer writes | portal |
| Portal *evaluate* (`POST /models/{id}/evaluate`) | optional, done **by you in the portal**, never called by the model project: ONNX + a test zip → held-out metrics on the portal side. Also how you check a **portal-trained** model against *your* withheld split | you upload |

**What the portal checks at upload (and refuses with a named check):**
`onnx_checker` · `opset` (== 13) · `input_rank3` + static feature dim (TS) · `head_present` /
`output_length_matches_head` · `scalar_head_bounded` (a forward pass lands inside (0, 1)) ·
`class_names_match` (identical, same order, across `meta.json`, `model_artifact.json`, the use case) ·
`baseline_present` / `baseline_beats_flag` / `baseline_metrics_comparable`. Raw `.pt` files are hashed
and stored for provenance and **never opened**.

**AWS phase.** Point `model_artifact.json`'s `uri` / `extras.onnx_uri` at `s3://…/model.onnx` and upload
only the JSON files; the portal resolves the URI (S3-compatible endpoints via `AWS_ENDPOINT_URL`) when
Optimize runs. Validation is deferred until then and is marked as such.

**Portal-trained models.** When `model_proposed.md` records `runner: portal`, train in the portal as usual;
M8 still evaluates on your withheld split — the portal's numbers are the trainer's self-report, M8's are
independent.

---

## Gates, approvals, and working offline

State is two plain files in the model folder:

```powershell
$RUN   = "<folder>\run.json"
$GATES = "<folder>\gates.json"
python agentforge\src\state\run_state.py  --path $RUN --gates-path $GATES status
python agentforge\src\state\gate_state.py --path $GATES audit
```

Everything the orchestrator asks can be answered outside it:

- **Verified the data by hand?** Drop your `profile.json` and `splits/` in place and record the decision:
  `gate_state.py --path $GATES decide data/profile.json approved --identity <you> --reason "…"` (`rejected`
  with the reason; *accept as hold-out* is `approved` with the reason `hold-out only — synth required`, which
  makes M6 `synth` mandatory on resume).
- **Re-do a stage:** `run_state.py --path $RUN reopen <stage>` then `--resume`.
- **Gates are enforced (ADR-0025 D-4).** `complete <stage>` is refused until that stage's gates are approved,
  and `start <stage>` is refused while an earlier stage owes one. `status` prints every gate owed as `Owed:`.

| Stage | Gate id | Who answers | Pack you read |
|---|---|---|---|
| M0 | `inputs/use_case.yaml` | you | the intake summary (hash, generated-at, findings) |
| M0 · M4 · M8 · M11 | `audit/M0` · `audit/M4` · `audit/M8` · `audit/M11` | automatic when no FAIL; otherwise you | `audit/<checkpoint>.md` |
| M2 | `data/fetch-plan.json` | you | the priced scopes |
| M4 | `data/profile.json` | you | claimed vs measured, split summary |
| M5 | `data/split-review.md` | you | per split × class: units, rows, windows, hours; split rationale |
| M6 | `data/synth-review.md` | you | real + synthetic per class, the cap, fidelity, per-split use (or the skip) |
| M7 | `model_proposed.md` | you | the proposal; *changes requested* archives it and re-runs M7 |
| M8 | `eval-methodology` | you | the eval-methodology review |
| M11 | `return-upload` | you | what to upload; paste the registration id |

### Offline inputs from the portal (ADR-0025 D-1)

The model project never calls the portal. Download what it needs and record it:

```powershell
python -m agentforge.src.ml_contract.intake record --dest <folder> --kind use_case            --file <use-case.yaml>
python -m agentforge.src.ml_contract.intake record --dest <folder> --kind capability_manifest --file <capability_manifest.json>
python -m agentforge.src.ml_contract.intake record --dest <folder> --kind scaffold            --file <neuroedge_train_<id>.py>
python -m agentforge.src.ml_contract.intake show   --dest <folder>
```

Or drop the files into `inputs\incoming\` and let the run find them:

```powershell
python -m agentforge.src.ml_contract.intake init  --dest <folder>                   # creates the drop folder + README
python -m agentforge.src.ml_contract.intake check --dest <folder> --need use_case,capability_manifest
python -m agentforge.src.ml_contract.intake check --dest <folder> --need scaffold    # always 0: a missing scaffold is [ABSENT]
```

`check` exits 3 only when the **use case** is missing. Re-downloading and re-recording a changed use case
re-opens its gate and every audit, and means a re-lock. The capability manifest and the scaffold are
optional: recording, replacing or omitting one opens no gate and re-opens no audit (ADR-0027).

- **Wrong stage id?** The CLI names the run's sequence in the error (`ml`). An SDLC stage id against an
  ML run is rejected before anything is written.

### `/usecase-audit` — is everything still aligned?

`python -m agentforge.src.ml_contract.audit --dest <folder>` (or `/usecase-audit`) compares:
- the use case;
- the device's capability manifest, when provided (advisory: WARN at most);
- the contract dataset and splits;
- the synthetic set (its lock and split stamps);
- the scaffold, when provided (advisory: WARN at most);
- the simulator export;
- and, after M9, the model package.

It reports PASS / WARN / FAIL / NOT_YET per check. NOT_YET means the source isn't expected yet; a source
that should exist and doesn't is a FAIL. Run it standalone whenever something changes, for example after
re-downloading a use case or re-assessing the device. The orchestrator runs it with `--checkpoint` at M0,
M4, M8 and M11, writes `audit\<checkpoint>.md`, and approves the audit gate itself only when nothing
FAILs.

---

## Worked example — CNC drift, end to end

```text
# 0. Start (ML root set in .env; use case validated in portal Step 1; target device = the Jetson)
/agentforge-ml "detect CNC machining drift from spindle-load, x_axis_error and vibration signals"
  → proposes C:\SanjeevE\NeuroEdge-ML-Models\neuroedge-ml-projects\cnc_drift-timeseries — accept
  → creates inputs\incoming\ and STOPS: use_case missing
# drop <use-case-id>.yaml (Step 1 → Download use_case.yaml); optionally the Jetson's capability_manifest.json
/agentforge-ml --resume
  → records both (gate: confirm each) → locks the use case → audit M0: use case ↔ Jetson (gate: automatic)

# 1. scout    → pick: KIT multimodal CNC milling (CC BY 4.0) — all three channels; licence gate passes
#               captures archive-manifest.tsv (64 KB) — no payload yet
# 2. plan     → prices it from the index, no bytes moved:
#                 44.58 GB total; 39.27 GB (88%) is processed_data/*_synchronized.mat — a PCHIP-upsampled
#                 merge of data already present as CSV + raw .mat, so it is derivable and excluded
#                 4.31 GB in 41 merged ranges ≈ 2.3 h   (vs 169 requests, rate-limited to 2 files/hour;
#                 vs one 44.58 GB stream at a measured 0.94 MB/s = 13.2 h)
#               gate: approve scope
# 3. download → 4.31 GB into data/raw/ (gitignored), resumable
# 4. verify   → profiles 33 experiments (resolves the record-vs-paper 32/33 ambiguity), splits per
#               experiment 23/5/5, withholds test, builds portal_upload.zip
#               audit M4: contract dataset ↔ lock
#               gate: approve   (or: accept as hold-out → M6 synthesises the rare drift class)
# 5. label    → TS window rule: any; training_labels: unit ground truth
#               gate: split review — per split × class: units, windows, hours; split rationale
# 6. synth    → asked: run it or skip. Run → stamped set, capped at 50% of real windows per class
#               gate: synthetic review (a skip is approved the same way)
# 7. select   → model_proposed.md: 1D-CNN with the reasoning for every size; framing; MiniRocket+ridge
#               baseline; runner: package; export ONNX; alternatives considered
#               gate: approve   (or: changes requested "one-class instead" → archived as v1, M7 re-runs)
# 8. build    → uses the Step 3 scaffold if you dropped one, else the default template (no question)
#               audit M8 → 1DCNN/train.py eval.py … (MLflow logging); ml-eval-reviewer passes
# 9. train    → session stops: HANDOFF.md written

cd …\cnc_drift-timeseries\1DCNN ; python train.py --config config.yaml      # on the RTX laptop

/agentforge-ml --resume
# 10. eval   → eval.py on the withheld experiments: pr_auc, recall@fpr=0.01, event_f1 … beats_baseline
#              gate: approve
# 11. return → audit M11 → return/upload.zip built + validated locally
#              you upload it (Step 3 · Prepare Model → Model Strategy → Finished training return package)
#              → 200, source=custom_return → paste the registration id at the return-upload gate
# 12. sim    → sim/train, sim/val CSVs at 10 Hz + manifest (lock-stamped)
# 13. card   → model-card.md

# Portal: Optimize shows "Uploaded: model.onnx · opset 13 · validated ✓" → Prepare Device → Deploy
```

If you already had the KIT data on disk: `/agentforge-ml "<objective>" --stage verify` and point
`--data-dir` at it.

---

## Failure modes and what they mean

| Symptom | Meaning | Do |
|---|---|---|
| A stage asks for a destination | It was run standalone without `--dest`, or the run's `--dest` was lost | Inside a run this is a bug; standalone, pass `--dest` |
| The run stops with `[MISSING] use_case` (`intake check` exit 3) | The use case isn't in `inputs\incoming\` | Drop it there (the README says where it comes from), then `--resume`. `[ABSENT] capability_manifest` / `scaffold` is information only: both are optional |
| `[AMBIGUOUS]` in `intake check` | Two files of the same kind were dropped | Delete the one you don't want, then `--resume` |
| `REFUSED: complete <stage> — gates are not through` | A gate of that stage is pending, rejected, or never opened | `run_state.py status` lists every `Owed:` gate; answer them. Never edit `run.json` by hand |
| Intake says the use case `differs from the use case the lock was built from` | The use case really changed in the portal (trailing newlines, CRLF and BOM are ignored) | Re-lock (`--force`) and re-run the stages the change affects, or re-download the version you locked |
| `audit/M0` WARN on `device_profile_id` or `runtime_profile available` | Usually a **stale manifest**: one assessed by the pre-2026-09-16 device agent still uses the old ids (`nvidia-jetson-orin-devkit`, `ep-jetson-tensorrt`, `ort-cpu`, `cuda`), where the use case uses the current ones (`nvidia-jetson-orin-nano`, `ep-tensorrt`, `ort-core`, `ep-cuda`). Otherwise the use case really targets a different device | Re-assess the device with the current `ne-device-agent assess --local` and record the new manifest. **Don't** change the use case to the old ids. If it really is a different device you deploy to, fix the target in portal Step 2 and re-download. If it is only a test target (laptop / VM), the WARN is expected and nothing needs doing |
| A scaffold intake FAILs on class order, channels, rate, window, stride, units/reduce, metric or `at_fpr` | The scaffold was generated from another version of the use case. M8 ignores it and uses the default template | To have it used, download a fresh scaffold after the use case is final and re-run M8 |
| `UNSTAMPED: the synthetic manifest has no lock_sha256` | The synthetic set predates the stamping rule, or its generator doesn't write the stamps | Re-run `/synth-data`; the generator must write `lock_sha256` and `split_hash` |
| The generated `train.py` stops with `CLASSES[0] … does not look like the normal class` | The use case lists the anomaly class first, so a single-score head would invert every metric | Put the normal class first in the use case. Or, if the first class really is normal, set `NOMINAL_CLASS_CONFIRMED = True` |
| `422 baseline_beats_flag` at return | `beats_baseline` is `null` — no baseline was computed | Run the baseline in `train.py`; never hand-write the flag |
| `422 opset` | Exported at 17/18 | Export with the pinned constant (13) — the generated `train.py` already does; a hand edit changed it |
| `422 scalar_head_bounded` | Sigmoid not folded into the graph | Re-export; the head must end in `Sigmoid` |
| `422 class_names_match` | Order differs between dataset, meta and use case | Fix the order once in `data/dataset-card.md`; regenerate |
| `single-class held-out set` from `/evaluate` or M8 | Test split has one class | Re-split at M2 with stratification; a single-unit dataset cannot produce a valid split |
| `--resume` says "waiting for package" | Path or file names differ from the contract | `runs/<run_id>/model-package/` with all four files |
| Numbers dropped vs the portal's own metrics | Expected: M8 is held-out, the portal's are self-reported validation | Publish M8's; label the split |
| `runner: portal` refused for time series | Portal TS preprocessor still shuffles overlapping windows (Web ADR-0002) | Use `runner: package` until V-1/V-2 land |

---

## Reference

**Stage ids (run_state sequence `ml`):** `destination scout plan download verify label synth model-select
model-build train eval return data-simulator model-card`.

**Environment variables:** `NEUROEDGE_ML_ROOT` (model root) · `NEUROEDGE_ML_DATA` (raw downloads,
optional) · `KAGGLE_USERNAME` / `KAGGLE_KEY` · `ROBOFLOW_API_KEY` · `HF_TOKEN` (all optional) ·
`MLFLOW_TRACKING_URI` (where `train.py` logs; default `./mlruns`) · `AWS_ENDPOINT_URL` (S3-compatible
stores, portal side).

**Tools the run calls (`agentforge/src/ml_contract/`):** `lock` (M0 lock, `verify`) · `intake` (`init`,
`check`, `record`, `show`) · `ts_contract` (M4 contract dataset; `--labels-only` for older
folders) · `review` (`split`, `synth`, `model`, `model --archive`) · `audit` (`/usecase-audit`) ·
`data_simulator` (M12). The state tools are `agentforge/src/state/run_state.py` and `gate_state.py`.

**Skills the run applies:** `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`,
`agentic-assets/skills/ENGINEERING/ai-ml/{dataset-sourcing, data-labeling, synthetic-data,
model-architectures, pretrained-and-transfer, model-codegen, time-series-ml, ml-model-package}.md`.

**Decisions:** `docs/decisions/ADR-0021-ml-artifact-destination.md`,
`docs/decisions/ADR-0022-agentforge-ml-orchestrator-and-model-package-contract.md`,
`ADR-0024-dataset-acquisition-and-transfer-planning.md`,
`ADR-0025-agentforge-ml-offline-inputs-review-gates-and-usecase-audit.md`,
`ADR-0026-agentforge-ml-input-contracts-portal-artifacts-now-generic-later.md`; NeuroEdge-Web
`docs/decisions/ADR-0001` (export contract, opset 13), `ADR-0002` (evaluation integrity), `ADR-0003`
(baseline floor, threshold, upload enforcement), `ADR-0005` (portal side of this flow).

**Not yet covered** (see `docs/decisions/ADR-0023-*.md`): vision transformers as first-class
architectures, **visual** anomaly detection (today `anomaly_detection` means time series everywhere),
image/screen description (VLM), and reinforcement learning.

**Related guides:** [how_to_build_ml_model.md](how_to_build_ml_model.md) (v1 — the per-step deep dive),
[how_to_run_agentforge.md](how_to_run_agentforge.md) (the SDLC orchestrator this one mirrors).
