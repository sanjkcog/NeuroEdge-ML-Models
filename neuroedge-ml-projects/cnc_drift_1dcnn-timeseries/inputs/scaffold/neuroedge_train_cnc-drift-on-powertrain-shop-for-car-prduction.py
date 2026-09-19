# -*- coding: utf-8 -*-
# # NeuroEdge Training Template — 'cnc-drift-on-powertrain-shop-for-car-prduction'
# Task: anomaly_detection - Classes: normal, tool_wear
# 
# Train on your own infrastructure, then return the generated 'neuroedge_return_package/' contents to NeuroEdge.
# ## 0 - NeuroEdge use-case context
import json
from pathlib import Path

NEUROEDGE_CONTEXT = json.loads(r'''{
  "business_requirement": {
    "business_kpi": "detection_latency",
    "objective": "Detect CNC machine drift on the powertrain shop floor using time-series sensor data, enabling faster response than manual operator detection.\n",
    "success_criteria": [],
    "target_improvement_percent": null
  },
  "contract_version": "web-v2-11",
  "data": {
    "format": "csv",
    "labeling_status": "not_available",
    "path": "",
    "sample_count": null,
    "source": "local"
  },
  "description": "Detect CNC machine drift on the powertrain shop floor using time-series sensor data, enabling faster response than manual operator detection.\n",
  "generated_at": "2026-09-18T22:44:44.430306+00:00",
  "industry": "manufacturing",
  "model_hint": {
    "family": "custom",
    "framework": "auto",
    "variant": null
  },
  "performance_targets": {
    "accuracy": {
      "at_fpr": 0.01,
      "metric": "recall",
      "min_value": 0.9,
      "notes": "Recall \u2265 0.90 (must catch at least 90% of real drift events). False alarm tolerance: \u2264 1 per week (at_fpr = 0.01).\n"
    },
    "latency_ms_p95_max": null,
    "max_latency_ms": 172000.0,
    "max_memory_mb": null,
    "max_seconds_per_cycle": null,
    "min_fps": 1.0,
    "power_w_max": null,
    "provenance": {
      "accuracy.at_fpr": {
        "because": "business_requirement.kpi_link.at_fpr",
        "enforcement": "info",
        "source": "business_kpi"
      },
      "accuracy.metric": {
        "enforcement": "info",
        "source": "stated"
      },
      "max_latency_ms": {
        "enforcement": "info",
        "source": "stated"
      },
      "min_fps": {
        "enforcement": "info",
        "source": "stated"
      }
    },
    "throughput_fps_min": 1.0
  },
  "return_package": {
    "directory": "neuroedge_return_package",
    "model_files": [
      "best.pt",
      "model.onnx"
    ],
    "optional_files": [
      "calibration/"
    ],
    "required_files": [
      "model_artifact.json",
      "metrics.json"
    ]
  },
  "target": {
    "accelerator": "cuda",
    "arch": "arm64",
    "device_name": "NVIDIA Jetson Orin Nano",
    "device_profile_id": "nvidia-jetson-orin-nano",
    "platform": "jetson",
    "runtime_profile": "ep-tensorrt"
  },
  "task": {
    "classes": [
      "normal",
      "tool_wear"
    ],
    "input": {
      "channels": [
        "spindle_load",
        "x_axis_error",
        "vibration_rms"
      ],
      "modality": "industrial_sensor",
      "sample_rate_hz": 10.0,
      "source": "opcua",
      "stride_samples": 10,
      "window_samples": 64
    },
    "model_category": "anomaly_detection",
    "timeseries": {
      "channels": [
        {
          "definition": "100 ms mean of spindle torque (SINUMERIK TORQUE|6)",
          "name": "spindle_load",
          "reduce": "mean",
          "unit": "Nm"
        },
        {
          "definition": "100 ms mean of X-axis following error (SINUMERIK CTRL_DIFF|1), in micrometres",
          "name": "x_axis_error",
          "reduce": "mean",
          "unit": "um"
        },
        {
          "definition": "exact 100 ms RMS of the mean-removed 3-axis spindle acceleration magnitude (unit g assumed, unconfirmed)",
          "name": "vibration_rms",
          "reduce": "rms",
          "unit": "g"
        }
      ],
      "decision_threshold": null,
      "sample_rate_hz": 10.0,
      "stride_samples": 10,
      "window_samples": 64
    },
    "type": "anomaly_detection"
  },
  "training": {
    "epochs": 50,
    "learning_rate": 0.001
  },
  "use_case_id": "cnc-drift-on-powertrain-shop-for-car-prduction",
  "use_case_name": "CNC Drift Detection \u2014 Powertrain Shop"
}''')

USE_CASE_ID = NEUROEDGE_CONTEXT['use_case_id']
USE_CASE_NAME = NEUROEDGE_CONTEXT['use_case_name']
TASK_TYPE = NEUROEDGE_CONTEXT['task']['type']
CLASSES = NEUROEDGE_CONTEXT['task']['classes']
DATASET_PATH = NEUROEDGE_CONTEXT['data']['path']
TARGET_DEVICE_PROFILE_ID = NEUROEDGE_CONTEXT['target'].get('device_profile_id') or 'unknown'
RUNTIME_PROFILE = NEUROEDGE_CONTEXT['target'].get('runtime_profile') or 'unknown'
PERFORMANCE_TARGETS = NEUROEDGE_CONTEXT.get('performance_targets', {})
BUSINESS_REQUIREMENT = NEUROEDGE_CONTEXT.get('business_requirement', {})
EPOCHS = int(NEUROEDGE_CONTEXT['training']['epochs'])
LR = float(NEUROEDGE_CONTEXT['training']['learning_rate'])
print(json.dumps(NEUROEDGE_CONTEXT, indent=2))

