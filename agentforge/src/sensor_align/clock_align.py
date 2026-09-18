"""Put a sensor DAQ stream on a machine controller's clock, using a sync pulse.

A lab rig usually has two recorders: the machine controller (e.g. a SINUMERIK Edge export at
500 Hz, keyed by a cycle counter) and a bolted-on DAQ (accelerometer, force platform at
10 kHz, keyed by its own sample index). They start at different moments and their clocks run
at slightly different rates. Joining them by "row 0 = row 0" is wrong by seconds; joining
them by a fixed offset is still wrong by tens of milliseconds at the end of a long run.

The rigs that get this right wire a **sync pulse** from the controller into a spare DAQ
channel: a square wave the NC program drives, with a deliberate pause (a dwell) that marks a
known program block. That gives two things, and this module uses both:

* **An anchor.** The single long gap in the square wave is the dwell. The controller's own
  block log records the dwell against its counter, so "first edge after the gap" and "counter
  of the block after the dwell" are the same instant.
* **A rate.** Every half-period of the square wave is a fixed number of controller ticks. A
  straight-line fit of edge position against edge number gives the DAQ samples per controller
  tick directly, which removes the drift a fixed offset leaves behind.

Measured on the reference dataset (KIT CNC milling, 10 kHz DAQ vs 500 Hz Edge, 33/33 recordings
aligned): the DAQ clock runs 75-81 ppm fast on every recording, up to 98 ms over a 20-minute
run, and the fit leaves 0.1-8 ms of edge residual. The anchor is good to about one sync
half-period, because the generator restarts on its own phase grid rather than on the logged
block: vibration leaves baseline a median 8 ms before spindle current does (range -14..+8 ms).
That is negligible for RMS features over windows of 0.2 s or more, and too coarse for timing
events shorter than ~20 ms. Whole-run cross-correlation of vibration against spindle power
could not find the offset at all (r <= 0.25, no clear peak), so it is not used.

Plain numpy, no I/O: `align.py` holds the file handling.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


class AlignmentError(RuntimeError):
    """The sync signal does not support a trustworthy alignment. Never guess past this."""


def square_wave_edges(sync: np.ndarray, threshold: float | None = None) -> np.ndarray:
    """Sample indices where the sync signal crosses the threshold, either direction.

    Each index is the first sample on the new side of the threshold. With no threshold the
    midpoint of the signal's range is used, which suits a 0/5 V logic output.
    """
    x = np.asarray(sync, dtype=float)
    if x.size < 2:
        return np.empty(0, dtype=np.int64)
    thr = (np.nanmin(x) + np.nanmax(x)) / 2.0 if threshold is None else threshold
    high = x > thr
    return (np.flatnonzero(high[1:] != high[:-1]) + 1).astype(np.int64)


def debounce(edges: np.ndarray, min_samples: float) -> tuple[np.ndarray, int]:
    """Drop edge pairs closer together than `min_samples`, returning (edges, dropped).

    A noise spike that crosses the threshold and comes back makes two extra edges a few
    samples apart. Left in, each spike shifts every later edge number by two, which a fit
    against edge number reads as a clock error.
    """
    kept: list[int] = []
    dropped = 0
    for edge in np.asarray(edges, dtype=np.int64):
        if kept and edge - kept[-1] < min_samples:
            kept.pop()
            dropped += 2
        else:
            kept.append(int(edge))
    return np.asarray(kept, dtype=np.int64), dropped


def find_gap(edges: np.ndarray, min_gap_samples: float) -> tuple[int, int, int]:
    """The single long pause in the square wave: (gap_start, gap_end, index_of_gap_end_edge).

    Exactly one is required. None means the program never ran its dwell, or the sync channel
    was not recorded; more than one means the anchor is ambiguous. Both are refused rather
    than resolved by picking one.
    """
    spacing = np.diff(edges)
    gaps = np.flatnonzero(spacing >= min_gap_samples)
    if gaps.size != 1:
        raise AlignmentError(
            f"expected exactly one sync gap >= {min_gap_samples:.0f} samples, found {gaps.size}"
        )
    i = int(gaps[0])
    return int(edges[i]), int(edges[i + 1]), i + 1


@dataclass(frozen=True)
class ClockMap:
    """Linear map from DAQ sample index to controller tick, fitted from the sync edges."""

    anchor_sample: float        # fitted DAQ position of the first edge after the dwell
    anchor_tick: float          # controller counter at that instant (from the block log)
    samples_per_tick: float     # measured, drift included
    nominal_samples_per_tick: float
    edges_used: int
    residual_max_samples: float
    glitch_edges_dropped: int
    gap_samples: int
    trailing_edges_ignored: int = 0   # edges after a late irregular phase (program end)

    @property
    def drift_ppm(self) -> float:
        """How fast the DAQ clock runs against the controller's, parts per million."""
        return (self.samples_per_tick / self.nominal_samples_per_tick - 1.0) * 1e6

    def ticks(self, samples: np.ndarray) -> np.ndarray:
        """Controller tick (fractional) for each DAQ sample index."""
        offset = np.asarray(samples, dtype=float) - self.anchor_sample
        return self.anchor_tick + offset / self.samples_per_tick


