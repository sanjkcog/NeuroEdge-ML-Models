---
name: synthetic-data
description: Generate synthetic training data when a real dataset is missing, too small, or missing rare classes — 3D-render pipelines (NVIDIA Omniverse Replicator, BlenderProc, Kubric) and diffusion-based augmentation (SDXL/ComfyUI) for vision, plus signal mode (parametric multi-channel cyclic sensor synthesis) for time series. Use when dataset-sourcing finds no suitable real data or a class is under-represented.
origin: NeuroEdge AgentForge
---

# Synthetic Data Generation

When [`dataset-sourcing`](dataset-sourcing.md) concludes "no suitable real dataset" — or a rare/
safety-critical class (a specific defect) has too few real examples — synthesize it. Rendered data
comes with **perfect, free labels** (the renderer knows every pixel's class, depth, and pose), which
is exactly where manual labeling is most expensive.

## When to Activate

- `dataset-sourcing` verdict is "no suitable real dataset" or "severe class imbalance"
- `/synth-data` is invoked
- The target class is rare, dangerous to capture, or privacy-restricted

## Three families

Families 1 and 2 are **vision**. Family 3 is **signal mode**, for sensor/process time series
(ADR-0015 decision 5) — a renderer has nothing to offer a vibration trace, and reaching for one is
the most common wrong turn here.

### 1. 3D-render pipelines (structure-accurate, auto-labeled)

| Tool | Strength |
|---|---|
| **NVIDIA Omniverse Replicator** | physically-based SDG engine; built-in annotators (2D/3D bbox, semantic/instance seg, depth, normals); domain randomization API |
| **BlenderProc** | scriptable Blender pipeline; procedural scenes; large asset reuse (Objaverse/-XL) |
| **Kubric** | scalable simulation + render + annotation, good for video/motion |

Use these when you have (or can get) 3D assets of the object and want geometry-correct labels —
defect detection, robotics, pose. Replicator's annotators give you segmentation/depth for free.

### 2. Diffusion-based augmentation (appearance-diverse)

Use **SDXL via ComfyUI** (or similar) as a **final augmentation step** — vary lighting, texture,
background, and weather on top of rendered or real images to close the appearance gap. Good for
robustness; weaker for precise geometry labels than a renderer.

### 3. Signal mode — parametric synthesis for time series

No renderer, no diffusion model: a waveform built from parameters, with seeded anomalies that carry
their labels for free. The worked example is the NeuroEdge simulator's
`agentforge_simulator/gen_input.py`.

**Three properties a synthetic sensor set must have**, and that a single-channel uniform stream does
not. Getting any of them wrong produces data a model can fit perfectly and learn nothing from:

| Property | Why it matters |
|---|---|
| **Correlated channels** | The fault signature lives in how channels move *together*. Independent per-channel noise is separable noise — a model trained on it learns a threshold on one channel, which is not the phenomenon. |
| **Cycle structure** | Real processes run in work cycles — entry, steady state, exit. A window's position within a cycle changes what it means. A uniform stream has no such structure and no cycle boundary to score against. |
| **Progression across cycles** | Degradation accumulates. A per-row anomaly coin flip models a *glitch*; the thing most PdM objectives care about is a *trend*. These are different problems. |

```bash
# Multi-channel cyclic time-series sensor generator — all three properties, stdlib only.
python agentforge_simulator/gen_input.py --profile cyclic_multichannel \
  --rows 800 --rows-per-cycle 80 \
  --channel-names spindle_load,axis_err,vibration_rms \
  --drift ramp-recover --seed 20260914 --start-ts 2026-01-01T00:00:00Z --recipe

# Single channel, uniform stream — glitch injection, no cycles, no progression.
python agentforge_simulator/gen_input.py --profile sensor --rows 500 --hz 10 --seed 20260914
```

`--drift` selects how the fault magnitude evolves across cycles: `none`, `ramp`, `step`, or
`ramp-recover` (degrade to a peak, then a maintenance action recovers it). Output is **wide CSV**:
`ts`, `cycle_index`, `row_in_cycle`, one column per channel, `severity`, `label`.

Four rules that are specific to signal mode:

- 🔴 **The column order IS the feature order.** Serialize channels in the order the model is trained
  and served with, and name them so that order is stable — a `std::map` sorts `sensor_10` before
  `sensor_2`, which is silent accuracy loss at the deployment seam.
- 🔴 **`--rows-per-cycle` must exceed the model's window size**, or no window ever fills and the
  pipeline scores nothing — usually without an error.
- **Always pass `--seed`, and `--start-ts` too.** The seed reproduces the *values*; without a pinned
  start timestamp the `ts` column is wall clock, so reruns differ in that column and the recipe cannot
  regenerate the file byte-for-byte. The generator warns for a missing seed and notes a missing
  `--start-ts`.
- **Record the label rule.** Labels here are per-cycle (`severity >= threshold`), so every row in a
  cycle shares one label. `--recipe` writes that rule into the `synthetic-recipe` sidecar.

## Domain randomization & the sim-to-real gap

- **Randomize** lighting, textures, camera pose, distractors, backgrounds so the model can't overfit
  to render artifacts — the single most important lever for sim-to-real transfer. **Signal mode's
  equivalent** is randomizing per-channel baselines, gains, noise floors, and cycle length across
  runs — a model that has only seen one machine's constants has memorized that machine.
- **Mix real + synthetic.** Pure-synthetic training usually underperforms; a small real validation/
  test set is mandatory to measure the real gap (never validate on synthetic-only).
- Add sensor-realistic **noise models** (blur, sensor noise) so synthetic images match the deployment
  camera.

## Output

A `synthetic-recipe` — generator + version, asset sources, randomization ranges, per-class counts,
and the real:synthetic mix. Reproducible: another run of the recipe reproduces the set. Feeds
`/data-labeling` (usually labels come free from the renderer) and `/model-build`.

## Do NOT

- Do not reach for a renderer or a diffusion model for a time-series objective — use signal mode.
- Do not synthesize a single uniform channel and call it sensor data: no correlation, no cycles, and
  no progression means no learnable signal.
- Do not generate without a seed, and do not ship a dataset whose label rule is unrecorded.
- Do not train and evaluate on synthetic only — always hold out **real** data for validation/test.
- Do not commit rendered image dirs into git (the `pre-commit-ml-artifact` hook blocks blobs); store
  the **recipe**, regenerate the pixels.
- Do not present synthetic samples as real in any dataset-card — provenance must stay labeled.
