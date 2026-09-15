"""Validates installed slash commands and referenced AgentForge skills."""

from __future__ import annotations

import re
from pathlib import Path

from health_check.checkers.base import CheckResult, Status

_SKILL_REF = re.compile(r"agentic-assets/skills/[^\s`)>\"]+\.md")


def _validate_one(path: Path) -> list[str]:
    errors: list[str] = []
    content = path.read_text(encoding="utf-8-sig").strip()  # utf-8-sig strips BOM

    if not content:
        return [f"{path.name}: file is empty"]

    lines = content.splitlines()
    uses_frontmatter = lines[0].strip() == "---"

    if not uses_frontmatter:
        if not [l for l in lines if l.startswith("# ")]:
            errors.append(f"{path.name}: missing top-level H1 heading")
        if not [l for l in lines if l.startswith("## ")]:
            errors.append(f"{path.name}: no H2 sections — skill has no steps")

    if "$ARGUMENTS" not in content and "argument" in content.lower():
        errors.append(f"{path.name}: mentions 'argument' but $ARGUMENTS placeholder is missing")

    return errors


def _find_skill_reference_errors(root: Path) -> list[str]:
    """Verify every agentic-assets/skills/... reference resolves in the target project."""
    errors: list[str] = []
    search_roots = [root / ".claude" / "commands", root / ".claude" / "agents"]
    for search_root in search_roots:
        if not search_root.exists():
            continue
        for path in sorted(search_root.rglob("*.md")):
            content = path.read_text(encoding="utf-8-sig")
            for ref in sorted(set(_SKILL_REF.findall(content))):
                if not (root / ref).exists():
                    rel = path.relative_to(root)
                    errors.append(f"{rel}: missing referenced skill {ref}")
    return errors


def check(root: Path) -> CheckResult:
    commands_dir = root / ".claude" / "commands"

    if not commands_dir.exists():
        return CheckResult("skills", Status.WARN, ".claude/commands/ not found — run install.py first")

    skill_files = sorted(commands_dir.rglob("*.md"))
    if not skill_files:
        return CheckResult("skills", Status.WARN, "No skill files in .claude/commands/")

    all_errors: list[str] = []
    for sf in skill_files:
        all_errors.extend(_validate_one(sf))
    all_errors.extend(_find_skill_reference_errors(root))

    names = ", ".join(f.stem for f in skill_files)
    if all_errors:
        return CheckResult("skills", Status.FAIL, f"{len(skill_files)} skill(s) — {len(all_errors)} error(s)", all_errors)
    return CheckResult("skills", Status.PASS, f"{len(skill_files)} skill(s) valid ({names})")
