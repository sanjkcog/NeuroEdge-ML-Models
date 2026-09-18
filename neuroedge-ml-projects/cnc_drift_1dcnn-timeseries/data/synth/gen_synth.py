#!/usr/bin/env python3
"""gen_synth.py — M6 signal-mode synthetic data for cnc_drift_1dcnn-timeseries.

Generates synthetic ``normal`` and ``tool_wear`` runs of the IM-01R program.
Real train data has plenty of *windows* of tool_wear (3,588, from A01/A02/A05)
but only **one** pure-wear unit (A05) and two wear+blowhole units (A01, A02).
The scarce resource is independent worn *units*, not windows, so this
generator's job is diversity of wear realisations (severity, onset ramp,
per-run gain/baseline/noise), not more rows of the same three units.

Approach (see ``data/synthetic-recipe.md`` for the full write-up):
  1. Base signal = block-bootstrap resample of the REAL IM-01R train-split
     head segment (spindle_load, x_axis_error, vibration_rms only). This
     keeps real local autocorrelation / machining structure per block while
     giving each synthetic run a distinct, non-identical-to-real sequence.
  2. Per-run domain randomization: gain, baseline offset and extra noise
     floor per channel, each drawn from a small range around 1.0 / 0.
  3. tool_wear runs additionally get a parametric wear delta — a per-channel
     std-ratio and mean-shift plus a spindle/vibration correlation nudge —
     fitted to the real A01/A02/A05 vs IM-01R-train-head comparison, with a
     within-run severity ramp/step from a partial value to 1.0 (progression),
     applied as an internal magnitude ramp, NOT a label change (see below).
  4. Label rule: **per-unit, single label** (matches the real data: a worn
     run is one unit, one label, for its whole duration — label-manifest.md
     "Taxonomy"). Progression is modeled as an internal severity ramp/step
     that changes wear MAGNITUDE within a tool_wear run, never its label.
     Matched normal runs use identical base/gain/baseline/noise
     randomization with the wear delta fixed at zero, so the two classes
     differ only in the wear delta, not in base signal character.

Train-split-only inputs (never opens splits/val.json, splits/test.json, or
any val/test unit's parquet):
  - data/contract/IM-01R.parquet, filtered to split == "train" (verified to
    match splits/train.json's IM-01R bounds [3210956, 3568011) exactly:
    block_start range [3211000, 3567950] at a 50-tick step)
  - data/contract/IM-01R-A01.parquet, IM-01R-A02.parquet, IM-01R-A05.parquet
    (each entirely a train unit per data/contract/manifest.json — no split
    column filtering needed, but the column is checked and asserted anyway)

Usage:
    python gen_synth.py --seed 20260918 --n-worn 30 --n-normal 30 \\
        --dest <dest-root> [--out-dir <dest>/data/synthetic]

Output: one parquet per synthetic unit at <out-dir>/SYN-<label>-NNN.parquet,
columns [block_start, split, label, spindle_load, x_axis_error,
vibration_rms, unit_id, source] — the three sensor channels in lock order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

CHANNELS = ["spindle_load", "x_axis_error", "vibration_rms"]

# Forbidden inputs: this script must never touch these, by name or by path.
FORBIDDEN_SPLIT_FILES = ("val.json", "test.json")
FORBIDDEN_UNIT_NAMES = (
    "IM-01F", "IMP-09", "IMP-12", "IM-01R-A04", "IMP-05", "TF-02", "IM-01R-A03",
)

# --- Wear signature, fitted from real train data -----------------------
# IM-01R train head (normal, 7140 rows) vs A01/A02 (wear+blowhole) and A05
# (pure wear), all train-split contract rows. See synthetic-recipe.md for
# the numbers this was measured from.
WEAR_STD_RATIO_RANGE: dict[str, tuple[float, float]] = {
    # spindle_load std ratio worn/normal measured 1.035 (A01) .. 1.095 (A05)
    "spindle_load": (1.03, 1.10),
    # x_axis_error std ratio measured 1.283 (A05) .. 1.294 (A01/A02) — the
    # most consistent signature across all three worn units.
    "x_axis_error": (1.20, 1.32),
    # vibration_rms std ratio measured 0.805 (A05) .. 0.832 (A02) — a
    # consistent DECREASE, present in all three worn units.
    "vibration_rms": (0.78, 0.85),
}
# Additive mean shift, in real units, bounded by the observed deltas.
WEAR_MEAN_SHIFT_RANGE: dict[str, tuple[float, float]] = {
    "spindle_load": (-0.06, 0.13),       # Nm
    "x_axis_error": (-0.0002, 0.0002),   # um — negligible in the real data
    "vibration_rms": (-0.31, 0.04),      # g
}
# spindle_load <-> vibration_rms correlation nudge; measured +0.120 (A05),
# roughly flat/slightly negative for A01/A02 (blowhole layered on top).
# Sampled per worn run so most runs get a small or no nudge, consistent
# with it being observed clearly in only 1 of 3 real worn units.
CORR_BOOST_RANGE = (0.0, 0.12)

DOMAIN_RANDOMIZATION = {
    "gain_range": (0.95, 1.05),          # multiplicative, per channel
    "baseline_frac_range": (-0.05, 0.05),  # of real channel std, additive
    "noise_frac_range": (0.0, 0.10),     # of real channel std, extra iid noise
    "block_len_range": (150, 400),       # rows per bootstrap block
    "run_len_range": (11000, 13000),     # rows per synthetic run
}
SEVERITY_START_RANGE = (0.3, 0.7)
RAMP_FRAC_RANGE = (0.05, 0.4)
# Clip synthetic values to the real train (normal + worn) envelope plus a 5%
# margin, so per-run noise/gain randomization cannot extrapolate far beyond
# what the real train units show (rule 3). vibration_rms is an RMS quantity
# and is additionally floored at 0 (never negative in the real data either).
CLIP_MARGIN = 0.05


def _clip_bounds(stats: dict[str, Any]) -> dict[str, tuple[float, float]]:
    bounds = {}
    for c in CHANNELS:
        lo = min(stats["normal_range"][c][0], stats["worn_range"][c][0])
        hi = max(stats["normal_range"][c][1], stats["worn_range"][c][1])
        span = hi - lo
        lo_c, hi_c = lo - CLIP_MARGIN * span, hi + CLIP_MARGIN * span
        if c == "vibration_rms":
            lo_c = max(lo_c, 0.0)
        bounds[c] = (lo_c, hi_c)
    return bounds


def _load_train_only(dest: Path) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Load ONLY train-split rows. Refuses to open val/test split files or
    val/test-only unit parquet files, and asserts the IM-01R filter matches
    the recorded train bounds."""
    contract_dir = dest / "data" / "contract"
    splits_dir = dest / "data" / "splits"

    # FORBIDDEN_SPLIT_FILES (val.json, test.json) are never referenced below —
    # this script opens splits/train.json only.
    train_manifest = json.loads((splits_dir / "train.json").read_text(encoding="utf-8"))
    im01r_seg = next(u for u in train_manifest["units"] if u["unit_id"] == "IM-01R")["segment"]
    bounds = (im01r_seg["cycle_start"], im01r_seg["cycle_end_exclusive"])

    im01r = pd.read_parquet(contract_dir / "IM-01R.parquet")
    im01r_train = im01r[im01r["split"] == "train"].reset_index(drop=True)
    # Assert the split column matches the recorded train bounds (belt + braces
    # for hard rule 1 — filter by bounds even though the contract file already
    # carries a split column).
    lo, hi = im01r_train["block_start"].min(), im01r_train["block_start"].max()
    assert bounds[0] <= lo and hi < bounds[1], (
        f"IM-01R train-split rows [{lo},{hi}] fall outside recorded train bounds {bounds}"
    )
    assert im01r_train["label"].eq("normal").all(), "IM-01R train segment must be all-normal"

    worn_units = {}
    for unit_id in ("IM-01R-A01", "IM-01R-A02", "IM-01R-A05"):
        assert unit_id not in FORBIDDEN_UNIT_NAMES
        df = pd.read_parquet(contract_dir / f"{unit_id}.parquet")
        # These three are entirely train units (data/contract/manifest.json);
        # assert it rather than assume it.
        assert set(df["split"].unique()) == {"train"}, f"{unit_id} is not train-only"
        assert df["label"].eq("tool_wear").all()
        worn_units[unit_id] = df.reset_index(drop=True)

    return im01r_train, worn_units


