"""Fine-tune a Hugging Face image classifier from a LOCAL snapshot, then write the model-package (ADR-0028 D-6).

    python train.py --config config.yaml

* No network at train time. The snapshot was fetched and hashed by /model-fetch; it is checked file by file
  before it is loaded, and the hub libraries are forced offline.
* Reads data/splits/train.json and val.json only. Nothing here opens test.json; eval.py is the only code that does.
* Trains the baseline first (a linear probe: frozen backbone, new head), then the fine-tuned model, on the same
  split and the same metrics. The comparison made here is on VALIDATION, and is labelled so
  (measured_on: self_reported_val). The baseline is exported too (model-package/baseline/model.onnx), so that
  eval.py can score both on the held-out test split: that comparison is the one M10 trusts.
* Exports ONNX through optimum at the pinned opset, folds the normalisation into the graph, checks the result with
  onnxruntime, and writes model.onnx, meta.json, model_artifact.json and metrics.json (eval_split: self_reported_val).
"""
from __future__ import annotations

import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # before transformers is imported: nothing may reach the hub
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import argparse  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
import shutil  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import numpy as np  # noqa: E402
import torch  # noqa: E402
from torch.utils.data import DataLoader, Dataset  # noqa: E402
from transformers import AutoModelForImageClassification  # noqa: E402

import tf_common as common  # noqa: E402


class SplitImages(Dataset):
    def __init__(self, paths: list[Path], labels: list[int], cfg: dict[str, Any], augment: bool):
        self.paths, self.labels, self.cfg, self.augment = paths, labels, cfg, augment

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        image = common.load_image(self.paths[index], self.cfg)
        if self.augment and self.cfg["train"]["augment"]["horizontal_flip"] and random.random() < 0.5:
            image = np.ascontiguousarray(image[:, :, ::-1])
        return torch.from_numpy(image), self.labels[index]


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def normalisation(snapshot: Path) -> tuple[list[float], list[float]]:
    """The pretrained model's own constants, read from the snapshot. They are not fitted on this data."""
    pre = json.loads((snapshot / "preprocessor_config.json").read_text(encoding="utf-8"))
    return [float(v) for v in pre["image_mean"]], [float(v) for v in pre["image_std"]]


def build_model(snapshot: Path, class_names: list[str]) -> torch.nn.Module:
    # attn_implementation="eager": scaled-dot-product attention needs a higher ONNX opset than the pinned one.
    return AutoModelForImageClassification.from_pretrained(
        str(snapshot), num_labels=len(class_names), id2label=dict(enumerate(class_names)),
        label2id={name: i for i, name in enumerate(class_names)}, ignore_mismatched_sizes=True,
        local_files_only=True, attn_implementation="eager")


def predict(model: torch.nn.Module, loader: DataLoader, mean: torch.Tensor, std: torch.Tensor,
            device: torch.device) -> tuple[np.ndarray, np.ndarray, float]:
    model.eval()
    truth, guess, loss_sum = [], [], 0.0
    with torch.no_grad():
        for images, labels in loader:
            logits = model(pixel_values=(images.to(device) - mean) / std).logits
            loss_sum += float(torch.nn.functional.cross_entropy(logits, labels.to(device), reduction="sum"))
            truth += labels.tolist()
            guess += logits.argmax(dim=1).tolist()
    return np.array(truth), np.array(guess), loss_sum / max(1, len(truth))


