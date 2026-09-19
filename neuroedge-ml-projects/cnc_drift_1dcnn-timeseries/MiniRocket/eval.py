#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Held-out evaluation for the MiniRocket + Ridge baseline (M8 round 3 -- Option 3).

This is the ONLY script in `MiniRocket/` allowed to open `data/splits/test.json`, and only when
the caller passes `--split .../test.json` explicitly (never by default).

🔴 SECURITY: `--model` is loaded with `joblib.load`, which unpickles arbitrary Python objects and
can execute code. This script REFUSES any `--model` path that resolves outside this MiniRocket
package's own directory tree (code-review HIGH #B) -- only ever point it at a
`baseline_model.joblib` YOU produced yourself with `train.py` in this folder.

Usage:
    python eval.py --config config.yaml --model baseline_model.joblib --split ../data/splits/test.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0]))
from common import metrics as m  # noqa: E402
from common import ts_data  # noqa: E402


def safe_model_path(model_path: str) -> Path:
    """Refuse to `joblib.load` (unpickle) anything outside this package's own directory tree --
    an absolute path elsewhere, or a `../` escape, is a code-execution risk (code-review HIGH #B).
    """
    resolved = Path(model_path).resolve()
    try:
        resolved.relative_to(HERE)
    except ValueError as exc:
        raise ValueError(
            f"Refusing to load {model_path!r}: it resolves to {resolved}, which is outside this "
            f"MiniRocket package's own directory ({HERE}). Loading a joblib/pickle file executes "
            "arbitrary code -- only ever load a baseline_model.joblib YOU produced yourself with "
            "train.py in this folder, never a file from an untrusted or unrelated location."
        ) from exc
    if not resolved.is_file():
        raise FileNotFoundError(f"{resolved} does not exist or is not a file.")
    return resolved


def main(config_path: str, model_path: str, split_path: str, out_path: str) -> None:
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    lock = ts_data.load_lock(Path(config_path).parent / cfg["lock"]["path"])
    contract_dir = Path(config_path).parent / cfg["paths"]["contract_dir"]
    split_path = Path(split_path)
    split_name = split_path.stem  # "train" | "val" | "test"

    bundle = joblib.load(safe_model_path(model_path))
    transformer, clf, threshold, at_fpr = bundle["transformer"], bundle["classifier"], bundle["threshold"], bundle["at_fpr"]

    windows = ts_data.assemble_real_split(split_name, lock, contract_dir, split_path.parent)
    y = (windows.y > 0).astype(int)
    feats = transformer.transform(windows.x)
    scores = 1.0 / (1.0 + np.exp(-clf.decision_function(feats)))

    # HEADLINE = pooled window metrics (Option 3) at the fixed, already-calibrated threshold.
    headline = m.pooled_window_metrics(y, scores, at_fpr, threshold=threshold)
    target_result = m.meets_target(headline, cfg["task"]["target_recall"], at_fpr, cfg["evaluation"]["fpr_tolerance"])

    stride = lock["timeseries"]["stride_samples"]
    rate = lock["timeseries"]["sample_rate_hz"]
    persistence = cfg["evaluation"]["alarm_persistence_windows"]
    rate_table = m.per_unit_rate_table(windows.y, scores, windows.unit_ids, threshold, stride, rate)
    event_table = m.per_unit_event_diagnostics(windows.y, scores, windows.unit_ids, threshold, persistence, stride, rate)
    if split_name == "test":
        for row in rate_table:
            if row["unit"] == "IM-01R-A03":
                row["single_trial_caveat"] = (
                    "Test holds exactly one worn trial (IM-01R-A03). The window recall reported "
                    "for this unit is a single-trial pass/fail, not a population estimate."
                )

    result = {
        "estimator": "minirocket_ridge",
        "trained_on": "real_train_only",
        "eval_split": "held_out_test" if split_name == "test" else f"self_reported_{split_name}",
        "split_hash": ts_data.split_hash_of("train", "val", splits_dir=split_path.parent),
        # HEADLINE = pooled window metrics.
        **headline,
        **target_result,
        "target_recall": cfg["task"]["target_recall"],
        **m.headline_trial_note(windows.y, windows.unit_ids),
        "per_unit_rate_table": rate_table,
        "per_unit_event_diagnostics": event_table,
    }
    Path(out_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                       if k not in ("per_unit_rate_table", "per_unit_event_diagnostics")}, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--model", default="baseline_model.joblib")
    parser.add_argument("--split", required=True, help="Path to a data/splits/*.json file. Pass test.json ONLY for the final held-out report.")
    parser.add_argument("--out", default="eval_metrics.json")
    args = parser.parse_args()
    main(args.config, args.model, args.split, args.out)
