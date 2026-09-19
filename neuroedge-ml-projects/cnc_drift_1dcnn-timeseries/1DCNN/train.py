#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Training entry point for the cnc_drift_1dcnn-timeseries 1D-CNN (M8, round 3 -- Option 3).

Reads ONLY `data/splits/train.json` and `data/splits/val.json` -- never `test.json` (leakage
rule, `model-codegen` invariant 3 / `ml-model-package`). `eval.py` is the only script that may
read `test.json`, and only when given it explicitly.

**Headline / gating metric = POOLED WINDOW-level recall_at_fpr / fpr / pr_auc** (human-approved
Option 3, M8 round 3). Round 2's per-unit max-aggregation "headline" is REMOVED from every gating
path: ml-eval-reviewer found it saturates almost regardless of the model (flagging a unit whenever
the MAX of its ~200-600 windows crosses a threshold calibrated at a 1% POOLED window FPR gives
~3.74-of-4 normal units alarming under pure noise). Per-unit reporting is now a descriptive RATE
TABLE (window recall / false-alarm rate / false-alarms-per-hour per unit), never a second gating
construction, plus separate, explicitly diagnostic-only event metrics (alarm persistence,
event recall, time-to-first-alarm).

By default (`ablation.enabled: true` in config.yaml) this trains TWO models with identical
seed/splits/hyperparameters -- real-only and real+capped-synthetic -- compares them on REAL VAL
ONLY (never synthetic, never test), and keeps synthetic in the deployable model only if it wins
(model_proposed.md §Synthetic, "Required M8 output -- the ablation"). Both runs are written to
disk regardless of outcome.

Also runs the leave-one-worn-unit-out cross-validation required by model_proposed.md §Evaluation
(train+val worn units only, real data only, additive to the official protocol -- never a
replacement, never touching A03/test).

Usage:
    python train.py --config config.yaml
    python train.py --config config.yaml --no-ablation --synthetic capped   # single variant
    python train.py --config config.yaml --no-cv                            # skip the LOWO-CV pass
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import yaml
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

HERE = Path(__file__).resolve().parent
# common/ holds ts_data + metrics, shared with MiniRocket/ (code-review HIGH #C) -- inserted via
# an absolute path relative to this file, so it works regardless of the caller's cwd.
sys.path.insert(0, str(HERE.parents[0]))
from common import metrics as m  # noqa: E402
from common import ts_data  # noqa: E402
from model import ScoreModel, build_model, count_parameters  # noqa: E402
from packaging_ import build_meta, export_onnx, write_package  # noqa: E402


# --------------------------------------------------------------------------------------------
# Reproducibility (pytorch-patterns.md)
# --------------------------------------------------------------------------------------------
def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def device_of() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


# --------------------------------------------------------------------------------------------
# Reuse exactly the scaffold's NEUROEDGE_CONTEXT literal -- never its training body
# (model-codegen: "Use exactly two things from a usable scaffold: its NEUROEDGE_CONTEXT ... and
# its return helper"). Extracted by locating the r'''...''' JSON block, never by importing/
# executing the scaffold module.
# --------------------------------------------------------------------------------------------
def load_neuroedge_context(scaffold_path: Path) -> dict | None:
    if not scaffold_path.exists():
        return None
    text = scaffold_path.read_text(encoding="utf-8")
    match = re.search(r"NEUROEDGE_CONTEXT\s*=\s*json\.loads\(r'''(.*?)'''\)", text, re.DOTALL)
    if not match:
        return None
    return json.loads(match.group(1))


def cosine_warmup_lambda(step: int, total_steps: int, warmup_steps: int) -> float:
    if step < warmup_steps:
        return (step + 1) / max(warmup_steps, 1)
    progress = (step - warmup_steps) / max(total_steps - warmup_steps, 1)
    return 0.5 * (1.0 + math.cos(math.pi * min(progress, 1.0)))


