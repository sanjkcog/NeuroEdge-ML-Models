# /auto-label — Zero-shot auto-label a vision dataset, then human-review

> **Scope: vision only.** The Grounding DINO / SAM pipeline below has no time-series equivalent.
> For sensor/TS data, labels come from the dataset's own ground truth, threshold/rule weak
> supervision, or controlled synthetic seeding — see the `time-series-ml` skill's labeling
> section; do not run this command on non-image data.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /auto-label · Skills: data-labeling`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/data-labeling.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Arguments

`$ARGUMENTS` — the image directory (or dataset id) to label, and the target classes / prompts
(e.g. `./data/castings --classes "cracked casting, clean casting"`). Optional `--seg` for masks
(Grounded-SAM-2) vs boxes only (Grounding DINO).

## What this does

Labels a vision dataset the **auto-label-first, human-correct-second** way (ADR-0014). Spawns
`ml-data-engineer`, which applies the `data-labeling` skill: **Autodistill** wires **Grounding DINO**
(open-vocabulary boxes from your prompts) + **SAM / Grounded-SAM-2** (masks) to pre-label every image
zero-shot, then routes candidates to a human review queue. Produces the `label-manifest`.

## Procedure

1. Define the **ontology** — map each prompt to a target class name. Precise prompts matter most.
2. Spawn **`ml-data-engineer`** to run the Autodistill pipeline over the images → **candidate** labels.
3. **Human review** — present candidates for correction; auto-labels are never ground truth until
   reviewed. For a large set, prioritize low-confidence / model-disagreement samples (active learning).
4. **Label QA** — verify class balance and **split integrity** (no image or near-duplicate across
   train/val/test). Emit the `label-manifest` (per-class counts, auto-vs-human provenance, estimated
   auto-label precision).

## Next step

`/model-select` (labels now exist). If a class is under-represented after labeling → `/synth-data` to
top it up.
