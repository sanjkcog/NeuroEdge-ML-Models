# How to build an ML model with AgentForge — v2: the `/agentforge-ml` orchestrated flow

**Applies to:** every model the `ai-ml` discipline covers — vision (classification, detection,
segmentation), time series (anomaly detection, fault classification, forecasting, RUL), tabular, and
recommenders — built as an **orchestrated run** that ends with a validated model registered in the
NeuroEdge Web portal.

**What changed from v1.** [how_to_build_ml_model.md](how_to_build_ml_model.md) walks the five standalone
commands by hand and stops at a handoff package. This guide supersedes it for day-to-day use:
`/agentforge-ml` sequences the same commands, resolves the model folder **once**, adds the missing
**verify** step (download, measure, split per unit, withhold test), suspends across your training run
and **resumes**, evaluates on a held-out split you control, and **returns the model to the portal**
so Part 3 → Prepare Device → Virtual Run → Deploy continue unchanged. v1 remains the deep reference for
*why* each step is shaped the way it is; read it once.

Decisions this guide implements: `docs/decisions/ADR-0021-ml-artifact-destination.md` (where artifacts
live), `docs/decisions/ADR-0022-agentforge-ml-orchestrator-and-model-package-contract.md` (the
orchestrator and the model-package contract), and NeuroEdge-Web `docs/decisions/ADR-0005-*.md` (the
portal side).

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
| M0 | `destination` | the orchestrator | `README.md`, `run.json`, `gates.json` | — |
| M1 | `scout` | `/dataset-scout` → `ml-data-engineer` | `data/dataset-card.md` | **hard, automatic: licence** |
| M2 | `plan` | `/dataset-download` phase 1 → `ml-data-engineer` | `data/archive-manifest.tsv`, `data/fetch-plan.json` | **hard, human: scope** |
| M3 | `download` | `/dataset-download` phase 2 | `data/raw/**` (gitignored) | waits — resumable |
| M4 | `verify` | `/dataset-verify` → `ml-data-engineer` | `data/profile.json`, `data/splits/{train,val,test}.json`, `data/portal_upload.zip` | **hard, human: data verified** |
| M5 | `label` | `/auto-label` (vision zero-shot → review · TS window rule) | `data/label-manifest.md` | hard for vision, soft for TS |
| M6 | `synth` | `/synth-data` — only when needed | `data/synthetic-recipe.md` | — |
| M7 | `model-select` | `/model-select` → `ml-modeler` | `model-select.md` | — |
| M8 | `model-build` | `/model-build` → `ml-modeler`, then `ml-eval-reviewer` | `<arch>/train.py · eval.py · config.yaml · requirements · RUN_ON_GPU.md` | **hard: eval methodology** |
| M9 | `train` | **you**, on your GPU (laptop / AWS VM) or the portal's trainer | `<arch>/runs/<run_id>/model-package/` | waits for you |
| M10 | `eval` | the orchestrator runs `eval.py` on the **withheld test split** | `metrics.json` (`eval_split: held_out_test`) | **hard: KPIs + beats the baseline** |
| M11 | `return` | `POST /models/{id}/upload-return-package` | `return.json` | — |
| M12 | `model-card` | `ml-modeler` | `model-card.md` | — |

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

**5. The NeuroEdge Web portal**, running, with the use case already created (its `use_case_id` is what
M11 returns the model to). Only needed from M8 onward (the scaffold context) and at M11.

**6. Data directory.** Raw downloads land outside git: `$NEUROEDGE_ML_DATA` if set, else
`<model-folder>/../.data/<dataset-id>/`. Both are gitignored; the `pre-commit-ml-artifact` hook blocks
blobs anyway.

---

## Two ways to run it

### A. Automated — one command, gates pause it

```text
/agentforge-ml "detect CNC machining drift from spindle-load, x_axis_error and vibration signals"
```

