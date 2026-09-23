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
* ``demo``  -- ``export_demo`` (ADR-0031 D-7): a short replay composed from those same rows, weighted
  toward the event class, in its own ``sim-demo/`` with its own manifest. ``demo_only``: weighting
  the classes changes the class prior, so no rate measured on it is evidence (D-8).

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


# --------------------------------------------------------------------------- the demo profile (ADR-0031 D-7, D-8)

DEMO_DIR = "sim-demo"
DEMO_PURPOSE = "demo_only"
DEMO_CAVEAT = ("The class balance of this replay is deliberately weighted toward the event class, so every rate "
               "measured on it (false-alarm rate, precision, recall) is meaningless as a measurement of the model. "
               "It is a demonstration; the unweighted export in sim/ is the evidence.")
#: About this many alternations over the replay: enough for the score to be seen low, then crossing,
#: more than once, without cutting the stretches so short that a window never fills.
DEMO_CHUNKS = 10


def write_demo_gitignore(folder: str) -> None:
    """The demo's data is regenerable from the split and can be large; its manifest stays tracked."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, ".gitignore")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# The demo replay (ADR-0031 D-7): regenerated from the split by /data-simulator --profile demo.\n"
                     "*.csv\nimages/\n")


def event_class(lock: dict[str, Any], windows_by_class: dict[str, int]) -> str | None:
    """The class the use case exists to catch, in terms the lock carries -- never one use case's name.

    The class that is not ``head.nominal_class``; where several are, or none is declared, the
    minority class by window count among the candidates. None when the data holds no candidate.
    """
    classes = [str(c) for c in lock.get("class_names") or []]
    nominal = (lock.get("head") or {}).get("nominal_class") if isinstance(lock.get("head"), dict) else None
    candidates = [c for c in classes if c != nominal] if nominal in classes else classes
    present = [c for c in candidates if windows_by_class.get(c, 0) > 0]
    if not present:
        return None
    return present[0] if len(present) == 1 else min(present, key=lambda c: (windows_by_class[c], c))


def interleave(n_chunks: int, n_event: int) -> list[bool]:
    """Nominal first, so the score is seen sitting low; then events spread through, not blocked.

    ``True`` is an event stretch. The count is exact: ``n_event`` of ``n_chunks``.
    """
    share = n_event / n_chunks
    order, placed = [False], 0
    for i in range(1, n_chunks):
        need_event, need_nominal = n_event - placed, (n_chunks - n_event) - (i - placed)
        take = need_nominal <= 0 or (need_event > 0 and placed / i < share)
        order.append(take)
        placed += take
    return order


def _windows(rows: int, window: int, stride: int) -> int:
    return 0 if rows < window else (rows - window) // stride + 1


def export_demo(dest: str, *, event_share: float = 0.7, minutes: float = 5.0,
                splits: list[str] | None = None, eval_stage: bool = False) -> dict[str, Any]:
    """Write ``<dest>/sim-demo/demo.csv`` and ``<dest>/sim-demo/manifest.json``: a short replay, composed
    from the same split rows the model saw, weighted toward the event class (ADR-0031 D-7).

    An addition to ``sim/``, never a replacement: it refuses until the unweighted export exists under
    the current lock, and it writes nothing there. Every file is ``purpose: demo_only`` (D-8).
    """
    import pandas as pd

    splits = splits or ["val"]
    if not 0 < event_share < 1:
        raise ExportError([f"--event-share must be between 0 and 1 (exclusive), got {event_share}: a demo "
                           "needs nominal data to show the score sitting low, and events to show it cross"])
    if minutes <= 0:
        raise ExportError([f"--minutes must be positive, got {minutes}"])
    if "test" in splits and not eval_stage:
        raise ExportError(["the test split is exported only by the eval stage (pass --eval-stage there)"])
    try:
        lock = read_lock(dest)
    except LockError as exc:
        raise ExportError(exc.problems) from exc
    unweighted = os.path.join(dest, "sim", "manifest.json")
    if not os.path.exists(unweighted):
        raise ExportError(["no sim/manifest.json: export the unweighted simulator data first. A demo is an "
                           "addition to it, never a replacement (ADR-0031 D-8)"])
    with open(unweighted, encoding="utf-8") as fh:
        if json.load(fh).get("lock_sha256") != lock["lock_sha256"]:
            raise ExportError(["sim/ was exported under a different lock; re-export it before composing a demo"])
    contract_dir = os.path.join(dest, "data", "contract")
    with open(os.path.join(contract_dir, "manifest.json"), encoding="utf-8") as fh:
        contract = json.load(fh)
    if contract.get("lock_sha256") != lock["lock_sha256"]:
        raise ExportError(["data/contract/ was built under a different lock than use_case.lock.json; rebuild it first"])

    ts = lock["timeseries"]
    names = [c["name"] for c in ts["channels"]]
    rate, window, stride = float(ts["sample_rate_hz"]), int(ts["window_samples"]), int(ts["stride_samples"])

    # Contiguous stretches of one class: the split's rows of one unit, cut wherever the label changes.
    stretches: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(glob.glob(os.path.join(contract_dir, "*.parquet"))):
        unit = os.path.splitext(os.path.basename(path))[0]
        frame = pd.read_parquet(path)
        for split in splits:
            part = frame[frame["split"] == split].reset_index(drop=True)
            if part.empty:
                continue
            cut = (part["label"] != part["label"].shift()).cumsum()
            for _, run in part.groupby(cut, sort=False):
                stretches.setdefault(str(run["label"].iloc[0]), []).append(
                    {"unit": unit, "split": split, "frame": run, "rows": len(run)})
    windows_by_class = {c: sum(_windows(s["rows"], window, stride) for s in ss) for c, ss in stretches.items()}
    event = event_class(lock, windows_by_class)
    if event is None:
        raise ExportError([f"the {'/'.join(splits)} split holds no window of a non-nominal class "
                           f"(windows by class: {windows_by_class}); a demo would show nothing happening"])
    nominal = [c for c in stretches if c != event and windows_by_class.get(c, 0) > 0]
    if not nominal:
        raise ExportError([f"the {'/'.join(splits)} split holds no nominal window to show the score sitting low"])

    total = int(round(minutes * 60 * rate))
    longest = {c: max(s["rows"] for s in stretches[c]) for c in [event, *nominal]}
    chunk = min(max(window + 4 * stride, total // DEMO_CHUNKS), min(longest.values()))
    if chunk < window + stride:
        raise ExportError([f"the longest stretch of one class is {min(longest.values())} rows, too short for two "
                           f"windows of {window} (stride {stride}); a device would barely score it"])
    n_chunks = max(2, total // chunk)
    n_event = min(n_chunks - 1, max(1, round(event_share * n_chunks)))

    # Take stretches in turn, each chunk a contiguous run of rows; wrap only when a class runs out.
    cursor = {c: [0, 0] for c in [event, *nominal]}          # [stretch index, row offset]
    repeated: set[str] = set()

    def take(cls: str) -> dict[str, Any]:
        pool = [s for s in stretches[cls] if s["rows"] >= chunk]
        idx, off = cursor[cls]
        if idx >= len(pool):
            idx, off = 0, 0
            repeated.add(cls)
        s, start = pool[idx], off
        piece = s["frame"].iloc[start:start + chunk]
        off = start + chunk
        if off + chunk > s["rows"]:
            idx, off = idx + 1, 0
        cursor[cls] = [idx, off]
        # block_start is the contract's own row key: where in the unit's data this stretch came from.
        origin = int(piece["block_start"].iloc[0]) if "block_start" in piece else start
        return {"class": cls, "unit": s["unit"], "split": s["split"], "block_start": origin,
                "rows": len(piece), "frame": piece}

    nominal_turn = 0
    pieces = []
    for is_event in interleave(n_chunks, n_event):
        if is_event:
            pieces.append(take(event))
        else:
            pieces.append(take(nominal[nominal_turn % len(nominal)]))
            nominal_turn += 1
    body = pd.concat([p["frame"] for p in pieces], ignore_index=True)
    out = pd.DataFrame({"timestamp": _timestamps(len(body), rate)})
    for n in names:
        out[n] = body[n].to_numpy()
    out["label"] = body["label"].to_numpy()

    folder = os.path.join(dest, DEMO_DIR)
    write_demo_gitignore(folder)
    for stale in glob.glob(os.path.join(folder, "*.csv")):
        os.remove(stale)
    out.to_csv(os.path.join(folder, "demo.csv"), index=False, float_format="%.6g")
    per_chunk = _windows(chunk, window, stride)
    composed = {c: per_chunk * sum(1 for p in pieces if p["class"] == c) for c in {p["class"] for p in pieces}}
    first_event = next(i for i, p in enumerate(pieces) if p["class"] == event)
    manifest = {
        "lock_sha256": lock["lock_sha256"],
        "use_case_id": lock["use_case_id"],
        "split_hash": contract.get("split_hash"),
        "sample_rate_hz": rate,
        "feature_order": names,
        "units": {c["name"]: c["unit"] for c in ts["channels"]},
        "definitions": {c["name"]: c["definition"] for c in ts["channels"]},
        "reduce": {c["name"]: c.get("reduce") for c in ts["channels"]},
        "window_samples": window,
        "stride_samples": stride,
        "replay": {"target_fps": rate, "note": "rows are 1/sample_rate_hz apart; the device counts rows"},
        "purpose": DEMO_PURPOSE,
        "caveat": DEMO_CAVEAT,
        "files": [{"path": "demo.csv", "split": "+".join(splits), "unit": "composed", "rows": len(out),
                   "purpose": DEMO_PURPOSE,
                   "labels": {str(k): int(v) for k, v in out["label"].value_counts().items()}}],
        "demo": {
            "event_class": event,
            "event_share": event_share,
            "event_share_windows": round(composed.get(event, 0) / max(1, sum(composed.values())), 3),
            "minutes": minutes,
            "composed_from": {"splits": splits, "unit_of_composition": "windows",
                              "windows_by_class": composed, "rows_per_stretch": chunk,
                              "available_windows_by_class": windows_by_class},
            "first_event_at_s": round(first_event * chunk / rate, 1),
            "order": [{"class": p["class"], "unit": p["unit"], "split": p["split"],
                       "block_start": p["block_start"], "rows": p["rows"]} for p in pieces],
            "repeated_classes": sorted(repeated),
            "paths": "relative to this manifest",
        },
    }
    with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as fh:
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
