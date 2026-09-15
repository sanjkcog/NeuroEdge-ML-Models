#!/usr/bin/env python3
"""audit_gates.py — approval-rate audit over gates.json (TS-02-02-07).

Reports approval_rate: approved gates / total gates ever opened (AC-4: target 100%,
a calibration target per the PRD, not a committed SLO). D3's PR-gate warn-with-override
was reversed (S13 review is now a plain hard gate, no bypass) — there is no longer a
sanctioned "overridden without approval" case to audit for, so that figure was removed
along with the mechanism it measured, not left dangling as dead output.

Limitation, stated here rather than implied away: this can only see what's recorded in
gates.json. A write that bypassed pre-write-hitl-gate.js entirely (e.g. a direct
filesystem edit outside Claude Code) leaves no trace here. This measures recorded
compliance, not absolute prevention — prevention is pre-write-hitl-gate.js's fail-closed
behaviour (Task 7), not this audit.

Usage:
    uv run python agentforge/src/audit_gates.py [--path gates.json]

    In a real run the ledger lives in the objective folder, so pass it explicitly:
    --path <docs root>/project_related/<objective-slug>/03-execution-plan/gates.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "state"))
from gate_state import GateState, InvalidGateState, audit  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit gates.json approval compliance.")
    parser.add_argument("--path", default="gates.json", help="Path to gates.json")
    args = parser.parse_args(argv)

    path = Path(args.path)
    if not path.exists():
        print(f"No gates.json at {path} — nothing to audit.")
        return 0

    try:
        state = GateState.load(path)
    except InvalidGateState as exc:
        print(exc)
        return 1

    report = audit(state)
    print(f"total_gates:          {report.total_gates}")
    print(f"approved:             {report.approved_count}")
    print(f"approval_rate:        {report.approval_rate:.2%}  (AC-4 target: 100%, calibration)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
