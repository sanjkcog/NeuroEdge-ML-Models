---
name: data-labeling
description: Label an image/vision dataset for CNN training — manual annotation (Label Studio, CVAT) and zero-shot auto-labeling (Autodistill = Grounding DINO + SAM / Grounded-SAM-2), plus active-learning and label-QA. Use when a sourced or synthetic dataset needs labels before training. VISION ONLY — for sensor/process time series see time-series-ml.md.
origin: NeuroEdge AgentForge
---

# Data Labeling (vision, CNN-focused)

> 🔴 **Scope: this skill is vision-only** (ADR-0015 decision 6). The zero-shot auto-label pipeline
> below is Grounding DINO + SAM — it segments *pixels* and has no meaning for a sensor stream.
> **Do not plan a time-series labeling effort around `/auto-label`.**
>
> For sensor / process time series, labels come from three places instead — see
> [`time-series-ml`](time-series-ml.md):
>
> 1. **The dataset's own ground truth** — wear measurements, run-to-failure timelines, recorded
>    fault annotations. Usually the answer; check before doing anything else.
> 2. **Threshold / rule weak supervision**, reviewed by a human who knows the process.
> 3. **Controlled seeding** — synthetic anomalies carry free labels
>    ([`synthetic-data`](synthetic-data.md), signal mode).
>
> Whichever is used, label the **window** by an explicit rule (majority vote, any-anomaly, or a
> per-cycle severity threshold) and record that rule in the `label-manifest`. A window label with an
> unrecorded rule is not reproducible.

Labeling is the cost and time sink of a CV project. The strategy here is **auto-label first, human-
correct second** — use foundation models to pre-label, then spend human effort only on review and the
hard cases. The user drives this from `/auto-label` without leaving AgentForge.

## When to Activate

- A dataset (real or synthetic) has images but no / partial labels
- `/auto-label` is invoked
- Before `/model-build` for any supervised vision task

## Auto-labeling with foundation models (the fast path)

**Autodistill** wires zero-shot foundation models into a labeling pipeline: a **Grounding DINO**
open-vocabulary detector proposes boxes from a text prompt ("cracked casting", "open fan louver"),
and **SAM / Grounded-SAM-2** turns boxes into precise masks. Because these models are zero-shot, they
work from the first image — no seed labels needed.

```
prompt (ontology)  →  Grounding DINO (boxes)  →  SAM 2 (masks)  →  candidate labels  →  human review
```

- Define an **ontology**: map each text prompt to the target class name. Precise prompts matter more
  than model choice.
- Auto-labels are **candidates**, never ground truth — they always enter a **human review queue**.
- Distill the foundation-model labels into your smaller target CNN (that is the "distill" in
  Autodistill): the big model labels, the small model trains.

## Manual / correction tooling

| Tool | Role |
|---|---|
| **Label Studio** | general-purpose, multi-modal, review UI over auto-labels |
| **CVAT** | video/frame-dense annotation, interpolation |
| **FiftyOne** | visualize + filter + fix labels programmatically; find mislabels & duplicates |

## Active learning (spend labels where they count)

After a first model exists, label the samples the model is **least confident** on (or where auto-label
and model disagree), not random images. This converges accuracy far faster per labeled image.

## Label QA — always

- Check **class balance** of the produced labels; a skewed label set biases the CNN.
- Check **split integrity** — no image (or near-duplicate) in both train and val/test (leakage).
- Sample-audit auto-labels: report an estimated auto-label precision so downstream trusts them
  appropriately.

## Output

A `label-manifest` — per split: image count, per-class label counts, auto-vs-human provenance, and an
estimated auto-label accuracy. Feeds `/model-build` and the `ml-eval-reviewer` leakage check.

## Do NOT

- Do not ship auto-labels as final without human review — that is how systematic labeling errors
  become systematic model errors.
- Do not let auto-label confidence masquerade as ground-truth confidence in any downstream metric.
