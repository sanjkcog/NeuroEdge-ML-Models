"""M12 `data-simulator`: simulator data from the same split data the model saw (NeuroEdge-Web ADR-0008).

Generic across modalities; the lock decides the format:

* ``timeseries``           -> CSVs at the contract rate (``export_sim``), read from ``data/contract/``.
* ``vision`` / ``vision_anomaly`` -> one image folder per split, copied from the files each split
  lists (``units[].files`` in ``data/splits/*.json``), for the device's folder/clip replay.
* anything else            -> refused, never guessed.

The test split is exported only after M10 ``eval`` is complete in ``run.json``, and only when the
caller asks for on-device acceptance. Each file's purpose is recorded in ``sim/manifest.json``.

    python -m agentforge.src.ml_contract.data_simulator --dest <model folder> [--acceptance]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from typing import Any

from . import export_sim
from .lock import LockError, read_lock


class SimulatorError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _eval_complete(dest: str) -> bool:
    path = os.path.join(dest, "run.json")
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as fh:
        run = json.load(fh)
    return (run.get("stages", {}).get("eval", {}) or {}).get("status") == "complete"


def _export_vision(dest: str, lock: dict[str, Any], splits: list[str]) -> dict[str, Any]:
    files, problems = [], []
    for split in splits:
        path = os.path.join(dest, "data", "splits", f"{split}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        for unit in doc.get("units", []):
            listed = unit.get("files")
            if not listed:
                problems.append(f"{split}/{unit.get('unit_id')}: the split lists no files to replay")
                continue
            out_dir = os.path.join(dest, "sim", split, str(unit["unit_id"]))
            os.makedirs(out_dir, exist_ok=True)
            for rel in listed:
                src = os.path.join(dest, rel)
                if not os.path.isfile(src):
                    problems.append(f"{split}/{unit['unit_id']}: {rel} does not exist")
                    continue
                shutil.copy2(src, os.path.join(out_dir, os.path.basename(rel)))
            files.append({"path": f"sim/{split}/{unit['unit_id']}", "split": split, "unit": unit["unit_id"],
                          "images": len(listed), "purpose": export_sim.PURPOSE[split],
                          "label": unit.get("label")})
    if problems:
        raise SimulatorError(problems)
    manifest = {"lock_sha256": lock["lock_sha256"], "use_case_id": lock["use_case_id"],
                "modality": lock["modality"], "vision": lock["vision"], "class_names": lock["class_names"],
                "files": files}
    os.makedirs(os.path.join(dest, "sim"), exist_ok=True)
    with open(os.path.join(dest, "sim", "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    return manifest


def run(dest: str, acceptance: bool = False) -> dict[str, Any]:
    """Export simulator data for ``dest``. Returns the manifest written to ``sim/manifest.json``."""
    try:
        lock = read_lock(dest)
    except (LockError, OSError) as exc:
        raise SimulatorError(getattr(exc, "problems", [str(exc)])) from exc
    splits = ["train", "val"]
    if acceptance:
        if not _eval_complete(dest):
            raise SimulatorError(["test data is exported for acceptance only after M10 eval is complete"])
        splits.append("test")
    if lock["modality"] == "timeseries":
        try:
            return export_sim.export(dest, splits, eval_stage=acceptance)
        except export_sim.ExportError as exc:
            raise SimulatorError(exc.problems) from exc
    if lock["modality"] in {"vision", "vision_anomaly"}:
        return _export_vision(dest, lock, splits)
    raise SimulatorError([f"no simulator format for modality {lock['modality']!r}"])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dest", required=True)
    p.add_argument("--acceptance", action="store_true",
                   help="also export the test split, for final on-device acceptance (after M10 eval)")
    a = p.parse_args(argv)
    try:
        m = run(a.dest, a.acceptance)
        print(f"{len(m['files'])} simulator item(s) -> {os.path.join(a.dest, 'sim')} (lock {m['lock_sha256'][:12]})")
        return 0
    except SimulatorError as exc:
        print("refused:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