def fit(cfg: dict[str, Any], snapshot: Path, loaders: tuple[DataLoader, DataLoader], *, freeze_backbone: bool,
        epochs: int, class_weights: torch.Tensor, device: torch.device, log: Any) -> tuple[torch.nn.Module, dict[str, Any]]:
    """Train one model and return it at its best validation macro-F1, with that epoch's validation metrics."""
    class_names = cfg["contract"]["class_names"]
    model = build_model(snapshot, class_names).to(device)
    head = getattr(model, "classifier", None)
    if freeze_backbone:
        if head is None:
            raise common.ContractError("this architecture has no `classifier` head to train a linear probe on")
        for parameter in model.parameters():
            parameter.requires_grad = False
        for parameter in head.parameters():
            parameter.requires_grad = True
    mean_list, std_list = normalisation(snapshot)
    mean = torch.tensor(mean_list, device=device).view(1, 3, 1, 1)
    std = torch.tensor(std_list, device=device).view(1, 3, 1, 1)
    train_loader, val_loader = loaders
    optimiser = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],
                                  lr=cfg["train"]["head_lr"] if freeze_backbone else cfg["train"]["lr"],
                                  weight_decay=cfg["train"]["weight_decay"])
    schedule = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=max(1, epochs * len(train_loader)))
    best: dict[str, Any] = {"macro_f1": -1.0}
    best_state, stale, epoch = None, 0, 0
    for epoch in range(1, epochs + 1):
        model.train()
        running = 0.0
        for images, labels in train_loader:
            optimiser.zero_grad()
            logits = model(pixel_values=(images.to(device) - mean) / std).logits
            loss = torch.nn.functional.cross_entropy(logits, labels.to(device), weight=class_weights)
            loss.backward()
            optimiser.step()
            schedule.step()
            running += float(loss) * len(labels)
        truth, guess, val_loss = predict(model, val_loader, mean, std, device)
        metrics = common.classification_metrics(truth, guess, class_names)
        log(epoch, running / max(1, len(train_loader.dataset)), val_loss, metrics)
        if metrics["macro_f1"] > best["macro_f1"]:
            best = {**metrics, "best_epoch": epoch, "epochs_completed": epoch, "val_loss": val_loss,
                    "train_loss": running / max(1, len(train_loader.dataset))}
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
            if stale >= cfg["train"]["early_stopping_patience"]:
                break
    if best_state is None:
        raise common.ContractError("epochs must be at least 1")
    best["epochs_completed"] = epoch
    model.load_state_dict(best_state)
    return model, best


def export_onnx(model: torch.nn.Module, snapshot: Path, run_dir: Path, cfg: dict[str, Any], *,
                tag: str = "model", out_rel: str = "model.onnx") -> Path:
    """Export through optimum at the pinned opset, then fold the normalisation into the graph.

    optimum refuses an opset lower than the architecture needs. That refusal is the answer (ADR-0028 D-7): the pin
    is a joint portal and device decision, so nothing is written as model.onnx and the run stops.
    """
    import onnx
    from onnx import TensorProto, helper
    from optimum.exporters.onnx import main_export

    saved = run_dir / f"{tag}_best"
    model.save_pretrained(saved)
    shutil.copy2(snapshot / "preprocessor_config.json", saved / "preprocessor_config.json")
    exported = run_dir / f"{tag}_onnx"
    opset = int(cfg["export"]["opset"])
    try:
        main_export(str(saved), output=str(exported), task="image-classification", opset=opset,
                    local_files_only=True, do_validation=False)
    except ValueError as exc:
        raise SystemExit(f"ONNX export at opset {opset} was refused: {exc}\nThe pin is {opset} (NeuroEdge-Web "
                         "ADR-0001 W-3). This architecture cannot meet it. Do not raise the opset here: choose "
                         "another base model, or take the pin to the portal and device owners.") from exc
    graph_model = onnx.load(str(exported / "model.onnx"))
    graph = graph_model.graph
    mean, std = normalisation(snapshot)
    old_input = graph.input[0]
    raw = helper.make_tensor_value_info("input", TensorProto.FLOAT,
                                        ["batch", 3, cfg["contract"]["input"]["height"], cfg["contract"]["input"]["width"]])
    graph.initializer.extend([helper.make_tensor("neuroedge_mean", TensorProto.FLOAT, [1, 3, 1, 1], mean),
                              helper.make_tensor("neuroedge_std", TensorProto.FLOAT, [1, 3, 1, 1], std)])
    nodes = [helper.make_node("Sub", ["input", "neuroedge_mean"], ["neuroedge_centred"], name="neuroedge_sub"),
             helper.make_node("Div", ["neuroedge_centred", "neuroedge_std"], [old_input.name], name="neuroedge_div")]
    rest = list(graph.node)
    del graph.node[:]
    graph.node.extend(nodes + rest)
    del graph.input[:]
    graph.input.extend([raw])
    onnx.checker.check_model(graph_model)
    out = run_dir / "model-package" / out_rel
    out.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(graph_model, str(out))
    got = [o.version for o in graph_model.opset_import if o.domain in ("", "ai.onnx")]
    if got != [opset]:
        out.unlink()
        raise SystemExit(f"the exported graph declares opset {got}, not the pinned {opset}: nothing was kept")
    return out


