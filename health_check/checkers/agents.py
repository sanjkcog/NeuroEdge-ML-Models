"""Validates agent definition files in .claude/agents/."""

from __future__ import annotations

from pathlib import Path

from health_check.checkers.base import CheckResult, Status


def _has_frontmatter(content: str) -> bool:
    lines = content.splitlines()
    return bool(lines) and lines[0].strip() == "---"


def _validate_one(path: Path) -> list[str]:
    errors: list[str] = []
    content = path.read_text(encoding="utf-8-sig").strip()

    if not content:
        return [f"{path.name}: file is empty"]

    if _has_frontmatter(content):
        # YAML frontmatter format — Claude Code native agent discovery
        if "name:" not in content:
            errors.append(f"{path.name}: YAML frontmatter missing 'name:' field")
        if "description:" not in content:
            errors.append(f"{path.name}: YAML frontmatter missing 'description:' field")
    else:
        # Legacy H1 prose format
        if not [l for l in content.splitlines() if l.startswith("# ")]:
            errors.append(f"{path.name}: missing H1 heading (agent name)")
        if not any(kw in content.lower() for kw in ("role", "responsibilities", "when to use", "trigger")):
            errors.append(f"{path.name}: no required section (role / responsibilities / when to use / trigger)")

    return errors


def check(root: Path) -> CheckResult:
    agents_dir = root / ".claude" / "agents"

    if not agents_dir.exists():
        return CheckResult("agents", Status.WARN, ".claude/agents/ not found — run install.py first")

    agent_files = [f for f in sorted(agents_dir.glob("*.md")) if f.name != "README.md"]
    if not agent_files:
        return CheckResult("agents", Status.WARN, "No agent files in .claude/agents/ — run install.py first")

    all_errors: list[str] = []
    for af in agent_files:
        all_errors.extend(_validate_one(af))

    if all_errors:
        return CheckResult(
            "agents", Status.WARN,
            f"{len(agent_files)} agent file(s) — {len(all_errors)} format issue(s)",
            all_errors,
        )
    return CheckResult("agents", Status.PASS, f"{len(agent_files)} agent file(s) active in .claude/agents/")