# ## Task section - time series / anomaly detection
# Expected dataset: one CSV of rows at the use case's sample rate, with one column per channel named exactly as the use case lists them, a 'label' column (class name or index), an optional 'timestamp' column and, ideally, a unit column ('unit' / 'unit_id': machine, trial or cutter). With a unit column the split is by unit; without one it is chronological with a one-window gap. Windows never cross a unit or split boundary, and each window is labelled from its own rows.
# ## 1 — Install dependencies
# Pinned so the run is reproducible. On a laptop / workstation NVIDIA GPU install the
# CUDA build of torch first, e.g.:
#   pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cu124
# Colab shell command: !pip install torch==2.6.0 numpy==2.4.4 pandas==2.3.3 onnx==1.22.0 onnxruntime==1.27.0 scikit-learn==1.7.2 --quiet
# Optional experiment tracking (training works without it):
# !pip install mlflow==3.16.1 --quiet
# NeuroEdge return-package writer, from your local NeuroEdge-Web copy (or its wheels):
# !pip install -e <NeuroEdge-Web>/src/neuroedge_design_usecase -e <NeuroEdge-Web>/src/neuroedge_return

# ## 2 — Parameters
# The first block is the use case's input contract (channels, rate, window, stride, false-alarm rate). The model is only deployable if it matches, so change those in the use case, not here. Edit the data and training blocks freely.
# --- Use-case contract (from the use case; change it in the use case, not here) ---
USE_CASE_ID    = 'cnc-drift-on-powertrain-shop-for-car-prduction'
CLASSES        = ['normal', 'tool_wear']   # index 0 is the normal class (checked below)
NOMINAL_CLASS_CONFIRMED = False   # set True only if CLASSES[0] is normal but not named so
FEATURE_ORDER  = ['spindle_load', 'x_axis_error', 'vibration_rms']   # channel names = model input order; never re-sort
CHANNEL_UNITS  = {'spindle_load': 'Nm', 'x_axis_error': 'um', 'vibration_rms': 'g'}
CHANNEL_DEFINITIONS = {'spindle_load': '100 ms mean of spindle torque (SINUMERIK TORQUE|6)', 'x_axis_error': '100 ms mean of X-axis following error (SINUMERIK CTRL_DIFF|1), in micrometres', 'vibration_rms': 'exact 100 ms RMS of the mean-removed 3-axis spindle acceleration magnitude (unit g assumed, unconfirmed)'}
CHANNEL_REDUCE = {'spindle_load': 'mean', 'x_axis_error': 'mean', 'vibration_rms': 'rms'}   # how one row was built from raw samples
SAMPLE_RATE_HZ = 10.0   # rows per second
WINDOW_SIZE    = 64   # rows per window
STRIDE         = 10   # use case stride_samples: the device scores one window every STRIDE rows
AT_FPR         = 0.01   # false-alarm rate for the threshold; from business_requirement.kpi_link.at_fpr
ONNX_OPSET     = 13   # NeuroEdge repo-wide contract (ADR-0001 W-3)

# --- Your data (edit these) ---
DATASET_PATH   = ''   # CSV: one column per channel + label (+ unit, timestamp)
LABEL_COLUMN   = 'label'       # class name or class index per row
LABEL_RULE     = 'any'         # window label from its own rows: 'any' (any anomaly) | 'last' (last row)
UNIT_COLUMN    = None          # e.g. 'unit' or 'unit_id'; None = auto-detect those, else split chronologically
TIMESTAMP_COLUMN = 'timestamp' # used for ordering rows when present
VAL_FRACTION   = 0.2           # share of units (or of the timeline) held out for validation
TRAIN_STRIDE   = STRIDE        # lower (e.g. 1) for more, overlapping training windows

# --- Training (edit these) ---
EPOCHS         = 50
LR             = 0.001
BATCH_SIZE     = 64
PATIENCE       = 10            # early stopping on validation PR-AUC
SEED           = 42
ARCH           = '1d-cnn'      # '1d-cnn' | 'lstm'
RUN_BASELINE   = True          # computes BASELINE; without one NeuroEdge refuses the upload
MLFLOW_PIN     = 'mlflow==3.16.1'

# ## 3 — Seed everything
import random

import numpy as np
import torch


