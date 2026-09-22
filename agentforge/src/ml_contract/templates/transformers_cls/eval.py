"""Held-out evaluation of the exported model.onnx. The ONLY code that opens data/splits/test.json (ADR-0022 M10).

    python eval.py --package <model-package folder> --split <test.json> --config config.yaml --out <metrics.json>

The command line is fixed (ADR-0028 D-12): the portal's evaluator calls exactly this on the sealed test bundle.
It runs the ONNX file with onnxruntime on CPU. It imports neither torch nor transformers, and it never reads
train or val. When the package carries the exported baseline (baseline/model.onnx), it scores BOTH on the split it
is given and writes `baseline` and `beats_baseline` with the same eval_split and split_hash: the comparison M10
trusts is this one, not the validation one train.py reported about itself.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort

import tf_common as common


def predict(onnx_path: Path, input_name: str, paths: list[Path], cfg: dict, batch: int) -> np.ndarray:
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    predicted: list[int] = []
    for start in range(0, len(paths), batch):
        images = np.stack([common.load_image(path, cfg) for path in paths[start:start + batch]])
        predicted += session.run(None, {input_name: images})[0].argmax(axis=1).tolist()
    return np.array(predicted)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--package", required=True, help="the model-package folder train.py wrote")
    parser.add_argument("--split", required=True, help="data/splits/test.json")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", help="where to write metrics.json (default: <package>/metrics.json)")
    args = parser.parse_args()

    cfg = common.load_config(args.config)
    root = (Path(args.config).resolve().parent / cfg["paths"]["model_folder"]).resolve()
    lock = common.check_lock(cfg, root)
    package = Path(args.package)
    meta = json.loads((package / "meta.json").read_text(encoding="utf-8"))
    class_names = meta["class_names"]
    if class_names != lock["class_names"] or meta["lock_sha256"] != lock["lock_sha256"]:
        raise common.ContractError("the model-package was built on another lock, or with other classes")

    paths, labels, split_hash = common.read_split(root, args.split, class_names)
    batch, name = int(cfg["eval"]["batch_size"]), meta["input"]["name"]
    truth = np.array(labels)
    scores = common.classification_metrics(truth, predict(package / "model.onnx", name, paths, cfg, batch), class_names)
    metrics = {"eval_split": "held_out_test", "split_hash": split_hash, "lock_sha256": lock["lock_sha256"],
               "map50": scores["accuracy"],  # the NeuroEdge schema carries top-1 accuracy in this field
               **scores}
    baseline_onnx = package / "baseline" / "model.onnx"
    if baseline_onnx.is_file():
        floor = common.classification_metrics(truth, predict(baseline_onnx, name, paths, cfg, batch), class_names)
        metrics["baseline"] = {"name": "linear_probe_frozen_backbone", "measured_on": "held_out_test",
                               "split_hash": split_hash,
                               "metrics": {"accuracy": floor["accuracy"], "macro_f1": floor["macro_f1"]}}
        metrics["beats_baseline"] = bool(scores["macro_f1"] > floor["macro_f1"])
    else:
        print("no baseline/model.onnx in the package: the baseline was compared on validation only", flush=True)
    out = Path(args.out) if args.out else package / "metrics.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"{out}: accuracy {scores['accuracy']:.4f} · macro_f1 {scores['macro_f1']:.4f} on {scores['n_samples']} images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
