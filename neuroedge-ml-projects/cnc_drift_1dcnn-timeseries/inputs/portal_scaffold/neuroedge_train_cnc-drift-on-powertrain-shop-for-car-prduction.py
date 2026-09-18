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
  "generated_at": "2026-09-18T15:05:10.908817+00:00",
  "industry": "manufacturing",
  "model_hint": {
    "family": "custom",
    "framework": "auto",
    "variant": null
  },
  "performance_targets": {
    "accuracy": {
      "metric": "recall",
      "min_value": 0.9,
      "notes": "Recall \u2265 0.90 (must catch at least 90% of real drift events). False alarm tolerance: \u2264 1 per week (at_fpr = 0.01).\n"
    },
    "latency_ms_p95_max": null,
    "max_latency_ms": 172000.0,
    "max_memory_mb": null,
    "max_seconds_per_cycle": null,
    "min_accuracy_map50": 0.5,
    "min_fps": 1.0,
    "power_w_max": null,
    "provenance": {
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
      "fps": null,
      "modality": "industrial_sensor",
      "resolution": [
        640,
        640
      ],
      "sample_rate_hz": 10.0,
      "source": "opcua",
      "streams": null,
      "window_samples": 64
    },
    "model_category": "anomaly_detection",
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
# Expected dataset: CSV or parquet-style sensor windows. The starter code assumes a CSV with sensor columns and a 'label' column.
# ## 1 — Install dependencies
# Colab shell command: !pip install torch pandas numpy onnx --quiet

# ## 2 — Parameters  *(edit these)*
USE_CASE_ID   = 'cnc-drift-on-powertrain-shop-for-car-prduction'
DATASET_PATH  = ''  # CSV: timestamp,sensor_1,...,sensor_N,label
CLASSES       = ['normal', 'tool_wear']
WINDOW_SIZE   = 64      # sliding window length in timesteps
EPOCHS        = 50
LR            = 0.001
BATCH_SIZE    = 64
ARCH          = '1d-cnn'  # '1d-cnn' | 'lstm' | 'transformer'

# ## 3 — Load and window data
import pandas as pd, numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

df = pd.read_csv(DATASET_PATH).ffill()
feature_cols = [c for c in df.columns if c not in ('timestamp', 'label')]
X_raw = df[feature_cols].values.astype('float32')
y_raw = df['label'].values.astype('int64')
# Z-score normalise
X_raw = (X_raw - X_raw.mean(0)) / (X_raw.std(0) + 1e-8)
# Sliding windows
X_w = np.stack([X_raw[i:i+WINDOW_SIZE] for i in range(len(X_raw)-WINDOW_SIZE)])
y_w = y_raw[WINDOW_SIZE:]
split = int(len(X_w) * 0.8)
train_ds = TensorDataset(torch.from_numpy(X_w[:split]).permute(0,2,1), torch.from_numpy(y_w[:split]))
val_ds   = TensorDataset(torch.from_numpy(X_w[split:]).permute(0,2,1), torch.from_numpy(y_w[split:]))
train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE)
NUM_FEATURES = X_w.shape[2]
NUM_CLASSES  = len(set(y_w.tolist()))
print(f'Features: {NUM_FEATURES}  Classes: {NUM_CLASSES}  Windows: {len(X_w)}')

# ## 4 — Build model
from torch import nn

class Conv1DModel(nn.Module):
    def __init__(self, n_features, n_classes):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(n_features, 64, kernel_size=5, padding=2), nn.ReLU(),
            nn.Conv1d(64, 128, kernel_size=3, padding=1), nn.ReLU(),
            nn.AdaptiveAvgPool1d(1), nn.Flatten(),
            nn.Linear(128, 64), nn.ReLU(),
            nn.Linear(64, n_classes),
        )
    def forward(self, x): return self.net(x)