def metric_value(name: str, headline: dict) -> float:
    """Look up a named metric from the (pooled-window) headline dict, for `config.yaml`'s
    `training.monitor` / `training.tie_break`."""
    if name not in headline or headline[name] is None:
        raise ValueError(f"Unknown or unavailable metric {name!r} for training.monitor/tie_break; "
                          f"choose one of {sorted(k for k, v in headline.items() if v is not None)}")
    return headline[name]


def build_diagnostics(
    y_true: np.ndarray, scores: np.ndarray, unit_ids: np.ndarray, threshold: float, cfg: dict, lock: dict
) -> dict:
    """Per-unit RATE TABLE + event diagnostics -- descriptive only, never a gating construction
    (data/label-manifest.md #4; the required blowhole-vs-pure-wear and same-program-vs-
    cross-program segmentations from model_proposed.md §Evaluation)."""
    stride = lock["timeseries"]["stride_samples"]
    rate = lock["timeseries"]["sample_rate_hz"]
    persistence = cfg["evaluation"]["alarm_persistence_windows"]
    rate_table = m.per_unit_rate_table(y_true, scores, unit_ids, threshold, stride, rate)
    event_table = m.per_unit_event_diagnostics(y_true, scores, unit_ids, threshold, persistence, stride, rate)
    ev_cfg = cfg["evaluation"]
    return {
        "rate_table": rate_table,
        "event_diagnostics": event_table,
        "segments": {
            "blowhole_units_A01_A02": m.segment_rows(rate_table, ev_cfg["blowhole_units"]),
            "pure_tool_wear_units_A03_A04_A05": m.segment_rows(rate_table, ev_cfg["pure_wear_units"]),
            "im01r_program_normal": m.segment_rows(rate_table, [ev_cfg["im01r_program_test_normal"]]),
            "cross_program_normals": m.segment_rows(rate_table, ev_cfg["cross_program_test_normal_units"]),
        },
    }