def _fit_stats(im01r_train: pd.DataFrame, worn_units: dict[str, pd.DataFrame]) -> dict[str, Any]:
    normal_stats = {c: {"mean": im01r_train[c].mean(), "std": im01r_train[c].std()} for c in CHANNELS}
    worn_stats = {
        uid: {c: {"mean": df[c].mean(), "std": df[c].std()} for c in CHANNELS}
        for uid, df in worn_units.items()
    }
    normal_range = {c: (im01r_train[c].min(), im01r_train[c].max()) for c in CHANNELS}
    worn_range = {c: (
        min(df[c].min() for df in worn_units.values()),
        max(df[c].max() for df in worn_units.values()),
    ) for c in CHANNELS}
    corr_normal = im01r_train[CHANNELS].corr()
    return {
        "normal": normal_stats,
        "worn": worn_stats,
        "normal_range": normal_range,
        "worn_range": worn_range,
        "corr_normal_spindle_vibration": corr_normal.loc["spindle_load", "vibration_rms"],
    }


STARTUP_TRANSIENT_THRESHOLD = -10.0  # Nm, spindle_load
STARTUP_TRANSIENT_PAD = 6            # rows of padding either side of the spike


def _find_startup_transient(pool: pd.DataFrame) -> tuple[int, int]:
    """Every real IM-01R-family train run (the normal head AND A01/A02/A05)
    has a single spindle spin-up transient a few dozen rows after its own
    start (spindle_load briefly to about -84 Nm, vs a steady-state floor
    around -1..-4 Nm) — a real, once-per-run machine-startup artifact, not
    noise. Locate it in the pool so it can be placed once per synthetic run
    (see `_gen_run`) instead of left to block-bootstrap luck, which under-
    represents it about half the time (see synthetic-recipe.md self-check)."""
    hits = pool.index[pool["spindle_load"] < STARTUP_TRANSIENT_THRESHOLD]
    assert len(hits) > 0, "expected a startup transient in the real train pool"
    lo = max(0, hits.min() - STARTUP_TRANSIENT_PAD)
    hi = min(len(pool), hits.max() + STARTUP_TRANSIENT_PAD + 1)
    return lo, hi


