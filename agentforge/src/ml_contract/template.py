"""M8 templates that are stored as files, not re-derived each run (ADR-0028 D-6).

The time-series build is written by ``ml-modeler`` from the ``model-codegen`` skill. A Hugging Face fine-tune has
more fixed parts (offline loading, the optimum export, folding normalisation into the graph), so it is a stored
template: ``write`` copies it into ``<dest>/<arch>/`` and fills ``config.yaml`` from the use-case lock and from
``model/base/`` as ``/model-fetch`` wrote it. ``ml-modeler`` then adapts the recipe; it does not rewrite the contract.

    python -m agentforge.src.ml_contract.template list
    python -m agentforge.src.ml_contract.template write --dest <model folder> --arch <Arch>
                                                        --template transformers-classification [--force]

``transformers-classification``: an image classifier (ADR-0023's family) with a ``class_logits`` head, runner
``portal-package``. The ``tao`` template is not built: it waits for the device (ADR-0028 O-1).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit import ONNX_OPSET
from .lock import LockError, read_lock
from .model_fetch import BASE_DIR, CARD_JSON, LOADER_FILE

TEMPLATES_DIR = Path(__file__).with_name("templates")
RECORD_FILE = "template.json"
RECORD_SCHEMA = "model-template/1"
# name -> (folder, the loader it needs, the runner it is built for, the output schema it writes)
TEMPLATES: dict[str, tuple[str, str, str, str]] = {
    "transformers-classification": ("transformers_cls", "transformers", "portal-package", "class_logits"),
}
_RENDERED = ("config.yaml", "RUN_ON_GPU.md")
_ARCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class TemplateError(ValueError):
    """The template cannot be written for this run. Each problem is listed."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _base_model(root: Path, loader_needed: str) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    base = root / BASE_DIR
    if not (base / LOADER_FILE).is_file() or not (base / CARD_JSON).is_file():
        return {}, {}, [f"{BASE_DIR}/{LOADER_FILE} or {CARD_JSON} is missing: run /model-fetch first"]
    loader = json.loads((base / LOADER_FILE).read_text(encoding="utf-8"))
    card = json.loads((base / CARD_JSON).read_text(encoding="utf-8"))
    problems = []
    if loader.get("loader") != loader_needed:
        problems.append(f"the fetched base model's loader is {loader.get('loader')!r}; this template needs "
                        f"{loader_needed!r}")
    if card.get("licence", {}).get("gate_outcome") in ("pending", "rejected"):
        problems.append(f"the base model's licence gate is {card['licence']['gate_outcome']}: M8 does not build on it")
    return loader, card, problems


def _contract_problems(lock: dict[str, Any], schema: str) -> list[str]:
    problems = []
    if lock.get("modality") != "vision":
        problems.append(f"the lock's modality is {lock.get('modality')!r}; this template trains an image classifier")
    if (lock.get("head") or {}).get("shape") != "multiclass":
        problems.append("the lock's head is not multiclass: a classification head needs one logit per class")
    wanted = (lock.get("vision") or {}).get("output_schema")
    if wanted not in (None, schema):
        problems.append(f"the use case asks for output_schema {wanted!r}; this template writes {schema!r}, and the "
                        "device picks its post-processor by that key (ADR-0028 D-7)")
    return problems


def _values(lock: dict[str, Any], loader: dict[str, Any], card: dict[str, Any], arch: str) -> dict[str, Any]:
    vision = lock["vision"]
    return {
        "ARCH": arch, "MODEL_FOLDER": "/".join([".."] * len(Path(arch).parts)), "USE_CASE_ID": lock["use_case_id"],
        "LOCK_SHA256": lock["lock_sha256"], "CLASS_NAMES": lock["class_names"], "HEIGHT": vision["input"]["height"],
        "WIDTH": vision["input"]["width"], "COLOR_ORDER": vision["input"]["color_order"],
        "PREPROCESS": vision["preprocess"], "MODEL_ID": loader["model_id"], "CATALOGUE_ID": card.get("catalogue_id"),
        "WEIGHTS_SHA256": loader["weights_sha256"], "LICENCE": card["licence"].get("spdx"),
        "DISTRIBUTION": card.get("distribution"), "OPSET": ONNX_OPSET,
    }


