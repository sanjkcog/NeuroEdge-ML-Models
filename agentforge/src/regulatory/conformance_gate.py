"""conformance_gate.py — the FR-05 conformance gate: HARD, no override (ADR-0009,
EP-01, US-01-05).

A wrapper, not an engine: this module adds only regulatory semantics on top of the
existing, unmodified `agentforge/src/state/gate_state.py`. It does not re-implement
gate mechanics, does not fork `gates.json`'s schema, and does not touch
`gate_state.py` at all.

`evaluate` exposes NO override / force / flag / bypass parameter — read its signature:
there is nothing to pass a bypass to. A gapful `conformance_result` can only ever
result in `BLOCKED`; the only accepted way out is the existing
`GateState.record_decision(artifact, "approved", identity=<reviewer>)`, which already
enforces a distinct-identity check (`SelfApprovalError`) before flipping status.
"""

from __future__ import annotations

from pathlib import Path

from gate_state import GateState  # bare import: the majority convention across
# agentforge/src (run_state, exchange_cli, ingestion, discover_plugins) — keeps a single
# module identity for gate_state so its SelfApprovalError is one class process-wide. Importing
# it here as `agentforge.src.state.gate_state` would mint a second, distinct class and make a
# cross-subsystem `except SelfApprovalError` silently miss (fail-open on the self-approval control).

BLOCKED = "BLOCKED"
PASS = "PASS"
CLEARED = "CLEARED"


def evaluate(
    conformance_result: dict,
    artifact: str,
    *,
    gates_path: str | Path,
    stage: str = "S-conformance",
    opened_by: str = "reformatter",
) -> str:
    """Open a hard gate when `conformance_result` reports any gap; otherwise pass.

    No override/force/flag parameter exists on this function — a caller cannot bypass
    a gapful result by any argument, config value, or agent assertion (AC-05.2, C-1).
    """
    path = Path(gates_path)
    status = conformance_result.get("status")

    if status == "gaps":
        state = GateState.load(path) if path.exists() else GateState.new()
        # Re-arm an existing gate with reopen_gate (preserves prior decisions) rather
        # than open_gate (which overwrites the Gate wholesale and would erase the
        # reviewer's audit trail on a second gapful evaluate of the same artifact).
        if artifact in state.gates:
            state.reopen_gate(artifact)
        else:
            state.open_gate(artifact, stage=stage, gate_type="hard", opened_by=opened_by)
        state.save(path)
        return BLOCKED

    return PASS


def is_cleared(artifact: str, *, gates_path: str | Path) -> bool:
    """True iff `artifact`'s gate exists and its status is exactly 'approved'.

    Absence of a gates file, absence of the artifact's gate, or any status other than
    'approved' (pending, changes_requested, rejected) all read as not-cleared.
    """
    path = Path(gates_path)
    if not path.exists():
        return False
    state = GateState.load(path)
    gate = state.gates.get(artifact)
    return gate is not None and gate.status == "approved"