The orchestrator asks two kinds of question and nothing else: the **destination** at M0 (accept the
proposed `cnc_drift-timeseries` or type another), and the **gates** (licence at M1 if unclear, the
**scope** decision at M2, the data-verified decision at M4, the KPI decision at M10). Everything between
gates runs without you. At M9
it stops and waits for your training run; `--resume` continues.

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
```

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
| A model the portal trained | `--stage eval` with `runner: portal` recorded in `model-select.md` |

Stages before the entry point are marked *supplied outside this run* — never fabricated.

---

## `/agentforge-ml` arguments

```text
/agentforge-ml "<objective>" [--dest <folder>] [--stage <id>]
/agentforge-ml --status | --resume | --dry-run
```

| Argument | Meaning |
|---|---|
| `"<objective>"` | Plain-language objective. Drives the derived folder name (`<intent>-<modality>`) and the task family. Blank ⇒ you are asked. |
| `--dest <folder>` | Use this folder as-is; **no question asked**. Omitted ⇒ derived from the objective and confirmed once. |
| `--stage <id>` | Join at `destination · scout · verify · label · synth · model-select · model-build · train · eval · return · model-card`. |
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
  data/
    dataset-card.md         M1 — YAML front matter (id, url, licence, units, split_rule, keys_required) + prose
    archive-manifest.tsv    M1 — the source's own index: path · offset · compressed · uncompressed · crc
                                 (kilobytes; every later scoping question is answered from this, for free)
    fetch-plan.json         M2 — the chosen scope, its spans, wire vs disk budget, projected wall-clock
    raw/                    M3 — the payload. GITIGNORED — never committed, never in the repo
    profile.json            M4 — what actually arrived: units, channels, rates, counts (claimed vs measured)
    splits/                 M4 — train.json · val.json · test.json + split_hash   ← test never leaves here
    portal_upload.zip       M4 — train + val only, in the portal's upload layout
    label-manifest.md       M5
    synthetic-recipe.md     M6
  model-select.md           M7 — family, backbone, baseline, runner, export path
  <architecture>/           M8 — one folder per architecture, e.g. 1DCNN/, MiniRocket/
    train.py eval.py config.yaml requirements.txt RUN_ON_GPU.md HANDOFF.md
    runs/<run_id>/model-package/    M9 — model.onnx · meta.json · model_artifact.json · metrics.json · calibration/
    runs/<run_id>/return.json       M11
  model-card.md             M12
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
**Verify:** `README.md` names your objective; `run.json` says `"sequence": "ml"`.

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
val only.
**Gate — three outcomes:** *approve*; *reject with a reason* (the reason picks the next move: a missing
channel re-scouts with it as a hard constraint; "too small" tries the next candidate — at most two real
candidates before synthetic is offered); *accept as hold-out* (real but insufficient: keep it as
validation/test and synthesize the rare class at M4).
**Verify:** `data/splits/test.json` exists and its unit ids appear in neither train nor val.

### M5 — `label`
Vision: Autodistill (Grounding DINO boxes, SAM masks) → Label Studio review → FiftyOne QA → YOLO
export with class names identical to the use case. Time series: no annotation tool — a **window rule**
(`majority` · `any` · `unit`) applied by code over the fixed splits, or `training_labels: none` for
normal-only anomaly detection; you review sample plots.
**Verify:** `label-manifest.md` states the rule, per-split counts and the `split_hash`.

### M6 — `synth` (conditional)
Runs only after *accept as hold-out* or when a class is rare. Synthesizes the rare class; keeps the real
hold-out; emits a reproducible recipe (generator, params, seed). Never validate on synthetic only.

### M7 — `model-select`
Decides family, backbone, transfer recipe, **baseline** (MiniRocket for TS, gradient-boosted trees for
tabular, a linear probe for vision), **runner** (`package` = your GPU; `portal` = the portal's own trainer,
only for families it supports **and** whose split integrity is proven — for NeuroEdge time series that is
disallowed until Web ADR-0002 V-1/V-2 land), and the export path (ONNX; TensorRT/QNN derived later).
**Verify:** `model-select.md` names the baseline and the runner.

### M8 — `model-build`
`ml-modeler` reads the portal's scaffold **context** for your use case (classes, resolution, target
device, KPIs), owns the training body, and generates the package. `train.py` reads only
`data/splits/{train,val}.json`; `eval.py` is the only code that opens `test.json`. `train.py` ends by
writing the **model-package** through the portal's `neuroedge_return` helper. Then `ml-eval-reviewer`
reviews the code: a leakage or wrong-metric finding blocks the stage until fixed.
**Verify:** `RUN_ON_GPU.md` exists; `grep test.json <arch>/train.py` returns nothing.

### M9 — `train` — see the next section.

### M10 — `eval`
The orchestrator runs `<arch>/eval.py --package <pkg> --split data/splits/test.json` (CPU is fine) and
writes `metrics.json` with `eval_split: held_out_test` and the `split_hash`. Then the gate: metrics
against the use case's KPIs (recall at the fixed FPR / mAP / …) **and** `beats_baseline: true`. You may
accept a documented miss; the acceptance is recorded, never implied.

### M11 — `return`
Posts `model_artifact.json`, `metrics.json`, `model.onnx`, `meta.json` (and calibration data) to the
portal. The portal re-validates the package (see the integration section). A 422 here means a defect in
M6/M8 to fix — not a second opinion to argue with.

### M12 — `model-card`
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

At M7 the orchestrator writes `<arch>/HANDOFF.md` (where the package is expected, the exact command,
the runner), sets `run.json` to `waiting_external`, and **stops the session cleanly**. It does not poll.

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
metrics.json}`. Found ⇒ `train` completes and M8 runs. Not found ⇒ it prints exactly what it is waiting
for and stops again. For `runner: portal` it first pulls the run through the portal's
`GET /use-cases/{id}/runs/{run_id}` and `download-model/raw|metadata` into the same folder.