def train_variant(
    variant: str,  # "real_only" | "real_synthetic"
    cfg: dict,
    lock: dict,
    real_train: ts_data.Windows,
    real_val: ts_data.Windows,
    synthetic_train: ts_data.Windows | None,
    device: torch.device,
    mlflow_call,
) -> dict:
    set_seed(cfg["seed"])
    use_synthetic = variant == "real_synthetic"

    if use_synthetic:
        assembled = ts_data.concat_windows(real_train, synthetic_train)
    else:
        assembled = real_train

    # Normalisation is fit on REAL TRAIN windows only, in BOTH variants (never real+synthetic).
    # Synthetic std runs 81-91% of real on two channels (data/synth-review.md), so mixing it into
    # the normalisation stats would itself shrink/shift the exact signal the model must detect --
    # an overfitting/leakage risk distinct from (and on top of) mixing synthetic into training.
    mean, std = ts_data.fit_normalization(real_train.x)
    x_train_aug = ts_data.augment_train_windows(
        assembled.x,
        assembled.source,
        channel_std=assembled.x.std(axis=(0, 2)),
        seed=cfg["seed"],
        jitter_std_frac=tuple(cfg["augmentation"]["jitter_std_frac"]),
        gain_range=tuple(cfg["augmentation"]["gain_range"]),
        time_shift_max=cfg["augmentation"]["time_shift_max_samples"],
    )

    y_train_bin = (assembled.y > 0).astype("float32")
    n_pos = int(y_train_bin.sum())
    n_neg = len(y_train_bin) - n_pos
    pos_weight = torch.tensor([n_neg / max(n_pos, 1)], dtype=torch.float32, device=device)

    train_ds = TensorDataset(torch.from_numpy(x_train_aug), torch.from_numpy(y_train_bin))
    val_ds = TensorDataset(torch.from_numpy(real_val.x), torch.from_numpy((real_val.y > 0).astype("float32")))
    gen = torch.Generator().manual_seed(cfg["seed"])
    train_loader = DataLoader(train_ds, batch_size=cfg["training"]["batch_size"], shuffle=True,
                               generator=gen, num_workers=cfg["training"]["num_workers"])
    val_loader = DataLoader(val_ds, batch_size=cfg["training"]["batch_size"])

    model = build_model(mean, std, n_features=len(cfg["timeseries"]["feature_order"]),
                         dropout=cfg["model"]["dropout"]).to(device)
    print(f"[{variant}] {count_parameters(model)} parameters, "
          f"train windows {len(y_train_bin)} (pos={n_pos}, neg={n_neg}), val windows {len(real_val.y)}")

    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg["optimizer"]["lr"],
                                   weight_decay=cfg["optimizer"]["weight_decay"])
    total_steps = cfg["training"]["epochs"] * max(len(train_loader), 1)
    warmup_steps = max(1, int(cfg["optimizer"]["warmup_frac"] * total_steps))
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lr_lambda=lambda s: cosine_warmup_lambda(s, total_steps, warmup_steps)
    )
    bce = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    at_fpr = cfg["task"]["at_fpr"]
    monitor = cfg["training"]["monitor"]
    tie_break = cfg["training"]["tie_break"]

    def run_val() -> tuple[float, dict, np.ndarray]:
        model.eval()
        all_logits, all_y, total_loss = [], [], 0.0
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                logit = model(xb).squeeze(1)
                total_loss += float(bce(logit, yb)) * len(yb)
                all_logits.append(logit.cpu())
                all_y.append(yb.cpu())
        logits = torch.cat(all_logits)
        scores = torch.sigmoid(logits.clamp(-15.0, 15.0)).numpy()
        y = torch.cat(all_y).numpy().astype(int)
        # HEADLINE = pooled window metrics (Option 3). Threshold calibrated on these same
        # validation windows at the lock's at_fpr.
        headline = m.pooled_window_metrics(y, scores, at_fpr)
        return total_loss / len(val_ds), headline, scores

    best = {"primary": -1.0, "tie": -1.0, "epoch": 0, "state": None, "train_loss": None, "val_loss": None}
    stale = 0
    t0 = time.perf_counter()
    epoch = 0
    for epoch in range(1, cfg["training"]["epochs"] + 1):
        model.train()
        total_loss = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad(set_to_none=True)
            logit = model(xb).squeeze(1)
            loss = bce(logit, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            scheduler.step()
            total_loss += float(loss) * len(yb)
        train_loss = total_loss / len(train_ds)
        val_loss, headline, _scores = run_val()
        print(f"[{variant}] epoch {epoch}/{cfg['training']['epochs']} "
              f"train_loss={train_loss:.4f} val_loss={val_loss:.4f} "
              f"val_pr_auc={headline['pr_auc']:.3f} "
              f"val_recall@fpr{at_fpr:g}={headline['recall_at_fpr']:.3f} (pooled window)")
        mlflow_call("log_metrics", {
            f"{variant}/train_loss": train_loss, f"{variant}/val_loss": val_loss,
            f"{variant}/val_pr_auc": headline["pr_auc"],
            f"{variant}/val_recall_at_fpr": headline["recall_at_fpr"],
        }, step=epoch)

        primary = metric_value(monitor, headline)
        tie = metric_value(tie_break, headline)
        improved = (primary, tie) > (best["primary"], best["tie"])
        if improved:
            best = {"primary": primary, "tie": tie, "epoch": epoch,
                    "state": copy.deepcopy(model.state_dict()), "train_loss": train_loss, "val_loss": val_loss}
            stale = 0
        else:
            stale += 1
            if stale >= cfg["training"]["patience"]:
                print(f"[{variant}] early stop: no improvement ({monitor} tie-broken by {tie_break}) "
                      f"for {cfg['training']['patience']} epochs")
                break
    training_duration_s = time.perf_counter() - t0

    model.load_state_dict(best["state"])
    model.eval()
    val_loss, headline_final, val_scores = run_val()
    target_result = m.meets_target(
        headline_final, cfg["task"]["target_recall"], at_fpr, cfg["evaluation"]["fpr_tolerance"]
    )
    diagnostics = build_diagnostics(real_val.y, val_scores, real_val.unit_ids,
                                     headline_final["decision_threshold"], cfg, lock)

    return {
        "variant": variant,
        "model": model,
        "mean": mean,
        "std": std,
        "epochs_completed": epoch,
        "best_epoch": best["epoch"],
        "train_loss": best["train_loss"],
        "val_loss": val_loss,
        "training_duration_s": training_duration_s,
        "headline": headline_final,
        **target_result,
        "diagnostics": diagnostics,
        "n_train_windows": len(y_train_bin),
        "n_train_pos": n_pos,
        "n_train_neg": n_neg,
        "used_synthetic": use_synthetic,
    }


# --------------------------------------------------------------------------------------------
# Leave-one-worn-unit-out CV (additive uncertainty band, train+val worn units only, real only)
# --------------------------------------------------------------------------------------------
def run_lowo_cv(cfg: dict, lock: dict, real_train: ts_data.Windows, real_val: ts_data.Windows, device: torch.device) -> dict:
    """Each fold holds out ONE worn unit; its threshold is calibrated on that fold's HELD-IN
    normal windows (never on the held-out unit -- `threshold_at_fpr` only ever looks at y==0
    windows, and the held-out worn unit is always y==1, so this holds automatically). Since each
    fold's validation set contains exactly one worn unit, the fold's pooled `recall_at_fpr` IS
    that unit's window recall at the fold's threshold, and the fold's pooled `fpr` is measured
    entirely on the held-in normal windows."""
    worn_units = cfg["cross_validation"]["worn_units"]
    all_real = ts_data.concat_windows(real_train, real_val)
    normal_train = ts_data.exclude_unit(real_train, worn_units)
    normal_val = ts_data.exclude_unit(real_val, worn_units)
    worn_pool = ts_data.filter_by_unit(all_real, worn_units)

    fold_cfg = json.loads(json.dumps(cfg))  # cheap deep copy
    fold_cfg["training"]["epochs"] = cfg["cross_validation"]["epochs"]
    fold_cfg["training"]["patience"] = cfg["cross_validation"]["patience"]

    fold_results = []
    for held_out in worn_units:
        fold_val_worn = ts_data.filter_by_unit(worn_pool, [held_out])
        fold_train_worn = ts_data.exclude_unit(worn_pool, [held_out])
        fold_train = ts_data.concat_windows(normal_train, fold_train_worn)
        fold_val = ts_data.concat_windows(normal_val, fold_val_worn)

        def _noop(*_a, **_k):
            return None

        result = train_variant("cv_" + held_out, fold_cfg, lock, fold_train, fold_val, None, device, _noop)
        fold_results.append({
            "held_out_unit": held_out,
            "recall_at_fpr": result["headline"]["recall_at_fpr"],  # this fold's held-out unit's window recall
            "fpr": result["headline"]["fpr"],  # pooled over this fold's held-in normal windows
            "pr_auc": result["headline"]["pr_auc"],
            "decision_threshold": result["headline"]["decision_threshold"],
            "n_val_windows": len(fold_val.y),
        })
        print(f"[cv] held out {held_out}: recall@fpr={result['headline']['recall_at_fpr']:.3f} "
              f"fpr={result['headline']['fpr']:.4f} pr_auc={result['headline']['pr_auc']:.3f}")

    recalls = [f["recall_at_fpr"] for f in fold_results]
    return {
        "protocol": "leave_one_worn_unit_out",
        "worn_units": worn_units,
        "folds": fold_results,
        "recall_at_fpr_min": float(np.min(recalls)),
        "recall_at_fpr_max": float(np.max(recalls)),
        "recall_at_fpr_mean": float(np.mean(recalls)),
        "note": "Additive uncertainty band around the single-trial (A03) test number. Real data "
                "only, never touches A03/test. Each fold's threshold is calibrated on that fold's "
                "held-in normal windows only, never on the held-out worn unit.",
    }


# --------------------------------------------------------------------------------------------
# MLflow (optional; reuses only the scaffold's run-naming/tag STRING LITERALS)
# --------------------------------------------------------------------------------------------
def make_mlflow_caller(cfg: dict, split_hash: str):
    try:
        import mlflow
    except ImportError:
        print("mlflow is not installed -- training without experiment tracking (pip install mlflow to enable).")
        return lambda *a, **k: None, None

    def call(name, *args, **kwargs):
        nonlocal mlflow
        if mlflow is None:
            return None
        try:
            return getattr(mlflow, name)(*args, **kwargs)
        except Exception as exc:
            print(f"MLflow logging disabled ({type(exc).__name__}: {exc})")
            mlflow = None
            return None

    import os
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
        tracking_uri = (HERE / "mlruns").resolve().as_uri()
    call("set_tracking_uri", tracking_uri)
    call("set_experiment", cfg["mlflow"]["experiment"])
    if mlflow is not None and mlflow.active_run() is not None:
        call("end_run")
    run = call("start_run", run_name=f"{cfg['mlflow']['use_case_id']}-1d-cnn")
    call("log_params", {
        "arch": "1d-cnn", "window": cfg["timeseries"]["window_samples"], "stride": cfg["timeseries"]["stride_samples"],
        "lr": cfg["optimizer"]["lr"], "epochs": cfg["training"]["epochs"], "seed": cfg["seed"],
        "split_hash": split_hash, "lock_sha256": cfg["lock"]["lock_sha256"],
    })
    return call, run


def main(config_path: str, ablation: bool, synthetic_variant: str, run_cv: bool) -> None:
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    lock = ts_data.load_lock(Path(config_path).parent / cfg["lock"]["path"])
    if lock["lock_sha256"] != cfg["lock"]["lock_sha256"]:
        raise RuntimeError("use_case.lock.json has changed since this config was written; re-check before training.")
    ts_data.assert_window_fits_gap(
        cfg["timeseries"]["window_samples"], cfg["timeseries"]["sample_rate_hz"],
        cfg["timeseries"]["split_boundary_gap_seconds"],
    )
    set_seed(cfg["seed"])
    device = device_of()
    print(f"Device: {device}")

    contract_dir = Path(config_path).parent / cfg["paths"]["contract_dir"]
    splits_dir = Path(config_path).parent / cfg["paths"]["splits_dir"]
    synthetic_dir = Path(config_path).parent / cfg["paths"]["synthetic_dir"]

    print("Loading real train/val windows from data/contract/ ...")
    real_train = ts_data.assemble_real_split("train", lock, contract_dir, splits_dir)
    real_val = ts_data.assemble_real_split("val", lock, contract_dir, splits_dir)
    print(f"real train windows: {len(real_train.y)} {np.bincount(real_train.y).tolist()}  "
          f"real val windows: {len(real_val.y)} {np.bincount(real_val.y).tolist()}")
    val_trial_note = m.headline_trial_note(real_val.y, real_val.unit_ids)

    class_names = lock["class_names"]
    real_train_counts = {class_names[c]: n for c, n in enumerate(np.bincount(real_train.y, minlength=2))}
    synthetic_train = None
    if ablation or synthetic_variant == "capped":
        print("Loading capped synthetic windows from data/synthetic/ ...")
        synthetic_train = ts_data.assemble_synthetic(
            lock, cfg["synthetic"]["cap_fraction"], real_train_counts, cfg["synthetic"]["seed"], synthetic_dir,
        )
        print(f"synthetic (capped) windows: {len(synthetic_train.y)} {np.bincount(synthetic_train.y).tolist()}")

    split_hash = ts_data.split_hash_of("train", "val", splits_dir=splits_dir)
    mlflow_call, mlflow_run = make_mlflow_caller(cfg, split_hash)

    variants_to_run = ["real_only", "real_synthetic"] if ablation else [
        "real_synthetic" if synthetic_variant == "capped" else "real_only"
    ]
    results = {}
    for variant in variants_to_run:
        print(f"\n=== Training variant: {variant} ===")
        results[variant] = train_variant(
            variant, cfg, lock, real_train, real_val,
            synthetic_train if variant == "real_synthetic" else None,
            device, mlflow_call,
        )

    monitor = cfg["training"]["monitor"]
    tie_break = cfg["training"]["tie_break"]

    if ablation:
        a, b = results["real_only"], results["real_synthetic"]
        a_key = (metric_value(monitor, a["headline"]), metric_value(tie_break, a["headline"]))
        b_key = (metric_value(monitor, b["headline"]), metric_value(tie_break, b["headline"]))
        winner = "real_synthetic" if b_key > a_key else "real_only"
        print(f"\nAblation result (headline = pooled-window recall@fpr, tie-break = {tie_break}): "
              f"real_only recall@fpr={a['headline']['recall_at_fpr']:.3f} "
              f"vs real_synthetic recall@fpr={b['headline']['recall_at_fpr']:.3f} -> winner={winner}")
    else:
        winner = variants_to_run[0]

    baseline_path = HERE.parent / "MiniRocket" / "baseline_metrics.json"
    if not baseline_path.exists():
        raise FileNotFoundError(
            f"{baseline_path} not found. Run `MiniRocket/train.py` first -- the honesty-floor "
            "baseline is mandatory before this package can be written (model-codegen invariant 9)."
        )
    baseline_metrics = json.loads(baseline_path.read_text(encoding="utf-8"))
    # baseline_metrics["recall_at_fpr"] is computed by the SAME shared m.pooled_window_metrics
    # function (MiniRocket/train.py uses common.metrics too) -- comparing like with like.
    baseline_recall = baseline_metrics["recall_at_fpr"]
    baseline_trained_on = baseline_metrics.get("trained_on", "real_train_only")
    winner_trained_on = "real_train+synthetic" if results[winner]["used_synthetic"] else "real_train"
    beats_baseline = results[winner]["headline"]["recall_at_fpr"] > baseline_recall
    print(f"Baseline (MiniRocket+Ridge, {baseline_trained_on}) recall@fpr={baseline_recall:.3f} vs "
          f"winner ({winner}, {winner_trained_on}) recall@fpr="
          f"{results[winner]['headline']['recall_at_fpr']:.3f} -> beats_baseline={beats_baseline}")

    cv_report = None
    if run_cv and cfg["cross_validation"]["enabled"]:
        print("\n=== Leave-one-worn-unit-out cross-validation ===")
        cv_report = run_lowo_cv(cfg, lock, real_train, real_val, device)

    neuroedge_context = load_neuroedge_context(HERE.parent / "inputs" / "scaffold" /
                                                "neuroedge_train_cnc-drift-on-powertrain-shop-for-car-prduction.py")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = HERE / cfg["paths"]["runs_dir"] / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if cv_report is not None:
        (run_dir / "cv_report.json").write_text(json.dumps(cv_report, indent=2), encoding="utf-8")

    ablation_report = {
        variant: {
            "recall_at_fpr": r["headline"]["recall_at_fpr"],
            "fpr": r["headline"]["fpr"],
            "pr_auc": r["headline"]["pr_auc"],
            "decision_threshold": r["headline"]["decision_threshold"],
            "meets_target": r["meets_target"], "meets_recall": r["meets_recall"], "meets_fpr": r["meets_fpr"],
            "fpr_tolerance": r["fpr_tolerance"], "effective_fpr_bound": r["effective_fpr_bound"],
            "trained_on": "real_train+synthetic" if r["used_synthetic"] else "real_train",
            "n_train_windows": r["n_train_windows"], "best_epoch": r["best_epoch"],
        }
        for variant in variants_to_run for r in [results[variant]]
    }
    ablation_report["winner"] = winner
    ablation_report["monitor"] = monitor
    ablation_report["tie_break"] = tie_break
    ablation_report.update(val_trial_note)
    (run_dir / "ablation_report.json").write_text(json.dumps(ablation_report, indent=2), encoding="utf-8")

    for variant in variants_to_run:
        r = results[variant]
        variant_dir = run_dir / variant
        onnx_path = variant_dir / "model.onnx"
        variant_dir.mkdir(parents=True, exist_ok=True)
        export_info = export_onnx(
            ScoreModel(r["model"]), cfg["timeseries"]["window_samples"],
            len(cfg["timeseries"]["feature_order"]), cfg["export"]["onnx_opset"], onnx_path,
        )
        meta = build_meta(lock, r["mean"], r["std"], r["headline"]["decision_threshold"],
                           cfg["export"]["onnx_opset"])
        this_trained_on = "real_train+synthetic" if r["used_synthetic"] else "real_train"
        metrics_json = {
            "epochs_completed": r["epochs_completed"], "best_epoch": r["best_epoch"],
            "train_loss": r["train_loss"], "val_loss": r["val_loss"],
            "training_duration_s": r["training_duration_s"],
            # HEADLINE = pooled window metrics -- the gating number (Option 3, M8 round 3).
            **r["headline"],
            "meets_target": r["meets_target"], "meets_recall": r["meets_recall"], "meets_fpr": r["meets_fpr"],
            "fpr_tolerance": r["fpr_tolerance"], "effective_fpr_bound": r["effective_fpr_bound"],
            "target_recall": cfg["task"]["target_recall"],
            **val_trial_note,
            "eval_split": "self_reported_val",
            "split_hash": split_hash,
            # Per-unit RATE TABLE + event diagnostics -- descriptive, never gating.
            "per_unit_rate_table": r["diagnostics"]["rate_table"],
            "per_unit_event_diagnostics": r["diagnostics"]["event_diagnostics"],
            "segments": r["diagnostics"]["segments"],
            "used_synthetic": r["used_synthetic"],
            "trained_on": this_trained_on,
            "cross_validation": cv_report if variant == winner else None,
        }
        this_beats_baseline = r["headline"]["recall_at_fpr"] > baseline_recall
        baseline_block = {
            "name": "minirocket_ridge", "metrics": baseline_metrics, "compared_on": "recall_at_fpr",
            "beats_baseline": this_beats_baseline,
            "baseline_trained_on": baseline_trained_on,
            "winner_trained_on": this_trained_on,
        }
        extras = {
            "model_name": f"1d-cnn-{variant}",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "split_hash": split_hash,
            "seed": cfg["seed"],
            "ablation": ablation_report if ablation else None,
        }
        files = write_package(
            variant_dir, lock, onnx_path, meta, metrics_json, baseline_block, extras,
            neuroedge_context=neuroedge_context,
        )
        print(f"[{variant}] package written to {variant_dir} (opset {export_info['opset']}, "
              f"max ONNX/PyTorch gap {export_info['max_onnx_vs_torch_gap']:.2e})")
        mlflow_call("log_artifact", files["model_onnx"])
        mlflow_call("log_dict", meta, f"{variant}_meta.json")

        if variant == winner:
            canonical = run_dir / "model-package"
            canonical.mkdir(exist_ok=True)
            for name in ("model.onnx", "meta.json", "metrics.json", "model_artifact.json"):
                (canonical / name).write_bytes((variant_dir / name).read_bytes())
            print(f"Canonical model-package (winner={winner}) at {canonical}")

    mlflow_call("end_run")
    print(f"\nDone. Winner: {winner}. beats_baseline={beats_baseline}. Run: {run_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--ablation", dest="ablation", action="store_true", default=None)
    parser.add_argument("--no-ablation", dest="ablation", action="store_false")
    parser.add_argument("--synthetic", choices=["none", "capped"], default="capped",
                         help="Only used with --no-ablation: which single variant to train.")
    parser.add_argument("--cv", dest="cv", action="store_true", default=None)
    parser.add_argument("--no-cv", dest="cv", action="store_false")
    args = parser.parse_args()

    _cfg_preview = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    ablation_flag = _cfg_preview["ablation"]["enabled"] if args.ablation is None else args.ablation
    cv_flag = _cfg_preview["cross_validation"]["enabled"] if args.cv is None else args.cv

    main(args.config, ablation_flag, args.synthetic, cv_flag)
