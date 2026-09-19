# -*- coding: utf-8 -*-
"""Rare-event metrics for cnc_drift_1dcnn-timeseries -- M8 round 3 (Option 3, human-approved).

**Headline / gating metric = POOLED WINDOW-level recall_at_fpr / fpr / pr_auc**, calibrated at the
lock's `at_fpr` on real validation windows. This is a deliberate reversal of round 2's per-unit
max-aggregation "headline": ml-eval-reviewer found that flagging a unit whenever the MAX of its
183-602 windows crosses a threshold calibrated at a 1% POOLED window FPR saturates almost
regardless of the model -- under pure noise, P(a normal unit's max of ~200 iid U(0,1) draws
exceeds the 99th percentile) is close to 1, so ~3.74 of 4 normal units alarm on average and the
per-unit headline FPR sits at ~0.75-1.0 no matter what the model does. Pooling over windows (never
taking a per-unit max as a boolean gate) does not have this failure mode.

Per-unit reporting (`data/label-manifest.md` requirement #4, "report metrics per experiment... not
per window") is satisfied here by a **rate table**, not a max-boolean: for each unit, at the SAME
shared threshold, report window recall (worn units) or false-alarm rate / false-alarms-per-hour
(normal units) -- descriptive, never a second gating construction.

Event diagnostics (alarm persistence, false-alarm events/hour, event recall, time-to-first-alarm)
are separate, explicitly diagnostic-only functions -- never used to select a model, decide the
ablation winner, or compute `beats_baseline`.
"""
from __future__ import annotations

import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score


def threshold_at_fpr(y_true: np.ndarray, scores: np.ndarray, at_fpr: float) -> float:
    """Lowest threshold whose false-positive rate on THESE windows is <= at_fpr. Call on the
    VALIDATION split only, never test."""
    neg = np.sort(scores[y_true == 0])[::-1]
    if len(neg) == 0:
        raise ValueError("No negative (normal) windows to calibrate a threshold against.")
    allowed = int(np.floor(at_fpr * len(neg)))
    if allowed >= len(neg):
        return float(neg[-1])
    return float(np.nextafter(neg[allowed], np.inf))


def pooled_window_metrics(
    y_true: np.ndarray, scores: np.ndarray, at_fpr: float, threshold: float | None = None
) -> dict:
    """THE HEADLINE / gating metric set (Option 3): pooled over ALL windows, never a per-unit
    max-boolean. `threshold`, when None, is calibrated here (val only)."""
    y = (y_true > 0).astype(int)
    if threshold is None:
        threshold = threshold_at_fpr(y, scores, at_fpr)
    pred = (scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "recall_at_fpr": float(tp / max(tp + fn, 1)),
        "fpr": float(fp / max(fp + tn, 1)),
        "at_fpr": at_fpr,
        "pr_auc": float(average_precision_score(y, scores)),
        "auroc": float(roc_auc_score(y, scores)) if len(np.unique(y)) > 1 else None,
        "decision_threshold": float(threshold),
        "aggregation": "window_pooled",
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
    }


def meets_target(headline: dict, target_recall: float, at_fpr: float, fpr_tolerance: float = 0.0) -> dict:
    """`meets_target` = recall_at_fpr >= target_recall AND fpr <= at_fpr + fpr_tolerance.

    On the split the threshold was calibrated on (val), `threshold_at_fpr` makes the realised fpr
    <= at_fpr by construction, so no tolerance is needed there. A tolerance only matters
    out-of-sample (test, LOWO folds), where it loosens the KPI -- so it defaults to 0 and the
    bound actually applied is always written out beside `meets_fpr`."""
    effective_fpr_bound = at_fpr + fpr_tolerance
    meets_recall = bool(headline["recall_at_fpr"] >= target_recall)
    meets_fpr = bool(headline["fpr"] <= effective_fpr_bound)
    return {
        "meets_recall": meets_recall,
        "meets_fpr": meets_fpr,
        "meets_target": meets_recall and meets_fpr,
        "fpr_tolerance": float(fpr_tolerance),
        "effective_fpr_bound": float(effective_fpr_bound),
    }


def headline_trial_note(y_true: np.ndarray, unit_ids: np.ndarray) -> dict:
    """How many independent worn units the pooled headline recall rests on. Windows overlap and
    come from few units, so with one worn unit the headline recall is a single-trial number, not
    a population estimate -- on val (it drives selection, the ablation and beats_baseline) as
    much as on test."""
    positive_units = sorted({str(u) for u, y in zip(unit_ids, y_true) if y > 0})
    note = {"headline_positive_units": len(positive_units)}
    if len(positive_units) <= 1:
        note["headline_single_trial_caveat"] = (
            f"The headline recall_at_fpr rests on {len(positive_units)} worn unit(s) "
            f"({', '.join(positive_units) or 'none'}): a single-trial pass/fail, NOT a population "
            "estimate. See cross_validation (leave-one-worn-unit-out) for the spread."
        )
    return note


