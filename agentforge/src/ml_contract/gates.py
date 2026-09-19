"""The ml_contract tools' one way to touch ``<dest>/gates.json`` (ADR-0025).

Intake, review and audit each *open* a gate for the human; only the audit ever *decides* one, and
only when it found nothing that fails (an automatic gate, like the M1 licence gate). Every human
decision still goes through ``gate_state.py decide`` from the orchestrator's AskUserQuestion.
"""
from __future__ import annotations

import os

from ..state import gate_state

GATES_FILE = "gates.json"
AUTOMATIC_IDENTITY = "usecase-audit (automatic)"


def _path(dest: str) -> str:
    return os.path.join(dest, GATES_FILE)


def _load(dest: str) -> gate_state.GateState:
    path = _path(dest)
    return gate_state.GateState.load(path) if os.path.exists(path) else gate_state.GateState.new()


def open_pending(dest: str, gate_id: str, *, stage: str, opened_by: str) -> str:
    """Open ``gate_id`` for a human decision, or re-arm it when it exists. Returns what was done.

    Re-arming keeps the decision history (gate_state.reopen_gate), so an earlier approval of a
    superseded input stays on the record beside the new pending one.
    """
    state = _load(dest)
    if gate_id in state.gates:
        state.reopen_gate(gate_id)
        state.gates[gate_id].stage = stage
        action = "re-opened"
    else:
        state.open_gate(gate_id, stage=stage, gate_type="hard", opened_by=opened_by)
        action = "opened"
    state.save(_path(dest))
    return action


def reopen_if_present(dest: str, gate_ids: list[str] | tuple[str, ...]) -> list[str]:
    """Re-arm each of ``gate_ids`` that already exists. Returns the ids re-armed.

    Used when a source an audit compared has changed: the audit's approval was computed against the
    old source, so it must not keep satisfying the stage (ADR-0025 D-4). Gates that were never opened
    are left alone; the audit opens them when it first runs.
    """
    path = _path(dest)
    if not os.path.exists(path):
        return []
    state = gate_state.GateState.load(path)
    reopened = [g for g in gate_ids if g in state.gates and state.gates[g].status != "pending"]
    for g in reopened:
        state.reopen_gate(g)
    if reopened:
        state.save(path)
    return reopened


def record_automatic(dest: str, gate_id: str, *, stage: str, passed: bool, reason: str) -> str:
    """The audit's gate: approved automatically when nothing failed, otherwise left pending.

    A failing audit never records a rejection on the human's behalf; it leaves the gate pending,
    and the human either fixes the source and re-runs the audit or approves a documented deviation.
    """
    state = _load(dest)
    if gate_id in state.gates:
        state.reopen_gate(gate_id)
        state.gates[gate_id].stage = stage
    else:
        # opened_by is left empty: the audit that opens the gate may also be the one that clears it.
        state.open_gate(gate_id, stage=stage, gate_type="hard")
    if passed:
        state.record_decision(gate_id, "approved", identity=AUTOMATIC_IDENTITY, reason=reason)
        outcome = "approved (automatic)"
    else:
        outcome = "pending (needs a human decision)"
    state.save(_path(dest))
    return outcome
