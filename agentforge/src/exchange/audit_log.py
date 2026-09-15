#!/usr/bin/env python3
"""audit_log.py — provenance audit trail for every ingested inbound drive intent
(ADR-0012 sprint-03, US-03-04, FR-09).

Extends this package's existing audit discipline (run_state.Spawn.identity already
attributes WHO proposed an applied 'advance'; gate_state.Decision already attributes WHO
decided a gate) to the INGESTION boundary itself: every intent this substrate pulls gets
one AuditEntry recording who/what/when/outcome — applied, refused by the fence, rejected
by authorization, or skipped as an idempotent replay — never silently dropped.

Deliberately NOT added to run_state.py/gate_state.py themselves: the package-wide
invariant (proven by test_exchange_record.py's structural test) is that those two
modules never import the exchange layer, so this stays exchange-side and one-directional,
composed by exchange_cli.apply at the boundary like every other exchange module.

Structural guarantee (`record`): an intent with no identity can never be logged as
"applied" — mirrors gate_state.record_decision's own identity guard, enforced a second
time here (defense in depth) so "unattributed" cannot slip through as a legitimate
execution even if a caller's own authorization check were ever bypassed or miswired.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AuditEntry:
    raw_id: str
    identity: str
    action: str
    target: str
    outcome: str     # "applied" | "refused" | "unauthorized" | "skipped_replay"
    detail: str = ""
    at: str = ""


@dataclass
class AuditLog:
    entries: list[AuditEntry] = field(default_factory=list)

    @classmethod
    def new(cls) -> AuditLog:
        return cls()

    def record(self, intent, outcome: str, detail: str = "") -> AuditEntry:
        """Append one AuditEntry for `intent`. Every call appends — there is no code
        path here that silently discards an intent without an entry, so "record every
        ingested intent" holds by construction, not merely by caller discipline.

        Refuses (raises ValueError, records nothing) when outcome=="applied" for an
        unattributed intent: an unattributed intent is REJECTED, never silently
        recorded as if it had legitimately executed (ADR-0012 US-03-04). A rejection
        outcome (e.g. "unauthorized") for that same unattributed intent is still fully
        recordable — the invariant is "never falsely applied", not "never logged".
        """
        identity = (intent.identity or "").strip()
        if outcome == "applied" and not identity:
            raise ValueError(
                "an unattributed intent (empty identity) cannot be recorded as "
                "'applied' — it must be rejected, not silently recorded"
            )
        entry = AuditEntry(
            raw_id=intent.raw_id, identity=intent.identity, action=intent.action,
            target=intent.target, outcome=outcome, detail=detail, at=_now_iso(),
        )
        self.entries.append(entry)
        return entry

    def save(self, path: str | Path) -> None:
        """Atomically persist — temp file + os.replace. Append-only in spirit: every
        prior entry already in `self.entries` (e.g. loaded from disk, then added to) is
        preserved — this method never removes an entry, only writes what it is given."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"entries": [asdict(e) for e in self.entries]}, indent=2, ensure_ascii=False
        ) + "\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> AuditLog:
        """Missing or corrupt log both report an EMPTY log, never an exception —
        mirrors ledger.AppliedIntentLedger.load's tolerant-load discipline. A malformed
        individual entry is skipped rather than aborting the whole load, so one bad
        record can't erase every other legitimately-recorded entry."""
        path = Path(path)
        if not path.is_file():
            return cls.new()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return cls.new()
            raw_entries = data.get("entries", [])
            if not isinstance(raw_entries, list):
                return cls.new()
        except json.JSONDecodeError:
            return cls.new()
        entries = []
        for e in raw_entries:
            if not isinstance(e, dict):
                continue
            entries.append(AuditEntry(
                raw_id=e.get("raw_id", ""), identity=e.get("identity", ""),
                action=e.get("action", ""), target=e.get("target", ""),
                outcome=e.get("outcome", ""), detail=e.get("detail", ""),
                at=e.get("at", ""),
            ))
        return cls(entries=entries)