def _unit_hours(n_windows: int, stride_samples: int, sample_rate_hz: float) -> float:
    """Hours of NEW data represented by n_windows scored at `stride_samples` apart (1 window =
    `stride_samples / sample_rate_hz` seconds of new data, since consecutive windows overlap)."""
    return n_windows * stride_samples / sample_rate_hz / 3600.0


def per_unit_rate_table(
    y_true: np.ndarray,
    scores: np.ndarray,
    unit_ids: np.ndarray,
    threshold: float,
    stride_samples: int,
    sample_rate_hz: float,
) -> list[dict]:
    """One row per unit, at the SAME shared (pooled-calibrated) threshold -- descriptive, not a
    second gating construction. Worn units get a window recall; normal units get a false-alarm
    rate and a false-alarms-per-hour figure derived from the lock's stride/rate, never a literal.
    """
    rows = []
    for unit in sorted(set(unit_ids.tolist())):
        idx = unit_ids == unit
        yt = y_true[idx]
        s = scores[idx]
        label_positive = bool(yt[0] > 0)
        pred = (s >= threshold).astype(int)
        n = int(idx.sum())
        hours = _unit_hours(n, stride_samples, sample_rate_hz)
        row = {
            "unit": unit,
            "label": "tool_wear" if label_positive else "normal",
            "n_windows": n,
            "hours_of_new_data": hours,
        }
        if label_positive:
            row["window_recall"] = float(pred.mean())
        else:
            row["false_alarm_rate"] = float(pred.mean())
            row["false_alarms_per_hour"] = float(pred.sum() / hours) if hours > 0 else None
        rows.append(row)
    return rows


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    padded = np.concatenate([[False], mask.astype(bool), [False]])
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return list(zip(edges[0::2], edges[1::2]))


def alarm_events(pred: np.ndarray, persistence_windows: int) -> list[tuple[int, int]]:
    """Runs of >= `persistence_windows` consecutive alarm windows, WITHIN one unit (never across
    units -- caller must pass one unit's predictions at a time)."""
    return [(a, b) for a, b in _runs(pred) if (b - a) >= persistence_windows]


def per_unit_event_diagnostics(
    y_true: np.ndarray,
    scores: np.ndarray,
    unit_ids: np.ndarray,
    threshold: float,
    persistence_windows: int,
    stride_samples: int,
    sample_rate_hz: float,
) -> list[dict]:
    """DIAGNOSTIC ONLY -- never used for selection, ablation, beats_baseline or meets_target.
    Alarm events = runs of >= persistence_windows consecutive over-threshold windows, per unit.
    Normal units: false-alarm events per hour. Worn units: event recall (did it alarm at all) and
    time-to-first-alarm in seconds (from the run's first window, at `stride_samples/sample_rate_hz`
    seconds per window step).
    """
    rows = []
    for unit in sorted(set(unit_ids.tolist())):
        idx = unit_ids == unit
        yt = y_true[idx]
        s = scores[idx]
        label_positive = bool(yt[0] > 0)
        pred = (s >= threshold).astype(int)
        n = int(idx.sum())
        hours = _unit_hours(n, stride_samples, sample_rate_hz)
        events = alarm_events(pred, persistence_windows)
        row = {
            "unit": unit,
            "label": "tool_wear" if label_positive else "normal",
            "persistence_windows": persistence_windows,
            "n_events": len(events),
        }
        if label_positive:
            row["event_recall"] = bool(len(events) > 0)
            row["time_to_first_alarm_s"] = (
                float(events[0][0] * stride_samples / sample_rate_hz) if events else None
            )
        else:
            row["false_alarm_events_per_hour"] = float(len(events) / hours) if hours > 0 else None
        rows.append(row)
    return rows


def segment_rows(rows: list[dict], unit_list: list[str]) -> list[dict]:
    """Filter a per-unit table (rate table or event-diagnostics table) down to the units named,
    for the required segmentations (model_proposed.md §Evaluation / label-manifest.md #4):
    blowhole units (A01/A02) vs pure tool wear (A03/A04/A05); the same-program IM-01R normal
    segment vs the cross-program normals."""
    keep = set(unit_list)
    return [r for r in rows if r["unit"] in keep]
