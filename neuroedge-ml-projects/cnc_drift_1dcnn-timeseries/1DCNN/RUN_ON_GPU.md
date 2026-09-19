# Running the 1D-CNN on your GPU box

AgentForge does not train models -- this folder is the handoff package. Everything below runs on
your own machine (laptop GPU, cloud VM, Colab).

## 0. Run the MiniRocket baseline FIRST

`train.py` refuses to write a package without a baseline (`model-codegen` invariant 9). Run
`../MiniRocket/RUN_ON_GPU.md` first -- it takes seconds on CPU and writes
`../MiniRocket/baseline_metrics.json`, which this folder's `train.py` reads automatically.

## 1. Bring the whole use case along, not just this folder

`train.py` reads paths relative to the use-case dest folder (this folder's parent). Copy the
whole tree, preserving structure:

```
cnc_drift_1dcnn-timeseries/
  use_case.lock.json
  data/splits/{train,val,test}.json           <- tracked in git
  data/contract/*.parquet + manifest.json     <- parquet gitignored, copy by hand or rebuild
  data/synthetic/*.parquet + manifest.json    <- parquet gitignored, copy by hand or regenerate
  inputs/scaffold/*.py                        <- optional, for NEUROEDGE_CONTEXT + MLflow naming
  common/                                     <- ts_data.py + metrics.py, SHARED by both packages below
  MiniRocket/                                 <- run this first (baseline_metrics.json)
  1DCNN/                                      <- this folder
```

`train.py` / `eval.py` import `common.ts_data` / `common.metrics` via a `sys.path` insert of this
folder's parent (the dest root), so `common/` must sit alongside `1DCNN/` and `MiniRocket/` --
copying just `1DCNN/` on its own will not work.

See `data/README.md` (this folder) for exactly what each path is and how to regenerate the
gitignored parquet if you don't have it.

## 2. Provision + install

A GPU is recommended but not required -- the model is ~11.4k parameters and trains in minutes even
on CPU. On a machine with an NVIDIA GPU:

```bash
cd 1DCNN
python -m venv .venv && source .venv/bin/activate    # or your platform's equivalent
pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
```

On CPU-only or a Colab notebook, `pip install -r requirements.txt` alone is enough (torch installs
the CPU build).

Optional (training works without either):

```bash
pip install mlflow==3.16.1                                    # experiment tracking
pip install -e <NeuroEdge-Web>/src/neuroedge_design_usecase \
            -e <NeuroEdge-Web>/src/neuroedge_return          # platform-side package validation
```

## 3. Train

```bash
python train.py --config config.yaml
```

By default this:

1. Trains **two** models with identical seed/hyperparameters -- `real_only` and
   `real_synthetic` (real train + the approved ≤50%-of-real synthetic cap) -- and compares them on
   **real validation only** (never synthetic, never test) at recall @ FPR 0.01.
2. Runs the **leave-one-worn-unit-out cross-validation** (4 folds over `IM-01R-A01/A02/A05/A04`,
   real data only, additive uncertainty band -- never touches `A03`/test).
3. Picks the ablation winner, checks it against the MiniRocket baseline
   (`beats_baseline = winner.recall_at_fpr > baseline.recall_at_fpr`, both the POOLED WINDOW-level
   headline computed by the same shared function -- comparing like with like), exports both
   variants to ONNX, and writes a full `ml-model-package` folder for each plus a canonical
   `runs/<run_id>/model-package/` pointing at the winner.

Single-variant / no-ablation / no-CV runs:

```bash
python train.py --config config.yaml --no-ablation --synthetic capped   # or --synthetic none
python train.py --config config.yaml --no-cv                             # skip the LOWO-CV pass
```

Training logs to MLflow when it is installed (`MLFLOW_TRACKING_URI`, else `./mlruns`); point the
tracking URI at the portal's MLflow server to see the run there. Without MLflow, training still
runs and says so.

## 4. What you get

```
1DCNN/runs/<run_id>/
  ablation_report.json          real_only vs real_synthetic, on real val, plus the winner
  cv_report.json                leave-one-worn-unit-out recall@FPR0.01 min/max/mean
  real_only/          model.onnx, meta.json, metrics.json, model_artifact.json
  real_synthetic/     model.onnx, meta.json, metrics.json, model_artifact.json
  model-package/      <- the WINNER, copied here as the canonical deployable package
```

## 5. Held-out evaluation (only once you are ready to report the final number)

```bash
python eval.py --package runs/<run_id>/model-package --split ../data/splits/test.json --out test_metrics.json
```

`eval.py` is the only script here allowed to open `test.json`, and only via this explicit
`--split` argument. It reports the HEADLINE (pooled window-level recall @ FPR 0.01, realised FPR,
PR-AUC, confusion matrix, at the package's calibrated threshold), a per-unit RATE TABLE (window
recall for worn units; false-alarm rate and false-alarms-per-hour for normal units) plus event
diagnostics (alarm persistence, event recall, time-to-first-alarm -- diagnostic only, never
gating), and the required segmentations (blowhole units A01/A02 vs pure-wear A03/A04/A05; the
same-program `IM-01R` test segment vs the cross-program normals `IMP-05`/`TF-02`) -- with the
single-trial caveat attached directly to the `IM-01R-A03` rate-table row it describes.

## 6. Uploading

This model project never calls the platform's API. Collect
`runs/<run_id>/model-package/` (and, once you have it, `test_metrics.json`) and hand it to
whatever return/upload step your `/agentforge-ml` run is at -- AgentForge's job stops here.
