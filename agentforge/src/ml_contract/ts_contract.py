"""Build the time-series contract dataset: the one place data is resampled and units applied (ADR-0008 L-3).

Everything a model folder produces afterwards -- training windows, simulator CSVs, the trainer
upload package -- is read from ``<dest>/data/contract/``, so model, simulator and device input
agree by construction. Nothing downstream may convert a unit or resample again.

Two inputs, deliberately separate:

* ``use_case.lock.json`` (from the use case): WHAT the device receives -- channel names, order,
  units, rate, window.
* ``data/contract_sources.json`` (from the dataset): HOW each channel is produced from this
  dataset's raw columns. It must cover exactly the lock's channels, in the lock's units.

    {"tick_hz": 500, "key": "CYCLE",
     "inputs": {"controller": {"template": "data/raw/Dataset/*/{unit}/processed_data/{unit}_hfdata.csv",
                               "key": "CYCLE"},
                "sensor":     {"template": "data/interim/{unit}_sensor.parquet", "key": "tick"}},
     "channels": {"spindle_load":  {"input": "controller", "column": "TORQUE|6", "agg": "mean", "unit": "Nm"},
                  "x_axis_error":  {"input": "controller", "column": "CTRL_DIFF|1", "agg": "mean",
                                    "scale": 1000, "unit": "um"},
                  "vibration_rms": {"input": "sensor", "column": "vibration_rms", "agg": "rms",
                                    "weight": "n_samples", "unit": "g"}}}

Aggregations over one contract timestep (``tick_hz / sample_rate_hz`` source rows):

* ``mean``  -- the mean; it is also the anti-alias filter. Point-sampling would alias.
* ``rms``   -- ``sqrt(sum(w * x**2) / sum(w))`` of per-row RMS values, weighted by ``weight``:
               exactly the RMS of all underlying samples.
* ``point`` -- the first row of the block, for a feed that genuinely sends instantaneous values.

A block is kept only when all of its source rows exist and it lies wholly inside one split's
bounds. Nothing is filled or interpolated.

    python -m agentforge.src.ml_contract.ts_contract --dest <model folder>
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
from typing import Any

import numpy as np

from .lock import LockError, normalise_unit, read_lock

_AGGS = {"mean", "rms", "point"}


class ContractError(ValueError):
    """The data cannot be brought to the contract honestly. Each problem is listed."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def load_units(dest: str) -> dict[str, list[dict[str, Any]]]:
    """``{unit_id: [{split, segment|None, label}, ...]}`` from ``data/splits/*.json``."""
    out: dict[str, list[dict[str, Any]]] = {}
    for split in ("train", "val", "test"):
        path = os.path.join(dest, "data", "splits", f"{split}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        for u in doc.get("units", []):
            out.setdefault(u["unit_id"], []).append(
                {"split": split, "segment": u.get("segment"), "label": u.get("label")}
            )
    return out


def split_hash(dest: str) -> str | None:
    path = os.path.join(dest, "data", "splits", "train.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("split_hash")


def check_split_gaps(units: dict[str, list[dict[str, Any]]], window_ticks: int) -> list[str]:
    """Every gap between time-split segments of one unit must hold at least one window (ADR-0008 M3).

    A window longer than the gap straddles train and test: the model sees the start of a test
    stretch while training. That is leakage no metric reveals afterwards.
    """
    problems = []
    for uid, entries in units.items():
        segs = sorted((e["segment"]["cycle_start"], e["segment"]["cycle_end_exclusive"], e["split"])
                      for e in entries if e.get("segment"))
        for (s0, e0, sp0), (s1, _e1, sp1) in zip(segs, segs[1:]):
            gap = s1 - e0
            if gap < window_ticks:
                problems.append(
                    f"{uid}: gap between its {sp0} and {sp1} segments is {gap} ticks, shorter than one "
                    f"window ({window_ticks} ticks). Re-split with a gap >= the window"
                )
    return problems


def aggregate_blocks(frame, key: str, block_ticks: int, specs: dict[str, dict[str, Any]]):
    """Reduce source rows to contract timesteps. Returns a DataFrame keyed by ``block_start``.

    ``frame`` holds one row per source tick, with ``key`` and every column the specs name.
    Only complete blocks (``block_ticks`` consecutive keys, one each) survive.
    """
    import pandas as pd

    keys = frame[key].to_numpy(np.int64)
    block = keys // block_ticks
    counts = pd.Series(block).value_counts()
    complete = counts[counts == block_ticks].index
    keep = np.isin(block, complete.to_numpy())
    f = frame.loc[keep].copy()
    f["_block"] = block[keep]
    f = f.sort_values(key)
    grouped = f.groupby("_block", sort=True)
    out = pd.DataFrame({"block_start": np.asarray(grouped.size().index, dtype=np.int64) * block_ticks})
    for name, spec in specs.items():
        col = spec["column"]
        scale = float(spec.get("scale", 1.0))
        if spec["agg"] == "mean":
            vals = grouped[col].mean().to_numpy(float)
        elif spec["agg"] == "point":
            vals = grouped[col].first().to_numpy(float)
        else:  # rms, weighted by the per-row sample count
            w = f[spec.get("weight")] if spec.get("weight") else pd.Series(1.0, index=f.index)
            num = (w * f[col].astype(float) ** 2).groupby(f["_block"]).sum()
            den = w.groupby(f["_block"]).sum()
            vals = np.sqrt((num / den).to_numpy(float))
        out[name] = vals * scale
    return out


def _validate_sources(lock: dict[str, Any], sources: dict[str, Any]) -> list[str]:
    problems = []
    ts = lock.get("timeseries") or {}
    want = [c["name"] for c in ts.get("channels", [])]
    have = list(sources.get("channels", {}))
    if sorted(want) != sorted(have):
        problems.append(f"contract_sources channels {have} must be exactly the lock's channels {want}")
    for ch in ts.get("channels", []):
        spec = sources.get("channels", {}).get(ch["name"])
        if not spec:
            continue
        if normalise_unit(spec.get("unit")) != normalise_unit(ch.get("unit")):
            problems.append(f"{ch['name']}: sources produce {spec.get('unit')!r} but the lock says {ch.get('unit')!r}")
        if spec.get("agg") not in _AGGS:
            problems.append(f"{ch['name']}: agg must be one of {sorted(_AGGS)}")
        if spec.get("input") not in sources.get("inputs", {}):
            problems.append(f"{ch['name']}: input {spec.get('input')!r} is not declared under inputs")
    tick_hz = float(sources.get("tick_hz") or 0)
    rate = float(ts.get("sample_rate_hz") or 0)
    if tick_hz <= 0 or rate <= 0 or abs(tick_hz / rate - round(tick_hz / rate)) > 1e-9:
        problems.append(f"tick_hz {tick_hz} must be a whole multiple of the lock's sample_rate_hz {rate}")
    return problems


def _read_input(dest: str, spec: dict[str, Any], unit: str, columns: list[str]):
    import pandas as pd

    pattern = os.path.join(dest, spec["template"].format(unit=unit))
    matches = sorted(glob.glob(pattern))
    if len(matches) != 1:
        raise ContractError([f"{unit}: expected exactly one file for {pattern}, found {len(matches)}"])
    path = matches[0]
    cols = [spec["key"], *columns]
    if path.endswith(".parquet"):
        df = pd.read_parquet(path, columns=cols)
    else:
        df = pd.read_csv(path, usecols=cols)
    return df.rename(columns={spec["key"]: "_key"}), path


def build_unit(dest: str, lock: dict[str, Any], sources: dict[str, Any], unit: str,
               entries: list[dict[str, Any]]):
    """One unit's contract rows: timesteps with their split and label, channels in lock order."""
    import pandas as pd

    ts = lock["timeseries"]
    block_ticks = int(round(float(sources["tick_hz"]) / float(ts["sample_rate_hz"])))
    by_input: dict[str, list[str]] = {}
    for name, spec in sources["channels"].items():
        cols = by_input.setdefault(spec["input"], [])
        for c in (spec["column"], spec.get("weight")):
            if c and c not in cols:
                cols.append(c)
    joined = None
    for inp, cols in by_input.items():
        df, _ = _read_input(dest, sources["inputs"][inp], unit, cols)
        joined = df if joined is None else joined.merge(df, on="_key", how="inner")
    specs = {c["name"]: sources["channels"][c["name"]] for c in ts["channels"]}
    blocks = aggregate_blocks(joined, "_key", block_ticks, specs)

    parts = []
    for e in entries:
        if e.get("segment"):
            lo, hi = e["segment"]["cycle_start"], e["segment"]["cycle_end_exclusive"]
            inside = (blocks["block_start"] >= lo) & (blocks["block_start"] + block_ticks <= hi)
            part = blocks.loc[inside].copy()
        else:
            part = blocks.copy()
        part.insert(1, "split", e["split"])
        part.insert(2, "label", e["label"])
        parts.append(part)
    out = pd.concat(parts, ignore_index=True).sort_values("block_start").reset_index(drop=True)
    return out[["block_start", "split", "label", *[c["name"] for c in ts["channels"]]]]


def build(dest: str, only_units: list[str] | None = None) -> dict[str, Any]:
    """Build ``<dest>/data/contract/`` for every unit in the splits. Returns the manifest written."""
    try:
        lock = read_lock(dest)
    except LockError as exc:
        raise ContractError(exc.problems) from exc
    if lock.get("modality") != "timeseries":
        raise ContractError([f"lock modality is {lock.get('modality')!r}; this builder is for timeseries"])
    src_path = os.path.join(dest, "data", "contract_sources.json")
    with open(src_path, encoding="utf-8") as fh:
        sources = json.load(fh)
    problems = _validate_sources(lock, sources)
    ts = lock["timeseries"]
    units = load_units(dest)
    if not units:
        problems.append("no data/splits/*.json: split the data before building the contract dataset")
    if not problems:
        block_ticks = int(round(float(sources["tick_hz"]) / float(ts["sample_rate_hz"])))
        problems += check_split_gaps(units, int(ts["window_samples"]) * block_ticks)
    if problems:
        raise ContractError(problems)

    out_dir = os.path.join(dest, "data", "contract")
    os.makedirs(out_dir, exist_ok=True)
    rows: dict[str, dict[str, int]] = {}
    for unit, entries in sorted(units.items()):
        if only_units and unit not in only_units:
            continue
        frame = build_unit(dest, lock, sources, unit, entries)
        frame.to_parquet(os.path.join(out_dir, f"{unit}.parquet"), index=False)
        rows[unit] = {str(k): int(v) for k, v in frame.groupby("split").size().items()}
        short = [s for s, n in rows[unit].items() if n < int(ts["window_samples"])]
        if short:
            print(f"{unit}: WARNING split(s) {short} hold fewer timesteps than one window", file=sys.stderr)
        print(f"{unit}: {len(frame)} timesteps {rows[unit]}")

    with open(src_path, "rb") as fh:
        sources_sha = hashlib.sha256(fh.read()).hexdigest()
    manifest = {
        "lock_sha256": lock["lock_sha256"],
        "split_hash": split_hash(dest),
        "sources_sha256": sources_sha,
        "sample_rate_hz": ts["sample_rate_hz"],
        "window_samples": ts["window_samples"],
        "stride_samples": ts["stride_samples"],
        "channels": ts["channels"],
        "units": rows,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    return manifest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--dest", required=True, help="the model folder (holds use_case.lock.json)")
    p.add_argument("--units", help="comma-separated unit ids to (re)build; default all")
    a = p.parse_args(argv)
    try:
        build(a.dest, [u.strip() for u in a.units.split(",")] if a.units else None)
        return 0
    except ContractError as exc:
        print("refused:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