def _block_bootstrap(pool: pd.DataFrame, n_rows: int, block_len: int, rng: np.random.Generator) -> pd.DataFrame:
    """Concatenate contiguous blocks sampled (with replacement, random start
    offset) from `pool` until n_rows are produced. Preserves real local
    autocorrelation within each block; block seams are simple concatenation
    (no crossfade) — see known-limits in the recipe."""
    n_pool = len(pool)
    chunks: list[pd.DataFrame] = []
    got = 0
    while got < n_rows:
        length = min(block_len, n_rows - got)
        start = int(rng.integers(0, max(1, n_pool - length)))
        chunks.append(pool.iloc[start:start + length][CHANNELS].reset_index(drop=True))
        got += length
    return pd.concat(chunks, ignore_index=True)


def _severity_curve(n_rows: int, severity_start: float, ramp_frac: float, shape: str) -> np.ndarray:
    ramp_rows = max(1, int(n_rows * ramp_frac))
    sev = np.ones(n_rows)
    if shape == "ramp":
        sev[:ramp_rows] = np.linspace(severity_start, 1.0, ramp_rows)
    else:  # "step"
        sev[:ramp_rows] = severity_start
    return sev


def _gen_run(
    unit_id: str,
    label: str,
    pool: pd.DataFrame,
    stats: dict[str, Any],
    rng: np.random.Generator,
    transient: pd.DataFrame,
    steady_pool: pd.DataFrame,
) -> pd.DataFrame:
    n_rows = int(rng.integers(*DOMAIN_RANDOMIZATION["run_len_range"]))
    block_len = int(rng.integers(*DOMAIN_RANDOMIZATION["block_len_range"]))
    # Place the real once-per-run spindle spin-up transient at the start of
    # every synthetic run (see _find_startup_transient), then fill the rest
    # by block-bootstrap from the steady-state pool (transient excluded, so
    # it is not accidentally resampled a second time).
    n_bootstrap = max(0, n_rows - len(transient))
    base = pd.concat(
        [transient[CHANNELS].reset_index(drop=True),
         _block_bootstrap(steady_pool, n_bootstrap, block_len, rng)],
        ignore_index=True,
    )
    n_rows = len(base)

    # Per-run domain randomization (same distributions for normal & tool_wear
    # matched pairs, so the two classes differ only in the wear delta below).
    gains = {c: rng.uniform(*DOMAIN_RANDOMIZATION["gain_range"]) for c in CHANNELS}
    baselines = {
        c: rng.uniform(*DOMAIN_RANDOMIZATION["baseline_frac_range"]) * stats["normal"][c]["std"]
        for c in CHANNELS
    }
    noise_stds = {
        c: rng.uniform(*DOMAIN_RANDOMIZATION["noise_frac_range"]) * stats["normal"][c]["std"]
        for c in CHANNELS
    }

    out = pd.DataFrame(index=range(n_rows))
    for c in CHANNELS:
        mu = stats["normal"][c]["mean"]
        deviation = (base[c].to_numpy() - mu) * gains[c]
        out[c] = mu + deviation + baselines[c] + rng.normal(0.0, max(noise_stds[c], 1e-9), n_rows)

    if label == "tool_wear":
        severity_start = rng.uniform(*SEVERITY_START_RANGE)
        ramp_frac = rng.uniform(*RAMP_FRAC_RANGE)
        shape = "ramp" if rng.random() < 0.5 else "step"
        severity = _severity_curve(n_rows, severity_start, ramp_frac, shape)

        std_ratio = {c: rng.uniform(*WEAR_STD_RATIO_RANGE[c]) for c in CHANNELS}
        mean_shift = {c: rng.uniform(*WEAR_MEAN_SHIFT_RANGE[c]) for c in CHANNELS}
        corr_boost = rng.uniform(*CORR_BOOST_RANGE)

        shared = rng.normal(0.0, 1.0, n_rows)  # common-mode term for the corr nudge
        for c in CHANNELS:
            mu = stats["normal"][c]["mean"]
            deviation = out[c].to_numpy() - mu
            scaled = deviation * (1.0 + severity * (std_ratio[c] - 1.0))
            out[c] = mu + scaled + severity * mean_shift[c]
        if corr_boost > 0:
            shared_scaled = shared * corr_boost
            out["spindle_load"] = out["spindle_load"] + severity * shared_scaled * stats["normal"]["spindle_load"]["std"] * 0.3
            out["vibration_rms"] = out["vibration_rms"] + severity * shared_scaled * stats["normal"]["vibration_rms"]["std"] * 0.3

        recipe_params = {
            "n_rows": n_rows, "block_len": block_len, "gains": gains, "baselines": baselines,
            "noise_stds": noise_stds, "severity_start": severity_start, "ramp_frac": ramp_frac,
            "shape": shape, "std_ratio": std_ratio, "mean_shift": mean_shift, "corr_boost": corr_boost,
        }
    else:
        recipe_params = {
            "n_rows": n_rows, "block_len": block_len, "gains": gains, "baselines": baselines,
            "noise_stds": noise_stds,
        }

    clip_bounds = _clip_bounds(stats)
    clipped_frac = {}
    for c in CHANNELS:
        lo, hi = clip_bounds[c]
        raw = out[c].to_numpy()
        clipped_frac[c] = float(((raw < lo) | (raw > hi)).mean())
        out[c] = np.clip(raw, lo, hi)
    recipe_params["clip_bounds"] = clip_bounds
    recipe_params["clipped_fraction"] = clipped_frac

    out.insert(0, "block_start", np.arange(n_rows) * 50)
    out.insert(1, "split", "train")
    out.insert(2, "label", label)
    out["unit_id"] = unit_id
    out["source"] = "synthetic"
    out = out[["block_start", "split", "label", *CHANNELS, "unit_id", "source"]]
    return out, recipe_params


