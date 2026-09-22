---
description: Fetch the pretrained base model that model_proposed.md names — from Hugging Face, NVIDIA NGC, a GitHub release, Ultralytics or torchvision — at a pinned revision, hash the weights, write base-model-card.md, base-model-card.json and loader.json into <dest>/model/base/, and gate the licence (ADR-0028 D-2, D-3, D-4). It never calls the portal.
argument-hint: --dest <folder> [--from-recommendation | --hub <hub> --ref <ref> --revision <pin> --loader <loader> --model-id <id>] [--licence <SPDX> --licence-evidence <where>] [--selection-note "<why>"] [--force]
---

# /model-fetch — Fetch the base model at a pinned revision, hash it, gate its licence

## Arguments

`$ARGUMENTS`:

- `--dest <folder>` — the model folder. Inside an `/agentforge-ml` run it is always passed. **Do not ask.**
  Standalone, resolve it once per `ml-artifact-destination`.
- `--from-recommendation` — fetch **exactly** the source the recorded `model_recommendation.json` picks
  (ADR-0028 D-9). Use it when the proposal adopts the portal's pick.
- or a free-form source: `--hub huggingface|ngc|github|ultralytics|torchvision`, `--ref`, `--revision`,
  `--loader ultralytics|torchvision|timm|transformers|tao|custom`, `--model-id`.
- `--licence <SPDX>` and `--licence-evidence <where it was read>` — the licence as you **read** it, and where.
  Leave both out when you could not read it. Never guess.
- `--selection-note "<why>"` — when the choice differs from the portal's pick. The portal shows it at upload.
- `--force` — replace a download that is already there.

## What this does

M7 runs this after `model_proposed.md` names a pretrained base. It is to the model what `/dataset-download` is to
the data: one place that downloads, pins, hashes and records.

**It never calls the portal** (ADR-0025 D-1). The portal downloads no model either (NeuroEdge-Web ADR-0010 R-5).
This command is the only downloader.

A model trained from scratch (`loader: none`) has no base model. Skip this command.

## Sources

| `--hub` | `--ref` | `--revision` (always pinned) | Key |
|---|---|---|---|
| `huggingface` | `org/model` | a commit hash (best) or a tag | `HF_TOKEN`, for gated repos only |
| `ngc` | `org/team/model:version` | the version is part of the ref | `NGC_API_KEY` |
| `github` | `owner/repo/asset-file` | the release tag | none |
| `ultralytics` | the file, for example `yolov8n.pt` | the release tag of `github.com/ultralytics/assets` that holds the file | none |
| `torchvision` | the model name | the weights **file name** from the model's `Weights` enum, for example `mobilenet_v3_small-047dcff4.pth`. Its suffix is the start of the file's sha256. It is checked after the download | none |
| `aihub` | refused | — | — |

**Qualcomm AI Hub.** An AI Hub download is a compiled inference artifact. It cannot be fine-tuned. Open the
open-source `qai_hub_models` package, find the model, and read which **upstream** repo and weights it loads.
Fetch that source with `--hub huggingface` or `--hub github`, and add `--via aihub:<model>`. If you could not
read the upstream source there, write it as `unverified` in the proposal (ADR-0028 D-8). Do not fetch a guess.

**A revision is always pinned.** `latest`, `main`, any branch name, an empty or a missing revision is refused.
The portal's catalogue carries no revision for Ultralytics and torchvision entries, so with
`--from-recommendation` you add `--revision`. The card records that the pin was chosen at fetch.

**Keys.** A key is read from the environment of this shell. Its value is never written to a file or a log. The
card records only the **name** of the variable. If a key is missing, say which variable to set, and stop.

## Procedure

1. **Read the proposal.** Take the base model, the loader and the licence from `<dest>/model_proposed.md`. Check the
   licence yourself at the source (the model card, the `LICENSE` file, the NGC page). Record where you read it.
2. **Check the pick (D-9).** When a recommendation is recorded:
   `python -m agentforge.src.ml_contract.recommendation check --dest <dest> --model-id <id>`.
   Exit 3 means the portal marked this model **does not fit**. That is binding. Choose another model, or ask
   the human. Only their recorded override lifts it (see `/model-select`).
