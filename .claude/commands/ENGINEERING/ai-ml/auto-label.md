# /auto-label — Zero-shot auto-label a vision dataset, then human-review

> **Two modes.** *Vision* — the zero-shot Grounding DINO / SAM pipeline below, then human review.
> *Time series* (`--timeseries`, or inferred from the card's `modality`) — no annotation tool: labels come
> from unit-level ground truth, a **window rule** applied by code, synthetic seeding, or none at all
> (normal-only training, labels used for evaluation only). See "Time-series mode" below and the
> `time-series-ml` skill's labeling section.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /auto-label · Skills: data-labeling, ml-artifact-destination`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/data-labeling.md`
> - `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`
<!-- neuroedge-assets-patched source-version=8acd6bf -->

## Arguments

`$ARGUMENTS` — the image directory (or dataset id) to label, and the target classes / prompts
(e.g. `./data/castings --classes "cracked casting, clean casting"`). Optional `--seg` for masks
(Grounded-SAM-2) vs boxes only (Grounding DINO).

`--dest <folder>` — where this command writes its artifacts. If omitted, the command proposes `<ML_ROOT>/<intent>-<modality>` and asks before writing (`agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`).

## What this does

Labels a vision dataset the **auto-label-first, human-correct-second** way (ADR-0014). Spawns
`ml-data-engineer`, which applies the `data-labeling` skill: **Autodistill** wires **Grounding DINO**
(open-vocabulary boxes from your prompts) + **SAM / Grounded-SAM-2** (masks) to pre-label every image
zero-shot, then routes candidates to a human review queue. Produces the `label-manifest`.

## Procedure

0. **Resolve the destination** — apply `ml-artifact-destination`: use `--dest`, or propose `<ML_ROOT>/<intent>-<modality>` and **ask the user to confirm before writing anything**. Call the confirmed absolute path `<dest>` and pass it to every spawned agent. Inside an `/agentforge-ml` run `--dest` is always passed — **do not ask**; the orchestrator already confirmed it (ADR-0022 D-2).
1. Define the **ontology** — map each prompt to a target class name. Precise prompts matter most.
2. Spawn **`ml-data-engineer`** to run the Autodistill pipeline over the images → **candidate** labels.
3. **Human review** — present candidates for correction; auto-labels are never ground truth until
   reviewed. For a large set, prioritize low-confidence / model-disagreement samples (active learning).
4. **Label QA** — verify class balance and **split integrity** (no image or near-duplicate across
   train/val/test). Emit the `label-manifest` to `<dest>/data/label-manifest.md` (per-class counts,
   auto-vs-human provenance, estimated auto-label precision). Label files go to a gitignored data dir, not `<dest>`.

## Time-series mode

1. Read `<dest>/data/profile.json` and `splits/` (from `/dataset-verify`): unit-level labels (e.g. anomaly type
   per experiment) and the per-unit split are already fixed — never re-split here.
2. Choose the **window rule** with the user and record it: `majority` (window label = majority of its samples),
   `any` (any anomalous sample ⇒ anomalous window), or `unit` (every window inherits its unit's label). For
   normal-only anomaly detection, record `training_labels: none` and label only val/test.
3. Apply the rule by code over train/val/test separately; emit per-split class counts and the resulting
   imbalance ratio. A single-class **test** split fails the step (Web ADR-0003 B-6).
4. Human review = a sample of labelled windows plotted per class; correct the rule, not the windows.
5. Write `<dest>/data/label-manifest.md` with the rule, counts per split, `split_hash`, and provenance
   (`ground_truth` | `rule` | `synthetic`). No gate for TS rules; the manifest is the record.

## Next step

`/model-select` (labels now exist). If a class is under-represented after labeling → `/synth-data` to
top it up.