Session breaks at any other stage resume the same way — state is `run.json` + `gates.json`, never the
transcript. `--status` tells you where you are.

---

## Integration with the NeuroEdge Web portal

| Portal step | What agentforge-ml gives it | Direction |
|---|---|---|
| 3 · Dataset — *Upload labelled dataset* | `data/portal_upload.zip` — train + val only, YOLO layout with `data.yaml` (vision) or CSV/JSON with `label` + unit columns (TS); class names identical to the use case | you upload |
| 3 · Model Strategy — *Custom development* | M6 reads the scaffold **context** (`GET /models/scaffold`) — use-case id, classes, resolution, device, KPIs — and writes the package through `neuroedge_return` | portal → run |
| 3 · Model Strategy — *Finished training return package* | M9 posts to `POST /models/{use_case_id}/upload-return-package` | run → portal |
| 3 · Optimize | `extras.source = custom_return` ⇒ the export step becomes **validate** (checker, ORT load, opset, shapes); *Re-export ONNX* reads *Re-validate*; FP16/INT8 and runtime-EP projection unchanged | portal |
| 4–6 · Prepare Device → Virtual Run → Deploy | unchanged — the package entered the same manifests location the portal's own trainer writes | portal |
| `POST /models/{id}/evaluate` | optional: ONNX + a test zip → held-out metrics on the portal side (also how you check a **portal-trained** model against *your* withheld split) | either |

**What the portal checks at upload (and refuses with a named check):**
`onnx_checker` · `opset` (== 13) · `input_rank3` + static feature dim (TS) · `head_present` /
`output_length_matches_head` · `scalar_head_bounded` (a forward pass lands inside (0, 1)) ·
`class_names_match` (identical, same order, across `meta.json`, `model_artifact.json`, the use case) ·
`baseline_present` / `baseline_beats_flag` / `baseline_metrics_comparable`. Raw `.pt` files are hashed
and stored for provenance and **never opened**.

**AWS phase.** Point `model_artifact.json`'s `uri` / `extras.onnx_uri` at `s3://…/model.onnx` and upload
only the JSON files; the portal resolves the URI (S3-compatible endpoints via `AWS_ENDPOINT_URL`) when
Optimize runs. Validation is deferred until then and is marked as such.

