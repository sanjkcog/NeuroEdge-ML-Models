# /synth-data — Generate synthetic training data when real data is missing or scarce

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /synth-data · Skills: synthetic-data, time-series-ml`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-ml/synthetic-data.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/time-series-ml.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Arguments

`$ARGUMENTS` — what to synthesize and why (e.g. `"rare weld-crack defect, 500 samples, have CAD"`,
`"seeded spindle-drift cycles, 8 channels at 10 Hz"`). Optional `--render` (3D pipeline) /
`--augment` (diffusion) / `--signal` (parametric time series) to force a family; chosen from
context otherwise.

## What this does

Produces synthetic, **auto-labeled** training data when `/dataset-scout` found no suitable real set or
a class is under-represented (ADR-0014). Spawns `ml-data-engineer`, applying the `synthetic-data`
skill. Rendered data comes with perfect free labels — exactly where manual labeling is most expensive.

## Procedure

1. Pick the family:
   - **3D render** (geometry-correct, free segmentation/depth labels): **NVIDIA Omniverse Replicator**,
     **BlenderProc**, or **Kubric** — needs 3D assets of the object.
   - **Diffusion augmentation** (appearance diversity): **SDXL/ComfyUI** as a final step over rendered
     or real images.
   - Often both: render for structure, diffuse for appearance.
   - **Signal** (time series, ADR-0015): parametric waveform + noise + seeded, labeled anomalies —
     per the `time-series-ml` skill's signal-mode section; the AgentForge simulator's
     `agentforge_simulator/gen_input.py --profile cyclic_multichannel` is the worked example
     (correlated channels, work cycles, `--drift` progression, `--recipe` sidecar). `--profile sensor`
     is single-channel glitch injection only — not for drift/wear objectives. Seeded faults carry
     free labels, the same way renders carry free segmentation.
2. Spawn **`ml-data-engineer`** to define **domain randomization** (lighting, texture, pose, distractors,
   sensor noise) and generate the set with per-class counts.
3. **Mix real + synthetic** and keep a **real hold-out** for validation/test — never validate on
   synthetic only.
4. Emit a reproducible **`synthetic-recipe`** (generator+version, assets, randomization ranges, counts,
   real:synthetic mix). Store the recipe, not the pixels (blobs are hook-blocked).

## Next step

`/auto-label` if any manual labels remain, else `/model-select`.