class LSTMModel(nn.Module):
    def __init__(self, n_features, n_classes):
        super().__init__()
        self.lstm = nn.LSTM(n_features, 128, num_layers=2, batch_first=True, dropout=0.2)
        self.head = nn.Linear(128, n_classes)
    def forward(self, x):
        x = x.permute(0, 2, 1)
        out, _ = self.lstm(x)
        return self.head(out[:, -1])

model = (LSTMModel if ARCH == 'lstm' else Conv1DModel)(NUM_FEATURES, NUM_CLASSES)
print(model)

# ## 5 — Train
import torch.optim as optim

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model = model.to(device)
optimizer = optim.Adam(model.parameters(), lr=LR)
criterion = nn.CrossEntropyLoss()

best_acc, best_state = 0.0, None
for epoch in range(EPOCHS):
    model.train()
    for xb, yb in train_loader:
        xb, yb = xb.to(device), yb.to(device)
        optimizer.zero_grad()
        criterion(model(xb), yb).backward()
        optimizer.step()
    model.eval()
    correct = total = 0
    with torch.no_grad():
        for xb, yb in val_loader:
            xb, yb = xb.to(device), yb.to(device)
            correct += (model(xb).argmax(1) == yb).sum().item()
            total += yb.size(0)
    acc = correct / total
    if acc > best_acc:
        best_acc, best_state = acc, {k: v.clone() for k, v in model.state_dict().items()}
    print(f'Epoch {epoch+1}/{EPOCHS}  val_acc={acc:.3f}  best={best_acc:.3f}')
model.load_state_dict(best_state)
torch.save(model.state_dict(), 'best.pt')
RAW_MODEL_PATH = 'best.pt'
METRICS = {'f1_score': best_acc, 'extra_metrics': {'window_accuracy': best_acc}}
print('Saved best.pt')

# ## 6 — Export to ONNX
import torch.onnx

model.eval().cpu()
dummy = torch.randn(1, NUM_FEATURES, WINDOW_SIZE)
torch.onnx.export(
    model, dummy, 'model.onnx',
    input_names=['input'], output_names=['output'],
    opset_version=13,  # NeuroEdge repo-wide contract (ADR-0001 W-3)
)
ONNX_MODEL_PATH = 'model.onnx'
print('Exported model.onnx')
print('Upload best.pt or model.onnx to NeuroEdge Step 4 → Build my own → Upload trained model')

# ## Calibration data for INT8 optimization
# Copy 50-200 representative samples into 'neuroedge_return_package/calibration/' when the target runtime will use INT8 quantization. Use real production-like camera frames or sensor windows, not public demo data.
from pathlib import Path
CALIBRATION_DATA_DIR = Path('neuroedge_return_package/calibration')
CALIBRATION_DATA_DIR.mkdir(parents=True, exist_ok=True)
print(f'Optional calibration directory ready: {CALIBRATION_DATA_DIR}')

# ## Write NeuroEdge return package
# This cell creates 'metrics.json', 'model_artifact.json', and copies the ONNX (and, if present, raw) model files into 'neuroedge_return_package/' using the shared 'neuroedge_return' writer — the same code the portal uses to validate the package on upload.
from pathlib import Path

try:
    from neuroedge_return import write_return_package
except ImportError as exc:
    raise ImportError(
        'neuroedge_return is not installed in this training environment. '
        'Install it with: pip install "git+https://github.com/cognizant/neuroedge-web.git#subdirectory=src/neuroedge_return"'
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
meta.setdefault('head', {'shape': 'multiclass', 'classes': CLASSES} if len(CLASSES) != 1 else {'shape': 'scalar'})
if 'ts' == 'ts':
    meta.setdefault(
        'feature_order',
        list(globals().get('FEATURE_ORDER', [f'sensor_{i}' for i in range(int(globals().get('NUM_FEATURES', 1)))])),
    )
    meta.setdefault('window', int(globals().get('WINDOW_SIZE', 64)))

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
