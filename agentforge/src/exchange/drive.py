#!/usr/bin/env python3
"""drive.py — apply_intent: THE HARD-GATE FENCE (ADR-0009 invariant, ADR-0012 EP-02).

The one code path that turns an inbound DriveIntent (parsed by an ExchangeAdapter from
an external agentic app) into a run_state/gate_state mutation. This is the single
load-bearing control the whole external-drive design depends on:

  * If `intent.target` names an artifact whose gate is pending AND type=="hard", the
    intent is refused outright — REGARDLESS of `intent.action` — before any dispatch
    on action even happens. `applied=False`, `blocked_on` names the artifact.
  * For the state-mutating `advance` action, whose `target` is a STAGE ID (not an artifact
    path), a second broad check refuses the advance while ANY hard gate is pending anywhere
    (`gate_state.any_pending()`). The per-target check above cannot match a stage id against
    artifact-keyed gates, so this second check is what actually holds the fence for advance.
  * `gate_state.record_decision(...)` is NEVER called anywhere in this module, for any
    action, against any gate — approving/resolving a gate is exclusively a human act
    via the main-session AskUserQuestion -> `gate_state decide` path (D1). This is not
    merely "never approves a hard gate"; this module has zero calls to
    record_decision at all, so there is no code path here that could ever be extended
    into one by accident.
  * All gate checks delegate to gate_state (`is_pending`, `.type`) — this module never
    re-implements gate semantics (COMPOSE_AT_BOUNDARY_ONLY, mirroring
    run_state._print_status's own run_state+gate_state composition).
  * An "advance" intent that clears the fence moves the run forward using run_state's
    own primitive (`enter_stage`), imported locally inside this function — `run_state`
    is never imported at module scope, so this module carries no import-time coupling
    to it. The spawn is recorded `spawned_by="external"` (ADR-0012 EP-02, the additive
    run_schema.json enum value) so audit can tell an external driver apart from a human
    or the orchestrator.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DriveOutcome:
    """The result of one apply_intent call. A refusal is a normal, expected outcome —
    never raised as an exception."""
    applied: bool
    blocked_on: str | None = None
    detail: str = ""


def apply_intent(run_state, gate_state, intent) -> DriveOutcome:
    """Apply one inbound DriveIntent against the authoritative state.

    `run_state`/`gate_state` are already-loaded RunState/GateState instances (compose-
    at-boundary — the caller, not this function, is responsible for loading them).
    """
    target = intent.target

    # THE FENCE — checked first, before any action dispatch, so it applies uniformly
    # to every action an external intent could carry, not only "approve_gate".
    if gate_state.is_pending(target):
        gate = gate_state.gates[target]
        if gate.type == "hard":
            return DriveOutcome(
                applied=False,
                blocked_on=target,
                detail=(
                    f"refused: {target!r} has a pending hard gate — only a recorded "
                    "human decision (gate_state decide, main session, D1) can clear it"
                ),
            )

    if intent.action == "approve_gate":
        # Reachable here only when there is no pending hard gate at `target` (the fence
        # above already refused that case). Even so, approving a gate is exclusively a
        # human act — this branch never calls gate_state.record_decision, for any gate
        # type, ever.
        return DriveOutcome(
            applied=False,
            detail=f"refused: external intents cannot approve gates ({target!r})",
        )

    if intent.action in ("request_run", "comment"):
        # ADR-0012 sprint-03, US-03-01, FR-05: tolerant orchestrator-observed signals.
        # Reachable only once the fence above has already cleared this exact target (no
        # pending hard gate) — a request_run/comment against a GATED target is refused
        # by that fence identically to advance/approve_gate, never reaching here
        # (test_request_run_and_comment_still_refused_against_a_pending_hard_gate).
        # Deliberately makes NO run_state/gate_state mutation: "the external agent never
        # mutates state directly — the orchestrator does" is satisfied here by the
        # orchestrator choosing to record/log this outcome (exchange_cli.apply's audit
        # trail, ADR-0012 US-03-04), not by this function writing to authoritative state.
        return DriveOutcome(
            applied=True,
            detail=(
                f"{intent.action} signal recorded for {target!r} "
                f"(identity={intent.identity!r}) — orchestrator-observed, no state mutation"
            ),
        )

    if intent.action != "advance":
        # Any action outside the DriveIntent enum this fence knows how to dispatch on —
        # tolerant no-op refusal, never a crash on an unrecognised action.
        return DriveOutcome(
            applied=False,
            detail=f"action {intent.action!r} is not applied by drive.apply_intent",
        )

    if target not in run_state.stages:
        return DriveOutcome(applied=False, detail=f"unknown stage {target!r}")

    # Broad fence for the one state-mutating action. An "advance" target is a STAGE ID,
    # but gates are keyed by ARTIFACT PATH — so the per-target is_pending() check above can
    # never match for advance (code-review CRITICAL, 2026-07-24). Refuse advancing the run
    # while ANY hard gate is pending anywhere, delegating to gate_state.any_pending() (which
    # already excludes soft gates) — the exact check the human orchestrator flow performs
    # (commands/agentforge.md gate-check step). Still never re-implements gate semantics.
    blocking = gate_state.any_pending()
    if blocking:
        return DriveOutcome(
            applied=False,
            blocked_on=blocking[0],
            detail=(
                f"refused: {blocking[0]!r} has a pending hard gate — advance is blocked "
                "until a recorded human decision (gate_state decide, main session, D1) clears it"
            ),
        )

    from run_state import enter_stage  # local import: drive.py depends on run_state,
    # never the reverse — mirrors exchange_record.py's boundary discipline.

    # ADR-0012 US-02-02: identity is stamped verbatim from the DriveIntent so an audit
    # can attribute WHO proposed this write, independent of (and never deriving)
    # spawned_by — a forged intent.identity=="human" still records spawned_by=="external".
    enter_stage(run_state, target, spawned_by="external", identity=intent.identity)
    return DriveOutcome(applied=True, detail=f"{target}: advanced (spawned_by=external)")
