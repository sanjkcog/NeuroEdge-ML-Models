---
name: dataset-sourcing
description: Find and evaluate a training dataset for an ML objective — search Hugging Face Datasets, Kaggle, Roboflow Universe, and TF Datasets; assess task-fit, license compatibility, and class balance; curate with FiftyOne. Use when a project needs a dataset before it can build a model.
origin: NeuroEdge AgentForge
---

# Dataset Sourcing

Turn an ML objective ("detect cracked castings", "classify cooling-tower fan states") into a
**shortlist of candidate datasets** with a defensible pick — or a clear finding that no suitable
real dataset exists (which routes to [`synthetic-data`](synthetic-data.md)). The user never leaves
AgentForge to hunt across five dataset portals.

## When to Activate

- The objective needs training data and none has been chosen yet
- `/dataset-scout` is invoked
- Before `/model-select` / `/model-build` — you cannot pick an architecture without knowing the data

## Where to look (in priority order)

| Source | Best for | Access |
|---|---|---|
| **Hugging Face Datasets** | broad ML/CV/NLP, versioned, `datasets` API, task tags | `huggingface_hub` / `datasets` |
| **Roboflow Universe** | ready-to-train **vision** datasets (detection/segmentation), many industrial | Roboflow API / export |
| **Kaggle** | competition + community datasets, tabular & vision | `kaggle` CLI |
| **TensorFlow Datasets (TFDS)** | canonical benchmarks, deterministic splits | `tfds` |
| **FiftyOne / Voxel51** | not a source — the **curation** layer over any of the above | `fiftyone` |

Industrial-inspection note: the **VISION-Datasets** collection (14 curated manufacturing-inspection
sets) on the HF Hub is a strong first stop for defect-detection objectives.

**Time-series / sensor objectives** (`--timeseries`): the portals above are image-first — go to the
PdM sources instead: **NASA PCoE** (milling, C-MAPSS, FEMTO, IMS — generally clean licensing),
**PHM Society data challenges** (PHM 2010 CNC tool wear — license informal, Kaggle "CC0" mirrors
are not authoritative), **UCI** (#447 Hydraulic), **UCR/UEA archives** (benchmark only), CWRU
(split by physical bearing or it leaks). 🔴 Non-commercial poison pills to keep out of product
builds: **Paderborn KAt (CC BY-NC)**, **MIMII / ToyADMOS2 / DCASE task-2 (CC BY-NC-SA)**. Full
table and split rules: [`time-series-ml`](time-series-ml.md).

**Keys (ADR-0022 D-12, closes ADR-0014 OQ-1).** Scouting reads public metadata and needs **no key**.
Downloading (`/dataset-verify`) needs one only for some sources: Kaggle — `KAGGLE_USERNAME` +
`KAGGLE_KEY`; Roboflow — `ROBOFLOW_API_KEY`; Hugging Face — `HF_TOKEN` for gated/private sets only;
PHM Society — manual registration. KIT / NASA PCoE / data.gov / Bosch GitHub / UCI / TFDS — none. Record
the requirement in the card's front matter as `keys_required`; an unset key stops the download with its
name, and never falls back to a mirror whose licence is not the rights holder's.

## The four evaluation gates (a candidate must pass all)

1. **Task fit** — label type matches the objective (bbox vs mask vs class vs value), domain matches
   (your cameras/sensors, not a toy set), resolution and capture conditions are realistic.
2. **License compatibility** — the dataset's license must be usable for the **product's** license and
   commercial posture. CC-BY-NC, "research only", or unknown ⇒ flag; do not silently proceed.
   (ADR-0014 OQ-2 asks whether this is a HARD gate — treat it as blocking until decided.)
3. **Class balance & size** — enough samples per class; report the imbalance ratio. Severe imbalance
   or a rare target class is a signal to add [`synthetic-data`](synthetic-data.md), not to give up.
4. **Label quality** — spot-check with FiftyOne (duplicates, mislabels, leakage between splits).
   Never trust a portal's stated split without checking for train/test overlap. For time series the
   check is stronger: the split must be **chronological or per physical unit** — a random split over
   (overlapping) windows is leakage even when no file is duplicated
   ([`time-series-ml`](time-series-ml.md)).

## Output: a dataset-scout report

Produce a ranked table — for each candidate: source + id, sample count, class distribution, license
(+ compatibility verdict), task-fit note, and a one-line recommendation. End with a single **picked**
dataset (or "no suitable real dataset — recommend synthetic", with the reason). This report is the
`dataset-card` artifact the downstream stages cite.

## Do NOT

- Do not download multi-GB datasets into the repo/git — reference them by id/URL; the
  `pre-commit-ml-artifact` hook blocks large blobs. Use a data dir or DVC/registry.
- Do not fabricate class counts or license terms — read them from the source, cite them, and mark
  anything you could not verify as `TBD` (never guess a license).