def generate(dest: Path, seed: int, n_worn: int, n_normal: int, out_dir: Path) -> dict[str, Any]:
    im01r_train, worn_units = _load_train_only(dest)
    stats = _fit_stats(im01r_train, worn_units)
    pool = im01r_train
    t_lo, t_hi = _find_startup_transient(pool)
    transient = pool.iloc[t_lo:t_hi]
    steady_pool = pd.concat([pool.iloc[:t_lo], pool.iloc[t_hi:]], ignore_index=True)

    rng = np.random.default_rng(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "seed": seed,
        "startup_transient_rows": [int(t_lo), int(t_hi)],
        "units": [],
    }

    for i in range(n_worn):
        uid = f"SYN-tool_wear-{i + 1:03d}"
        df, params = _gen_run(uid, "tool_wear", pool, stats, rng, transient, steady_pool)
        df.to_parquet(out_dir / f"{uid}.parquet", index=False)
        manifest["units"].append({"unit_id": uid, "label": "tool_wear", "rows": len(df), "params": params})

    for i in range(n_normal):
        uid = f"SYN-normal-{i + 1:03d}"
        df, params = _gen_run(uid, "normal", pool, stats, rng, transient, steady_pool)
        df.to_parquet(out_dir / f"{uid}.parquet", index=False)
        manifest["units"].append({"unit_id": uid, "label": "normal", "rows": len(df), "params": params})

    manifest["fitted_stats"] = {
        k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items()})
        for k, v in stats.items()
        if k not in ("normal", "worn")  # keep manifest small; full stats in synthetic-recipe.md
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=float), encoding="utf-8")
    return manifest


def _hash_dir(out_dir: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(out_dir.glob("SYN-*.parquet")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dest", type=Path, required=True, help="project root, e.g. .../cnc_drift_1dcnn-timeseries")
    p.add_argument("--out-dir", type=Path, default=None, help="default: <dest>/data/synthetic")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--n-worn", type=int, default=30)
    p.add_argument("--n-normal", type=int, default=30)
    p.add_argument("--self-check", action="store_true", help="rerun with the same seed and hash-compare")
    args = p.parse_args(argv)

    out_dir = args.out_dir or (args.dest / "data" / "synthetic")
    manifest = generate(args.dest, args.seed, args.n_worn, args.n_normal, out_dir)
    print(f"[gen_synth] wrote {len(manifest['units'])} unit(s) to {out_dir}")

    if args.self_check:
        h1 = _hash_dir(out_dir)
        check_dir = out_dir.parent / "synthetic_selfcheck_tmp"
        generate(args.dest, args.seed, args.n_worn, args.n_normal, check_dir)
        h2 = _hash_dir(check_dir)
        print(f"[gen_synth] self-check: first_hash={h1} second_hash={h2} match={h1 == h2}")
        import shutil
        shutil.rmtree(check_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
