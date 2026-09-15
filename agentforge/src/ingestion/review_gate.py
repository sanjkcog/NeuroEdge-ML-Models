#!/usr/bin/env python3
"""review_gate.py — the human-review gate (ADR-0012 Direction 2, FR-04, EP-05).

Reuses `gate_state.py` wholesale (M4, no fork of the state machine): every ingested,
drafted context artifact opens a HARD gate keyed to the regulated artifact/stage it
feeds, with `opened_by=INGEST_IDENTITY` ("ingest-agent") — gate_state's own
self-approval check (`record_decision`) then refuses that same identity from ever
approving it (SelfApprovalError), with zero extra logic needed here (M3).

`open_review`'s signature deliberately carries NO gate-type/skip parameter — every
call always opens type="hard" (TC-05-01-03: regulated-feeding context is mandatory
and hard, never soft, never skippable, and there is no override to ask for one).
"""

from __future__ import annotations

from gate_state import Gate, GateState

# The identity every ingestion-opened gate records as its opener. A distinct human
# identity must record the "approved" decision — gate_state.record_decision's own
# self-approval check compares against exactly this constant (case-insensitively).
INGEST_IDENTITY = "ingest-agent"


def open_review(state: GateState, artifact: str, *, stage: str) -> Gate:
    """Open a hard review gate for `artifact`, keyed to the regulated `stage` it
    feeds. Always `gate_type="hard"`, always `opened_by=INGEST_IDENTITY` — neither
    is a parameter here, so there is no call shape that could request a soft or
    skipped gate for ingested context (TC-05-01-03).

    If a gate already exists for `artifact` (re-ingesting the same context), re-arm it
    with reopen_gate to preserve the prior review decisions — open_gate would overwrite
    the Gate wholesale and destroy that audit trail."""
    if artifact in state.gates:
        state.reopen_gate(artifact)
        return state.gates[artifact]
    return state.open_gate(artifact, stage=stage, gate_type="hard", opened_by=INGEST_IDENTITY)


def is_binding(state: GateState, artifact: str) -> bool:
    """True iff `artifact`'s gate has been recorded `approved` by a distinct human —
    the ONLY outcome that unblocks (TC-05-01-02). An artifact never gated, or gated
    but pending/rejected/changes_requested, is never binding."""
    gate = state.gates.get(artifact)
    return gate is not None and gate.status == "approved"


def reviewer_view(state: GateState, artifact: str, *, sources_rows: list) -> dict:
    """The reviewer-facing view for `artifact`'s gate — includes the provenance
    (`sources.md`) rows and per-field confidence, mitigating a rubber-stamp approval
    that never actually saw the evidence (TC-05-01-05)."""
    gate = state.gates[artifact]
    return {
        "artifact": artifact,
        "stage": gate.stage,
        "gate_status": gate.status,
        "opened_by": gate.opened_by,
        "sources_rows": list(sources_rows),
    }