def fit_clock_map(
    sync: np.ndarray,
    *,
    sensor_hz: float,
    tick_hz: float,
    ticks_per_half_period: int,
    anchor_tick: float,
    min_gap_s: float = 1.0,
    expected_gap_s: float | None = None,
    gap_tolerance_s: float | None = None,
    threshold: float | None = None,
    min_regular_fraction: float = 0.9,
) -> ClockMap:
    """Fit the sample-to-tick map from a sync channel and the controller tick of the anchor.

    `ticks_per_half_period` is how many controller ticks one high or low phase of the square
    wave lasts (KIT: 8 ticks of 2 ms = 16 ms). `expected_gap_s`, when given, is the dwell as
    the controller logged it; a measured gap that disagrees by more than `gap_tolerance_s`
    (default: three half-periods) is refused, because it means the gap is not the dwell. The
    measured gap is longer than the dwell by the phase held before it and the generator's
    restart latency -- up to a half-period each, 16-42 ms on KIT against 2.002 s.
    """
    nominal = sensor_hz / tick_hz
    half = nominal * ticks_per_half_period
    edges, dropped = debounce(square_wave_edges(sync, threshold), 0.5 * half)
    gap_start, gap_end, pos = find_gap(edges, min_gap_s * sensor_hz)

    if expected_gap_s is not None:
        measured = (gap_end - gap_start) / sensor_hz
        tolerance = 3 * half / sensor_hz if gap_tolerance_s is None else gap_tolerance_s
        if abs(measured - expected_gap_s) > tolerance:
            raise AlignmentError(
                f"sync gap is {measured:.3f} s but the logged dwell is {expected_gap_s:.3f} s "
                f"(tolerance {tolerance:.3f} s) -- the gap is not the dwell"
            )

    after = edges[pos:]
    if after.size < 3:
        raise AlignmentError(f"only {after.size} sync edges after the dwell -- too few for a rate")
    spacing = np.diff(after)
    irregular = np.flatnonzero((spacing < 0.5 * half) | (spacing > 1.5 * half))
    trailing_edges_ignored = 0
    if irregular.size:
        # Edge counting is only valid up to the first irregular phase: past it, edge number no
        # longer equals elapsed half-periods. KIT programs stretch one phase at shutdown
        # (M5/M30, the last 2-14 s), so the fit stops there and the fitted rate carries the
        # tail. An irregular phase EARLY in the run is a missing or extra edge and is refused.
        first = int(irregular[0])
        if first + 1 < min_regular_fraction * after.size:
            raise AlignmentError(
                f"irregular sync half-period at edge {first + 1} of {after.size} after the dwell "
                f"(sample {after[first]}, {spacing[first]} samples vs {half:.0f}); a missing or "
                f"extra edge this early would shift every later sample"
            )
        trailing_edges_ignored = int(after.size - (first + 1))
        after = after[: first + 1]

    k = np.arange(after.size, dtype=float)
    slope, intercept = np.polyfit(k, after.astype(float), 1)
    residual = after - (slope * k + intercept)
    return ClockMap(
        anchor_sample=float(intercept),
        anchor_tick=float(anchor_tick),
        samples_per_tick=float(slope / ticks_per_half_period),
        nominal_samples_per_tick=float(nominal),
        edges_used=int(after.size),
        residual_max_samples=float(np.abs(residual).max()),
        glitch_edges_dropped=dropped,
        gap_samples=gap_end - gap_start,
        trailing_edges_ignored=trailing_edges_ignored,
    )


def rms_per_tick(
    values: np.ndarray, ticks: np.ndarray, min_samples: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """RMS of `values` over the DAQ samples that fall inside each whole controller tick.

    Returns (tick, rms, n_samples) for ticks with at least `min_samples` samples, so the
    partial ticks at either end of the recording are dropped rather than reported from one
    or two samples. Binning on the drift-corrected tick keeps exactly one value per
    controller row, which a fixed block size would not over a long run.
    """
    whole = np.floor(np.asarray(ticks, dtype=float)).astype(np.int64)
    base = whole.min()
    key = whole - base
    x = np.asarray(values, dtype=float)
    ok = np.isfinite(x)
    count = np.bincount(key[ok], minlength=key.max() + 1)
    sumsq = np.bincount(key[ok], weights=x[ok] ** 2, minlength=key.max() + 1)
    keep = count >= min_samples
    return np.flatnonzero(keep) + base, np.sqrt(sumsq[keep] / count[keep]), count[keep]