def seed_everything(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    # Reproducible cuDNN kernels (slightly slower on GPU; fine for a 1D model).
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


seed_everything(SEED)
print(f'Seeded torch / numpy / random with SEED={SEED}')

# ## 4 — Load, split and window
# Split by unit when the CSV has a unit column, otherwise chronologically with a one-window gap. Windows are cut inside each unit/segment, labelled from their own rows, and normalisation statistics come from the train split only.
import hashlib
import json

import numpy as np
import pandas as pd
import torch
from numpy.lib.stride_tricks import sliding_window_view
from torch.utils.data import DataLoader, TensorDataset

if LABEL_RULE not in ('any', 'last'):
    raise ValueError(f"LABEL_RULE must be 'any' or 'last', got {LABEL_RULE!r}")
if not DATASET_PATH:
    raise ValueError('DATASET_PATH is empty -- set it in the Parameters cell to your CSV file.')
df = pd.read_csv(DATASET_PATH)

# --- Unit column: split by unit when there is one -------------------------------------
if UNIT_COLUMN is None:
    UNIT_COLUMN = next((c for c in ('unit', 'unit_id') if c in df.columns), None)
elif UNIT_COLUMN not in df.columns:
    raise KeyError(f'UNIT_COLUMN {UNIT_COLUMN!r} is not a column of {DATASET_PATH}')

# --- Channels, in the use case's order (that order IS the model's input order) ---------
if not FEATURE_ORDER:
    _reserved = {LABEL_COLUMN, TIMESTAMP_COLUMN, UNIT_COLUMN}
    FEATURE_ORDER = [c for c in df.columns if c not in _reserved and pd.api.types.is_numeric_dtype(df[c])]
    print('The use case lists no channels; using the CSV columns in file order:', FEATURE_ORDER)
_missing = [c for c in [*FEATURE_ORDER, LABEL_COLUMN] if c not in df.columns]
if _missing:
    raise KeyError(
        f'The CSV is missing column(s) {_missing}. Channels must be named exactly as the use case '
        f'lists them, in this order: {FEATURE_ORDER}'
    )
NUM_FEATURES = len(FEATURE_ORDER)

# --- Rows without a label or a unit cannot be placed; say so instead of dropping them ---
_no_label = int(df[LABEL_COLUMN].isna().sum())
if _no_label:
    raise ValueError(f'{_no_label} row(s) have no {LABEL_COLUMN!r} value; label every row (or remove those rows).')
if UNIT_COLUMN and df[UNIT_COLUMN].isna().any():
    raise ValueError(f'{int(df[UNIT_COLUMN].isna().sum())} row(s) have no {UNIT_COLUMN!r} value; '
                     'every row must belong to a unit.')

# --- Row order and gaps: time order inside each unit; never fill across a unit ---------
if TIMESTAMP_COLUMN in df.columns:
    df = df.sort_values(([UNIT_COLUMN] if UNIT_COLUMN else []) + [TIMESTAMP_COLUMN], kind='stable')
if UNIT_COLUMN:
    df[FEATURE_ORDER] = df.groupby(UNIT_COLUMN, sort=False)[FEATURE_ORDER].ffill()
else:
    df[FEATURE_ORDER] = df[FEATURE_ORDER].ffill()
_before = len(df)
df = df.dropna(subset=FEATURE_ORDER).reset_index(drop=True)
if len(df) < _before:
    print(f'Dropped {_before - len(df)} leading row(s) with channel values that could not be forward-filled.')

# --- Labels: class name or class index, mapped onto CLASSES (index 0 = normal) ---------
_labels = df[LABEL_COLUMN]
if pd.api.types.is_numeric_dtype(_labels):
    y_all = _labels.astype('int64').to_numpy()
else:
    _index = {name: i for i, name in enumerate(CLASSES)}
    _unknown = sorted(set(_labels.astype(str)) - set(_index))
    if _unknown:
        raise ValueError(f'Label value(s) {_unknown} are not in CLASSES {CLASSES}')
    y_all = _labels.astype(str).map(_index).to_numpy(dtype='int64')
if y_all.min() < 0 or y_all.max() >= len(CLASSES):
    raise ValueError(f'Labels must be class indices 0..{len(CLASSES) - 1} (CLASSES = {CLASSES})')
X_all = df[FEATURE_ORDER].to_numpy(dtype='float32')

SCALAR_HEAD = TASK_TYPE == 'anomaly_detection' and len(CLASSES) == 2

# A scalar head scores "how anomalous": label 0 must be the normal class, or every metric, the
# threshold and the exported score silently measure the opposite. The use case lists classes in
# order, nominal first; a first class that does not look nominal stops here unless confirmed.
_NOMINAL_TOKENS = {'normal', 'ok', 'good', 'nominal', 'healthy', 'pass', 'negative', 'background', 'no_fault'}
if SCALAR_HEAD and str(CLASSES[0]).strip().lower() not in _NOMINAL_TOKENS and not NOMINAL_CLASS_CONFIRMED:
    raise ValueError(
        f'CLASSES[0] = {CLASSES[0]!r} does not look like the normal class, but a scalar anomaly head treats '
        f'index 0 as normal. Fix the class order in the use case (normal first), or set '
        f'NOMINAL_CLASS_CONFIRMED = True if {CLASSES[0]!r} really is the normal class.'
    )


def make_windows(X, y, stride):
    # Windows of WINDOW_SIZE rows inside ONE segment, channels-first [n, features, window].
    # The label comes from the rows INSIDE the window: 'any' = the highest class index
    # present (any-anomaly for two classes), 'last' = the window's last row.
    if len(X) < WINDOW_SIZE:
        return np.empty((0, X.shape[1], WINDOW_SIZE), dtype='float32'), np.empty((0,), dtype='int64')
    xw = sliding_window_view(X, WINDOW_SIZE, axis=0)[::stride]   # [n, features, window]
    yw = sliding_window_view(y, WINDOW_SIZE)[::stride]            # [n, window]
    labels = yw[:, -1] if LABEL_RULE == 'last' else yw.max(axis=1)
    return np.ascontiguousarray(xw, dtype='float32'), labels.astype('int64')


def _has_both_classes(labels):
    return len(labels) > 0 and len(np.unique(labels > 0 if SCALAR_HEAD else labels)) >= 2


# --- Split ------------------------------------------------------------------------------
if UNIT_COLUMN:
    _segments = {str(k): rows for k, rows in df.groupby(UNIT_COLUMN, sort=False).indices.items()}
    _units = list(_segments)
    if len(_units) < 2:
        raise ValueError(
            f'Only one {UNIT_COLUMN!r} value: a by-unit split needs at least 2 units. '
            'Set UNIT_COLUMN = None to split chronologically instead.'
        )
    _unit_labels = {u: make_windows(X_all[r], y_all[r], STRIDE)[1] for u, r in _segments.items()}
    _n_val = min(len(_units) - 1, max(1, round(len(_units) * VAL_FRACTION)))
    _rng = np.random.default_rng(SEED)
    for _attempt in range(200):
        _perm = _rng.permutation(len(_units))
        val_units = [_units[i] for i in sorted(_perm[:_n_val])]
        train_units = [u for u in _units if u not in val_units]
        _yv = np.concatenate([_unit_labels[u] for u in val_units])
        _yt = np.concatenate([_unit_labels[u] for u in train_units])
        if _has_both_classes(_yv) and _has_both_classes(_yt):
            break
    else:
        raise ValueError(
            'No split of whole units puts both classes in train AND validation (ADR-0003 B-6). '
            'Add units, or change VAL_FRACTION.'
        )
    train_parts = [(u, _segments[u]) for u in train_units]
    val_parts = [(u, _segments[u]) for u in val_units]
    SPLIT_STRATEGY = f'by_unit:{UNIT_COLUMN}'
else:
    _rows = np.arange(len(df))
    _cut = int(len(_rows) * (1 - VAL_FRACTION))
    train_parts = [('train', _rows[:_cut])]
    # One-window gap: no validation window shares a row with a training window.
    val_parts = [('val', _rows[_cut + WINDOW_SIZE:])]
    SPLIT_STRATEGY = 'chronological_gap'
    print(
        'No unit column: chronological split with a one-window gap. On run-to-failure data this '
        'can put every drift window in validation (ADR-0003 B-6); prefer a unit column.'
    )


def build_windows(parts, stride):
    xs, ys, seg = [], [], []
    for key, rows in parts:
        xw, yw = make_windows(X_all[rows], y_all[rows], stride)
        xs.append(xw)
        ys.append(yw)
        seg.extend([key] * len(yw))
    return np.concatenate(xs), np.concatenate(ys), np.array(seg)


X_train, y_train, seg_train = build_windows(train_parts, TRAIN_STRIDE)
X_val, y_val, seg_val = build_windows(val_parts, STRIDE)
if not (_has_both_classes(y_train) and _has_both_classes(y_val)):
    raise ValueError(
        'Train and validation must each contain both classes (ADR-0003 B-6): '
        f'train={np.bincount(y_train, minlength=len(CLASSES)).tolist()} '
        f'val={np.bincount(y_val, minlength=len(CLASSES)).tolist()}'
    )

# --- Normalisation statistics: TRAIN rows only. Applied inside the model (see below). ---
_train_rows = np.concatenate([rows for _, rows in train_parts])
NORM_MEAN = X_all[_train_rows].mean(axis=0).astype('float32')
NORM_STD = X_all[_train_rows].std(axis=0).astype('float32')
NORM_STD[NORM_STD < 1e-6] = 1.0   # a constant channel must not divide by ~0

SPLIT_HASH = hashlib.sha256(json.dumps({
    'strategy': SPLIT_STRATEGY,
    'train': [[str(k), int(r.min()), int(r.max()), len(r)] for k, r in train_parts],
    'val': [[str(k), int(r.min()), int(r.max()), len(r)] for k, r in val_parts],
    'window': WINDOW_SIZE, 'stride': STRIDE, 'train_stride': TRAIN_STRIDE, 'label_rule': LABEL_RULE,
}, sort_keys=True).encode('utf-8')).hexdigest()[:16]

_loader_gen = torch.Generator().manual_seed(SEED)
train_loader = DataLoader(TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train)),
                          batch_size=BATCH_SIZE, shuffle=True, generator=_loader_gen)
