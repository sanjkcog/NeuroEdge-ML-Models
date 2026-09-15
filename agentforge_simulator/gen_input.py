#!/usr/bin/env python3
"""gen_input.py — generate realistic sample inputs for the NeuroEdge simulator.

When you don't have a real capture to replay, generate one. Produces a
timeseries dataset for a chosen *profile* and writes it into ``sim_input/`` (or
anywhere via --out) as csv / json / jsonl. The simulator then replays it over
any transport.

Profiles model the four things people usually simulate:
  edge_device          device health telemetry (cpu/mem/temp/uptime/status)
  sensor               a single sensor channel (baseline + sine + noise + anomalies)
  enterprise_ops       ops/event stream (service, severity, latency, status_code)
  cyclic_multichannel  multi-channel cyclic time-series sensor generator — N correlated
                       channels, a repeating work-cycle envelope, and a fault magnitude
                       that progresses across cycles (ADR-0015 D-1 item 5, signal mode)

Stdlib only — no third-party dependency, so this always runs.

Examples:
  python gen_input.py --profile sensor --rows 500 --hz 10 --out sim_input/vibration.csv
  python gen_input.py --profile edge_device --rows 200 --format jsonl
  python gen_input.py --profile enterprise_ops --rows 1000 --anomaly-rate 0.05 --format json
  python gen_input.py --profile cyclic_multichannel --rows 800 --rows-per-cycle 80 \
      --channel-names spindle_load,axis_err,vibration_rms --drift ramp-recover \
      --seed 20260914 --recipe
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

_ROOT = Path(__file__).resolve().parent
PROFILES = ("edge_device", "sensor", "enterprise_ops", "cyclic_multichannel")


def _iso(base: datetime, i: int, step_s: float) -> str:
    return (base + timedelta(seconds=i * step_s)).isoformat().replace("+00:00", "Z")


def gen_edge_device(n: int, base: datetime, step_s: float, rng: random.Random,
                    anomaly_rate: float, **_: Any) -> Iterator[dict[str, Any]]:
    device_id = "edge-01"
    fw = "1.4.2"
    uptime = rng.randint(3600, 864000)
    for i in range(n):
        anomaly = rng.random() < anomaly_rate
        cpu = min(100.0, rng.gauss(35 if not anomaly else 92, 6))
        mem = min(100.0, rng.gauss(55 if not anomaly else 88, 5))
        temp = rng.gauss(46 if not anomaly else 71, 2)
        status = "alarm" if temp > 65 or cpu > 90 else "warn" if temp > 55 or cpu > 75 else "ok"
        yield {
            "device_id": device_id,
            "ts": _iso(base, i, step_s),
            "cpu_pct": round(max(0.0, cpu), 1),
            "mem_pct": round(max(0.0, mem), 1),
            "temp_c": round(temp, 1),
            "uptime_s": uptime + int(i * step_s),
            "fw_version": fw,
            "status": status,
        }


def gen_sensor(n: int, base: datetime, step_s: float, rng: random.Random,
               anomaly_rate: float, **_: Any) -> Iterator[dict[str, Any]]:
    sensor_id = "vib-07"
    unit = "g"
    baseline, amp, period = 0.05, 0.03, 40.0
    for i in range(n):
        anomaly = rng.random() < anomaly_rate
        value = baseline + amp * math.sin(2 * math.pi * i / period) + rng.gauss(0, 0.004)
        quality = "good"
        if anomaly:
            value += rng.choice([0.4, -0.35, 0.6])  # spike
            quality = "suspect"
        yield {
            "sensor_id": sensor_id,
            "ts": _iso(base, i, step_s),
            "value": round(value, 5),
            "unit": unit,
            "quality": quality,
        }


def gen_enterprise_ops(n: int, base: datetime, step_s: float, rng: random.Random,
                       anomaly_rate: float, **_: Any) -> Iterator[dict[str, Any]]:
    services = ["auth", "billing", "orders", "inventory", "notifications", "gateway"]
    for i in range(n):
        anomaly = rng.random() < anomaly_rate
        service = rng.choice(services)
        latency = rng.gauss(120 if not anomaly else 1400, 40)
        status_code = rng.choices([200, 201, 400, 404, 500, 503],
                                  weights=[70, 10, 6, 5, 5, 4] if not anomaly
                                  else [10, 2, 8, 5, 45, 30])[0]
        severity = ("critical" if status_code >= 500 else
                    "warning" if status_code >= 400 or latency > 500 else "info")
        yield {
            "event_id": f"evt-{i:06d}",
            "ts": _iso(base, i, step_s),
            "service": service,
            "severity": severity,
            "latency_ms": round(max(1.0, latency), 1),
            "status_code": status_code,
            "message": f"{service} responded {status_code}",
        }


DRIFT_PROFILES = ("none", "ramp", "ramp-recover", "step")

# Fraction of a cycle spent ramping in / out of the steady phase. A real work
# cycle is not a rectangle: it enters, holds, and exits.
_ENTRY_FRAC, _EXIT_FRAC = 0.15, 0.15


def _n_cycles(rows: int, rows_per_cycle: int) -> int:
    """Whole cycles in `rows`. One definition, so the data, the log line and the
    recipe sidecar cannot disagree about how many cycles were written."""
    return max(1, rows // max(2, rows_per_cycle))


def _cycle_envelope(row_in_cycle: int, rows_per_cycle: int) -> float:
    """Trapezoid 0→1→0 over one cycle: entry ramp, steady plateau, exit ramp."""
    if rows_per_cycle <= 1:
        return 1.0
    f = row_in_cycle / (rows_per_cycle - 1)
    if f < _ENTRY_FRAC:
        return f / _ENTRY_FRAC
    if f > 1.0 - _EXIT_FRAC:
        return max(0.0, (1.0 - f) / _EXIT_FRAC)
    return 1.0


def _cycle_severity(cycle_idx: int, n_cycles: int, drift: str) -> float:
    """Fault magnitude for one whole cycle, in 0..1. This is what *progresses*."""
    if n_cycles <= 1 or drift == "none":
        return 0.0
    f = cycle_idx / (n_cycles - 1)
    if drift == "ramp":
        return f
    if drift == "step":
        return 0.0 if f < 0.5 else 1.0
    if drift == "ramp-recover":
        # Degrade to a peak at 70 % of the run, then a maintenance action recovers it.
        return f / 0.7 if f <= 0.7 else 0.1
    return 0.0  # pragma: no cover - argparse restricts choices


def gen_cyclic_multichannel(n: int, base: datetime, step_s: float, rng: random.Random,
                            anomaly_rate: float, *, channel_names: list[str] | None = None,
                            rows_per_cycle: int = 80, drift: str = "ramp-recover",
                            label_threshold: float = 0.5,
                            **_: Any) -> Iterator[dict[str, Any]]:
    """Multi-channel cyclic time-series sensor generator.

    Three properties a single-channel uniform stream cannot express, and that any
    window-scoring model needs in order to learn something real:

    1. **Correlated channels.** Every channel is driven by the *same* cycle envelope
       and the *same* fault magnitude, each with its own gain, and additionally shares
       a common-mode per-row disturbance. The envelope and fault terms are the
       dominant correlation; the disturbance is a smaller jitter on top. The fault
       signature lives in how the channels move *together* — independent per-channel
       noise teaches a model nothing.
    2. **Cycle structure.** Each cycle ramps in, holds steady, and ramps out, so a
       window's position within a cycle matters.
    3. **Progression across cycles.** The fault magnitude evolves cycle to cycle
       (`--drift`), which is the phenomenon itself — not a per-row coin flip.

    Emits one wide row per timestep: `ts`, `cycle_index`, `row_in_cycle`, one column
    per channel, `severity`, and `label`. Wide-CSV shape, so the column order is the
    feature order a downstream model is trained and served with.
    """
    names = channel_names or [f"c{i:02d}" for i in range(3)]
    rows_per_cycle = max(2, rows_per_cycle)
    n_cycles = _n_cycles(n, rows_per_cycle)
    # Emit whole cycles only. A trailing partial cycle would be sized against the
    # full rows_per_cycle, so it would never leave the entry ramp -- a fragment that
    # looks like a cycle in the data but is not one -- and its cycle_index would run
    # one past the count reported in the log and the recipe.
    n = n_cycles * rows_per_cycle

    # Per-channel character, deterministic from the seeded rng: a baseline level, a
    # gain on the cycle envelope, a response to the fault, and a noise floor.
    profile = []
    for _ in names:
        profile.append({
            "baseline": rng.uniform(0.5, 2.0),
            "gain": rng.uniform(0.8, 1.6),
            "fault_response": rng.uniform(0.4, 1.2),
            "noise": rng.uniform(0.01, 0.04),
            "corr": rng.uniform(0.2, 0.6),
        })

    for i in range(n):
        cycle_idx, row_in_cycle = divmod(i, rows_per_cycle)
        severity = _cycle_severity(cycle_idx, n_cycles, drift)
        envelope = _cycle_envelope(row_in_cycle, rows_per_cycle)

        shared = rng.gauss(0.0, 1.0)          # common-mode disturbance: the correlation
        spike = rng.random() < anomaly_rate

        rec: dict[str, Any] = {
            "ts": _iso(base, i, step_s),
            "cycle_index": cycle_idx,
            "row_in_cycle": row_in_cycle,
        }
        for name, ch in zip(names, profile):
            value = (ch["baseline"]
                     + ch["gain"] * envelope
                     + ch["fault_response"] * severity * envelope
                     + ch["corr"] * shared * ch["noise"]
                     + rng.gauss(0.0, ch["noise"]))
            if spike:
                value += rng.choice([1.0, -0.8, 1.4]) * ch["noise"] * 10
            rec[name] = round(value, 5)

        rec["severity"] = round(severity, 4)
        # Label rule (record it in the label-manifest): a row belongs to a cycle
        # whose fault magnitude is at or above the threshold.
        rec["label"] = 1 if severity >= label_threshold else 0
        yield rec


GENERATORS: dict[str, Callable[..., Iterator[dict[str, Any]]]] = {
    "edge_device": gen_edge_device,
    "sensor": gen_sensor,
    "enterprise_ops": gen_enterprise_ops,
    "cyclic_multichannel": gen_cyclic_multichannel,
}


def write_records(records: list[dict[str, Any]], out: Path, fmt: str) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        fields = list(records[0].keys()) if records else []
        with out.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
    elif fmt == "jsonl":
        with out.open("w", encoding="utf-8", newline="\n") as fh:
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    elif fmt == "json":
        out.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8", newline="\n")
    else:  # pragma: no cover - argparse restricts choices
        raise ValueError(f"unknown format {fmt!r}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="gen_input",
        description="Generate a sample timeseries input for the NeuroEdge simulator.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--profile", choices=PROFILES, required=True,
                   help="what to simulate")
    p.add_argument("--rows", type=int, default=200, help="number of records")
    p.add_argument("--format", choices=("csv", "json", "jsonl"), default="csv")
    p.add_argument("--out", type=Path, default=None,
                   help="output path (default: sim_input/<profile>.<ext>)")
    p.add_argument("--hz", type=float, default=1.0,
                   help="sample rate used to space timestamps (records/sec)")
    p.add_argument("--anomaly-rate", type=float, default=0.03,
                   help="fraction of records that carry an injected anomaly (0..1)")
    p.add_argument("--seed", type=int, default=None, help="RNG seed for reproducibility")
    p.add_argument("--start-ts", default=None,
                   help="ISO-8601 UTC start timestamp, e.g. 2026-01-01T00:00:00Z. Pin it "
                        "alongside --seed for byte-identical reruns; the default is wall "
                        "clock, so values reproduce but timestamps do not")

    cyc = p.add_argument_group("cyclic_multichannel options")
    cyc.add_argument("--channel-names", default=None,
                     help="comma-separated channel column names, in feature order "
                          "(default: c00,c01,c02). The column order IS the feature order")
    cyc.add_argument("--rows-per-cycle", type=int, default=80,
                     help="rows in one work cycle; must exceed the model's window size")
    cyc.add_argument("--drift", choices=DRIFT_PROFILES, default="ramp-recover",
                     help="how the fault magnitude progresses across cycles")
    cyc.add_argument("--label-threshold", type=float, default=0.5,
                     help="cycle severity at or above which rows are labelled 1")
    cyc.add_argument("--recipe", action="store_true",
                     help="also write <out>.recipe.json — the reproducible synthetic-recipe "
                          "(generator, params, seed, label rule)")
    args = p.parse_args(argv)

    out = args.out or (_ROOT / "sim_input" / f"{args.profile}.{args.format}")
    step_s = 1.0 / args.hz if args.hz > 0 else 1.0
    if args.start_ts:
        try:
            base = datetime.fromisoformat(args.start_ts.replace("Z", "+00:00"))
        except ValueError:
            print(f"[gen] ERROR: --start-ts {args.start_ts!r} is not ISO-8601 "
                  "(expected e.g. 2026-01-01T00:00:00Z)")
            return 2
        # A naive value is read as UTC; an explicit non-UTC offset is CONVERTED to it
        # rather than preserved -- the flag is documented as UTC, and _iso() only
        # rewrites "+00:00" to "Z", so a kept offset would leak into every timestamp.
        base = (base.replace(tzinfo=timezone.utc) if base.tzinfo is None
                else base.astimezone(timezone.utc)).replace(microsecond=0)
    else:
        base = datetime.now(timezone.utc).replace(microsecond=0)
    rng = random.Random(args.seed)

    names = ([s.strip() for s in args.channel_names.split(",") if s.strip()]
             if args.channel_names else None)

    if args.profile == "cyclic_multichannel":
        # A drift profile needs at least two cycles to progress across. With fewer,
        # severity is 0.0 for every row and the whole dataset is silently degenerate
        # -- no labels, no signal -- which is exactly what this generator exists to
        # avoid. Refuse rather than warn: a warning here would be read after the fact,
        # against data that looks superficially fine.
        if args.rows < max(2, args.rows_per_cycle):
            print(f"[gen] ERROR: --rows {args.rows} is fewer than one whole cycle of "
                  f"{args.rows_per_cycle} rows. This profile emits whole cycles only, so "
                  f"there is nothing valid to write -- and rounding up to a full cycle "
                  f"would hand you more rows than you asked for. Raise --rows to at least "
                  f"{max(2, args.rows_per_cycle)}, or lower --rows-per-cycle.")
            return 2
        n_cycles = _n_cycles(args.rows, args.rows_per_cycle)
        if args.drift != "none" and n_cycles < 2:
            print(f"[gen] ERROR: --drift {args.drift} needs at least 2 whole cycles to "
                  f"progress across, but --rows {args.rows} / --rows-per-cycle "
                  f"{args.rows_per_cycle} yields {n_cycles}. Every row would get "
                  f"severity=0.0 and label=0. Raise --rows to at least "
                  f"{2 * args.rows_per_cycle}, lower --rows-per-cycle, or pass "
                  f"--drift none if a flat dataset is what you want.")
            return 2
        if args.rows % max(2, args.rows_per_cycle):
            print(f"[gen] note: --rows {args.rows} is not a whole number of "
                  f"{args.rows_per_cycle}-row cycles; emitting {n_cycles} whole "
                  f"cycle(s) and dropping the remainder.")

    records = list(GENERATORS[args.profile](
        args.rows, base, step_s, rng, args.anomaly_rate,
        channel_names=names, rows_per_cycle=args.rows_per_cycle,
        drift=args.drift, label_threshold=args.label_threshold))
    write_records(records, out, args.format)

    print(f"[gen] wrote {len(records)} {args.profile} record(s) to {out} ({args.format})")

    if args.profile == "cyclic_multichannel":
        n_cycles = _n_cycles(args.rows, args.rows_per_cycle)
        print(f"[gen] {n_cycles} cycle(s) of {args.rows_per_cycle} rows, drift={args.drift}, "
              f"channels={names or ['c00', 'c01', 'c02']}")
        if args.seed is None:
            # ASCII only: this goes to a console that may be cp1252 on Windows.
            print("[gen] WARNING: no --seed given - this dataset is NOT reproducible. "
                  "Synthetic data without a seed cannot be regenerated or audited.")
        elif not args.start_ts:
            print("[gen] note: values are reproducible from --seed, but the ts column is "
                  "wall clock. Add --start-ts for byte-identical reruns.")

    if args.recipe:
        recipe = {
            "generator": "gen_input.py",
            "profile": args.profile,
            "params": {
                "rows": args.rows, "hz": args.hz, "anomaly_rate": args.anomaly_rate,
                "rows_per_cycle": args.rows_per_cycle, "drift": args.drift,
                "channel_names": names, "label_threshold": args.label_threshold,
            },
            "seed": args.seed,
            "start_ts": args.start_ts,
            "label_rule": (f"label=1 when cycle severity >= {args.label_threshold}; "
                           "severity is per-cycle, so every row in a cycle shares its label"),
            "provenance": "SYNTHETIC - never present these rows as real captured data",
            "reproducibility": (
                "Values reproduce exactly from `seed` alone. Timestamps reproduce only "
                "when `start_ts` is also set -- otherwise the ts column is wall clock at "
                "generation time and reruns differ in that column only."
            ),
        }
        recipe_path = out.with_suffix(out.suffix + ".recipe.json")
        recipe_path.write_text(json.dumps(recipe, indent=2) + "\n",
                               encoding="utf-8", newline="\n")
        print(f"[gen] wrote synthetic-recipe to {recipe_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
