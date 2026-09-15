"""id_map.py — boundary-only, append-only, degrade-to-canonical ID translation (FR-06).

Canonical (`FR-NN` / `EP-NN` / `US-NN` / `TS-NN` / `TC-NN`) stays the working currency
everywhere else (FR-01) — this module exists only so a rendered customer-facing
document can show the customer's own ID scheme. It is consulted ONLY at the
render/ingest boundary (see `reformat._resolve_trace_id`); the canonical-currency
engine and downstream tooling (`/prd-to-epics`, `/stories-to-tasks`, `/trace-matrix`)
never import or call it (`test_no_idmap_in_tooling.py` / `test_id_map_boundary_only.py`,
grep-count == 0).

One instance-map file spans all five namespaces:

    NAMESPACES = ("requirement", "epic", "story", "task", "testcase")

`resolve()`/`bind()` take the canonical ID alone — no separate namespace argument to
keep in sync with the ID's own prefix (`FR-` requirement, `EP-` epic, `US-` story,
`TS-` task, `TC-` testcase); this module does not need to parse that prefix at all
since the map itself is a flat `canonical_id -> customer_id` dict, populated from
whichever namespaces a project chooses to bind.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

NAMESPACES = ("requirement", "epic", "story", "task", "testcase")

# Reference default location (FR-06, OQ-5 TBD/non-blocking) — callers may pass any
# path to load(); this constant is only a convenience default for reformat.py.
DEFAULT_PATH = Path("id-map.instance.json")


class IdMapRenumberError(Exception):
    """Raised by `IdMap.bind` when a canonical ID already bound to one customer ID is
    rebound to a DIFFERENT customer ID (AC-06.3). The append-only map can grow; it can
    never renumber or overwrite an existing binding.
    """


@dataclass
class IdMap:
    """One project's instance map, spanning all five namespaces in a single flat
    `bindings` dict (canonical_id -> customer_id).

    `degraded` is True when this instance was constructed because the backing file
    was absent or corrupt (see `load`) — `resolve` still works in that state, it just
    never finds a binding and always returns the canonical id unchanged.
    """

    degraded: bool = False
    bindings: dict[str, str] = field(default_factory=dict)
    notices: list[str] = field(default_factory=list)

    def resolve(self, canonical_id: str) -> str:
        """Boundary-only. Returns the bound customer ID, or `canonical_id` unchanged
        on a miss or while degraded. NEVER raises. While degraded, records exactly one
        non-fatal notice on this instance (not one per call) so a caller can surface
        it without a second resolve turning into a second warning (H4).
        """
        if self.degraded:
            if not self.notices:
                self.notices.append(
                    f"id-map degraded — showing canonical ID {canonical_id!r} unresolved"
                )
            return canonical_id
        return self.bindings.get(canonical_id, canonical_id)

    def bind(self, canonical_id: str, customer_id: str) -> None:
        """Append-only. Binding `canonical_id` to the same `customer_id` again is a
        no-op (idempotent). Rebinding an ALREADY-bound `canonical_id` to a DIFFERENT
        `customer_id` raises `IdMapRenumberError` and leaves the existing binding
        untouched (AC-06.3) — the map can only grow, never renumber.
        """
        existing = self.bindings.get(canonical_id)
        if existing is not None and existing != customer_id:
            raise IdMapRenumberError(
                f"cannot rebind {canonical_id!r}: already bound to {existing!r}; "
                f"refusing to renumber to {customer_id!r} (append-only map, AC-06.3)"
            )
        self.bindings[canonical_id] = customer_id


def load(path: str | Path) -> IdMap:
    """Read one instance-map file. An absent path or a corrupt (unparseable,
    truncated, or malformed-shape) file both degrade to `IdMap(degraded=True)` —
    this function NEVER raises.
    """
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        bindings = data.get("bindings", {})
        if not isinstance(bindings, dict):
            raise ValueError("'bindings' must be an object")
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in bindings.items()):
            raise ValueError("'bindings' entries must all be string -> string")
        return IdMap(degraded=False, bindings=dict(bindings))
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError, AttributeError):
        return IdMap(degraded=True)
