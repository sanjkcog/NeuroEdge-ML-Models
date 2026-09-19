# M9 `train` — external training handoff

The `/agentforge-ml` run is stopped at M9, waiting for an external training run
(`run.json` gate: `{pending: true, stage: train, reason: waiting_external}`). Nothing here trains
or polls. Train on your own machine, then resume.

## Runner

`package` (from `model_proposed.md` §Runner): run the generated code yourself on a laptop GPU, a
VM or Colab. The portal is not the runner for this dataset: it cannot take the approved split
files, would not keep test withheld, and its TS trainer produces no calibrated threshold and no
baseline.

## Commands (full detail in `RUN_ON_GPU.md` and `../MiniRocket/RUN_ON_GPU.md`)

Copy the whole `cnc_drift_1dcnn-timeseries/` tree, including `common/`, `data/contract/*.parquet`
and `data/synthetic/*.parquet` (these are gitignored), then:

```bash
# 1. Baseline first (seconds, CPU). It writes MiniRocket/baseline_metrics.json.
cd MiniRocket && pip install -r requirements.txt
python train.py --config config.yaml

# 2. The 1D-CNN: real-only vs real+synthetic ablation, LOWO-CV, ONNX export, package.
cd ../1DCNN && pip install -r requirements.txt   # add the CUDA torch index on a GPU box
python train.py --config config.yaml
```

Do not run `eval.py` on `test.json` yourself. M10 `eval` runs it once, after resume.

## What M9 waits for

A package at:

```
1DCNN/runs/<run_id>/model-package/
  model.onnx            opset 13, [1,3,64] input, Sigmoid in the graph
  meta.json             lock_sha256 b7a3765f48f6…, decision_threshold calibrated on real val at FPR 0.01
  model_artifact.json   includes extras.baseline (beats_baseline, baseline_trained_on, winner_trained_on)
  metrics.json          eval_split self_reported_val, split_hash, cross_validation spread
```

If you train on another machine, copy `1DCNN/runs/<run_id>/` back into this folder.

## Then

`/agentforge-ml --resume --dest neuroedge-ml-projects/cnc_drift_1dcnn-timeseries` finds the
package, completes M9 and runs M10: `eval.py` once on the held-out test split. The KPI gate is
recall ≥ 0.90 **and** realised FPR ≤ 0.01 (no tolerance), plus `beats_baseline`.