def check_onnx(onnx_path: Path, sample: np.ndarray, n_classes: int) -> None:
    import onnxruntime as ort

    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    output = session.run(None, {"input": sample})[0]
    if output.shape != (sample.shape[0], n_classes):
        onnx_path.unlink()
        raise SystemExit(f"model.onnx returns shape {output.shape}, expected (batch, {n_classes}): nothing was kept")


def write_package(package: Path, cfg: dict[str, Any], lock: dict[str, Any], snapshot: Path, split_hash: str | None,
                  model_metrics: dict[str, Any], baseline_metrics: dict[str, Any], duration_s: float) -> None:
    import onnx
    import onnxruntime
    import transformers

    mean, std = normalisation(snapshot)
    contract = cfg["contract"]
    beats = model_metrics["macro_f1"] > baseline_metrics["macro_f1"]
    versions = {"torch": torch.__version__, "transformers": transformers.__version__, "onnx": onnx.__version__,
                "onnxruntime": onnxruntime.__version__}
    meta = {
        "input": {"name": "input", "layout": "NCHW", "resolution": [contract["input"]["height"], contract["input"]["width"]],
                  "color_order": contract["input"]["color_order"], "range": [0.0, 1.0], "preprocess": contract["preprocess"]},
        "normalization": {"mean": mean, "std": std, "applied": "in_graph",
                          "source": "the pretrained model's preprocessor_config.json, not fitted on this data"},
        "head": {"shape": "multiclass", "classes": contract["class_names"], "output_length": len(contract["class_names"]),
                 "activation": "none", "range": None},
        "output_schema": "class_logits",
        "class_names": contract["class_names"],
        "lock_sha256": lock["lock_sha256"],
        "opset": int(cfg["export"]["opset"]),
        "framework_versions": versions,
    }
    metrics = {"eval_split": "self_reported_val", "split_hash": split_hash, "lock_sha256": lock["lock_sha256"],
               "map50": model_metrics["accuracy"],  # the NeuroEdge schema carries top-1 accuracy in this field
               **model_metrics, "training_duration_s": round(duration_s, 1)}
    artifact = {
        "use_case_id": lock["use_case_id"], "model_name": cfg["arch"], "framework": "pytorch", "format": "onnx",
        "uri": "model.onnx", "metrics": {"accuracy": model_metrics["accuracy"], "macro_f1": model_metrics["macro_f1"]},
        "metrics_type": "classification", "class_names": contract["class_names"],
        "input_shape": [1, 3, contract["input"]["height"], contract["input"]["width"]],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "extras": {
            "lock_sha256": lock["lock_sha256"], "use_case_id": lock["use_case_id"], "split_hash": split_hash,
            "seed": cfg["seed"], "eval_split": "self_reported_val", "source": "custom_return",
            "catalogue_id": cfg["base_model"].get("catalogue_id"),
            "base_model": {k: cfg["base_model"][k] for k in ("model_id", "weights_sha256", "licence", "distribution")},
            # Compared on VALIDATION, which also picked both best epochs. eval.py repeats the comparison on the
            # held-out split from baseline/model.onnx, and M10 prefers that one.
            "baseline": {"name": "linear_probe_frozen_backbone", "metrics": {
                "accuracy": baseline_metrics["accuracy"], "macro_f1": baseline_metrics["macro_f1"]},
                "beats_baseline": bool(beats), "measured_on": "self_reported_val",
                "onnx": "baseline/model.onnx"},
        },
    }
    for name, body in (("meta.json", meta), ("metrics.json", metrics), ("model_artifact.json", artifact)):
        (package / name).write_text(json.dumps(body, indent=2), encoding="utf-8")


