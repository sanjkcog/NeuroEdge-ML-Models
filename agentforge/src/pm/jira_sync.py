#!/usr/bin/env python3
"""jira_sync.py — best-effort Jira push, never a hard dependency (EP-08, ADR-0005).

Mirrors agentforge/src/qa/zephyr_adapter.py's "never raise on network/tool failure"
discipline: every call is wrapped, and failure is returned as a SyncResult, never an
unhandled exception. Local sprint_state is always the caller's source of truth — these
functions never mutate the SprintState they're given, only read it to build a payload
(US-08-03's own failure-case AC: "a Jira write that fails leaves local sprint state
unchanged").

No `mcp-atlassian` client is imported here. `jira_tool` is an injected callable (the
Jira MCP tool, when the caller has one) so this module has no hard dependency on any
particular MCP wiring — OQ-6 (is a Jira MCP server actually available with sprint/
board/issue write ops?) is unresolved in this repo (ADR-0005); nothing here assumes
an answer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

from jira_config import JiraConfig
from sprint_state import SprintState


@dataclass
class SyncResult:
    success: bool
    reason: str = ""


def _read_only_payload(sprint: SprintState) -> dict:
    """A snapshot dict built WITHOUT calling sprint.to_dict() — to_dict() has a
    documented side effect (it stamps a fresh `self.updated` before returning, the
    same pattern gate_state.py/run_state.py use right before a save()). Calling it
    here for a push that might not even reach Jira would silently touch state this
    module promises never to mutate (code-review MEDIUM finding)."""
    return {
        "sprint_id": sprint.sprint_id,
        "status": sprint.status,
        "capacity_points": sprint.capacity_points,
        "committed_items": [asdict(item) for item in sprint.committed_items],
    }


def push_sprint_backlog(
    sprint: SprintState,
    config: JiraConfig,
    *,
    jira_tool: Callable[[dict], None] | None = None,
) -> SyncResult:
    """Push the sprint's committed items to Jira. Read-only against `sprint` — never
    mutates it, so a failed push cannot half-apply local state (US-08-03)."""
    if not config.is_configured():
        return SyncResult(success=False, reason="Jira not configured — repo-local only (OQ-7)")
    if jira_tool is None:
        return SyncResult(success=False, reason="no Jira tool available — repo-local only")
    try:
        jira_tool(_read_only_payload(sprint))
    except Exception as exc:  # noqa: BLE001 — must never escape, only report (D12)
        return SyncResult(success=False, reason=str(exc))
    return SyncResult(success=True)


def push_issue_status(
    item_id: str,
    status: str,
    *,
    config: JiraConfig,
    jira_tool: Callable[[str, str], None] | None = None,
) -> SyncResult:
    """Push a single committed item's status transition to Jira."""
    if not config.is_configured():
        return SyncResult(success=False, reason="Jira not configured — repo-local only (OQ-7)")
    if jira_tool is None:
        return SyncResult(success=False, reason="no Jira tool available — repo-local only")
    try:
        jira_tool(item_id, status)
    except Exception as exc:  # noqa: BLE001 — must never escape, only report (D12)
        return SyncResult(success=False, reason=str(exc))
    return SyncResult(success=True)
