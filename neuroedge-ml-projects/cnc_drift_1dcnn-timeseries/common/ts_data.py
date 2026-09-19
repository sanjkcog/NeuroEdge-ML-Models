# -*- coding: utf-8 -*-
"""Shared, leakage-safe data loading for cnc_drift_1dcnn-timeseries (M8).

Everything here is driven by three files that are the binding contract for this build and are
NEVER re-derived:

  - ``use_case.lock.json``      channel order, window, stride, rate, head, class order.
  - ``data/splits/*.json``      which units belong to train / val / test, and (for IM-01R, the one
                                 unit that legitimately spans all three splits) the CYCLE bounds of
                                 each segment.
  - ``data/contract/manifest.json``  the authoritative per-unit / per-split row counts and labels
                                 the M4 contract build produced. Used to *verify* whatever the
                                 loader reads from the parquet files, so a wrong guess about the
                                 parquet's internal column layout fails loudly instead of silently
                                 mis-aligning windows.

`train.py` reads `train.json` + `val.json` only. `eval.py` is the only script that may open
`test.json`, and only when the caller passes ``--split .../test.json`` explicitly.

Windows are built from contiguous row blocks that already lie inside one unit's split bounds (the
M4 contract build trimmed the boundary gaps out), so a window can never straddle a split boundary
by construction. The loader still asserts the row counts it reads for each unit/split against
``data/contract/manifest.json`` before windowing, which is the "assert at load time" requirement
from ``data/label-manifest.md`` requirement #2.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------------------------
# Paths (relative to this file's parent, i.e. the use-case dest folder). config.yaml may override.
# --------------------------------------------------------------------------------------------
DEST_ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = DEST_ROOT / "use_case.lock.json"
SPLITS_DIR = DEST_ROOT / "data" / "splits"
CONTRACT_DIR = DEST_ROOT / "data" / "contract"
CONTRACT_MANIFEST_PATH = CONTRACT_DIR / "manifest.json"
SYNTHETIC_DIR = DEST_ROOT / "data" / "synthetic"
SYNTHETIC_MANIFEST_PATH = SYNTHETIC_DIR / "manifest.json"

# Candidate column names for the row-order / tick column, tried in this order. The contract
# build's own docs (`data/contract_sources.json`) key the controller stream on `CYCLE`; this list
# is defensive against a renamed column in the built parquet.
_TICK_CANDIDATES = ("CYCLE", "cycle", "tick", "block_start", "row_id")
_SPLIT_COL_CANDIDATES = ("split", "SPLIT")
_LABEL_COL_CANDIDATES = ("label", "LABEL")
_SOURCE_COL_CANDIDATES = ("source", "SOURCE")


def load_lock(lock_path: Path = LOCK_PATH) -> dict:
    lock = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    # lock_sha256 = sha256 of the canonical JSON (sorted keys, compact separators) of every OTHER
    # field -- verified empirically against this project's use_case.lock.json.
    payload = {k: v for k, v in lock.items() if k != "lock_sha256"}
    computed = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if computed != lock["lock_sha256"]:
        raise RuntimeError(
            f"use_case.lock.json content does not hash to its own recorded lock_sha256 "
            f"({computed} != {lock['lock_sha256']}). Refusing to build against a lock that may "
            f"have been edited after it was recorded."
        )
    return lock


def load_split(name: str, splits_dir: Path = SPLITS_DIR) -> dict:
    if name not in ("train", "val", "test"):
        raise ValueError(f"split name must be one of train/val/test, got {name!r}")
    return json.loads((Path(splits_dir) / f"{name}.json").read_text(encoding="utf-8"))


def load_contract_manifest(path: Path = CONTRACT_MANIFEST_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def assert_window_fits_gap(window_samples: int, sample_rate_hz: float, gap_seconds: float = 10.0) -> None:
    """Binding requirement #1 (`data/label-manifest.md`): the window must fit inside the smallest
    time-split gap, or a window could cross a split boundary. Checked once, at config load time.
    """
    window_seconds = window_samples / sample_rate_hz
    if window_seconds > gap_seconds:
        raise ValueError(
            f"window {window_samples} samples at {sample_rate_hz} Hz = {window_seconds:.2f}s "
            f"exceeds the {gap_seconds:.2f}s split-boundary gap (`data/label-manifest.md`). "
            "This window would be able to cross a split boundary; refusing to build it."
        )


def _read_unit_parquet(unit_id: str, contract_dir: Path) -> pd.DataFrame:
    path = Path(contract_dir) / f"{unit_id}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Did you copy data/contract/*.parquet from the dest folder onto "
            "this machine? These blobs are gitignored and regenerated from data/raw + the lock, "
            "so `git clone` alone does not bring them."
        )
    return pd.read_parquet(path)


def _find_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _unit_split_rows(
    df: pd.DataFrame,
    unit_id: str,
    split_name: str,
    split_entry: dict,
    contract_manifest: dict,
) -> pd.DataFrame:
    """Return the rows of ``df`` (one unit's contract parquet) that belong to ``split_name``,
    verified against ``data/contract/manifest.json``'s authoritative row count for this
    unit/split. Handles both an explicit `split` column and, if absent, a segment defined by
    CYCLE bounds in `data/splits/*.json` (only IM-01R has more than one split in its file).
    """
    split_col = _find_col(df, _SPLIT_COL_CANDIDATES)
    tick_col = _find_col(df, _TICK_CANDIDATES)
    segment = split_entry.get("segment")

    if split_col is not None:
        rows = df[df[split_col].astype(str).str.lower() == split_name.lower()].copy()
    elif segment is not None:
        if tick_col is None:
            raise RuntimeError(
                f"{unit_id}.parquet has a split-boundary segment recorded in data/splits/"
                f"{split_name}.json but no split column and no recognised tick column "
                f"(tried {_TICK_CANDIDATES}); cannot locate the {split_name} rows safely."
            )
        rows = df[
            (df[tick_col] >= segment["cycle_start"]) & (df[tick_col] < segment["cycle_end_exclusive"])
        ].copy()
    else:
        # Single-split unit: the whole file belongs to this split.
        rows = df.copy()

    if tick_col is not None:
        rows = rows.sort_values(tick_col, kind="stable").reset_index(drop=True)

    expected = contract_manifest.get("units", {}).get(unit_id, {}).get(split_name)
    if expected is None:
        # Missing from the manifest is NOT "nothing to check" -- it means the loader cannot
        # verify it read the right rows at all. Silently skipping this check is exactly the
        # failure mode requirement #2 exists to prevent (code review HIGH #A).
        raise RuntimeError(
            f"data/contract/manifest.json has no recorded row count for {unit_id}/{split_name}. "
            "Cannot verify the loader read the right rows for this unit/split -- refusing to "
            "window unverified data rather than silently skipping the check "
            "(label-manifest.md binding requirement #2, 'assert at load time')."
        )
    if len(rows) != expected:
        raise RuntimeError(
            f"Row-count mismatch for {unit_id}/{split_name}: read {len(rows)} rows, "
            f"data/contract/manifest.json says {expected}. The parquet's column layout could not "
            "be resolved unambiguously; refusing to window mis-aligned data (label-manifest.md "
            "binding requirement #2, 'assert at load time')."
        )
    return rows


@dataclass
class Windows:
    x: np.ndarray  # [n, n_features, window] float32
    y: np.ndarray  # [n] int64, 0 = normal, 1 = tool_wear
    unit_ids: np.ndarray  # [n] str
    source: np.ndarray  # [n] str, "real" | "synthetic"


def _make_windows_for_block(
    values: np.ndarray, label_idx: int, unit_id: str, source: str, window: int, stride: int
) -> Windows:
    n_rows = values.shape[0]
    if n_rows < window:
        return Windows(
            x=np.empty((0, values.shape[1], window), dtype="float32"),
            y=np.empty((0,), dtype="int64"),
            unit_ids=np.empty((0,), dtype=object),
            source=np.empty((0,), dtype=object),
        )
    n_windows = (n_rows - window) // stride + 1
    x = np.empty((n_windows, values.shape[1], window), dtype="float32")
    for i in range(n_windows):
        start = i * stride
        x[i] = values[start : start + window].T  # -> [features, window]
    y = np.full((n_windows,), label_idx, dtype="int64")
    unit_ids = np.full((n_windows,), unit_id, dtype=object)
    src = np.full((n_windows,), source, dtype=object)
    return Windows(x=x, y=y, unit_ids=unit_ids, source=src)


def assemble_real_split(
    split_name: str,
    lock: dict,
    contract_dir: Path = CONTRACT_DIR,
    splits_dir: Path = SPLITS_DIR,
) -> Windows:
    """Build all windows for one split ("train" | "val" | "test") from `data/contract/`.

    `train.py` calls this with "train" and "val" only. `eval.py` is the only caller allowed to
    pass "test", and only via an explicit `--split .../test.json` argument.
    """
    split_json = load_split(split_name, splits_dir)
    contract_manifest = load_contract_manifest(contract_dir / "manifest.json")
    feature_order = [c["name"] for c in lock["timeseries"]["channels"]]
    class_names = lock["class_names"]
    window = lock["timeseries"]["window_samples"]
    stride = lock["timeseries"]["stride_samples"]

    blocks = []
    for unit_entry in split_json["units"]:
        unit_id = unit_entry["unit_id"]
        label = unit_entry["label"]
        label_idx = class_names.index(label)
        df = _read_unit_parquet(unit_id, contract_dir)
        rows = _unit_split_rows(df, unit_id, split_name, unit_entry, contract_manifest)
        missing = [c for c in feature_order if c not in rows.columns]
        if missing:
            raise KeyError(f"{unit_id}.parquet is missing channel column(s) {missing}; expected {feature_order}")
        values = rows[feature_order].to_numpy(dtype="float32")
        if np.isnan(values).any():
            raise ValueError(f"{unit_id}/{split_name} has NaNs in {feature_order} after loading")
        blocks.append(_make_windows_for_block(values, label_idx, unit_id, "real", window, stride))

    return Windows(
        x=np.concatenate([b.x for b in blocks]),
        y=np.concatenate([b.y for b in blocks]),
        unit_ids=np.concatenate([b.unit_ids for b in blocks]),
        source=np.concatenate([b.source for b in blocks]),
    )


def assemble_synthetic(
    lock: dict,
    cap_fraction: float,
    real_train_counts: dict[str, int],
    seed: int,
    synthetic_dir: Path = SYNTHETIC_DIR,
) -> Windows:
    """Build synthetic train windows, subsampled uniformly across all 30 units per class down to
    ``cap_fraction`` of the real train window count for that class (never used for val/test —
    `data/synth-review.md` hard rule 6, `use_case.lock.json` split design).
    """
    manifest = json.loads((synthetic_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest["lock_sha256"] != lock["lock_sha256"]:
        raise RuntimeError("data/synthetic/manifest.json was built against a different lock; refusing to mix it in.")
    feature_order = [c["name"] for c in lock["timeseries"]["channels"]]
    class_names = lock["class_names"]
    window = lock["timeseries"]["window_samples"]
    stride = lock["timeseries"]["stride_samples"]
    rng = np.random.default_rng(seed)

    per_class_blocks: dict[str, list[Windows]] = {c: [] for c in class_names}
    for unit in manifest["units"]:
        unit_id, label = unit["unit_id"], unit["label"]
        path = synthetic_dir / f"{unit_id}.parquet"
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Regenerate with "
                f"`python data/synth/gen_synth.py --dest . --seed {manifest['seed']} --n-worn 30 --n-normal 30`"
            )
        df = pd.read_parquet(path)
        split_col = _find_col(df, _SPLIT_COL_CANDIDATES)
        if split_col is not None:
            df = df[df[split_col].astype(str).str.lower() == "train"]
        values = df[feature_order].to_numpy(dtype="float32")
        label_idx = class_names.index(label)
        per_class_blocks[label].append(
            _make_windows_for_block(values, label_idx, unit_id, "synthetic", window, stride)
        )

    out_blocks = []
    for cls_name, blocks in per_class_blocks.items():
        if not blocks:
            continue
        x = np.concatenate([b.x for b in blocks])
        y = np.concatenate([b.y for b in blocks])
        u = np.concatenate([b.unit_ids for b in blocks])
        s = np.concatenate([b.source for b in blocks])
        # floor, not round: data/synth-review.md's approved cap is floor(0.5 * real windows per
        # class) -- e.g. floor(0.5 * 4491) = 2245, not round(2245.5) = 2246.
        cap = int(np.floor(cap_fraction * real_train_counts.get(cls_name, 0)))
        cap = min(cap, len(x))
        idx = rng.permutation(len(x))[:cap]
        out_blocks.append(Windows(x=x[idx], y=y[idx], unit_ids=u[idx], source=s[idx]))

    return Windows(
        x=np.concatenate([b.x for b in out_blocks]),
        y=np.concatenate([b.y for b in out_blocks]),
        unit_ids=np.concatenate([b.unit_ids for b in out_blocks]),
        source=np.concatenate([b.source for b in out_blocks]),
    )


def concat_windows(*parts: Windows) -> Windows:
    parts = [p for p in parts if len(p.y) > 0]
    return Windows(
        x=np.concatenate([p.x for p in parts]),
        y=np.concatenate([p.y for p in parts]),
        unit_ids=np.concatenate([p.unit_ids for p in parts]),
        source=np.concatenate([p.source for p in parts]),
    )


def fit_normalization(x_train: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Global, per-channel mean/std over TRAIN windows only (never per-window — the wear signal
    IS a window-to-window variance change; per-window standardisation would erase it, see
    `model_proposed.md` §Synthetic guard #3)."""
    mean = x_train.mean(axis=(0, 2)).astype("float32")
    std = x_train.std(axis=(0, 2)).astype("float32")
    std[std < 1e-6] = 1.0
    return mean, std


def augment_train_windows(
    x: np.ndarray,
    source: np.ndarray,
    channel_std: np.ndarray,
    seed: int,
    jitter_std_frac: tuple[float, float],
    gain_range: tuple[float, float],
    time_shift_max: int,
) -> np.ndarray:
    """Train-only, REAL windows only augmentation (`model_proposed.md` §Augmentation). Synthetic
    windows, val and test are never augmented."""
    rng = np.random.default_rng(seed)
    x = x.copy()
    real_idx = np.flatnonzero(source == "real")
    n_features, window = x.shape[1], x.shape[2]
    for i in real_idx:
        jitter_std = rng.uniform(*jitter_std_frac, size=n_features) * channel_std
        jitter = rng.normal(0.0, 1.0, size=(n_features, window)) * jitter_std[:, None]
        gain = rng.uniform(*gain_range, size=(n_features, 1))
        x[i] = x[i] * gain + jitter
        shift = int(rng.integers(-time_shift_max, time_shift_max + 1))
        if shift > 0:
            x[i, :, shift:] = x[i, :, :-shift]
            x[i, :, :shift] = x[i, :, :1]
        elif shift < 0:
            x[i, :, :shift] = x[i, :, -shift:]
            x[i, :, shift:] = x[i, :, -1:]
    return x


def filter_by_unit(windows: Windows, unit_ids: list[str]) -> Windows:
    keep = np.isin(windows.unit_ids, list(unit_ids))
    return Windows(x=windows.x[keep], y=windows.y[keep], unit_ids=windows.unit_ids[keep], source=windows.source[keep])


def exclude_unit(windows: Windows, unit_ids: list[str]) -> Windows:
    drop = np.isin(windows.unit_ids, list(unit_ids))
    return Windows(x=windows.x[~drop], y=windows.y[~drop], unit_ids=windows.unit_ids[~drop], source=windows.source[~drop])


def split_hash_of(*split_names: str, splits_dir: Path = SPLITS_DIR) -> str:
    payload = [load_split(name, splits_dir)["units"] for name in split_names]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
