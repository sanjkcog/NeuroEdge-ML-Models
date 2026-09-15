#!/usr/bin/env python3
"""refresh.py — the PM-lane refresh (EP-08, US-08-05).

Scope-limited per pm-delivery-management.plan.md's Orchestrator scope note: the
stages are sequential in run_state.STAGE_SEQUENCE (S6 test-plan and S12 trace-matrix
included) and there is no concurrent dev/QA-lane-vs-PM-lane execution graph, so this
is a single callable a human or the orchestrator invokes after a stage transition —
not concurrency/branching machinery. The one contract this function must uphold regardless of who calls it:
`PM lane blocking the dev/QA lane = 0 occurrences` (US-08-05's own AC) is enforced at
the function level — `refresh()` can never raise, only report.

Folds the calling run's current cumulative usage into `sprint-NN.json` (ADR-0005's
run-archival workaround: run.json is a single active-run file, so the sprint container
is the durable record) and keeps a `## Sprint <id>` section in PROGRESS.md current,
extending the existing Done/In progress/Blocked/Next format rather than replacing it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from run_state import InvalidRunState, RunState
    from sprint_state import InvalidSprintState, SprintState
except ModuleNotFoundError:  # script mode — see the __main__ guard below
    import sys as _bootstrap_sys
    _bootstrap_src = Path(__file__).resolve().parents[1]
    for _bootstrap_p in (_bootstrap_src, _bootstrap_src / "state"):
        if str(_bootstrap_p) not in _bootstrap_sys.path:
            _bootstrap_sys.path.insert(0, str(_bootstrap_p))
    from run_state import InvalidRunState, RunState
    from sprint_state import InvalidSprintState, SprintState


@dataclass
class RefreshResult:
    success: bool
    reason: str = ""


def _total_usage(run: RunState) -> tuple[int, int, int, float]:
    tokens_in = sum(st.usage.tokens_in for st in run.stages.values())
    tokens_out = sum(st.usage.tokens_out for st in run.stages.values())
    api_calls = sum(st.usage.api_calls for st in run.stages.values())
    cost_usd = sum(st.usage.cost_usd for st in run.stages.values())
    return tokens_in, tokens_out, api_calls, cost_usd


def _render_section(sprint: SprintState, run: RunState) -> str:
    delivered = sum(1 for item in sprint.committed_items if item.status == "done")
    total = len(sprint.committed_items)
    stage = run.current_stage or "complete"
    return (
        f"## Sprint {sprint.sprint_id}\n"
        f"- **Done:** {delivered}/{total} committed items delivered\n"
        f"- **In progress:** {run.objective} (stage: {stage})\n"
        f"- **Blocked:** None\n"
        f"- **Next:** {sprint.remaining_capacity()} pts remaining of {sprint.capacity_points}\n"
    )


def _upsert_section(text: str, heading: str, section: str) -> str:
    """Replace an existing `## <heading>` section in place, or append one — never
    duplicates (a second refresh call must not grow the file unboundedly)."""
    marker = f"## {heading}"
    lines = text.split("\n")
    start = next((i for i, line in enumerate(lines) if line.strip() == marker), None)
    if start is None:
        sep = "" if text.endswith("\n") or not text else "\n"
        return text + sep + "\n" + section
    end = start + 1
    while end < len(lines) and not (lines[end].startswith("## ") and lines[end].strip() != marker):
        end += 1
    new_lines = lines[:start] + section.rstrip("\n").split("\n") + lines[end:]
    return "\n".join(new_lines)


def refresh(
    run_path: str | Path,
    sprint_path: str | Path,
    run_id: str,
    *,
    progress_path: str | Path,
) -> RefreshResult:
    """Fold `run_path`'s current usage into `sprint_path`'s container and refresh the
    matching PROGRESS.md section. Every failure mode is caught and returned — this
    function must never be the reason a caller's own stage transition fails."""
    try:
        run = RunState.load(run_path)
    except (FileNotFoundError, InvalidRunState) as exc:
        return RefreshResult(success=False, reason=f"could not load run.json: {exc}")

    try:
        sprint = SprintState.load(sprint_path)
    except FileNotFoundError:
        return RefreshResult(success=False, reason=f"no active sprint at {sprint_path}")
    except InvalidSprintState as exc:
        return RefreshResult(success=False, reason=f"could not load sprint container: {exc}")

    try:
        tokens_in, tokens_out, api_calls, cost_usd = _total_usage(run)
        # merge_run_snapshot (not record_run_snapshot + save): a sprint spans many
        # concurrent /agentforge runs by design (D23) — a plain load-modify-save
        # cycle silently drops a sibling run's snapshot if two refreshes race
        # (CRITICAL finding, code review). merge_run_snapshot re-reads on-disk state
        # immediately before writing instead of trusting this stale in-memory copy.
        sprint.merge_run_snapshot(
            sprint_path, run_id,
            last_stage=run.current_stage or (run.completed_stages[-1] if run.completed_stages else ""),
            tokens_in=tokens_in, tokens_out=tokens_out, api_calls=api_calls, cost_usd=cost_usd,
        )

        progress_path = Path(progress_path)
        existing = progress_path.read_text(encoding="utf-8") if progress_path.is_file() else "# Progress\n"
        updated = _upsert_section(existing, f"Sprint {sprint.sprint_id}", _render_section(sprint, run))
        # Atomic write — temp file + os.replace, mirrors every other state file in
        # this codebase (HIGH finding, code review: a direct write_text() here was
        # the one exception, risking a truncated PROGRESS.md on a crash mid-write).
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = progress_path.with_name(progress_path.name + ".tmp")
        tmp.write_text(updated, encoding="utf-8", newline="\n")
        os.replace(tmp, progress_path)
    except (OSError, UnicodeDecodeError, InvalidSprintState) as exc:
        return RefreshResult(success=False, reason=f"refresh write failed: {exc}")

    return RefreshResult(success=True)


