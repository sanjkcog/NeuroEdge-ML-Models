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


#: A vision demo replays a folder; the device's folder replay has no rate of its own in the lock.
VISION_DEMO_IMAGES_PER_SECOND = 1.0


def _export_vision_demo(dest: str, lock: dict[str, Any], splits: list[str], event_share: float,
                        minutes: float) -> dict[str, Any]:
    """The demo profile for vision: images are the unit of composition (ADR-0031 D-7)."""
    if not os.path.exists(os.path.join(dest, "sim", "manifest.json")):
        raise SimulatorError(["no sim/manifest.json: export the unweighted simulator data first. A demo is an "
                              "addition to it, never a replacement (ADR-0031 D-8)"])
    by_class: dict[str, list[tuple[str, str, str]]] = {}
    for split in splits:
        path = os.path.join(dest, "data", "splits", f"{split}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        for unit in doc.get("units", []):
            for rel in unit.get("files") or []:
                if os.path.isfile(os.path.join(dest, rel)):
                    by_class.setdefault(str(unit.get("label")), []).append((rel, str(unit["unit_id"]), split))
    counts = {c: len(v) for c, v in by_class.items()}
    event = export_sim.event_class(lock, counts)
    nominal = [c for c in by_class if c != event]
    if event is None or not nominal:
        raise SimulatorError([f"the {'/'.join(splits)} split needs images of both the event class and a nominal "
                              f"class for a demo (images by class: {counts})"])
    total = max(2, int(round(minutes * 60 * VISION_DEMO_IMAGES_PER_SECOND)))
    chunk = max(1, total // export_sim.DEMO_CHUNKS)
    n_chunks = max(2, total // chunk)
    n_event = min(n_chunks - 1, max(1, round(event_share * n_chunks)))
    cursor = {c: 0 for c in by_class}
    export_sim.write_demo_gitignore(os.path.join(dest, export_sim.DEMO_DIR))
    out_dir = os.path.join(dest, export_sim.DEMO_DIR, "images")
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    order, labels, repeated, n = [], {}, set(), 0
    nominal_turn = 0
    for is_event in export_sim.interleave(n_chunks, n_event):
        cls = event if is_event else nominal[nominal_turn % len(nominal)]
        nominal_turn += not is_event
        for _ in range(chunk):
            if cursor[cls] >= len(by_class[cls]):
                cursor[cls] = 0
                repeated.add(cls)
            rel, unit, split = by_class[cls][cursor[cls]]
            cursor[cls] += 1
            n += 1
            shutil.copy2(os.path.join(dest, rel), os.path.join(out_dir, f"{n:05d}_{os.path.basename(rel)}"))
            labels[cls] = labels.get(cls, 0) + 1
            order.append({"n": n, "class": cls, "unit": unit, "split": split, "source": rel})
    manifest = {"lock_sha256": lock["lock_sha256"], "use_case_id": lock["use_case_id"], "modality": lock["modality"],
                "vision": lock["vision"], "class_names": lock["class_names"],
                "purpose": export_sim.DEMO_PURPOSE, "caveat": export_sim.DEMO_CAVEAT,
                "files": [{"path": "images", "split": "+".join(splits), "unit": "composed", "images": n,
                           "purpose": export_sim.DEMO_PURPOSE, "labels": labels}],
                "demo": {"event_class": event, "event_share": event_share,
                         "event_share_images": round(labels.get(event, 0) / max(1, n), 3), "minutes": minutes,
                         "composed_from": {"splits": splits, "unit_of_composition": "images",
                                           "images_per_second": VISION_DEMO_IMAGES_PER_SECOND,
                                           "available_images_by_class": counts},
                         "order": order, "repeated_classes": sorted(repeated),
                         "paths": "relative to this manifest"}}
    with open(os.path.join(dest, export_sim.DEMO_DIR, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    return manifest


def run_demo(dest: str, *, event_share: float = 0.7, minutes: float = 5.0,
             splits: list[str] | None = None) -> dict[str, Any]:
    """The demo profile (ADR-0031 D-7): a short replay weighted toward the event class, in ``sim-demo/``.

    Generic because it is defined in the lock's terms: the event class is the non-nominal one, the unit
    of composition is the modality's own. Composed from ``val`` by default -- never from the test split
    unless M10 eval is complete -- and fenced from evidence by ``purpose: demo_only`` (D-8).
    """
    try:
        lock = read_lock(dest)
    except (LockError, OSError) as exc:
        raise SimulatorError(getattr(exc, "problems", [str(exc)])) from exc
    splits = splits or ["val"]
    if "test" in splits and not _eval_complete(dest):
        raise SimulatorError(["a demo draws on the test split only after M10 eval is complete"])
    if not 0 < event_share < 1 or minutes <= 0:
        raise SimulatorError([f"--event-share must be in (0, 1) and --minutes positive; got {event_share}, "
                              f"{minutes}"])
    if lock["modality"] == "timeseries":
        try:
            return export_sim.export_demo(dest, event_share=event_share, minutes=minutes, splits=splits,
                                          eval_stage="test" in splits)
        except export_sim.ExportError as exc:
            raise SimulatorError(exc.problems) from exc
    if lock["modality"] in {"vision", "vision_anomaly"}:
        return _export_vision_demo(dest, lock, splits, event_share, minutes)
    raise SimulatorError([f"no simulator format for modality {lock['modality']!r}, so no demo profile either"])


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
    p.add_argument("--profile", choices=("default", "demo"), default="default",
                   help="demo: a short replay weighted toward the event class, in sim-demo/ (demo_only)")
    p.add_argument("--event-share", type=float, default=0.7, help="demo: share of units from the event class")
    p.add_argument("--minutes", type=float, default=5.0, help="demo: length of the replay")
    p.add_argument("--splits", default="val", help="demo: comma-separated splits to compose from (default val)")
    a = p.parse_args(argv)
    try:
        if a.profile == "demo":
            m = run_demo(a.dest, event_share=a.event_share, minutes=a.minutes,
                         splits=[s.strip() for s in a.splits.split(",") if s.strip()])
            d = m["demo"]
            print(f"demo -> {os.path.join(a.dest, export_sim.DEMO_DIR)} (lock {m['lock_sha256'][:12]}): "
                  f"{d['minutes']} min, event class {d['event_class']!r}, "
                  f"share {d.get('event_share_windows', d.get('event_share_images'))} of "
                  f"{d['composed_from']['unit_of_composition']}")
            print(f"  demo_only: {export_sim.DEMO_CAVEAT}")
            return 0
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
