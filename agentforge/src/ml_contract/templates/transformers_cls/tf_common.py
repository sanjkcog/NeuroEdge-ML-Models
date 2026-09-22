"""Shared by train.py and eval.py: the config, the lock check, the split files, image preprocessing, metrics.

Nothing here imports torch or transformers, so eval.py runs on a machine that has only onnxruntime.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image

LETTERBOX_FILL = 114  # the grey the device's letterbox uses


class ContractError(ValueError):
    """The folder is not the one this code was generated for. Training on it would break the use-case contract."""


def load_config(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_lock(cfg: dict[str, Any], root: Path) -> dict[str, Any]:
    """The lock in the model folder must be the one this config was generated from, classes and order included."""
    lock = json.loads((root / "use_case.lock.json").read_text(encoding="utf-8"))
    if lock["lock_sha256"] != cfg["contract"]["lock_sha256"]:
        raise ContractError("use_case.lock.json is not the lock this code was generated for: run /model-build again")
    if lock["class_names"] != cfg["contract"]["class_names"]:
        raise ContractError("the class names, or their order, differ from the lock")
    return lock


def check_base_weights(cfg: dict[str, Any], root: Path) -> Path:
    """The fetched snapshot must be the one /model-fetch recorded, file by file. Returns its folder."""
    base = root / cfg["base_model"]["folder"]
    loader = json.loads((base / "loader.json").read_text(encoding="utf-8"))
    if loader["weights_sha256"] != cfg["base_model"]["weights_sha256"]:
        raise ContractError("model/base/loader.json names other weights than this code was generated for")
    snapshot = base / loader["weights_dir"]
    for name, digest in loader["files"].items():
        if not (snapshot / name).is_file() or sha256_of(snapshot / name) != digest:
            raise ContractError(f"{name} in the base model snapshot is missing or changed: run /model-fetch again")
    return snapshot


def read_split(root: Path, split_file: str, class_names: list[str]) -> tuple[list[Path], list[int], str | None]:
    """(image paths, class indices, split_hash) of one split file: each unit lists its files and carries one label."""
    doc = json.loads(Path(split_file).read_text(encoding="utf-8"))
    paths: list[Path] = []
    labels: list[int] = []
    for unit in doc.get("units", []):
        label = unit.get("label")
        if label not in class_names:
            raise ContractError(f"unit {unit.get('unit_id')!r}: label {label!r} is not one of the lock's classes")
        for rel in unit.get("files") or []:
            paths.append(root / rel)
            labels.append(class_names.index(label))
    if not paths:
        raise ContractError(f"{split_file} lists no image files")
    return paths, labels, doc.get("split_hash")


def load_image(path: Path, cfg: dict[str, Any]) -> np.ndarray:
    """One image as float32 CHW in [0, 1], sized and ordered as the lock says. Normalisation is in the graph."""
    height, width = cfg["contract"]["input"]["height"], cfg["contract"]["input"]["width"]
    image = Image.open(path).convert("RGB")
    if cfg["contract"]["preprocess"] == "letterbox":
        scale = min(width / image.width, height / image.height)
        resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.BILINEAR)
        canvas = Image.new("RGB", (width, height), (LETTERBOX_FILL,) * 3)
        canvas.paste(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
        image = canvas
    else:
        image = image.resize((width, height), Image.BILINEAR)
    array = np.asarray(image, dtype=np.float32) / 255.0
    if cfg["contract"]["input"]["color_order"] == "BGR":
        array = array[:, :, ::-1]
    return np.ascontiguousarray(array.transpose(2, 0, 1))


def classification_metrics(y_true: np.ndarray, y_pred: np.ndarray, class_names: list[str]) -> dict[str, Any]:
    """Top-1 accuracy, macro F1, per-class recall and the confusion matrix (rows = true class)."""
    n = len(class_names)
    confusion = np.zeros((n, n), dtype=np.int64)
    for t, p in zip(y_true, y_pred):
        confusion[int(t), int(p)] += 1
    tp = np.diag(confusion).astype(np.float64)
    recall = np.divide(tp, confusion.sum(axis=1), out=np.zeros(n), where=confusion.sum(axis=1) > 0)
    precision = np.divide(tp, confusion.sum(axis=0), out=np.zeros(n), where=confusion.sum(axis=0) > 0)
    f1 = np.divide(2 * precision * recall, precision + recall, out=np.zeros(n), where=(precision + recall) > 0)
    return {
        "accuracy": float(tp.sum() / max(1, confusion.sum())),
        "macro_f1": float(f1.mean()),
        "per_class_recall": {name: float(recall[i]) for i, name in enumerate(class_names)},
        "confusion_matrix": confusion.tolist(),
        "n_samples": int(confusion.sum()),
    }
