# -*- coding: utf-8 -*-
"""Writes the `ml-model-package` folder contract: model.onnx, meta.json, metrics.json,
model_artifact.json, optional calibration/ (ADR-0022; agentic-assets/skills/ENGINEERING/ai-ml/
ml-model-package.md).

Self-sufficient: works with no external dependency. When `neuroedge_return` (from the platform's
own return-package writer, installed locally per RUN_ON_GPU.md) is importable, its
`validate_package` is run against the folder afterwards as an extra check — never a hard
requirement, since AgentForge does not fetch it during training (model-codegen: "never fetched
during training").
"""
from __future__ import annotations

import json
import platform as _platform
import subprocess
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch

from model import ScoreModel


def export_onnx(score_model: ScoreModel, window: int, n_features: int, opset: int, out_path: Path) -> dict:
    score_model.eval().cpu()
    dummy = torch.randn(1, n_features, window)
    torch.onnx.export(
        score_model,
        dummy,
        str(out_path),
        input_names=["input"],
        output_names=["output"],
        opset_version=opset,
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
    )
    onnx_model = onnx.load(str(out_path))
    onnx.checker.check_model(onnx_model)
    got_opset = next(o.version for o in onnx_model.opset_import if o.domain in ("", "ai.onnx"))
    if got_opset != opset:
        raise RuntimeError(f"Exported opset {got_opset} != required {opset}")

    sess = ort.InferenceSession(str(out_path), providers=["CPUExecutionProvider"])
    in_shape = sess.get_inputs()[0].shape
    if in_shape[1:] != [n_features, window]:
        raise RuntimeError(f"ONNX input shape {in_shape} != [batch, {n_features}, {window}]")

    probe = np.random.default_rng(0).standard_normal((16, n_features, window)).astype("float32")
    onnx_out = sess.run(None, {"input": probe})[0]
    if not ((onnx_out > 0) & (onnx_out < 1)).all():
        raise RuntimeError("Scalar head ONNX output is not strictly inside (0, 1) on a random probe")
    with torch.no_grad():
        torch_out = score_model(torch.from_numpy(probe)).numpy()
    max_gap = float(np.abs(onnx_out - torch_out).max())
    if max_gap > 1e-3:
        raise RuntimeError(f"ONNX vs PyTorch score mismatch too large ({max_gap:.2e}); export did not reproduce the model")
    return {"opset": got_opset, "input_shape": [1, n_features, window], "max_onnx_vs_torch_gap": max_gap}


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def build_meta(
    lock: dict,
    mean: np.ndarray,
    std: np.ndarray,
    decision_threshold: float,
    opset: int,
) -> dict:
    ts = lock["timeseries"]
    feature_order = [c["name"] for c in ts["channels"]]
    return {
        "feature_order": feature_order,
        "window": ts["window_samples"],
        "stride": ts["stride_samples"],
        "sample_rate_hz": ts["sample_rate_hz"],
        "units": {c["name"]: c["unit"] for c in ts["channels"]},
        "definitions": {c["name"]: c["definition"] for c in ts["channels"]},
        "reduce": {c["name"]: c["reduce"] for c in ts["channels"]},
        "lock_sha256": lock["lock_sha256"],
        "normalization": {"mean": mean.tolist(), "std": std.tolist(), "applied": "in_graph"},
        "head": {
            "shape": "scalar",
            "classes": lock["class_names"],
            "range": [0.0, 1.0],
            "activation": "sigmoid",
        },
        "output_schema": "anomaly_score",
        "decision_threshold": decision_threshold,
        "at_fpr": lock["target"]["at_fpr"],
        "class_names": lock["class_names"],
        "opset": opset,
        "input_shape": [1, len(feature_order), ts["window_samples"]],
        "input_layout": "channels_first",
        "framework_versions": {
            "torch": torch.__version__,
            "onnx": onnx.__version__,
            "onnxruntime": ort.__version__,
            "python": _platform.python_version(),
        },
    }


def write_package(
    out_dir: Path,
    lock: dict,
    onnx_path: Path,
    meta: dict,
    metrics: dict,
    baseline: dict,
    extras: dict,
    calibration_samples: np.ndarray | None = None,
    neuroedge_context: dict | None = None,
) -> dict:
    """Writes model.onnx (already at onnx_path, copied in), meta.json, metrics.json,
    model_artifact.json, optional calibration/ into `out_dir`. Returns the file map."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    final_onnx = out_dir / "model.onnx"
    if Path(onnx_path).resolve() != final_onnx.resolve():
        final_onnx.write_bytes(Path(onnx_path).read_bytes())

    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    model_artifact = {
        "use_case_id": lock["use_case_id"],
        "model_name": extras.pop("model_name", "1d-cnn"),
        "framework": "pytorch",
        "format": "onnx",
        "uri": "model.onnx",
        "metrics": {k: v for k, v in metrics.items() if isinstance(v, (int, float)) and v is not None},
        "metrics_type": "rare_event_detection",
        "class_names": lock["class_names"],
        "input_shape": meta["input_shape"],
        "created_at": extras.pop("created_at"),
        "extras": {
            "dataset_id": "kit-cnc-milling-multimodal",
            "dataset_license": "CC BY 4.0",
            "attribution": (
                "Stroebel, R. et al. (2025). A Multimodal Dataset for Process Monitoring and "
                "Anomaly Detection in Industrial CNC Milling. Karlsruhe Institute of Technology. "
                "DOI: 10.35097/hvvwn1kfwf7qt48z."
            ),
            "split_hash": extras.pop("split_hash"),
            "seed": extras.pop("seed"),
            "code_commit": _git_commit(),
            "eval_split": metrics.get("eval_split"),
            "lock_sha256": lock["lock_sha256"],
            "sample_rate_hz": meta["sample_rate_hz"],
            "stride": meta["stride"],
            "units": meta["units"],
            "definitions": meta["definitions"],
            "reduce": meta["reduce"],
            "baseline": baseline,
            "onnx_uri": "model.onnx",
            "meta_uri": "meta.json",
            "calibration_data_uri": "calibration/" if calibration_samples is not None else None,
            "source": "custom_return",
            **extras,
        },
    }
    if neuroedge_context is not None:
        model_artifact["extras"]["contract_version"] = neuroedge_context.get("contract_version")
        model_artifact["extras"]["target"] = neuroedge_context.get("target")
        model_artifact["extras"]["business_requirement"] = neuroedge_context.get("business_requirement")

    (out_dir / "model_artifact.json").write_text(json.dumps(model_artifact, indent=2, default=str), encoding="utf-8")

    files = {"model_onnx": str(final_onnx), "meta_json": str(out_dir / "meta.json"),
             "metrics_json": str(out_dir / "metrics.json"), "model_artifact_json": str(out_dir / "model_artifact.json")}

    if calibration_samples is not None and len(calibration_samples) > 0:
        calib_dir = out_dir / "calibration"
        calib_dir.mkdir(exist_ok=True)
        np.save(calib_dir / "windows.npy", calibration_samples)
        files["calibration"] = str(calib_dir)

    try:
        from neuroedge_return import validate_package  # type: ignore

        result = validate_package(out_dir)
        print(f"neuroedge_return.validate_package: {result}")
    except ImportError:
        print("neuroedge_return is not installed -- skipping the optional platform-side package validation.")
    except Exception as exc:  # pragma: no cover - best effort only
        print(f"neuroedge_return.validate_package raised {type(exc).__name__}: {exc} (non-fatal)")

    return files
