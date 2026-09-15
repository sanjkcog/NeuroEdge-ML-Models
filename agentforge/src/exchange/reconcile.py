#!/usr/bin/env python3
"""reconcile.py — one reconcile cycle: re-fetch/rebuild the outbound projection and
reconcile it against authoritative run.json/gates.json (ADR-0012 US-01-04, FR-07).

`reconcile(run_state, gate_state, adapter, record_path)` is a single, idempotent cycle
— COMPOSE_AT_BOUNDARY_ONLY, mirroring exchange_record.build's own discipline: it takes
already-loaded RunState/GateState instances and never mutates either. An external
loop/cron/CLI invocation calls this repeatedly for "periodic re-fetch"; cadence/backoff
scheduling (TS-01-04-03, OQ-4) is a separate, deferred concern this module does not own.

Drift model: `pre_drift` counts (artifact, status) disagreements between whatever is
currently on disk at `record_path` (possibly stale, corrupt, or entirely missing —
simulating a stale label or a partial write) and the freshly-rebuilt authoritative
record; `post_drift` is measured the same way AFTER the atomic overwrite + push + a
read-back from disk, so a successful reconcile always drives it to exactly 0. A corrupt
or missing existing record is treated as maximal drift (every authoritative gate counts
as drifted), never a crash — mirrors this whole package's result-object-never-raise
discipline for external/uncertain state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from exchange import exchange_record
from exchange.adapter import ExchangeAdapter, PushResult


@dataclass
class ReconcileResult:
    """The outcome of one reconcile cycle. Never raised — always this."""
    push_result: PushResult
    pre_drift: int
    post_drift: int
    detail: str = ""


def _gate_status_map(record: exchange_record.ExchangeRecord) -> dict[str, str]:
    return {gate.get("artifact", "?"): gate.get("status", "") for gate in record.gates}


def _drift(old: exchange_record.ExchangeRecord, new: exchange_record.ExchangeRecord) -> int:
    """Count of (artifact, status) disagreements between two records, in either
    direction — an artifact present in one but not the other counts too, so a partial
    write (missing gates) is caught, not just a changed status."""
    old_map = _gate_status_map(old)
    new_map = _gate_status_map(new)
    drift = sum(1 for artifact, status in new_map.items() if old_map.get(artifact) != status)
    drift += sum(1 for artifact in old_map if artifact not in new_map)
    return drift


def _empty_record() -> exchange_record.ExchangeRecord:
    """Represents "nothing usable was projected yet" — a missing or corrupt
    record_path is treated as this, so every authoritative gate counts as drifted
    rather than reconcile crashing on a read it cannot trust."""
    return exchange_record.ExchangeRecord(
        objective="", current_stage=None, stages={}, gates=[], blocked_on=[], artifacts=[],
    )


def _load_existing(record_path: Path) -> exchange_record.ExchangeRecord:
    try:
        return exchange_record.ExchangeRecord.load(record_path)
    except (OSError, exchange_record.InvalidExchangeRecord):
        # Missing (OSError/FileNotFoundError) or corrupt/partial (InvalidExchangeRecord)
        # — both are "nothing usable was projected", not a reconcile failure.
        return _empty_record()


def reconcile(
    run_state, gate_state, adapter: ExchangeAdapter, record_path: str | Path
) -> ReconcileResult:
    """One reconcile cycle against `record_path`.

    `run_state`/`gate_state` are already-loaded state instances (compose-at-boundary —
    the caller loads them); `adapter` is any ExchangeAdapter (NoneExchangeAdapter is a
    fully legitimate choice, mirroring the rest of this package). Never mutates
    run_state/gate_state, and never calls `adapter.pull_intents()` — reconcile is an
    OUTBOUND projection-fidelity cycle, not an inbound-drive path.
    """
    record_path = Path(record_path)
    fresh = exchange_record.build(run_state, gate_state)

    existing = _load_existing(record_path)
    pre_drift = _drift(existing, fresh)

    fresh.save(record_path)                       # atomic write (ExchangeRecord.save)
    push_result = adapter.push(record_path)

    # Read-back after write (LLD-wide pattern): reload from disk, not the in-memory
    # `fresh` object, so post_drift proves the write actually landed correctly.
    reloaded = exchange_record.ExchangeRecord.load(record_path)
    post_drift = _drift(reloaded, fresh)

    return ReconcileResult(
        push_result=push_result,
        pre_drift=pre_drift,
        post_drift=post_drift,
        detail=f"{record_path}: pre_drift={pre_drift}, post_drift={post_drift}",
    )
