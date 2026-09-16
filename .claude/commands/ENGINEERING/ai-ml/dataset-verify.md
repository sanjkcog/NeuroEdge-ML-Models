# /dataset-verify — Download the picked dataset, measure it, split it per unit, withhold test, gate

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /dataset-verify · Skills: dataset-sourcing, time-series-ml, ml-artifact-destination`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/dataset-sourcing.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/time-series-ml.md`
> - `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`
<!-- neuroedge-assets-patched source-version=4cf4279 -->

## Arguments

`$ARGUMENTS` — optional: a dataset id/URL to verify instead of the card's pick, and `--dest <folder>` (the model
folder; inside an `/agentforge-ml` run it is always passed, standalone it is resolved per
`agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`). `--data-dir <path>` overrides where the
raw download lands (default: `$NEUROEDGE_ML_DATA` if set, else `<dest>/../.data/<dataset-id>/`, always gitignored).
`--no-download` profiles data the user already has at `--data-dir`.

## What this does

Closes the gap between a dataset **card** (claims read from a portal) and a dataset **on disk** (measured). This is
the step ADR-0022 M2 `verify`: acquire → profile → split per physical unit → **withhold the test split** → build
the platform-ready upload zip from train + val only → stop at a **human gate**. Spawns `ml-data-engineer`.
Nothing downstream is allowed to re-shuffle what this step decides.

## Procedure

0. **Destination.** `<dest>` from `--dest` (orchestrated) or resolved once per `ml-artifact-destination`
   (standalone). Read `<dest>/data/dataset-card.md`; its front matter names the pick, URL, licence, expected
   channels/classes and the split rule. If there is no card (the user brought their own data), write one from what
   they state before continuing — never require a `/dataset-scout` run that did not happen.
1. **Keys and source.** Per `dataset-sourcing`: KIT / NASA PCoE / Bosch GitHub / data.gov need no key; Kaggle
   needs `KAGGLE_USERNAME`+`KAGGLE_KEY`; Roboflow `ROBOFLOW_API_KEY`; Hugging Face `HF_TOKEN` only for gated sets;
   PHM Society is manual. If a needed key is unset, say which and stop — do not fall back to a mirror whose licence
   is not the rights holder's.
2. **Acquire** into the data dir (outside git; the `pre-commit-ml-artifact` hook blocks blobs). Record the URL,
   checksum and size. Re-read the **licence file that arrived**, not the portal's summary.
3. **Profile → `<dest>/data/profile.json`** (measured, never copied from the card): units found (experiments /
   cutters / machines / recordings), channels present vs the card's required list, sample rates, rows, per-class or
   per-anomaly-type counts, missing values, per-unit class presence. For vision: images, boxes per class,
   duplicates/near-duplicates (FiftyOne), resolution spread. Print **claimed vs measured** side by side; a
   discrepancy is the finding, not an error to hide.
4. **Split per unit** (`time-series-ml` / Web ADR-0002 V-2): group key = the physical unit; grouped assignment,
   or chronological with a one-window gap when no key exists; **fail loudly** when neither exists. Stratify by
   class so no split is single-class (a single-class test set fails the run). Write
   `<dest>/data/splits/{train,val,test}.json` (unit ids + file lists) and a `split_hash` over their contents.
5. **Withhold test.** The test split stays under `<dest>/data/` and is never packaged for a trainer.
6. **Platform-ready upload** → `<dest>/data/portal_upload.zip` from **train + val only**: vision → YOLO layout
   with `data.yaml`, class names identical to the use case; time series → the platform's CSV/JSON layout with a
   `label` column and unit id. Record the layout and the class list in `profile.json`.
7. **Gate (human).** Present claimed vs measured, the split summary, and any licence discrepancy. Outcomes,
   recorded via `gate_state.py` into `<dest>/gates.json`: **approve**; **reject with reason** — the reason chooses
   the next move (a missing channel is fatal to same-family candidates → re-scout with it as a hard constraint; a
   size/quality reason → next candidate); **accept as hold-out** — real but insufficient → keep as val/test and
   route to `/synth-data` for the rare class. At most **two** real candidates are verified per objective before
   synthetic is offered (ADR-0022 D-5). Recorded with `gate_state.py decide` as: approve → `approved`; reject →
   `rejected` with the reason; accept-as-hold-out → `approved` with the note `hold-out only — synth required`, which
   `/agentforge-ml` reads to make M4 mandatory.
8. Update the card's front matter with `local_path`, `split_hash`, `profile: data/profile.json`; add a stage-log
   row to `<dest>/README.md`; print the paths.

## Offline verification

Everything this command writes is a plain file. A user who downloads and inspects by hand can drop
`profile.json` + `splits/` in place and record the approval with `gate_state.py` themselves;
`/agentforge-ml --resume` reads the gate, not the transcript.

## Next step

Approved → `/auto-label` (vision, or the TS window rule) or straight to `/model-select`. Accept-as-hold-out →
`/synth-data`. Rejected → `/dataset-scout` with the reason as a constraint.