val_loader = DataLoader(TensorDataset(torch.from_numpy(X_val), torch.from_numpy(y_val)),
                        batch_size=BATCH_SIZE)
print(f'Split: {SPLIT_STRATEGY}  (split_hash {SPLIT_HASH})')
print(f'Channels ({NUM_FEATURES}): {FEATURE_ORDER}')
print(f'Train windows: {len(y_train)}  per class {np.bincount(y_train, minlength=len(CLASSES)).tolist()}')
print(f'Val windows:   {len(y_val)}  per class {np.bincount(y_val, minlength=len(CLASSES)).tolist()}')
print(f'Head: {"scalar (one logit -> Sigmoid)" if SCALAR_HEAD else "multiclass"}')

# ## 5 — Build model
# Normalisation is part of the model, so the exported graph takes raw sensor values. A two-class anomaly use case has a scalar head (one logit).
from torch import nn


class Conv1DModel(nn.Module):
    def __init__(self, n_features, n_out):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(n_features, 64, kernel_size=5, padding=2), nn.ReLU(),
            nn.Conv1d(64, 128, kernel_size=3, padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool1d(1), nn.Flatten(),
            nn.Linear(128, 64), nn.ReLU(),
            nn.Linear(64, n_out),
        )

    def forward(self, x):
        return self.net(x)


class LSTMModel(nn.Module):
    def __init__(self, n_features, n_out):
        super().__init__()
        self.lstm = nn.LSTM(n_features, 128, num_layers=2, batch_first=True, dropout=0.2)
        self.head = nn.Linear(128, n_out)

    def forward(self, x):
        out, _ = self.lstm(x.permute(0, 2, 1))   # [batch, window, features]
        return self.head(out[:, -1])


ARCHS = {'1d-cnn': Conv1DModel, 'lstm': LSTMModel}
if ARCH not in ARCHS:
    # Fail loudly rather than silently training something else (ADR-0003 B-8).
    raise ValueError(f'ARCH {ARCH!r} is not implemented in this template; choose one of {sorted(ARCHS)}')


class NeuroEdgeTSModel(nn.Module):
    # Normalisation lives INSIDE the model, so the exported graph starts with Sub/Div and
    # takes raw sensor values exactly as the device sends them (ADR-0001 W-4).
    def __init__(self, core, mean, std):
        super().__init__()
        self.core = core
        self.register_buffer('mean', torch.as_tensor(mean, dtype=torch.float32).view(1, -1, 1))
        self.register_buffer('std', torch.as_tensor(std, dtype=torch.float32).view(1, -1, 1))

    def forward(self, x):   # x: [batch, features, window] in raw units
        return self.core((x - self.mean) / self.std)


# The logit is clamped to +-LOGIT_CLAMP before the Sigmoid so the float32 score stays
# strictly inside (0, 1) even for inputs far outside the training range (ADR-0003 B-3/B-4).
LOGIT_CLAMP = 15.0


class ScoreModel(nn.Module):
    # Export wrapper for a scalar head: the graph ends in Sigmoid, output in (0, 1).
    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, x):
        return torch.sigmoid(self.model(x).clamp(-LOGIT_CLAMP, LOGIT_CLAMP))


N_OUT = 1 if SCALAR_HEAD else len(CLASSES)
model = NeuroEdgeTSModel(ARCHS[ARCH](NUM_FEATURES, N_OUT), NORM_MEAN, NORM_STD)
print(model)

# ## 6 — Metrics (PR-AUC, recall at the fixed FPR, event F1, confusion matrix)
import numpy as np
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, roc_auc_score


def threshold_at_fpr(y_true, scores, at_fpr):
    # Lowest threshold whose false-positive rate on these windows is <= at_fpr.
    # Called on the VALIDATION split only (ADR-0003 B-5), never on test.
    neg = np.sort(scores[y_true == 0])[::-1]
    allowed = int(np.floor(at_fpr * len(neg)))   # negatives allowed at or above the threshold
    if allowed >= len(neg):
        return float(neg[-1])
    return float(np.nextafter(neg[allowed], np.inf))   # just above that negative's score


def _runs(mask):
    # (start, end) of each run of True values.
    padded = np.concatenate([[False], mask.astype(bool), [False]])
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return list(zip(edges[0::2], edges[1::2]))


def event_f1(y_true, y_pred, seg_ids):
    # Event-level F1: an event is a run of consecutive positive windows within one unit.
    # A true event counts as caught if any of its windows alarms; an alarm run counts as
    # correct if it overlaps a true event.
    caught = missed = good_alarms = alarms = 0
    for seg in np.unique(seg_ids):
        idx = seg_ids == seg
        yt, yp = y_true[idx], y_pred[idx]
        for a, b in _runs(yt == 1):
            caught, missed = (caught + 1, missed) if yp[a:b].any() else (caught, missed + 1)
        for a, b in _runs(yp == 1):
            alarms += 1
            good_alarms += int(yt[a:b].any())
    recall = caught / max(caught + missed, 1)
    precision = good_alarms / max(alarms, 1)
    return float(2 * precision * recall / max(precision + recall, 1e-12))