def start_mlflow(cfg: dict[str, Any], lock: dict[str, Any], split_hash: str | None) -> Any:
    """MLflow when it is importable (MLFLOW_TRACKING_URI decides where), else None and training still runs."""
    try:
        import mlflow
    except ImportError:
        print("mlflow is not installed: training runs without tracking", flush=True)
        return None
    mlflow.set_experiment(lock["use_case_id"])
    mlflow.start_run(run_name=cfg["arch"])
    mlflow.log_params({"arch": cfg["arch"], "base_model": cfg["base_model"]["model_id"], "lr": cfg["train"]["lr"],
                       "epochs": cfg["train"]["epochs"], "seed": cfg["seed"], "split_hash": split_hash,
                       "lock_sha256": lock["lock_sha256"]})
    return mlflow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    cfg = common.load_config(args.config)
    root = (Path(args.config).resolve().parent / cfg["paths"]["model_folder"]).resolve()
    lock = common.check_lock(cfg, root)
    snapshot = common.check_base_weights(cfg, root)
    set_seed(int(cfg["seed"]))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    class_names = cfg["contract"]["class_names"]

    train_paths, train_labels, split_hash = common.read_split(root, str(root / cfg["paths"]["train_split"]), class_names)
    val_paths, val_labels, _ = common.read_split(root, str(root / cfg["paths"]["val_split"]), class_names)
    counts = np.bincount(train_labels, minlength=len(class_names)).astype(np.float64)
    class_weights = torch.tensor(counts.sum() / np.maximum(counts, 1.0) / len(class_names), dtype=torch.float32, device=device)
    loaders = (DataLoader(SplitImages(train_paths, train_labels, cfg, augment=True), batch_size=cfg["train"]["batch_size"],
                          shuffle=True, num_workers=cfg["train"]["num_workers"]),
               DataLoader(SplitImages(val_paths, val_labels, cfg, augment=False), batch_size=cfg["train"]["batch_size"],
                          num_workers=cfg["train"]["num_workers"]))

    run_dir = Path(args.config).resolve().parent / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True)
    started = time.time()

    tracker = start_mlflow(cfg, lock, split_hash)

    def log(stage: str) -> Any:
        def write(epoch: int, train_loss: float, val_loss: float, metrics: dict[str, Any]) -> None:
            if tracker is not None:
                tracker.log_metrics({f"{stage}_train_loss": train_loss, f"{stage}_val_loss": val_loss,
                                     f"{stage}_val_macro_f1": metrics["macro_f1"],
                                     f"{stage}_val_accuracy": metrics["accuracy"]}, step=epoch)
            print(f"[{stage}] epoch {epoch}: train_loss {train_loss:.4f} val_loss {val_loss:.4f} "
                  f"val_macro_f1 {metrics['macro_f1']:.4f} val_accuracy {metrics['accuracy']:.4f}", flush=True)
        return write

    baseline_model, baseline_metrics = fit(cfg, snapshot, loaders, freeze_backbone=True,
                                           epochs=cfg["baseline"]["epochs"], class_weights=class_weights,
                                           device=device, log=log("baseline"))
    baseline_model = baseline_model.to("cpu").eval()
    set_seed(int(cfg["seed"]))
    model, model_metrics = fit(cfg, snapshot, loaders, freeze_backbone=False, epochs=cfg["train"]["epochs"],
                               class_weights=class_weights, device=device, log=log("model"))

    onnx_path = export_onnx(model.to("cpu").eval(), snapshot, run_dir, cfg)
    sample = np.stack([common.load_image(path, cfg) for path in val_paths[:2]])
    check_onnx(onnx_path, sample, len(class_names))
    baseline_onnx = export_onnx(baseline_model, snapshot, run_dir, cfg, tag="baseline", out_rel="baseline/model.onnx")
    check_onnx(baseline_onnx, sample, len(class_names))
    write_package(onnx_path.parent, cfg, lock, snapshot, split_hash, model_metrics, baseline_metrics, time.time() - started)
    print(f"model-package written: {onnx_path.parent}")
    print(f"baseline macro_f1 {baseline_metrics['macro_f1']:.4f} · model macro_f1 {model_metrics['macro_f1']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
