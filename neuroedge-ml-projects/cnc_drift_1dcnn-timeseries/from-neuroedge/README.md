# Drop portal files here

`/agentforge-ml` never calls the portal. Download these files from the portal (or the device) and
drop them in this folder. The run records each one with its hash, asks you to confirm it at a gate,
then moves it to `recorded/`. Nothing proceeds until the files a stage needs are here.

| File | Needed from | Where to get it | Recognised as |
|---|---|---|---|
| the use case (`<use-case-id>.yaml`) | M0 | Portal **Step 1 · Edge Use Case Design** → validate the spec → **Download use_case.yaml** | any `*.yaml` / `*.yml` with a top-level `id:` and `task:` |
| the device capability manifest | M0 | The target device's assessment: `ne-device-agent assess --local` writes `capability_manifest.json`, the same file uploaded to the portal in **Step 2 · Target Device** | any `*.json` with `manifest_id` or `device_profile_id` |
| the training scaffold (`neuroedge_train_<id>.py`) | M8 | Portal **Step 3 · Model Strategy** → *Build my own* → **Script (.py)** (a notebook also works) | any `*.py` / `*.ipynb` containing `NEUROEDGE_CONTEXT` |

Check what is here and what is missing:

    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need use_case,capability_manifest
    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need scaffold

One file per kind. If two files of the same kind are here, `check` stops and names both; remove the
one you do not want. A newer download of a file already recorded replaces it, and its gate and every
audit that compared it are asked again.