def evaluate(y_true, scores, seg_ids, threshold=None):
    # Rare-event metrics (ADR-0002 V-4). Never accuracy.
    if SCALAR_HEAD:
        y = (y_true > 0).astype(int)
        if threshold is None:
            threshold = threshold_at_fpr(y, scores, AT_FPR)
        pred = (scores >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
        return {
            'pr_auc': float(average_precision_score(y, scores)),
            'auroc': float(roc_auc_score(y, scores)),
            'recall_at_fpr': float(tp / max(tp + fn, 1)),
            'fpr': float(fp / max(fp + tn, 1)),
            'event_f1': event_f1(y, pred, seg_ids),
            'window_f1': float(f1_score(y, pred, zero_division=0)),
            'decision_threshold': float(threshold),
            'confusion_matrix': [[int(tn), int(fp)], [int(fn), int(tp)]],
        }
    # Multiclass: scores is [n, classes] of probabilities.
    labels = list(range(len(CLASSES)))
    pred = scores.argmax(axis=1)
    onehot = np.eye(len(CLASSES))[y_true]
    present = onehot.sum(axis=0) > 0
    return {
        'pr_auc': float(average_precision_score(onehot[:, present], scores[:, present], average='macro')),
        'macro_f1': float(f1_score(y_true, pred, labels=labels, average='macro', zero_division=0)),
        'confusion_matrix': confusion_matrix(y_true, pred, labels=labels).tolist(),
    }

# ## 7 — Train
# Early stopping on validation PR-AUC. Logs to MLflow when it is installed ('MLFLOW_TRACKING_URI', else './mlruns').
import os
import time
from pathlib import Path

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = model.to(device)
optimizer = torch.optim.Adam(model.parameters(), lr=LR)

if SCALAR_HEAD:
    # One logit; pos_weight from the TRAIN class balance so rare anomalies are not ignored.
    _n_pos = int((y_train > 0).sum())
    _pos_weight = torch.tensor([(len(y_train) - _n_pos) / max(_n_pos, 1)], device=device)
    _bce = nn.BCEWithLogitsLoss(pos_weight=_pos_weight)

    def loss_fn(out, yb):
        return _bce(out.squeeze(1), (yb > 0).float())
else:
    _ce = nn.CrossEntropyLoss()

    def loss_fn(out, yb):
        return _ce(out, yb)


def predict(net, loader, with_loss=False):
    # Scores exactly as the exported graph computes them (Sigmoid of the clamped logit).
    net.eval()
    outs, total = [], 0.0
    with torch.no_grad():
        for xb, yb in loader:
            out = net(xb.to(device))
            if with_loss:
                total += float(loss_fn(out, yb.to(device))) * len(yb)
            outs.append(out.float().cpu())
    logits = torch.cat(outs)
    if SCALAR_HEAD:
        scores = torch.sigmoid(logits.squeeze(1).clamp(-LOGIT_CLAMP, LOGIT_CLAMP))
    else:
        scores = torch.softmax(logits, dim=1)
    return scores.numpy(), (total / len(loader.dataset) if with_loss else None)


# --- Optional MLflow tracking ------------------------------------------------------------
MLFLOW_RUN_ID = None
try:
    import mlflow
except ImportError:
    mlflow = None
    print('mlflow is not installed -- training without experiment tracking (pip install ' + MLFLOW_PIN + ' to enable).')


def mlflow_call(name, *args, **kwargs):
    # Tracking must never stop training: the first MLflow error disables it.
    global mlflow
    if mlflow is None:
        return None
    try:
        return getattr(mlflow, name)(*args, **kwargs)
    except Exception as exc:
        print(f'MLflow logging disabled ({type(exc).__name__}: {exc})')
        mlflow = None
        return None


if mlflow is not None:
    _tracking_uri = os.environ.get('MLFLOW_TRACKING_URI')
    if not _tracking_uri:
        # Local fallback: ./mlruns. MLflow 3.x keeps the file store only behind this opt-in.
        os.environ.setdefault('MLFLOW_ALLOW_FILE_STORE', 'true')
        _tracking_uri = Path('mlruns').resolve().as_uri()
    mlflow_call('set_tracking_uri', _tracking_uri)
    mlflow_call('set_experiment', USE_CASE_ID)
    if mlflow is not None and mlflow.active_run() is not None:
        mlflow_call('end_run')
    _run = mlflow_call('start_run', run_name=f'{USE_CASE_ID}-{ARCH}')
    MLFLOW_RUN_ID = _run.info.run_id if _run is not None else None
    mlflow_call('log_params', {
        'arch': ARCH, 'window': WINDOW_SIZE, 'stride': STRIDE, 'train_stride': TRAIN_STRIDE,
        'lr': LR, 'epochs': EPOCHS, 'batch_size': BATCH_SIZE, 'seed': SEED, 'at_fpr': AT_FPR,
        'label_rule': LABEL_RULE, 'split_strategy': SPLIT_STRATEGY, 'split_hash': SPLIT_HASH,
        'head': 'scalar' if SCALAR_HEAD else 'multiclass', 'features': ','.join(FEATURE_ORDER),
    })

# --- Train: early stopping on validation PR-AUC --------------------------------------------
best = {'pr_auc': -1.0, 'epoch': 0, 'state': None, 'train_loss': None, 'val_loss': None}
_stale = 0
_t0 = time.perf_counter()
for epoch in range(1, EPOCHS + 1):
    model.train()
    _total = 0.0
    for xb, yb in train_loader:
        xb, yb = xb.to(device), yb.to(device)
        optimizer.zero_grad()
        loss = loss_fn(model(xb), yb)
        loss.backward()
        optimizer.step()
        _total += float(loss) * len(yb)
    train_loss = _total / len(train_loader.dataset)
    val_scores, val_loss = predict(model, val_loader, with_loss=True)
    m = evaluate(y_val, val_scores, seg_val)
    _line = f"Epoch {epoch}/{EPOCHS}  train_loss={train_loss:.4f}  val_loss={val_loss:.4f}  val_pr_auc={m['pr_auc']:.3f}"
    if SCALAR_HEAD:
        _line += f"  val_recall@fpr{AT_FPR:g}={m['recall_at_fpr']:.3f}"
    print(_line)
    _epoch_metrics = {'train_loss': train_loss, 'val_loss': val_loss, 'val_pr_auc': m['pr_auc']}
    if SCALAR_HEAD:
        _epoch_metrics['val_recall_at_fpr'] = m['recall_at_fpr']
    mlflow_call('log_metrics', _epoch_metrics, step=epoch)
    if m['pr_auc'] > best['pr_auc']:
        best = {'pr_auc': m['pr_auc'], 'epoch': epoch, 'train_loss': train_loss, 'val_loss': val_loss,
                'state': {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}}
        _stale = 0
    else:
        _stale += 1
        if _stale >= PATIENCE:
            print(f'Early stop: val PR-AUC has not improved for {PATIENCE} epochs')
            break
EPOCHS_COMPLETED = epoch
TRAINING_DURATION_S = time.perf_counter() - _t0

# --- Best checkpoint -> final validation metrics and the calibrated threshold --------------
model.load_state_dict(best['state'])
val_scores, _ = predict(model, val_loader)
VAL_METRICS = evaluate(y_val, val_scores, seg_val)   # threshold chosen on val at AT_FPR (B-5)
DECISION_THRESHOLD = VAL_METRICS.get('decision_threshold')
PR_AUC = VAL_METRICS['pr_auc']
RECALL_AT_FPR = VAL_METRICS.get('recall_at_fpr')
FPR = VAL_METRICS.get('fpr')
EVENT_F1 = VAL_METRICS.get('event_f1')
BEST_EPOCH = best['epoch']
TRAIN_LOSS = best['train_loss']
VAL_LOSS = best['val_loss']

METRICS = {
    'epochs_completed': EPOCHS_COMPLETED,
    'best_epoch': BEST_EPOCH,
    'train_loss': TRAIN_LOSS,
    'val_loss': VAL_LOSS,
    'training_duration_s': TRAINING_DURATION_S,
    'pr_auc': PR_AUC,
    'auroc': VAL_METRICS.get('auroc'),
    'recall_at_fpr': RECALL_AT_FPR,
    'fpr': FPR,
    'at_fpr': AT_FPR,
    'event_f1': EVENT_F1,
    'decision_threshold': DECISION_THRESHOLD,
    'confusion_matrix': {'labels': list(CLASSES), 'matrix': VAL_METRICS['confusion_matrix']},
    # Measured on the validation split that also chose the threshold and the epoch:
    # label it as the weaker claim it is (ADR-0005 P-3).
    'eval_split': 'self_reported_val',
    'split_hash': SPLIT_HASH,
    'extra_metrics': {k: VAL_METRICS[k] for k in ('window_f1', 'macro_f1') if k in VAL_METRICS},
}
mlflow_call('log_metrics', {k: v for k, v in METRICS.items() if isinstance(v, (int, float)) and v is not None})

torch.save(model.state_dict(), 'best.pt')
RAW_MODEL_PATH = 'best.pt'
print(json.dumps({k: v for k, v in METRICS.items() if k != 'confusion_matrix'}, indent=2))
print('Confusion matrix [[tn, fp], [fn, tp]] on val:', VAL_METRICS['confusion_matrix'])

# ## 8 — Baseline (optional, recommended)
# Optional but recommended: NeuroEdge refuses a package whose baseline was not computed
# (ADR-0003 B-1). This is a cheap reference -- logistic regression on per-window
# mean/std/min/max of each channel -- measured on the SAME split, threshold rule and
# metrics as the model. (ADR-0003's reference baseline is MiniRocket; this is a
# lighter stand-in and is named as such.)
if RUN_BASELINE:
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def window_stats(xw):   # [n, features, window] -> [n, 4 * features]
        return np.concatenate([xw.mean(axis=2), xw.std(axis=2), xw.min(axis=2), xw.max(axis=2)], axis=1)

    _clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight='balanced'))
    _clf.fit(window_stats(X_train), (y_train > 0).astype(int) if SCALAR_HEAD else y_train)
    _proba = _clf.predict_proba(window_stats(X_val))
    if SCALAR_HEAD:
        _base_scores = _proba[:, 1]
    else:
        _base_scores = np.zeros((len(y_val), len(CLASSES)))
        _base_scores[:, _clf.classes_] = _proba
    _base_metrics = evaluate(y_val, _base_scores, seg_val)   # own threshold, also chosen on val
    BASELINE = {
        'estimator': 'logistic_regression_window_stats',
        'features': 'per-channel mean/std/min/max of each window',
        'metrics': _base_metrics,
        'compared_on': 'pr_auc',
        'beats_baseline': bool(PR_AUC > _base_metrics['pr_auc']),
        'eval_split': 'self_reported_val',
        'split_hash': SPLIT_HASH,
    }
    print(f"Baseline PR-AUC {_base_metrics['pr_auc']:.3f} vs model {PR_AUC:.3f} "
          f"-> beats_baseline={BASELINE['beats_baseline']}")
    if not BASELINE['beats_baseline']:
        print('The model does NOT beat the baseline. That is reported, not hidden (ADR-0003 B-2).')
    mlflow_call('log_metrics', {'baseline_pr_auc': _base_metrics['pr_auc']})
