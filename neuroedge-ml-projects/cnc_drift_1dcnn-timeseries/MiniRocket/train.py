#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MiniRocket + Ridge baseline for cnc_drift_1dcnn-timeseries -- the `time-series-ml` honesty
floor (M8 round 3 -- Option 3). `model_proposed.md` §Baseline: fit on the same windows and the
same `split_hash` as the 1D-CNN, and its headline computed by the SAME shared
`common.metrics.pooled_window_metrics` function the CNN uses, so `beats_baseline` in the CNN's
`train.py` compares like with like. No ONNX export -- `time-series-ml` is explicit that MiniRocket
has no edge-deployment path in this stack (the transform emits ~10k features into a linear head,
not the `{1, C, W}` ONNX Conv graph the device runtime loads).

Uses `aeon`'s MiniRocket (BSD-3), never `angus924/minirocket` (GPL-3.0).

Leakage-safety: the MiniRocket kernels are fixed/random (nothing to fit), but the transform's
PPV feature scaling and the Ridge classifier ARE fit -- on TRAIN windows only, then applied frozen
to val (and, via eval.py, test). This mirrors the leakage rule already binding on the CNN's
normalisation stats.

Usage:
    python train.py --config config.yaml
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml
from sklearn.linear_model import RidgeClassifierCV

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0]))
from common import metrics as m  # noqa: E402
from common import ts_data  # noqa: E402


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


def main(config_path: str) -> None:
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    set_seed(cfg["seed"])

    lock = ts_data.load_lock(Path(config_path).parent / cfg["lock"]["path"])
    if lock["lock_sha256"] != cfg["lock"]["lock_sha256"]:
        raise RuntimeError("use_case.lock.json has changed since this config was written; re-check before training.")

    contract_dir = Path(config_path).parent / cfg["paths"]["contract_dir"]
    splits_dir = Path(config_path).parent / cfg["paths"]["splits_dir"]

    print("Loading real train/val windows from data/contract/ ...")
    train_w = ts_data.assemble_real_split("train", lock, contract_dir, splits_dir)
    val_w = ts_data.assemble_real_split("val", lock, contract_dir, splits_dir)
    print(f"train windows: {len(train_w.y)} ({np.bincount(train_w.y).tolist()})  "
          f"val windows: {len(val_w.y)} ({np.bincount(val_w.y).tolist()})")

    try:
        from aeon.transformations.collection.convolution_based import MiniRocket
    except ImportError as exc:
        raise ImportError(
            "aeon is required for the MiniRocket baseline (pip install aeon). "
            "Never install angus924/minirocket directly -- it is GPL-3.0 "
            "(time-series-ml license rule); aeon's reimplementation is BSD-3."
        ) from exc

    t0 = time.perf_counter()
    transformer = MiniRocket(n_kernels=cfg["minirocket"]["num_kernels"], random_state=cfg["seed"])  # aeon>=1.0 name
    x_train_feat = transformer.fit_transform(train_w.x)  # fit on TRAIN windows only
    x_val_feat = transformer.transform(val_w.x)  # frozen transform applied to val
    fit_s = time.perf_counter() - t0

    y_train = (train_w.y > 0).astype(int)
    y_val = (val_w.y > 0).astype(int)

    clf = RidgeClassifierCV(alphas=cfg["minirocket"]["ridge_alphas"])
    clf.fit(x_train_feat, y_train)  # ridge fit on TRAIN only

    # RidgeClassifier has no predict_proba; use the decision function as the score.
    val_scores = clf.decision_function(x_val_feat)
    # Rescale to (0, 1) with a logistic squash purely for score-range parity with the CNN's
    # sigmoid output -- this is a monotonic transform, so it changes no ranking metric (PR-AUC,
    # recall@FPR, threshold search are all rank-based).
    val_scores_01 = 1.0 / (1.0 + np.exp(-val_scores))

    at_fpr = cfg["task"]["at_fpr"]
    # HEADLINE = pooled window metrics (Option 3), calibrated on these val windows -- the SAME
    # function the CNN's train.py uses, so `beats_baseline` compares like with like.
    threshold = m.threshold_at_fpr(y_val, val_scores_01, at_fpr)
    headline = m.pooled_window_metrics(y_val, val_scores_01, at_fpr, threshold=threshold)
    target_result = m.meets_target(headline, cfg["task"]["target_recall"], at_fpr, cfg["evaluation"]["fpr_tolerance"])

    stride = lock["timeseries"]["stride_samples"]
    rate = lock["timeseries"]["sample_rate_hz"]
    persistence = cfg["evaluation"]["alarm_persistence_windows"]
    rate_table = m.per_unit_rate_table(val_w.y, val_scores_01, val_w.unit_ids, threshold, stride, rate)
    event_table = m.per_unit_event_diagnostics(val_w.y, val_scores_01, val_w.unit_ids, threshold, persistence, stride, rate)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(config_path).parent / cfg["paths"]["runs_dir"] / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    metrics = {
        "estimator": "minirocket_ridge",
        "library": "aeon",
        "num_kernels": cfg["minirocket"]["num_kernels"],
        "fit_seconds": fit_s,
        "eval_split": "self_reported_val",
        "split_hash": ts_data.split_hash_of("train", "val", splits_dir=splits_dir),
        "trained_on": "real_train_only",
        # HEADLINE = pooled window metrics -- the number `beats_baseline` compares against.
        **headline,
        **target_result,
        "target_recall": cfg["task"]["target_recall"],
        **m.headline_trial_note(val_w.y, val_w.unit_ids),
        # Per-unit RATE TABLE + event diagnostics -- descriptive, never gating.
        "per_unit_rate_table": rate_table,
        "per_unit_event_diagnostics": event_table,
    }
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    # Canonical "latest" pointer the 1D-CNN's train.py reads for `beats_baseline`.
    latest = Path(config_path).parent / "baseline_metrics.json"
    latest.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    import joblib

    joblib.dump({"transformer": transformer, "classifier": clf, "threshold": threshold, "at_fpr": at_fpr},
                run_dir / "minirocket_ridge.joblib")
    joblib.dump({"transformer": transformer, "classifier": clf, "threshold": threshold, "at_fpr": at_fpr},
                Path(config_path).parent / "baseline_model.joblib")

    print(json.dumps({k: v for k, v in metrics.items() if k not in ("per_unit_rate_table", "per_unit_event_diagnostics")}, indent=2))
    print(f"MiniRocket+Ridge baseline written to {run_dir} and {latest}")
    print("No ONNX export for MiniRocket -- baseline only (time-series-ml: no edge path for this family).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    main(args.config)
