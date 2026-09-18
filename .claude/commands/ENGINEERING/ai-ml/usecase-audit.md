---
description: Check that the use case, the dataset, the simulator export and the target device (plus the scaffold and the model package, once they exist) agree on channels, order, units, rate, window, classes and runtime — run standalone at any time, and automatically by /agentforge-ml at M0, M4, M8 and M11 (ADR-0025 D-6).
argument-hint: --dest <folder> [--checkpoint M0|M4|M8|M11]
---

# /usecase-audit — Do the use case, dataset, simulator and device agree?

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /usecase-audit · Skills: ml-model-package, time-series-ml, ml-artifact-destination`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/ml-model-package.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/time-series-ml.md`
> - `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`

## Arguments

`$ARGUMENTS` — `--dest <folder>` (the model folder; inside `/agentforge-ml` it is always passed), and optionally
`--checkpoint <M0|M4|M8|M11>`. `/agentforge-ml` passes a checkpoint, which writes `audit/<checkpoint>.{md,json}`
and records the gate `audit/<checkpoint>`. Without one, the audit checks everything that exists, writes nothing
and opens no gate. That is the mode for a human asking "is this still aligned?" at any moment, for example after
re-downloading a use case or re-assessing the device.

## What this does

Four artifacts each carry their own copy of the same contract. They drift apart silently: a use case edited in the
portal, a device re-flashed, a simulator export built on an old lock. This command compares them:

| Pair | What must agree |
|---|---|
| use case ↔ device (`inputs/capability_manifest.json`) | task in `supported_tasks`; `onnx` export; the use case's `runtime_profile` offered by the device; `device_profile_id`; `capability_manifest_id` linked; each lock channel covered by a declared device sensor; manifest status and age; an ONNX Runtime provider available |
| use case ↔ dataset (`data/contract/`, splits, synthetic) | the contract's `lock_sha256`, rate, window, stride, channel order, units, reduce; one `split_hash` across contract and splits; the synthetic set stamped with this lock and split hash |
| use case ↔ scaffold (`inputs/scaffold/`) | use case id, class order, channel order, rate and window equal the lock; the vision defaults and free-text `at_fpr` the lock overrides are listed |
| use case ↔ simulator (`sim/manifest.json`) | `lock_sha256`, `split_hash`, feature order, rate, units, reduce; test exported only as `acceptance_only` |
| package ↔ all (`<arch>/runs/*/model-package/meta.json`) | `lock_sha256`, class names, head, opset 13, feature order, window, stride, rate, reduce |

Each check is **PASS**, **WARN**, **FAIL** or **NOT_YET**. NOT_YET means the source does not exist at this
checkpoint by design. A source that should exist by now and does not is a FAIL.

## When it runs inside `/agentforge-ml`

| Checkpoint | Point in the run | Why there |
|---|---|---|
| `M0` | after the lock is built | a device that cannot run the use case should stop the run before any data is fetched |
| `M4` | after the contract dataset, before the data-verified gate | the data the human approves must be the data the lock describes |
| `M8` | after the scaffold is recorded, before code is generated | the portal contract the package is written against must be this use case's |
| `M11` | after M10 eval, before the upload zip | what leaves the folder must agree with the lock, the device and the simulator export |

## Procedure

1. Run `python -m agentforge.src.ml_contract.audit --dest <dest> [--checkpoint <cp>]`.
2. Present the verdict, then every FAIL and WARN, grouped by pair. Don't just give the path to the report.
3. **No FAIL:** at a checkpoint the gate is approved automatically (identity `usecase-audit (automatic)`); the
   WARNs are listed in its reason. Show them anyway, because a WARN is something a human should know.
4. **FAIL:** say which source to fix and how. Examples: re-download the use case after correcting it in portal
   Step 1, or pick the device the use case names; re-run `/synth-data` so the set is stamped; rebuild the contract
   dataset. Re-run the audit after the fix. If the human decides to proceed anyway, record their decision on the
   gate with their reason (`gate_state.py decide audit/<cp> approved --identity <user> --reason "..."`). The
   deviation is then on the record, never implied.

## Do NOT

- Do not edit any of the compared files to make the audit pass. Fix the source (use case, device assessment,
  dataset build) and re-record it.
- Do not open `data/splits/test.json`. The audit reads split hashes from train and val only.
- Do not call the portal to fetch a newer manifest or use case. Ask the human to download it (ADR-0025 D-1).
