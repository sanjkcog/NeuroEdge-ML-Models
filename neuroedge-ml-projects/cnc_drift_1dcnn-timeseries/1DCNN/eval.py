#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Held-out evaluation for a trained 1D-CNN model-package (M8 round 3 -- Option 3).

This is the ONLY script in `1DCNN/` allowed to open `data/splits/test.json`, and only when the
caller passes `--split .../test.json` explicitly (never by default) -- `train.py` never reads it.

Loads `model.onnx` + `meta.json` from a model-package folder (e.g.
`runs/<run_id>/model-package/`), runs it with onnxruntime (no PyTorch dependency needed for
eval), and reports:

  - the HEADLINE = pooled window-level recall_at_fpr / fpr / pr_auc at the package's calibrated
    threshold (never a per-unit max-boolean -- ml-eval-reviewer round 2 CRITICAL: that
    construction saturates FPR under pure noise)
  - a per-unit RATE TABLE (window recall for worn units, false-alarm rate / false-alarms-per-hour
    for normal units) plus event diagnostics (alarm persistence, event recall,
    time-to-first-alarm) -- descriptive only, never gating
  - the required segmentations: A01/A02 (tool wear + seeded blowholes) vs A03/A04/A05 (pure tool
    wear); the IM-01R same-program normal segment vs the cross-program normals
  - the single-trial caveat, attached directly to the A03 rate-table row it describes

Usage:
    python eval.py --package runs/<run_id>/model-package --split ../data/splits/test.json
    python eval.py --package runs/<run_id>/model-package --split ../data/splits/val.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import onnxruntime as ort
import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[0]))
from common import metrics as m  # noqa: E402
from common import ts_data  # noqa: E402

SINGLE_TRIAL_CAVEAT = (
    "Test holds exactly one worn trial (IM-01R-A03). The window recall reported for this unit "
    "is a single-trial pass/fail, NOT a population estimate over multiple independent worn units "
    "(data/label-manifest.md, model_proposed.md §Evaluation)."
)


def main(package_dir: str, split_path: str, config_path: str, out_path: str) -> None:
    package_dir = Path(package_dir)
    meta = json.loads((package_dir / "meta.json").read_text(encoding="utf-8"))
    pkg_metrics_path = package_dir / "metrics.json"
    pkg_metrics = json.loads(pkg_metrics_path.read_text(encoding="utf-8")) if pkg_metrics_path.exists() else {}
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    lock = ts_data.load_lock(Path(config_path).parent / cfg["lock"]["path"])

    split_path = Path(split_path)
    split_name = split_path.stem  # "train" | "val" | "test"
    if split_name == "test":
        print("Evaluating on the WITHHELD test split (data/splits/test.json), by explicit request.")

    contract_dir = Path(config_path).parent / cfg["paths"]["contract_dir"]
    windows = ts_data.assemble_real_split(split_name, lock, contract_dir, split_path.parent)

    sess = ort.InferenceSession(str(package_dir / "model.onnx"), providers=["CPUExecutionProvider"])
    scores = sess.run(None, {"input": windows.x})[0].reshape(-1)
    y = (windows.y > 0).astype(int)
    # The package's decision_threshold was calibrated on real VAL windows at meta["at_fpr"].
    threshold = meta["decision_threshold"]
    at_fpr = meta["at_fpr"]

    # HEADLINE = pooled window metrics (Option 3) -- fixed threshold, no re-calibration on test.
    headline = m.pooled_window_metrics(y, scores, at_fpr, threshold=threshold)
    target_result = m.meets_target(
        headline, cfg["task"]["target_recall"], at_fpr, cfg["evaluation"]["fpr_tolerance"]
    )

    stride = lock["timeseries"]["stride_samples"]
    rate = lock["timeseries"]["sample_rate_hz"]
    persistence = cfg["evaluation"]["alarm_persistence_windows"]
    rate_table = m.per_unit_rate_table(windows.y, scores, windows.unit_ids, threshold, stride, rate)
    event_table = m.per_unit_event_diagnostics(windows.y, scores, windows.unit_ids, threshold, persistence, stride, rate)

    if split_name == "test":
        for row in rate_table:
            if row["unit"] == "IM-01R-A03":
                row["single_trial_caveat"] = SINGLE_TRIAL_CAVEAT

    ev_cfg = cfg["evaluation"]
    segments = {
        "blowhole_units_A01_A02": m.segment_rows(rate_table, ev_cfg["blowhole_units"]),
        "pure_tool_wear_units_A03_A04_A05": m.segment_rows(rate_table, ev_cfg["pure_wear_units"]),
        "im01r_program_normal": m.segment_rows(rate_table, [ev_cfg["im01r_program_test_normal"]]),
        "cross_program_normals": m.segment_rows(rate_table, ev_cfg["cross_program_test_normal_units"]),
    }

    result = {
        "eval_split": "held_out_test" if split_name == "test" else f"self_reported_{split_name}",
        "split_hash": ts_data.split_hash_of("train", "val", splits_dir=split_path.parent),
        # HEADLINE = pooled window metrics -- the gating number (Option 3, M8 round 3).
        **headline,
        **target_result,
        "target_recall": cfg["task"]["target_recall"],
        **m.headline_trial_note(windows.y, windows.unit_ids),
        # The leave-one-worn-unit-out spread from training travels with the single-trial number.
        "cross_validation": pkg_metrics.get("cross_validation"),
        "im01r_deviation_note": (
            "IM-01R is the only normal run of the worn-tool program and spans train/val/test by "
            "time (documented deviation in data/label-manifest.md); its test segment is the tail "
            "of a run whose head was trained on, which can flatter specificity."
        ) if split_name == "test" else None,
        # Per-unit RATE TABLE + event diagnostics -- descriptive, never gating.
        "per_unit_rate_table": rate_table,
        "per_unit_event_diagnostics": event_table,
        "segments": segments,
    }
    Path(out_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items()
                       if k not in ("per_unit_rate_table", "per_unit_event_diagnostics", "segments")}, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, help="Path to a model-package folder (must contain model.onnx + meta.json).")
    parser.add_argument("--split", required=True, help="Path to a data/splits/*.json file. Pass test.json ONLY for the final held-out report.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", default="eval_metrics.json")
    args = parser.parse_args()
    main(args.package, args.split, args.config, args.out)