# ---------------------------------------------------------------------------
# CLI (TD-017)
# ---------------------------------------------------------------------------
#
# refresh() was library-only, and that is precisely WHY it was never wired: the
# orchestrator drives every state transition through a bash CLI call, so a function
# with no command-line surface could not be invoked from the stage loop no matter how
# well it worked. Three command docs nonetheless described it as running on every
# dev/QA stage transition. This closes that gap in the direction that makes the docs
# true, rather than downgrading them to admit a gap.
#
# ALWAYS EXITS 0, including on failure. refresh()'s defining contract is "PM lane
# blocking the dev/QA lane = 0 occurrences" (US-08-05's own AC), enforced at the
# function level by never raising. A CLI that exited non-zero would reintroduce exactly
# that coupling one layer up: a missing sprint container would fail the orchestrator's
# stage bookkeeping. The reason is printed either way, so a real problem is visible
# without being fatal.

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Fold a run's usage into its sprint container and refresh PROGRESS.md.",
    )
    parser.add_argument("--run", required=True, help="Path to run.json")
    parser.add_argument("--sprint", required=True, help="Path to sprint-NN.json")
    parser.add_argument("--run-id", required=True, help="This run's id, as keyed in the sprint container")
    parser.add_argument("--progress", required=True, help="Path to PROGRESS.md")
    args = parser.parse_args(argv)

    result = refresh(args.run, args.sprint, args.run_id, progress_path=args.progress)
    if result.success:
        print(f"PM refresh: ok (PROGRESS.md + {args.sprint} updated)")
    else:
        print(f"PM refresh: skipped - {result.reason}")
    return 0


if __name__ == "__main__":
    # Script mode only. `from run_state import ...` at module level resolves because
    # the test harness pre-seeds sys.path; running this file directly it does not, so
    # seed it here rather than at import time (which would mutate sys.path for every
    # library consumer as a side effect). Mirrors discover_plugins.py's seam.
    import sys as _sys
    _src = Path(__file__).resolve().parents[1]
    for _p in (_src, _src / "state"):
        if str(_p) not in _sys.path:
            _sys.path.insert(0, str(_p))
    raise SystemExit(main())
