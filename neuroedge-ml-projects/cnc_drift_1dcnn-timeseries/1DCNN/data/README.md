# Data pointer (this is NOT the data)

`train.py` / `eval.py` read three things from the **use-case dest folder** (this folder's
grandparent, `cnc_drift_1dcnn-timeseries/`), not from anywhere under `1DCNN/`:

| What | Path (relative to `1DCNN/`) | Notes |
|---|---|---|
| Contract dataset | `../data/contract/*.parquet` + `manifest.json` | 10 Hz, 3-channel, per-unit parquet built at M4 from `data/raw/` + `use_case.lock.json`. **Gitignored** (`neuroedge-ml-projects/*/data/contract/*.parquet`) — regenerable from `data/raw/` + the lock, but `data/raw/` is a 44.6 GB KIT CNC-milling archive (CC BY 4.0) that is not re-downloaded here. Copy the parquet files from wherever this use case was built, or ask the data-engineering stage to rebuild `data/contract/`. |
| Splits | `../data/splits/{train,val,test}.json` | Which units go in which split, and (for `IM-01R`, the one unit that legitimately spans all three) the `[cycle_start, cycle_end_exclusive)` bounds of each segment. Tracked in git — nothing to fetch. |
| Synthetic (train-only) | `../data/synthetic/*.parquet` + `manifest.json` | 30 synthetic `tool_wear` + 30 synthetic `normal` runs, block-bootstrapped from the real train-only `IM-01R` head. **Gitignored** blobs, but reproducible byte-for-byte: `python ../data/synth/gen_synth.py --dest .. --seed 20260918 --n-worn 30 --n-normal 30`. |
| The lock | `../use_case.lock.json` | Channel order, window/stride/rate, class order, head shape. `train.py` refuses to run if this file's content does not hash to its own `lock_sha256`. |
| Shared code | `../common/{ts_data.py,metrics.py}` | Data loading + metrics, shared with `../MiniRocket/` (not per-package copies). `train.py`/`eval.py` add the dest root to `sys.path` and `from common import ts_data, metrics` -- `common/` must sit alongside `1DCNN/`. |

**Attribution (CC BY 4.0), required wherever this model's results are shown:**

> Stroebel, R. et al. (2025). *A Multimodal Dataset for Process Monitoring and Anomaly Detection
> in Industrial CNC Milling.* Karlsruhe Institute of Technology. DOI: 10.35097/hvvwn1kfwf7qt48z.

See `../RUN_ON_GPU.md` for exactly what to copy where before running `train.py`.
