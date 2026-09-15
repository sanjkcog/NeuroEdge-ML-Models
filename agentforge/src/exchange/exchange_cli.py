#!/usr/bin/env python3
"""exchange_cli.py — export / import-intents / apply subcommands for the Git exchange
substrate (ADR-0012, LLD §3.6).

Mirrors state/run_state.py's main(): argparse + exit-code discipline is deliberately
the same shape a caller already knows from run_state.py --help — 0 on success, 1 on a
load/validation error, and a dedicated BLOCKED(=3) exit code (the same value as
run_state.RESUME_BLOCKED_BY_GATE, for the same reason: "state is fine, a human is
needed" is distinct from "something is actually broken") when `apply` pulls an intent
that the hard-gate fence (exchange.drive.apply_intent) refuses.

Nothing here re-implements gate semantics or ever calls gate_state.record_decision —
`apply` delegates every mutation exclusively to drive.apply_intent (COMPOSE_AT_BOUNDARY,
mirroring the rest of this package).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Production-safety net: run_state.py / gate_state.py live in a sibling directory
# (agentforge/src/state/), and this module imports its own package as `exchange.*`, which
# resolves only when agentforge/src/ itself is importable. pytest's conftest already puts
# both on sys.path for every test in this suite; this bootstrap makes a direct, standalone
# invocation (`python agentforge/src/exchange/exchange_cli.py ...`) work identically,
# without requiring the caller to set PYTHONPATH by hand. Before agentforge/src/ was added
# here, that direct invocation died with `ModuleNotFoundError: No module named 'exchange'`.
_SRC_DIR = Path(__file__).resolve().parent.parent
_STATE_DIR = _SRC_DIR / "state"
for _bootstrap_dir in (_STATE_DIR, _SRC_DIR):
    if str(_bootstrap_dir) not in sys.path:
        sys.path.insert(0, str(_bootstrap_dir))

from exchange.audit_log import AuditLog
from exchange.authz import authorize
from exchange.config import ExchangeConfig
from exchange.drive import apply_intent
from exchange.exchange_record import build
from exchange.ledger import AppliedIntentLedger

# Exit code for "apply ran, but a hard gate refused at least one intent" — mirrors
# run_state.RESUME_BLOCKED_BY_GATE (=3).
BLOCKED = 3


def _load_run_and_gate_state(run_path: Path, gates_path: Path):
    import gate_state
    import run_state

    run = run_state.RunState.load(run_path)
    gstate = gate_state.GateState.load(gates_path) if gates_path.exists() else gate_state.GateState.new()
    return run, gstate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export/pull/apply the Git exchange substrate (ADR-0012)."
    )
    parser.add_argument("--run-path", default="run.json", help="Path to run.json (default: run.json)")
    parser.add_argument("--gates-path", default="gates.json", help="Path to gates.json (default: gates.json)")
    parser.add_argument(
        "--record-path", default="exchange.json",
        help="Path to build/save the exchange record at (default: exchange.json)",
    )
    parser.add_argument(
        "--config-path", default="exchange_config.json",
        help="Path to the persisted ExchangeConfig choice + drivers allowlist (default: exchange_config.json)",
    )
    parser.add_argument(
        "--ledger-path", default="exchange_ledger.json",
        help="Path to the applied-intents idempotency ledger, `apply` only (default: exchange_ledger.json)",
    )
    parser.add_argument(
        "--audit-path", default="exchange_audit.json",
        help="Path to the inbound-intent provenance audit trail, `apply` only (default: exchange_audit.json)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("export", help="Build the exchange record from run.json/gates.json, save it, and push it")
    sub.add_parser("import-intents", help="Pull inbound drive intents and print them")
    sub.add_parser("apply", help="Pull inbound drive intents and apply each through the hard-gate fence")

    args = parser.parse_args(argv)
    run_path = Path(args.run_path)
    gates_path = Path(args.gates_path)
    record_path = Path(args.record_path)
    config_path = Path(args.config_path)

    if not run_path.exists():
        print(f"No run.json at {run_path} — run 'python state/run_state.py init' first.")
        return 1

    import gate_state
    import run_state

    try:
        run, gstate = _load_run_and_gate_state(run_path, gates_path)
    except run_state.InvalidRunState as exc:
        print(exc)
        return 1
    except gate_state.InvalidGateState as exc:
        print(exc)
        return 1

    config = ExchangeConfig.load(config_path)
    adapter = config.get_adapter()

    if args.cmd == "export":
        record = build(run, gstate)
        record.save(record_path)
        result = adapter.push(record_path)
        status = "pushed" if result.success else "push failed"
        print(f"exported: {record_path} ({status}: {result.detail})")
        return 0

    if args.cmd == "import-intents":
        pulled = adapter.pull_intents()
        if not pulled.success:
            print(f"pull failed: {pulled.detail}")
            return 1
        if not pulled.intents:
            print("no inbound intents.")
        for intent in pulled.intents:
            print(f"{intent.raw_id}: {intent.action} {intent.target} (by {intent.identity})")
        return 0

    # apply — ADR-0012 sprint-03 (EP-03 inbound drive): pull -> authorize -> execute ->
    # re-project. Composed here, at the CLI boundary, exactly like every other
    # cross-module composition in this package (COMPOSE_AT_BOUNDARY_ONLY) — none of
    # authz.py / ledger.py / audit_log.py / drive.py know about each other.
    ledger_path = Path(args.ledger_path)
    audit_path = Path(args.audit_path)
    ledger = AppliedIntentLedger.load(ledger_path)
    audit_log = AuditLog.load(audit_path)

    pulled = adapter.pull_intents()
    if not pulled.success:
        print(f"pull failed: {pulled.detail}")
        return 1

    blocked = False
    for intent in pulled.intents:
        # US-03-02 / FR-10 (the security foundation, checked FIRST, before
        # drive.apply_intent is ever called): an unauthorized or unattributed intent
        # never reaches the fence at all. This is a SEPARATE, decoupled concern from
        # the hard-gate fence — see drive.py's own docstring and
        # test_exchange_drive.py's adversarial proof that an allowlisted 'advance'
        # still cannot clear a pending hard gate; authorization only ever narrows what
        # reaches the fence, it can never widen it.
        auth = authorize(config, intent)
        if not auth.authorized:
            audit_log.record(intent, outcome="unauthorized", detail=auth.detail)
            print(f"{intent.raw_id}: rejected (unauthorized) — {auth.detail}")
            continue

        # US-03-03 / FR-08: idempotent at-most-once. A raw_id already recorded as
        # applied is never re-run through apply_intent — the ledger, not a second call
        # into apply_intent, is what makes a replay a no-op.
        if ledger.has_applied(intent.raw_id):
            audit_log.record(
                intent, outcome="skipped_replay",
                detail="already applied — idempotent, executed at most once",
            )
            print(f"{intent.raw_id}: skipped — already applied (idempotent)")
            continue

        outcome = apply_intent(run, gstate, intent)
        state_word = "applied" if outcome.applied else "refused"
        print(f"{intent.raw_id}: {state_word} — {outcome.detail}")
        if outcome.applied:
            ledger.mark_applied(intent.raw_id)
        # US-03-04 / FR-09: every ingested intent gets one audit entry — applied,
        # refused (by the fence), unauthorized, or skipped as a replay — never
        # silently dropped.
        audit_log.record(intent, outcome=state_word, detail=outcome.detail)
        if not outcome.applied and outcome.blocked_on:
            blocked = True

    run.save(run_path)
    gstate.save(gates_path)
    ledger.save(ledger_path)
    audit_log.save(audit_path)

    # Re-project (US-03-01): rebuild the outbound record from the just-applied state so
    # an external observer's NEXT poll sees the result of what it drove, closing the
    # pull -> authorize -> execute -> re-project loop.
    record = build(run, gstate)
    record.save(record_path)
    adapter.push(record_path)

    return BLOCKED if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