3. **Fetch.**
   ```
   python -m agentforge.src.ml_contract.model_fetch fetch --dest <dest> --from-recommendation [--revision <pin>]
   python -m agentforge.src.ml_contract.model_fetch fetch --dest <dest> --hub <hub> --ref <ref> --revision <pin> \
       --loader <loader> --model-id <id> --licence <SPDX> --licence-evidence "<where it was read>"
   ```
   It writes `<dest>/model/base/`:
   - `weights/` — the downloaded files. `model/base/.gitignore` keeps them out of git. Confirm it:
     `git check-ignore <dest>/model/base/weights/<file>`.
   - `loader.json` — the loader family, the entry file, and the sha256 of every file.
   - `base-model-card.json` — source, pinned revision, sha256, licence and its gate outcome, loader, the runners
     the loader allows, and `selection_note`. The portal matches an uploaded weights file against it.
   - `base-model-card.md` — the same, for the human.
4. **The licence gate (D-3).** The command decides only what needs no human:

   | Licence | Outcome | Gate |
   |---|---|---|
   | permissive (Apache-2.0, MIT, BSD, ISC, CC0, CC-BY-4.0), with evidence | `approved` | none |
   | AGPL-3.0 (every Ultralytics model) | `approved_internal_only` | **none** (owner's MVP decision, 2026-09-21) |
   | non-commercial, unverifiable, missing, no evidence, per-model terms (NGC, AI Hub), other copyleft | `pending` | **hard** `model/base-model-card.md`, stage `model-select` |

   **A licence named in `model_recommendation.json` is a claim, not evidence.** That file is a dropped input. With
   `--from-recommendation`, a permissive licence it names still opens the hard gate, unless you read the licence in
   the download and pass `--licence-evidence "<the file you read it in>"`. The one exception is the owner's: an
   AGPL-3.0 claim gets the **more restrictive** outcome (`approved_internal_only`) without a gate.

   **Exit code 3 means the hard gate is open. Stop.** Show `base-model-card.md` to the human. Ask with
   `AskUserQuestion`, offering the three outcomes: **approved**, **approved, internal and demo use only**,
   **rejected**. Record what they chose:
   ```
   gate_state.py decide model/base-model-card.md <approved|rejected> --identity <user> --reason "<their words>"
   python -m agentforge.src.ml_contract.model_fetch licence --dest <dest> --outcome <approved|approved_internal_only|rejected>
   ```
   The second command copies the decision into the card, so that it travels with the weights. It refuses an
   outcome the gate does not carry. `rejected` → go back to `/model-select` with the reason as a constraint.

   **`distribution: internal_only` is information, not a refusal (MVP).** It is written into the card, it travels
   with the model, and the portal shows it. For the MVP nothing downstream refuses on it, and a release is not
   refused. A customer who uses an AGPL model commercially obtains their own commercial licence. Say this once
   when you present an Ultralytics model.
5. **Propose the runner (D-4).** `python -m agentforge.src.ml_contract.model_fetch runner --loader <loader>
   [--path <catalogue path>]` prints the runner to propose and the runners the loader allows. Write it in
   `model_proposed.md` §Runner.

## Then

Back to `/model-select` step 4: `review model`, then the M7 gate. On the fine-tune path the handoff is the dataset
zip, the weights and `base-model-card.json`. **The human uploads them in the portal.** Nothing here uploads.

## Do NOT

- Do not call the portal, and do not ask the portal to download a model.
- Do not fetch `latest`, `main` or any branch.
- Do not guess a licence, and do not write one you did not read. "Not read" is a valid answer: the gate handles it.
- Do not decide the licence gate for the human.
- Do not write a token or a key anywhere. Name the variable only.
- Do not `git add` anything under `model/base/weights/`.
- Do not evaluate the pretrained model as it is and call that a baseline (ADR-0028 D-11).

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /model-fetch · Skills: pretrained-and-transfer, ml-artifact-destination`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/pretrained-and-transfer.md`
> - `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`
<!-- neuroedge-assets-patched source-version=a3cf127 -->
