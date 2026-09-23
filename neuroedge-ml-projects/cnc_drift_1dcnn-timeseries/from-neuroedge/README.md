# What NeuroEdge gives this run

`/agentforge-ml` never calls the portal. Download these files from the portal (or the device) and
drop them in this folder. The run records each one with its hash, then moves it to `recorded/`.
What this run gives back to the portal is staged in `../to-neuroedge/`.

Only the **use case** is required: the run stops at M0 until it is here, and asks you to confirm it
at a gate. The others are **optional**. Drop one and it is used. Leave it out and the run goes
on without it. They can be added or replaced at any time without re-answering a gate.

| File | Needed from | Where to get it | Recognised as |
|---|---|---|---|
| the use case (`<use-case-id>.yaml`), **required** | M0 | Portal **Step 1 · Edge Use Case Design** → validate the spec → **Download use_case.yaml** | any `*.yaml` / `*.yml` with a top-level `id:` and `task:` |
| the device capability manifest, *optional* (advisory device-fit warnings) | M0 | The target device's assessment: `ne-device-agent assess --local` writes `capability_manifest.json`, the same file uploaded to the portal in **Step 2 · Target Device** | any `*.json` with `manifest_id` or `device_profile_id` |
| the training scaffold (`neuroedge_train_<id>.py`), *optional* (without it M8 uses the default template) | M8 | Portal **Step 3 · Model Strategy** → *Build my own* → **Script (.py)** (a notebook also works) | any `*.py` / `*.ipynb` containing `NEUROEDGE_CONTEXT` |
| the portal's model recommendation (`model_recommendation.json`), *optional* (advisory; `/model-select` must answer it) | M7 | Portal **Step 3 · Model Strategy**: pick from the rated list, then export the recommendation | any `*.json` whose `schema` is `model-recommendation/1` |

Check what is here and what is missing:

    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need use_case,capability_manifest
    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need scaffold
    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need model_recommendation

One file per kind. If two files of the same kind are here, `check` stops and names both; remove the
one you do not want. A newer download of a file already recorded replaces it. For the use case, its
gate and every audit are then asked again, and the lock must be rebuilt.

## What comes back after training

| File | Needed by | Where to get it | Recognised as |
|---|---|---|---|
| the portal's model package (`<use-case-id>-model-package.zip`) | M9 | Portal **Step 3 · Optimize** → *Downloads* → **Download all as .zip** | a `*.zip` holding `model_artifact.json` (and `model.onnx`, `meta.json`, `metrics.json`) |
| the held-out result (`*.json`) | M10 | Portal **Step 3 · Train** → *Held-out evaluation* → **Download result** | a `*.json` whose `eval_split` is `held_out_test` |

Drop either here as it is: **never unzip the package yourself, and never pick a run id.** The run
reads the run id from the package's own `model_artifact.json` and unpacks it to
`<arch>/runs/<run_id>/model-package/`; the held-out result goes beside it as `portal_held_out.json`,
matched to its package by the model's hash. A package whose `lock_sha256` is not this project's lock
is refused, naming both hashes, and left here; nothing is written under `<arch>/runs/`.

    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need model_package
    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need held_out_result
