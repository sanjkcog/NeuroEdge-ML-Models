#!/usr/bin/env python3
"""
NeuroEdge Assets Health Check — verifies that assets are correctly installed.

Usage (from project root after running install.py):
    python health_check/cli.py
    python health_check/cli.py --only hooks,skills
    python health_check/cli.py --verbose
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow `python health_check/cli.py` to resolve `health_check.*` imports
# regardless of PYTHONPATH by inserting the project root on sys.path.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from health_check.checkers import agents, hooks, memory, skills, tools
from health_check.checkers.base import CheckResult, Status

ROOT = Path.cwd()
ALL_CHECKERS = ["hooks", "skills", "agents", "memory", "tools"]
_WIDTH = 54


def _run(only: list[str]) -> list[CheckResult]:
    results: list[CheckResult] = []
    if "hooks" in only:
        results.append(hooks.check(ROOT))
    if "skills" in only:
        results.append(skills.check(ROOT))
    if "agents" in only:
        results.append(agents.check(ROOT))
    if "memory" in only:
        results.append(memory.check(ROOT))
    if "tools" in only:
        results.append(tools.check(ROOT))
    return results


def _report(results: list[CheckResult], verbose: bool) -> None:
    print("\n" + "═" * _WIDTH)
    print("  NeuroEdge Assets — Health Check")
    print("═" * _WIDTH)

    for r in results:
        badge = f"[{r.status.value}]"
        print(f"  {badge:<8}  {r.name:<10}  {r.summary}")
        if verbose and r.issues:
            for issue in r.issues[:10]:
                print(f"             {issue}")
            if len(r.issues) > 10:
                print(f"             … and {len(r.issues) - 10} more")

    print("─" * _WIDTH)

    fails  = [r for r in results if r.status == Status.FAIL]
    warns  = [r for r in results if r.status == Status.WARN]
    passes = [r for r in results if r.status == Status.PASS]

    if fails:
        overall = f"[{Status.FAIL.value}]"
    elif warns:
        overall = f"[{Status.WARN.value}]"
    else:
        overall = f"[{Status.PASS.value}]"

    detail = f"{len(passes)} passed, {len(warns)} warned, {len(fails)} failed"
    print(f"  {overall:<8}  {'overall':<10}  {detail}")
    print("═" * _WIDTH)

    if warns or fails:
        print()
        print("  Next steps:")
        print("  1. Re-run: python agentic-assets/patch_assets.py")
        print("  2. Re-run: python agentic-assets/install.py --project .")
        print("  3. Restart Claude Code")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify NeuroEdge AgentForge are correctly installed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Checkers: {', '.join(ALL_CHECKERS)}",
    )
    parser.add_argument(
        "--only", default=",".join(ALL_CHECKERS),
        help="Comma-separated checkers to run (default: all)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show individual issues")
    args = parser.parse_args()

    requested = [c.strip() for c in args.only.split(",") if c.strip()]
    unknown = [c for c in requested if c not in ALL_CHECKERS]
    if unknown:
        print(f"[ERROR] Unknown checker(s): {unknown}. Valid: {ALL_CHECKERS}", file=sys.stderr)
        return 1

    results = _run(requested)
    _report(results, verbose=args.verbose)
    return 1 if any(r.status == Status.FAIL for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