else:
    print('RUN_BASELINE is False: set BASELINE yourself, or NeuroEdge will refuse the upload (ADR-0003 B-1).')

# ## 9 — Export to ONNX
# Opset 13, input '[batch, features, window]' (dynamic batch), normalisation in the graph and, for a scalar head, a terminal Sigmoid so the score is in (0, 1).
import inspect

import onnx
import onnxruntime as ort

model.eval().cpu()
export_model = ScoreModel(model).eval() if SCALAR_HEAD else model
dummy = torch.from_numpy(X_val[:1])   # raw units: normalisation is inside the graph
_export_kwargs = {'dynamo': False} if 'dynamo' in inspect.signature(torch.onnx.export).parameters else {}
torch.onnx.export(
    export_model, dummy, 'model.onnx',
    input_names=['input'], output_names=['output'],
    opset_version=ONNX_OPSET,   # NeuroEdge repo-wide contract (ADR-0001 W-3)
    # [batch, features, window]: dynamic batch, static features and window.
    dynamic_axes={'input': {0: 'batch'}, 'output': {0: 'batch'}},
    **_export_kwargs,
)
ONNX_MODEL_PATH = 'model.onnx'

# --- Check what was exported before it is packaged --------------------------------------
_onnx_model = onnx.load(ONNX_MODEL_PATH)
onnx.checker.check_model(_onnx_model)
_opset = next(o.version for o in _onnx_model.opset_import if o.domain in ('', 'ai.onnx'))
if _opset != ONNX_OPSET:
    raise RuntimeError(f'Exported opset {_opset} != required {ONNX_OPSET}')