**Portal-trained models.** When `model-select.md` records `runner: portal`, train in the portal as usual;
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
  `gate_state.py --path $GATES decide dataset-card --outcome approved --note "…"` (`rejected` with the
  reason; *accept as hold-out* is `approved` with the note `hold-out only — synth required`, which makes
  M4 mandatory on resume).
- **Re-do a stage:** `run_state.py --path $RUN reopen <stage>` then `--resume`.
- **Wrong stage id?** The CLI names the run's sequence in the error (`ml`) — an SDLC stage id against an
  ML run is rejected before anything is written.

---

## Worked example — CNC drift, end to end

```text
# 0. Start (ML root set in .env; portal use case exists)
/agentforge-ml "detect CNC machining drift from spindle-load, x_axis_error and vibration signals"
  → proposes C:\SanjeevE\NeuroEdge-ML-Models\neuroedge-ml-projects\cnc_drift-timeseries — accept

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
#               gate: approve   (or: accept as hold-out → synth the rare drift class)
# 5. label    → TS window rule: any; training_labels: unit ground truth
# 7. select   → baseline MiniRocket+ridge; deployable 1D-CNN; runner: package; export ONNX
# 8. build    → 1DCNN/train.py eval.py …; ml-eval-reviewer passes
# 9. train    → session stops: HANDOFF.md written

cd …\cnc_drift-timeseries\1DCNN ; python train.py --config config.yaml      # on the RTX laptop

/agentforge-ml --resume
# 10. eval   → eval.py on the withheld experiments: pr_auc, recall@fpr=0.01, event_f1 … beats_baseline
#              gate: approve
# 11. return → upload-return-package → 200, source=custom_return
# 12. card   → model-card.md

# Portal: Optimize shows "Uploaded: model.onnx · opset 13 · validated ✓" → Prepare Device → Deploy
```

If you already had the KIT data on disk: `/agentforge-ml "<objective>" --stage verify` and point
`--data-dir` at it.

---

## Failure modes and what they mean

| Symptom | Meaning | Do |
|---|---|---|
| A stage asks for a destination | It was run standalone without `--dest`, or the run's `--dest` was lost | Inside a run this is a bug; standalone, pass `--dest` |
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

**Stage ids (run_state sequence `ml`):** `destination scout verify label synth model-select model-build
train eval return model-card`.

**Environment variables:** `NEUROEDGE_ML_ROOT` (model root) · `NEUROEDGE_ML_DATA` (raw downloads,
optional) · `KAGGLE_USERNAME` / `KAGGLE_KEY` · `ROBOFLOW_API_KEY` · `HF_TOKEN` (all optional) ·
`AWS_ENDPOINT_URL` (S3-compatible stores, portal side).

**Skills the run applies:** `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`,
`agentic-assets/skills/ENGINEERING/ai-ml/{dataset-sourcing, data-labeling, synthetic-data,
model-architectures, pretrained-and-transfer, model-codegen, time-series-ml, ml-model-package}.md`.

**Decisions:** `docs/decisions/ADR-0021-ml-artifact-destination.md`,
`docs/decisions/ADR-0022-agentforge-ml-orchestrator-and-model-package-contract.md`; NeuroEdge-Web
`docs/decisions/ADR-0001` (export contract, opset 13), `ADR-0002` (evaluation integrity), `ADR-0003`
(baseline floor, threshold, upload enforcement), `ADR-0005` (portal side of this flow).

**Not yet covered** (see `docs/decisions/ADR-0023-*.md`): vision transformers as first-class
architectures, **visual** anomaly detection (today `anomaly_detection` means time series everywhere),
image/screen description (VLM), and reinforcement learning.

**Related guides:** [how_to_build_ml_model.md](how_to_build_ml_model.md) (v1 — the per-step deep dive),
[how_to_run_agentforge.md](how_to_run_agentforge.md) (the SDLC orchestrator this one mirrors).
