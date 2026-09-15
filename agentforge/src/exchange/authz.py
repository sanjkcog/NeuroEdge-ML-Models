#!/usr/bin/env python3
"""authz.py — inbound drive intent authorization (ADR-0012 sprint-03, US-03-02, FR-10,
OQ-2 config allowlist).

`authorize(config, intent)` is the SECURITY FOUNDATION for accepting any inbound
non-gate action: an intent whose `identity` is not allowlisted in
`ExchangeConfig.drivers` for its `action` is REJECTED here, BEFORE the orchestrator ever
calls `drive.apply_intent` (exchange_cli.apply composes the two at the boundary — this
module never imports drive.py or gate_state, and has no way to see a gate at all).

Deliberately decoupled from GitHub repo write access ("can write the repo" != "authorized
to drive") and deliberately decoupled from drive.py's hard-gate fence, which stays
independent and absolute (OQ-2, ADR-0012's whole-point guardrail): this module governs
only whether an identity may attempt a NON-GATE action — an allowlisted 'advance'
permission grants nothing against a pending hard gate, because authorize() never touches
gate_state and apply_intent's fence never consults this module (see
test_exchange_drive.py's adversarial proof of that independence).

Result-object-never-raise (mirrors adapter.py/qa/adapter.py): authorize() always returns
an AuthorizationResult, never raises — a missing/malformed drivers entry is a normal,
expected refusal, not an exception the caller must catch.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AuthorizationResult:
    """The outcome of one authorization check. Never raised — always this."""
    authorized: bool
    detail: str = ""


def authorize(config, intent) -> AuthorizationResult:
    """Check `intent` against `config.drivers` (identity -> permitted actions).

    `config` is an already-loaded ExchangeConfig (compose-at-boundary — the caller
    loads it); `intent` is a DriveIntent already parsed by an adapter. An empty/
    whitespace-only identity is refused outright — an unattributed intent is never
    authorized for anything, mirroring gate_state.record_decision's own identity guard.
    Fail-closed throughout: an unknown identity, an identity with no allowlist entry at
    all, or a malformed (non-list) allowlist entry are all refused, never defaulted to
    "allowed".
    """
    identity = (intent.identity or "").strip()
    if not identity:
        return AuthorizationResult(
            False, "refused: intent has no identity (unattributed) — cannot be authorized"
        )

    permitted = config.drivers.get(identity)
    if not isinstance(permitted, list) or not permitted:
        return AuthorizationResult(
            False, f"refused: identity {identity!r} is not in the drivers allowlist"
        )

    if intent.action not in permitted:
        return AuthorizationResult(
            False,
            f"refused: identity {identity!r} is not authorized for action "
            f"{intent.action!r} (permitted: {sorted(permitted)})",
        )

    return AuthorizationResult(True, f"authorized: identity {identity!r} may {intent.action!r}")
