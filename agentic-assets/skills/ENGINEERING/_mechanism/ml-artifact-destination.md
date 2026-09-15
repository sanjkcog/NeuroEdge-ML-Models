---
name: ml-artifact-destination
description: Cross-pack rule for where the ai-ml and ai-genai commands write their artifacts — resolve a destination folder from --dest, NEUROEDGE_ML_ROOT, or a neuroedge-ml-projects/ folder, confirm it with the user, and keep every artifact inside it. Use at the start of /dataset-scout, /auto-label, /synth-data, /model-select, /model-build, /gan-build, and /model-route (when saving).
origin: ADR-0021
---

# ML Artifact Destination

Model work lives in a **model-development project**, not in whichever repo the command happens to
run in. Every `ai-ml` / `ai-genai` command resolves **one destination folder per objective** before
it writes anything, and writes only inside it.

## Resolve the destination (before any write)

1. **`--dest <folder>` given** → that folder is the destination, used as-is. State it; do not ask.
2. **Otherwise ask for the folder, and say where it will live.** Resolve `ML_ROOT` first, then ask
   the user to confirm the folder **name**, stating plainly that it will be created under that root
   and showing the full resolved path (use `AskUserQuestion` where available):

   > Destination for this objective's artifacts. It will be created under
   > `C:\…\neuroedge-ml-projects` (from `NEUROEDGE_ML_ROOT`):
   > **`cnc_drift-timeseries`** — accept, or give a different name or a full path.

   Pre-fill the derived `<intent>-<modality>` as the default, list any existing folders that look
   like the same objective, and **write nothing until the user answers**.
3. **Reuse before create.** If a folder for the same objective already exists under `ML_ROOT` (its
   `README.md` names the objective), offer that folder as the default instead of a new one — later
   stages add to the folder an earlier stage created; they never start a second one.

**Any command may be the entry point.** Do not assume `/dataset-scout` ran first: a user who already
has a dataset may start at `/model-select` or `/model-build`, and a user with no real data may start
at `/synth-data`. Whichever command runs first resolves the destination, creates the folder and its
`README.md`, and records the objective there. Never require a missing upstream artifact — if
`data/dataset-card.md` does not exist because the user brought their own dataset, record what they
gave you (source, license, splits) in `data/dataset-card.md` yourself and carry on.

### `ML_ROOT` — resolved in this order

| # | Source | Example |
|---|---|---|
| a | `NEUROEDGE_ML_ROOT` environment variable (absolute path) | `C:\SanjeevE\NeuroEdge-ML-Models\neuroedge-ml-projects` |
| b | `neuroedge-ml-projects/` at the git root of the current project, **if it exists** | `<repo>/neuroedge-ml-projects/` |
| c | Neither → **no default**; ask the user for the full destination path | — |

Never fall back to the current working directory silently, and never write into a product repo's
source tree (e.g. `neuroedge/industries/…`) unless the user names it as the destination.

## Folder name: `<intent>-<modality>`

- **intent** — short `snake_case` slug of what the model does, 1–3 words: `cnc_drift`,
  `casting_crack`, `fan_louver_state`.
- **modality** — one of `vision` · `timeseries` · `tabular` · `reco` · `text` · `audio` ·
  `multimodal` · `genai`.
- Joined by a single hyphen: `cnc_drift-timeseries`, `casting_crack-vision`.

### Derive both from the objective — never ask the user to invent them

The user states an objective, not a folder name. Derive the proposal yourself and put it in the
confirmation question; the user edits or accepts it.

**modality** — the task-family flag if one was passed (`--vision` / `--timeseries` / `--tabular` /
`--reco`). With no flag, infer from the objective's wording:

| Wording in the objective | modality |
|---|---|
| sensor, vibration, spindle, telemetry, drift, wear, RUL, signal, Hz, time window | `timeseries` |
| image, camera, photo, visual, defect on a part, detect/segment an object | `vision` |
| rows, columns, CSV, features, a record per event | `tabular` |
| recommend, ranking, next-best, personalization | `reco` |
| prompt, agent, LLM, RAG, summarize/extract/generate text | `genai` |
| text/audio as the raw input, or two of the above together | `text` · `audio` · `multimodal` |

**intent** — a 1–3 word `snake_case` slug naming **what is being judged**, not how. Keep the
subject (the asset/part) and the condition (the fault/decision). Drop the verb (`detect`,
`predict`, `classify`), the sensor/channel names, and the site or line id:

| Objective | intent |
|---|---|
| "detect CNC machining drift from spindle-load, x_axis_error and vibration signals" | `cnc_drift` |
| "detect cracked castings on a conveyor" | `casting_crack` |
| "predict remaining useful life of pump bearings" | `bearing_rul` |
| "classify cooling-tower fan louver open/closed" | `fan_louver_state` |

If the objective is too vague to yield a slug (or two readings are equally good), offer 2–3
candidate names in the question rather than guessing silently. Before proposing a new folder, list
the existing folders under `ML_ROOT` — a near-match usually means this objective already has one
(see *Reuse before create*).

The architecture is **not** in the folder name — it is not known until `/model-select`, and one
objective is often built with more than one (a MiniRocket floor and a 1D-CNN). Each architecture
gets its own subfolder instead.

## Layout inside the destination

```
<intent>-<modality>/
  README.md                  objective, modality, and a stage log (command · date · artifact)
  data/
    dataset-card.md          /dataset-scout
    label-manifest.md        /auto-label
    synthetic-recipe.md      /synth-data
  model-select.md            /model-select
  <architecture>/            /model-build — one handoff package per architecture
                               (e.g. MiniRocket/, 1DCNN/, EfficientNetLite0/)
  gan-harness/               /gan-build
  model-route.md             /model-route — only when the user asks to save it
```

Create `README.md` if missing, and append one stage-log row per command run.

## Rules

- **Every write goes under the confirmed destination.** Pass the **absolute** destination path to
  any spawned agent. An agent spawned without one writes nothing and returns the artifact content in
  its report instead of choosing a folder.
- **No blobs.** Datasets are referenced by id/URL; generated samples, checkpoints, and downloads go
  to a gitignored data dir or DVC/registry — the destination holds cards, recipes, code, and configs.
- **Report the path** of every artifact written, as the last line of the command's output.