_sess = ort.InferenceSession(ONNX_MODEL_PATH, providers=['CPUExecutionProvider'])
_in_shape = _sess.get_inputs()[0].shape
if _in_shape[1:] != [NUM_FEATURES, WINDOW_SIZE]:
    raise RuntimeError(f'ONNX input shape {_in_shape} != [batch, {NUM_FEATURES}, {WINDOW_SIZE}]')
_onnx_val = _sess.run(None, {'input': X_val[:256]})[0]
_probe = np.random.default_rng(SEED).standard_normal((8, NUM_FEATURES, WINDOW_SIZE)).astype('float32')
_onnx_probe = _sess.run(None, {'input': _probe})[0]
if SCALAR_HEAD:
    for _name, _out in (('validation windows', _onnx_val), ('a random probe', _onnx_probe)):
        if not ((_out > 0) & (_out < 1)).all():
            # ADR-0003 B-4: refuse to package a scalar head whose output leaves (0, 1).
            raise RuntimeError(f'Scalar head output on {_name} is not strictly inside (0, 1)')
    _gap = float(np.abs(_onnx_val[:, 0] - val_scores[:len(_onnx_val)]).max())
    print(f'ONNX vs PyTorch max score difference on val: {_gap:.2e}')
    if _gap > 1e-2:
        raise RuntimeError('The exported graph does not reproduce the PyTorch scores')

HEAD = ({'shape': 'scalar', 'classes': CLASSES, 'range': [0.0, 1.0], 'activation': 'sigmoid'}
        if SCALAR_HEAD else {'shape': 'multiclass', 'classes': CLASSES, 'activation': 'none'})
META = {
    'feature_order': list(FEATURE_ORDER),   # channel names, in model input order
    'window': WINDOW_SIZE,
    'stride': STRIDE,
    'sample_rate_hz': SAMPLE_RATE_HZ,
    'units': {c: CHANNEL_UNITS[c] for c in FEATURE_ORDER if CHANNEL_UNITS.get(c)},
    'definitions': {c: CHANNEL_DEFINITIONS[c] for c in FEATURE_ORDER if CHANNEL_DEFINITIONS.get(c)},
    'reduce': {c: CHANNEL_REDUCE[c] for c in FEATURE_ORDER if CHANNEL_REDUCE.get(c)},
    'head': HEAD,
    'output_schema': 'anomaly_score' if SCALAR_HEAD else 'class_logits',
    'decision_threshold': DECISION_THRESHOLD,
    'at_fpr': AT_FPR,
    'class_names': list(CLASSES),
    'opset': ONNX_OPSET,
    'input_shape': [1, NUM_FEATURES, WINDOW_SIZE],
    'input_layout': 'channels_first',
    'normalization': {'mean': NORM_MEAN.tolist(), 'std': NORM_STD.tolist(), 'applied': 'in_graph'},
    'label_rule': LABEL_RULE,
    'split_strategy': SPLIT_STRATEGY,
    'framework_versions': {'torch': torch.__version__, 'onnx': onnx.__version__, 'onnxruntime': ort.__version__},
}
mlflow_call('log_artifact', ONNX_MODEL_PATH)
mlflow_call('log_dict', META, 'meta.json')
mlflow_call('end_run')
print(f'Exported {ONNX_MODEL_PATH}: opset {_opset}, input {_in_shape}, output {_sess.get_outputs()[0].shape}')
print('Next: the return-package cell below writes neuroedge_return_package/ for upload to NeuroEdge.')

# ## Calibration data for INT8 optimization
# Copy 50-200 representative samples into 'neuroedge_return_package/calibration/' when the target runtime will use INT8 quantization. Use real production-like camera frames or sensor windows, not public demo data.
from pathlib import Path
CALIBRATION_DATA_DIR = Path('neuroedge_return_package/calibration')
CALIBRATION_DATA_DIR.mkdir(parents=True, exist_ok=True)
print(f'Optional calibration directory ready: {CALIBRATION_DATA_DIR}')

# ## Write NeuroEdge return package
# This cell creates 'metrics.json', 'model_artifact.json', and copies the ONNX (and, if present, raw) model files into 'neuroedge_return_package/' using the shared 'neuroedge_return' writer — the same code the portal uses to validate the package on upload.
from pathlib import Path

# Secondary option, if this machine can reach the Git remote:
#   pip install "git+https://github.com/cognizant/neuroedge-web.git#subdirectory=src/neuroedge_design_usecase"
#   pip install "git+https://github.com/cognizant/neuroedge-web.git#subdirectory=src/neuroedge_return"
try:
    from neuroedge_return import write_return_package
except ImportError as exc:
    raise ImportError(
        'neuroedge_return is not installed in this training environment. '
        'Install it with: pip install -e <NeuroEdge-Web>/src/neuroedge_design_usecase -e <NeuroEdge-Web>/src/neuroedge_return  (or pip install the two built wheels)'
    ) from exc

RETURN_DIR = Path('neuroedge_return_package')
raw_model_path = Path(str(globals().get('RAW_MODEL_PATH', 'best.pt')))
onnx_model_path = Path(str(globals().get('ONNX_MODEL_PATH', 'model.onnx')))
if not onnx_model_path.exists():
    raise FileNotFoundError(
        f'{onnx_model_path} not found — export to ONNX (Step 6 above) before writing '
        'the return package. A custom return package must include an ONNX model.'
    )

