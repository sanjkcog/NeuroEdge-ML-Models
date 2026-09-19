# Running the MiniRocket + Ridge baseline

This is the `time-series-ml` honesty floor: no GPU needed, trains in seconds on a laptop CPU. Run
this **before** `1DCNN/train.py` -- the CNN's `train.py` reads this baseline's
`baseline_metrics.json` to fill in `beats_baseline`.

## 0. Bring the data along

Copy the whole use-case folder (this folder's parent, `cnc_drift_1dcnn-timeseries/`) to wherever
you run this, preserving the relative layout:

```
cnc_drift_1dcnn-timeseries/
  use_case.lock.json
  data/splits/{train,val,test}.json
  data/contract/*.parquet          <- gitignored; must be copied by hand or rebuilt
  common/                          <- ts_data.py + metrics.py, SHARED with 1DCNN/ -- required
  MiniRocket/                      <- this folder
  1DCNN/
```

`train.py`/`eval.py` here import `common.ts_data`/`common.metrics` via a `sys.path` insert of
this folder's parent (the dest root) -- `common/` must sit alongside `MiniRocket/` and `1DCNN/`.

`data/contract/*.parquet` and `data/synthetic/*.parquet` are gitignored (regenerable from
`data/raw/` + the lock, or from `data/synth/gen_synth.py`) -- `git clone` alone will not bring
them. If you cloned this repo instead of copying a working tree that already has them, either
copy the parquet files directly or ask the data-engineering stage to rebuild `data/contract/`.

## 1. Install

```bash
cd MiniRocket
python -m venv .venv && source .venv/bin/activate   # or your platform's equivalent
pip install -r requirements.txt
```

🔴 This installs `aeon`'s MiniRocket (BSD-3-Clause). Never install `angus924/minirocket` directly
-- the original reference implementation is GPL-3.0 (`time-series-ml` license rule).

## 2. Train (fits in seconds to low minutes on CPU)

```bash
python train.py --config config.yaml
```

Writes `runs/<run_id>/metrics.json` + `runs/<run_id>/minirocket_ridge.joblib`, and copies both to
`baseline_metrics.json` / `baseline_model.joblib` at this folder's root (the paths `1DCNN/train.py`
reads by default).

## 3. Held-out evaluation (only when you are ready to report the final number)

```bash
python eval.py --config config.yaml --model baseline_model.joblib --split ../data/splits/test.json --out test_metrics.json
```

`eval.py` is the only script here allowed to open `test.json`, and only via this explicit
`--split` argument -- never by default.

🔴 **Pickle safety.** `--model` is loaded with `joblib.load`, which executes arbitrary code on
unpickle. `eval.py` refuses any `--model` path that resolves outside this `MiniRocket/` folder
(an absolute path elsewhere, or a `../` escape) -- only ever point it at a `baseline_model.joblib`
**you produced yourself** with `train.py` in this folder. Never load a joblib file you downloaded
or received from someone else without treating it as untrusted code.

## What you get

- `baseline_metrics.json` -- the HEADLINE (pooled window-level recall @ FPR 0.01, realised FPR,
  PR-AUC, confusion matrix, at the val-calibrated threshold), computed by the SAME shared function
  the 1D-CNN uses, so `beats_baseline` compares like with like; plus a per-unit RATE TABLE and
  event diagnostics (diagnostic only), all measured with the SAME splits as the 1D-CNN.
- No `model.onnx` -- `time-series-ml` is explicit that MiniRocket has no edge-deployment path in
  this stack (the transform emits ~10k features into a linear head, not the device's
  `{1, C, W}` ONNX Conv graph). This is a baseline and a gate, never the shipped artifact.
