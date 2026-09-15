"""Validates hook scripts referenced in .claude/settings.json are present on disk."""

from __future__ import annotations

import json
import re
from pathlib import Path

from health_check.checkers.base import CheckResult, Status

_LOCAL_SCRIPT = re.compile(r'scripts/hooks/[\w\-\.]+\.js')


def check(root: Path) -> CheckResult:
    settings_file = root / ".claude" / "settings.json"

    if not settings_file.exists():
        return CheckResult("hooks", Status.WARN, ".claude/settings.json not found — no hooks configured")

    try:
        data = json.loads(settings_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CheckResult("hooks", Status.FAIL, ".claude/settings.json is not valid JSON", [str(exc)])

    hooks_block = data.get("hooks", {})
    if not hooks_block:
        return CheckResult("hooks", Status.WARN, "No hooks defined in .claude/settings.json")

    hook_entries: list[dict] = []
    for event_name, event_hooks in hooks_block.items():
        if not isinstance(event_hooks, list):
            continue
        for group in event_hooks:
            group_id = group.get("id", "<no-id>")
            for hook in group.get("hooks", []):
                hook_entries.append({"group_id": group_id, "event": event_name, **hook})

    missing: list[str] = []
    for hook in hook_entries:
        cmd = hook.get("command", "")
        if "${" in cmd:  # skip ECC / external plugin commands
            continue
        for match in _LOCAL_SCRIPT.findall(cmd):
            if not (root / match).exists():
                missing.append(f"[{hook['group_id']}] missing: {match}")

    total = len(hook_entries)
    if missing:
        return CheckResult(
            "hooks", Status.WARN,
            f"{total} hook(s) configured — {len(missing)} local script(s) missing",
            missing,
        )
    return CheckResult("hooks", Status.PASS, f"{total} hook(s) configured, all local scripts present")
