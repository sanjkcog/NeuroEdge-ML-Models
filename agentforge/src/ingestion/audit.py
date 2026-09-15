#!/usr/bin/env python3
"""audit.py — ingestion actions append to the EXISTING exchange.audit_log.AuditLog
(ADR-0012 Direction 2, FR-07, EP-07, Should).

No new/parallel log is ever created here (TC-07-01-01): pull, map, and gate each
build a `DriveIntent`-shaped carrier (reused, not forked — the same object
`AuditLog.record` already accepts for drive intents; `action` is simply "pull" /
"map" / "gate" instead of "advance"/"comment"/etc.) and call the exact same
`AuditLog.record` every other exchange action calls. `AuditLog.record`'s own guard
(an empty-identity intent can never be recorded `outcome=="applied"`) applies here
unchanged — a second line of defense this module gets for free by reuse.
"""

from __future__ import annotations

from exchange.adapter import DriveIntent
from exchange.audit_log import AuditEntry, AuditLog


def record_pull(
    log: AuditLog, *, source_id: str, identity: str, outcome: str, detail: str = ""
) -> AuditEntry:
    """Record one pull_artifacts() action. `raw_id`/`target` are both the
    source-id — a pull has no downstream artifact yet, only its source
    (TC-07-01-02)."""
    intent = DriveIntent(action="pull", target=source_id, identity=identity, raw_id=source_id)
    return log.record(intent, outcome=outcome, detail=detail)


def record_map(
    log: AuditLog, *, source_id: str, identity: str, fields_written: list[str],
    outcome: str, detail: str = "",
) -> AuditEntry:
    """Record one map_docs() action. The fields actually written/flagged/tbd/refused
    are named in `detail` — a reviewer (or an auditor) can see exactly what a mapper
    run touched without re-running it (TC-07-01-02)."""
    full_detail = f"fields: {', '.join(fields_written)}" if fields_written else "fields: (none)"
    if detail:
        full_detail = f"{full_detail}; {detail}"
    intent = DriveIntent(action="map", target=source_id, identity=identity, raw_id=source_id)
    return log.record(intent, outcome=outcome, detail=full_detail)


def record_gate(
    log: AuditLog, *, source_id: str, identity: str, gate_id: str, outcome: str, detail: str = "",
) -> AuditEntry:
    """Record one review_gate action (open/decide). `target` is the gate id
    (the gated artifact path) — named explicitly, not merely folded into `detail`
    (TC-07-01-02)."""
    intent = DriveIntent(action="gate", target=gate_id, identity=identity, raw_id=source_id)
    return log.record(intent, outcome=outcome, detail=detail)
