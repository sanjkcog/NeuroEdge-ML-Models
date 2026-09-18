"""Decode a DAQ `.mat` timetable, align it to the controller clock, write per-tick features.

The file-handling half of `clock_align`. Three things here are easy to get wrong:

* **MATLAB `timetable` files are MCOS objects.** `scipy.io.loadmat` returns an opaque handle,
  and `pymatreader` returns only the object metadata (`_TypeSystem`, `_Class`,
  `_ObjectMetadata`) with no signal arrays. Neither fails loudly. `mat-io` (import name
  `matio`) decodes the object into a pandas DataFrame, for MAT v5 and v7.3 alike.
* **The decoded time index can be truncated.** On the KIT files `mat-io` returns
  `timedelta64[s]`, so a 10 kHz recording collapses to one index value per second. Time is
  rebuilt from the sample number and the stated rate, and the index is discarded.
* **The anchor comes from the controller's block log, not from a guess.** The dwell block
  (`G04 F2` on KIT) and the block after it give both the anchor tick and the dwell length the
  sync gap is checked against.

CLI (defaults are the KIT CNC reference values -- override every one for another rig). Run it in
its own environment -- mat-io needs numpy>=2.2, which the voice stack forbids on Python < 3.13:

    uv run --no-project --with-requirements agentforge/src/requirements-sensor.txt python -m ...

    python -m agentforge.src.sensor_align.align --mat T.mat --events T_hfblockevent.csv --out T.parquet

    python -m agentforge.src.sensor_align.align --root data/raw/Dataset \\
        --mat-glob "*/*/raw_data/*.mat" \\
        --events-template "{mat_dir}/../processed_data/{trial}_hfblockevent.csv" \\
        --out-template "data/interim/{trial}_sensor.parquet"
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from dataclasses import asdict, dataclass, field

import numpy as np

from .clock_align import AlignmentError, ClockMap, fit_clock_map, rms_per_tick


@dataclass(frozen=True)
class RigConfig:
    """What must be known about the rig. Defaults: KIT CNC milling (DOI 10.35097/hvvwn1kfwf7qt48z)."""

    sensor_hz: float = 10_000.0
    tick_hz: float = 500.0
    ticks_per_half_period: int = 8
    sync_col: str = "Sync_Signal"
    channels: tuple[str, ...] = (
        "xAcceleration", "yAcceleration", "zAcceleration", "xForce", "yForce", "zForce",
    )
    magnitudes: dict[str, tuple[str, ...]] = field(default_factory=lambda: {
        "vibration": ("xAcceleration", "yAcceleration", "zAcceleration"),
        "force": ("xForce", "yForce", "zForce"),
    })
    anchor_pattern: str = r"^G04\b"
    event_text_col: str = "GCode"
    event_counter_col: str = "HFProbeCounter"
    min_gap_s: float = 1.0


def load_timetable(path: str, sensor_hz: float, variable: str | None = None):
    """Load a MATLAB timetable as a DataFrame with a rebuilt `t_s` column (seconds from sample 0)."""
    try:
        import matio  # mat-io
    except ImportError as exc:  # pragma: no cover - exercised only without the dependency
        raise ImportError(
            "reading MATLAB timetable (.mat MCOS) files needs `mat-io`: pip install mat-io"
        ) from exc
    data = matio.load_from_mat(path)
    names = [k for k in data if not k.startswith("__")]
    name = variable or (names[0] if len(names) == 1 else None)
    if name is None:
        raise ValueError(f"{path}: several variables {names}; pass `variable`")
    frame = data[name]
    if not hasattr(frame, "columns"):
        raise ValueError(f"{path}: variable {name!r} decoded to {type(frame).__name__}, not a table")
    frame = frame.reset_index(drop=True)
    frame["t_s"] = np.arange(len(frame)) / sensor_hz
    return frame


def anchor_from_events(events, cfg: RigConfig) -> tuple[int, float]:
    """(anchor_tick, logged_dwell_s): the counter of the block after the dwell, and the dwell length."""
    text = events[cfg.event_text_col].astype(str)
    hits = np.flatnonzero(text.str.contains(cfg.anchor_pattern, regex=True).to_numpy())
    if hits.size == 0:
        raise AlignmentError(f"no block matching {cfg.anchor_pattern!r} in the event log")
    i = int(hits[0])
    if i + 1 >= len(events):
        raise AlignmentError("the dwell is the last logged block -- nothing marks its end")
    start = int(events[cfg.event_counter_col].iloc[i])
    end = int(events[cfg.event_counter_col].iloc[i + 1])
    return end, (end - start) / cfg.tick_hz


def align_trial(
    mat_path: str,
    events_path: str,
    cfg: RigConfig = RigConfig(),
    centre_ticks: tuple[int, int] | None = None,
):
    """Return (features DataFrame keyed by controller tick, diagnostics dict) for one recording.

    ``centre_ticks`` = ``[start, end)`` restricts the samples each channel's mean is taken
    from. 🔴 Pass the TRAIN segment's range for any recording whose ticks are split across
    train/val/test: a mean over the whole recording is a statistic fitted on test data.
    """
    import pandas as pd

    frame = load_timetable(mat_path, cfg.sensor_hz)
    missing = [c for c in (cfg.sync_col, *cfg.channels) if c not in frame.columns]
    if missing:
        raise AlignmentError(f"{mat_path}: missing columns {missing}; has {list(frame.columns)}")
    events = pd.read_csv(events_path)
    anchor_tick, dwell_s = anchor_from_events(events, cfg)

    cmap: ClockMap = fit_clock_map(
        frame[cfg.sync_col].to_numpy(),
        sensor_hz=cfg.sensor_hz, tick_hz=cfg.tick_hz,
        ticks_per_half_period=cfg.ticks_per_half_period,
        anchor_tick=anchor_tick, min_gap_s=cfg.min_gap_s, expected_gap_s=dwell_s,
    )
    ticks = cmap.ticks(np.arange(len(frame)))
    min_samples = int(np.ceil(0.5 * cmap.nominal_samples_per_tick))

    # Remove each channel's mean first: an accelerometer's DC offset (and a force platform's
    # preload) is not vibration, and it would dominate an RMS. The mean comes from the whole
    # recording unless `centre_ticks` confines it (see the docstring).
    if centre_ticks is None:
        centre_mask = np.ones(len(frame), dtype=bool)
    else:
        centre_mask = (ticks >= centre_ticks[0]) & (ticks < centre_ticks[1])
        if not centre_mask.any():
            raise AlignmentError(f"{mat_path}: centre_ticks {list(centre_ticks)} select no samples")
    means = {c: float(np.nanmean(frame[c].to_numpy(float)[centre_mask])) for c in cfg.channels}
    centred = {c: frame[c].to_numpy(float) - means[c] for c in cfg.channels}
    columns: dict[str, np.ndarray] = {}
    tick_index = None
    series = {f"{c}_rms": centred[c] for c in cfg.channels}
    for name, parts in cfg.magnitudes.items():
        series[f"{name}_rms"] = np.sqrt(sum(centred[p] ** 2 for p in parts))
    for col, values in series.items():
        t, rms, n = rms_per_tick(values, ticks, min_samples)
        if tick_index is None:
            tick_index, columns["n_samples"] = t, n
        elif not np.array_equal(t, tick_index):
            # rms_per_tick keeps ticks by sample count alone, so this cannot happen; if it
            # ever does, a column would be bound to the wrong ticks -- refuse, don't write it.
            raise AlignmentError(f"{mat_path}: column {col} produced a different tick set")
        columns[col] = rms
    out = pd.DataFrame({"tick": tick_index, **columns})

    diagnostics = {
        "mat": os.path.basename(mat_path),
        "events": os.path.basename(events_path),
        "sensor_rows": int(len(frame)),
        "sensor_duration_s": round(len(frame) / cfg.sensor_hz, 3),
        "anchor_tick": anchor_tick,
        "anchor_sample": round(cmap.anchor_sample, 2),
        "logged_dwell_s": round(dwell_s, 4),
        "sync_gap_s": round(cmap.gap_samples / cfg.sensor_hz, 4),
        "drift_ppm": round(cmap.drift_ppm, 2),
        "drift_over_run_ms": round(abs(cmap.drift_ppm) * 1e-6 * len(frame) / cfg.sensor_hz * 1000, 2),
        "edge_residual_max_ms": round(cmap.residual_max_samples / cfg.sensor_hz * 1000, 3),
        "sync_edges_used": cmap.edges_used,
        "glitch_edges_dropped": cmap.glitch_edges_dropped,
        "trailing_sync_edges_ignored": cmap.trailing_edges_ignored,
        "trailing_s_on_fitted_rate": round(cmap.trailing_edges_ignored * cfg.ticks_per_half_period / cfg.tick_hz, 2),
        "ticks": [int(out["tick"].iloc[0]), int(out["tick"].iloc[-1])] if len(out) else None,
        "rows_out": int(len(out)),
        "centre_ticks": list(centre_ticks) if centre_ticks else "whole recording",
        "channel_means": {c: round(v, 6) for c, v in means.items()},
        "config": asdict(cfg),
    }
    return out, diagnostics


def _write(frame, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if path.endswith(".parquet"):
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--mat", help="one DAQ .mat file")
    p.add_argument("--events", help="its controller block log (CSV)")
    p.add_argument("--out", help="output .parquet or .csv for --mat")
    p.add_argument("--root", help="batch: directory the globs and templates resolve against")
    p.add_argument("--mat-glob", help="batch: glob under --root for the .mat files")
    p.add_argument("--events-template", help="batch: events path; {mat_dir} {trial} available")
    p.add_argument("--out-template", help="batch: output path; {trial} available (relative to cwd)")
    p.add_argument("--diagnostics", help="write every trial's diagnostics to this JSON file")
    p.add_argument("--centre-ranges", help="JSON file {trial: [start_tick, end_tick]}: take that trial's "
                   "channel means from those ticks only (its train segment)")
    cfg0 = RigConfig()
    p.add_argument("--sensor-hz", type=float, default=cfg0.sensor_hz)
    p.add_argument("--tick-hz", type=float, default=cfg0.tick_hz)
    p.add_argument("--ticks-per-half-period", type=int, default=cfg0.ticks_per_half_period)
    p.add_argument("--sync-col", default=cfg0.sync_col)
    p.add_argument("--anchor-pattern", default=cfg0.anchor_pattern)
    a = p.parse_args(argv)
    cfg = RigConfig(sensor_hz=a.sensor_hz, tick_hz=a.tick_hz,
                    ticks_per_half_period=a.ticks_per_half_period,
                    sync_col=a.sync_col, anchor_pattern=a.anchor_pattern)

    if a.mat:
        jobs = [(a.mat, a.events, a.out)]
    elif a.root and a.mat_glob and a.events_template and a.out_template:
        jobs = []
        for mat in sorted(glob.glob(os.path.join(a.root, a.mat_glob))):
            trial = os.path.splitext(os.path.basename(mat))[0]
            fields = {"mat_dir": os.path.dirname(mat), "trial": trial}
            jobs.append((mat, os.path.normpath(a.events_template.format(**fields)),
                         a.out_template.format(**fields)))
        if not jobs:
            p.error(f"no files match {a.mat_glob!r} under {a.root!r}")
    else:
        p.error("give --mat/--events/--out, or --root/--mat-glob/--events-template/--out-template")

    centre_ranges: dict[str, list[int]] = {}
    if a.centre_ranges:
        with open(a.centre_ranges, encoding="utf-8") as fh:
            centre_ranges = json.load(fh)

    report, failed = [], 0
    try:
        for mat, events, out in jobs:
            trial = os.path.splitext(os.path.basename(mat))[0]
            rng = centre_ranges.get(trial)
            try:
                frame, diag = align_trial(mat, events, cfg, tuple(rng) if rng else None)
                _write(frame, out)
                diag["out"] = out
                print(f"{diag['mat']}: {diag['rows_out']} ticks, drift {diag['drift_ppm']} ppm "
                      f"({diag['drift_over_run_ms']} ms over run), gap {diag['sync_gap_s']} s vs dwell "
                      f"{diag['logged_dwell_s']} s -> {out}")
            except Exception as exc:  # noqa: BLE001 -- one bad file must not end an unattended batch
                failed += 1
                diag = {"mat": os.path.basename(mat), "error": f"{type(exc).__name__}: {exc}"}
                print(f"{diag['mat']}: FAILED {diag['error']}", file=sys.stderr)
            report.append(diag)
    finally:
        # Written even if the loop dies, so the trials that DID succeed keep their evidence.
        if a.diagnostics:
            os.makedirs(os.path.dirname(os.path.abspath(a.diagnostics)), exist_ok=True)
            with open(a.diagnostics, "w", encoding="utf-8") as fh:
                json.dump(report, fh, indent=2, default=str)
    print(f"{len(jobs) - failed}/{len(jobs)} aligned")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