default_metrics = {
    'epochs_completed': int(globals().get('EPOCHS', 0)),
    'best_epoch': int(globals().get('BEST_EPOCH', globals().get('EPOCHS', 0))),
    'train_loss': float(globals().get('TRAIN_LOSS', 0.0)),
    'val_loss': float(globals().get('VAL_LOSS', 0.0)),
    'training_duration_s': float(globals().get('TRAINING_DURATION_S', 0.0)),
    'extra_metrics': {},
    # ADR-0005 P-3: this notebook's val metrics are self-reported by construction —
    # there is no held-out test split here. State that explicitly rather than
    # letting a number render without provenance.
    'eval_split': 'self_reported_val',
}
metrics = {**default_metrics, **globals().get('METRICS', {})}
if 'ts' == 'cv':
    metrics.setdefault('map50', float(globals().get('MAP50', 0.0)))
    metrics.setdefault('map50_95', globals().get('MAP50_95'))
    metrics.setdefault('precision', globals().get('PRECISION'))
    metrics.setdefault('recall', globals().get('RECALL'))
else:
    metrics.setdefault('pr_auc', globals().get('PR_AUC'))
    metrics.setdefault('recall_at_fpr', globals().get('RECALL_AT_FPR'))
    metrics.setdefault('fpr', globals().get('FPR'))
    metrics.setdefault('event_f1', globals().get('EVENT_F1'))

meta = dict(globals().get('META', {}))
meta.setdefault('class_names', CLASSES)
if TASK_TYPE == 'anomaly_detection' and len(CLASSES) == 2:
    # Two-class anomaly detection is a SCALAR score in (0, 1), not a 2-logit argmax
    # (ml-model-package; ADR-0003 B-3).
    _default_head = {'shape': 'scalar', 'classes': CLASSES, 'range': [0.0, 1.0], 'activation': 'sigmoid'}
elif len(CLASSES) != 1:
    _default_head = {'shape': 'multiclass', 'classes': CLASSES}
else:
    _default_head = {'shape': 'scalar'}
meta.setdefault('head', _default_head)
_ts_ctx = NEUROEDGE_CONTEXT['task'].get('timeseries') or {}
_ts_channels = _ts_ctx.get('channels') or []
meta.setdefault('feature_order', list(globals().get('FEATURE_ORDER') or [c['name'] for c in _ts_channels]))
if not meta['feature_order']:
    raise ValueError(
        'meta.feature_order is empty. Set FEATURE_ORDER to the channel names in model input order '
        '(the use case channel names, never sensor_i placeholders).'
    )
meta.setdefault('window', int(globals().get('WINDOW_SIZE') or _ts_ctx.get('window_samples') or 64))
meta.setdefault('stride', globals().get('STRIDE', _ts_ctx.get('stride_samples')))
meta.setdefault('sample_rate_hz', globals().get('SAMPLE_RATE_HZ', _ts_ctx.get('sample_rate_hz')))
for _key, _field in (('units', 'unit'), ('definitions', 'definition'), ('reduce', 'reduce')):
    meta.setdefault(_key, {c['name']: c[_field] for c in _ts_channels if c.get(_field)})
meta.setdefault('at_fpr', globals().get('AT_FPR', (PERFORMANCE_TARGETS.get('accuracy') or {}).get('at_fpr')))
meta.setdefault('decision_threshold', globals().get('DECISION_THRESHOLD'))
meta.setdefault('output_schema', 'anomaly_score' if meta['head'].get('shape') == 'scalar' else 'class_logits')
meta.setdefault('input_shape', [1, len(meta['feature_order']), int(meta['window'])])

model_name = str(globals().get('MODEL_SIZE', globals().get('MODEL_NAME', globals().get('ARCH', 'custom_model'))))

# ADR-0003 B-1: a baseline must be *computed*, not fabricated. If BASELINE isn't
# wired up, write the package without a baseline block — NeuroEdge will then reject
# the upload naming the missing check, instead of silently accepting an
# uncompared {'beats_baseline': None} that would clear the B-1/B-7 gate.
baseline = globals().get('BASELINE')
if baseline is None:
    print(
        'WARNING: no BASELINE computed (ADR-0003 B-1). Set BASELINE = '
        "{'estimator': <name>, 'beats_baseline': True/False, 'metrics': {...}} "
        'before running this cell, or NeuroEdge will refuse the upload naming '
        "the missing 'baseline_present' check."
    )

extras = {
    'contract_version': NEUROEDGE_CONTEXT['contract_version'],
    'task_type': TASK_TYPE,
    'dataset_uri': DATASET_PATH,
    'device_profile_id': TARGET_DEVICE_PROFILE_ID,
    'runtime_profile': RUNTIME_PROFILE,
    'performance_targets': PERFORMANCE_TARGETS,
    'business_requirement': BUSINESS_REQUIREMENT,
    'model_name': model_name,
}
if baseline is not None:
    extras['baseline'] = baseline
# The input contract travels in extras too: upload holds extras to the use case, and the
# device's input contract is built from them (ADR-0008 L-4).
for _key in ('feature_order', 'window', 'stride', 'sample_rate_hz', 'units', 'definitions', 'reduce',
             'head', 'output_schema', 'decision_threshold', 'at_fpr', 'normalization', 'opset'):
    if meta.get(_key) is not None:
        extras[_key] = meta[_key]
extras['eval_split'] = metrics.get('eval_split')
for _key, _name in (('split_hash', 'SPLIT_HASH'), ('split_strategy', 'SPLIT_STRATEGY'),
                    ('label_rule', 'LABEL_RULE'), ('seed', 'SEED'), ('mlflow_run_id', 'MLFLOW_RUN_ID')):
    if globals().get(_name) is not None:
        extras[_key] = globals()[_name]

files = write_return_package(
    RETURN_DIR,
    use_case_id=USE_CASE_ID,
    task_type=TASK_TYPE,
    classes=CLASSES,
    onnx_path=onnx_model_path,
    meta=meta,
    metrics=metrics,
    model_artifact_extras=extras,
    raw_model_path=raw_model_path if raw_model_path.exists() else None,
    calibration_dir=CALIBRATION_DATA_DIR if any(CALIBRATION_DATA_DIR.iterdir()) else None,
)
print('NeuroEdge return package ready (model_artifact.json, metrics.json):')
for name, path in sorted(files.items()):
    print(' - upload_files:', name, '=', path)
print('onnx_uri:', files.get("model_onnx"))