def _render(text: str, values: dict[str, Any], *, as_json: bool) -> str:
    """Fill ``{{KEY}}``. In YAML every value is written as JSON, which YAML reads as the same value."""
    short = {"LOCK_SHORT": str(values["LOCK_SHA256"])[:12], "WEIGHTS_SHORT": str(values["WEIGHTS_SHA256"])[:12]}
    for key, value in {**values, **short}.items():
        text = text.replace("{{" + key + "}}", json.dumps(value) if as_json else str(value))
    left = re.findall(r"\{\{[A-Z_]+\}\}", text)
    if left:
        raise TemplateError([f"the template has placeholders nothing fills: {sorted(set(left))}"])
    return text


def write(dest: str, arch: str, template: str, *, force: bool = False) -> dict[str, Any]:
    """Copy the template into ``<dest>/<arch>/`` and fill it from the lock and the fetched base model."""
    if template not in TEMPLATES:
        raise TemplateError([f"unknown template {template!r}, expected one of {sorted(TEMPLATES)}"])
    folder, loader_needed, runner, schema = TEMPLATES[template]
    root, source = Path(dest), TEMPLATES_DIR / folder
    if not _ARCH.match(arch):
        raise TemplateError([f"arch {arch!r} is not a plain folder name"])
    try:
        lock = read_lock(str(root))
    except (OSError, LockError) as exc:
        raise TemplateError([f"no valid use-case lock in {root}: {exc}"]) from exc
    loader, card, problems = _base_model(root, loader_needed)
    problems += _contract_problems(lock, schema)
    target = root / arch
    if target.is_symlink() or (target.exists() and not target.resolve().is_relative_to(root.resolve())):
        problems.append(f"{target} is a link or leads outside the model folder")
    elif target.is_dir() and any(target.iterdir()) and not force:
        problems.append(f"{target} is not empty: pass --force to overwrite the template's files in it")
    if problems:
        raise TemplateError(problems)

    values = _values(lock, loader, card, arch)
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for path in sorted(p for p in source.iterdir() if p.is_file()):
        text = path.read_text(encoding="utf-8")
        if path.name in _RENDERED:
            text = _render(text, values, as_json=path.suffix == ".yaml")
        (target / path.name).write_text(text, encoding="utf-8", newline="\n")
        written.append(path.name)
    record = {"schema": RECORD_SCHEMA, "template": template, "runner": runner, "output_schema": schema,
              "loader": loader_needed, "opset": ONNX_OPSET, "lock_sha256": lock["lock_sha256"],
              "weights_sha256": loader["weights_sha256"], "catalogue_id": card.get("catalogue_id"),
              "executed": False, "generated_at": datetime.now(timezone.utc).isoformat(), "files": written}
    (target / RECORD_FILE).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="template", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the stored templates, with the loader and the runner each is built for")
    w = sub.add_parser("write", help="copy a template into <dest>/<arch>/ and fill it from the lock and model/base/")
    w.add_argument("--dest", required=True)
    w.add_argument("--arch", required=True, help="the architecture folder, e.g. ViT")
    w.add_argument("--template", required=True, choices=sorted(TEMPLATES))
    w.add_argument("--force", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "list":
        for name, (_, loader, runner, schema) in sorted(TEMPLATES.items()):
            print(f"{name}: loader {loader} · runner {runner} · output_schema {schema}")
        return 0
    try:
        record = write(a.dest, a.arch, a.template, force=a.force)
    except TemplateError as exc:
        print("refused:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    print(f"{a.arch}/: {', '.join(record['files'])} (+ {RECORD_FILE})")
    print(f"runner {record['runner']} · output_schema {record['output_schema']} · opset {record['opset']}. "
          "These scripts have never been executed: read RUN_ON_GPU.md before you hand them over.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
