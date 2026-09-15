#!/usr/bin/env python3
"""ledger.py — the applied-intents idempotency ledger (ADR-0012 sprint-03, US-03-03,
FR-08).

Mirrors gate_state.py's atomic-JSON, tolerant-load discipline exactly. Keyed on each
DriveIntent's `raw_id` (the natural idempotency key — git_adapter._parse_intent derives
it from the originating Issue/comment so it is stable across repeated pulls of the SAME
external event). A `raw_id` recorded here has already been APPLIED (drive.apply_intent
returned applied=True) at least once; the caller (exchange_cli.apply) checks
`has_applied` BEFORE calling apply_intent again for that same raw_id, and calls
`mark_applied` only after apply_intent reports applied=True — a refused/unauthorized
intent is never marked, so a legitimately-retried refusal (e.g. a gate that later
clears) can still be re-attempted on a later pull.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AppliedIntentLedger:
    """raw_id -> ISO-8601 timestamp it was first applied. Presence of a key IS the
    at-most-once fact; the timestamp is diagnostic only, never re-checked for TTL/expiry
    (out of scope for this keystone slice — every applied raw_id blocks replay forever,
    matching "executes at most once" literally)."""
    applied: dict[str, str] = field(default_factory=dict)

    @classmethod
    def new(cls) -> AppliedIntentLedger:
        return cls()

    def has_applied(self, raw_id: str) -> bool:
        return raw_id in self.applied

    def mark_applied(self, raw_id: str) -> None:
        # Idempotent at the ledger's own granularity too: marking the same raw_id twice
        # (e.g. two rapid calls before a save) leaves exactly one fact recorded, not a
        # growing structure — a plain dict assignment already guarantees this, so no
        # extra guard is needed, but the intent is documented here rather than left
        # implicit (code review: at-most-once must hold at every layer, not just the
        # caller's own has_applied() check).
        self.applied[raw_id] = _now_iso()

    def save(self, path: str | Path) -> None:
        """Atomically persist — temp file + os.replace, mirrors gate_state.save."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"applied": self.applied}, indent=2, ensure_ascii=False) + "\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> AppliedIntentLedger:
        """Missing or corrupt ledger both report an EMPTY ledger, never an exception —
        a caller checking has_applied() on a ledger that hasn't been written yet (or was
        hand-edited into an invalid state) must not crash. Treating it as empty is the
        conservative choice: worst case a duplicate re-execution is re-attempted (never
        a false "already applied" that would silently drop a real intent)."""
        path = Path(path)
        if not path.is_file():
            return cls.new()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return cls.new()
            applied = data.get("applied", {})
            if not isinstance(applied, dict):
                return cls.new()
        except json.JSONDecodeError:
            return cls.new()
        return cls(applied={str(k): str(v) for k, v in applied.items()})
