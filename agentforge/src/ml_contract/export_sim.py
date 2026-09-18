"""Export simulator CSVs from the contract dataset, with a manifest the device checks (ADR-0008 M4, D6).

The CSVs are the training data row for row, because they are read from ``data/contract/`` and
nowhere else. Header = ``timestamp`` + the lock's channel names in lock order + ``label``; rows are
``1 / sample_rate_hz`` apart. ``sim/manifest.json`` records the lock hash, so a device can refuse
to replay a CSV built for a different model.

Which split may be exported, for what:

* ``train`` -- smoke / plumbing only; the model has seen it.
* ``val``   -- device debugging, threshold and latency checks, device-vs-eval.py parity.
* ``test``  -- final on-device acceptance only. Written only when ``--eval-stage`` is passed,
  because only the eval stage may read the test split.

    python -m agentforge.src.ml_contract.export_sim --dest <model folder> [--splits train,val]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from .lock import LockError, read_lock

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)   # same convention as the device's demo fixture

#: What each split's simulator data may be used for (ADR-0008). Recorded per file in the manifest.
PURPOSE = {"train": "smoke_only", "val": "debug_and_parity", "test": "acceptance_only"}


class ExportError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _timestamps(n: int, rate: float) -> list[str]:
    step = timedelta(seconds=1.0 / rate)
    return [(_EPOCH + i * step).isoformat(timespec="milliseconds").replace("+00:00", "Z") for i in range(n)]


def export(dest: str, splits: list[str], eval_stage: bool = False) -> dict[str, Any]:
    """Write ``<dest>/sim/<split>/<unit>.csv`` and ``<dest>/sim/manifest.json``. Returns the manifest."""
    import pandas as pd

    if "test" in splits and not eval_stage:
        raise ExportError(["the test split is exported only by the eval stage (pass --eval-stage there)"])
    try:
        lock = read_lock(dest)
    except LockError as exc:
        raise ExportError(exc.problems) from exc
    contract_dir = os.path.join(dest, "data", "contract")
    with open(os.path.join(contract_dir, "manifest.json"), encoding="utf-8") as fh:
        contract = json.load(fh)
    if contract.get("lock_sha256") != lock["lock_sha256"]:
        raise ExportError([
            "data/contract/ was built under a different lock than use_case.lock.json; rebuild it first"
        ])

    ts = lock["timeseries"]
    names = [c["name"] for c in ts["channels"]]
    rate = float(ts["sample_rate_hz"])
    files = []
    for path in sorted(glob.glob(os.path.join(contract_dir, "*.parquet"))):
        unit = os.path.splitext(os.path.basename(path))[0]
        frame = pd.read_parquet(path)
        multi = frame["split"].nunique() > 1
        for split in splits:
            part = frame[frame["split"] == split]
            if part.empty:
                continue
            if len(part) <= int(ts["window_samples"]):
                print(f"{unit} [{split}]: skipped, {len(part)} rows <= window {ts['window_samples']} "
                      "(the device would never score it)", file=sys.stderr)
                continue
            out = pd.DataFrame({"timestamp": _timestamps(len(part), rate)})
            for n in names:
                out[n] = part[n].to_numpy()
            out["label"] = part["label"].to_numpy()
            name = f"{unit}_{split}-segment.csv" if multi else f"{unit}.csv"
            rel = os.path.join("sim", split, name)
            os.makedirs(os.path.join(dest, "sim", split), exist_ok=True)
            out.to_csv(os.path.join(dest, rel), index=False, float_format="%.6g")
            files.append({"path": rel.replace(os.sep, "/"), "split": split, "unit": unit, "rows": len(out),
                          "purpose": PURPOSE[split],
                          "labels": {str(k): int(v) for k, v in out["label"].value_counts().items()}})

    manifest = {
        "lock_sha256": lock["lock_sha256"],
        "use_case_id": lock["use_case_id"],
        "split_hash": contract.get("split_hash"),
        "sample_rate_hz": rate,
        "feature_order": names,
        "units": {c["name"]: c["unit"] for c in ts["channels"]},
        "definitions": {c["name"]: c["definition"] for c in ts["channels"]},
        "reduce": {c["name"]: c.get("reduce") for c in ts["channels"]},
        "window_samples": ts["window_samples"],
        "stride_samples": ts["stride_samples"],
        "replay": {"target_fps": rate, "note": "rows are 1/sample_rate_hz apart; the device counts rows"},
        "files": files,
    }
    os.makedirs(os.path.join(dest, "sim"), exist_ok=True)
    with open(os.path.join(dest, "sim", "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    return manifest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dest", required=True)
    p.add_argument("--splits", default="train,val", help="comma-separated; test needs --eval-stage")
    p.add_argument("--eval-stage", action="store_true", help="only the M10 eval stage passes this")
    a = p.parse_args(argv)
    try:
        m = export(a.dest, [s.strip() for s in a.splits.split(",") if s.strip()], a.eval_stage)
        print(f"{len(m['files'])} CSVs -> {os.path.join(a.dest, 'sim')} (lock {m['lock_sha256'][:12]})")
        return 0
    except ExportError as exc:
        print("refused:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
