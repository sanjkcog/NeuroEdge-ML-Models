"""Validates the AgentForge memory-bank bootstrap."""

from __future__ import annotations

from pathlib import Path

from health_check.checkers.base import CheckResult, Status

_REQUIRED_FILES = [
    "CLAUDE.md",
    "AGENTS.md",
    "docs/context/ACTIVE.md",
    "docs/context/PROGRESS.md",
    "docs/context/REPO_MAP.md",
    "docs/decisions/ADR-0000-template.md",
]

_OPTIONAL_FILES = [
    "docs/context/OPEN_QUESTIONS.md",
    "docs/context/GLOSSARY.md",
]

_IGNORE_LINES = [
    ".claude/settings.local.json",
    ".claude/.ts-edited-files",
]


def check(root: Path) -> CheckResult:
    missing = [path for path in _REQUIRED_FILES if not (root / path).exists()]
    optional_missing = [path for path in _OPTIONAL_FILES if not (root / path).exists()]

    gitignore = root / ".gitignore"
    ignore_issues: list[str] = []
    if gitignore.exists():
        lines = {line.strip() for line in gitignore.read_text(encoding="utf-8").splitlines()}
        ignore_issues = [line for line in _IGNORE_LINES if line not in lines]
    else:
        ignore_issues = _IGNORE_LINES.copy()

    issues = [f"missing memory file: {path}" for path in missing]
    issues.extend(f"missing optional memory file: {path}" for path in optional_missing)
    issues.extend(f".gitignore missing: {line}" for line in ignore_issues)

    if missing or ignore_issues:
        return CheckResult(
            "memory",
            Status.FAIL,
            f"{len(missing)} required memory file(s) missing, {len(ignore_issues)} ignore rule(s) missing",
            issues,
        )

    if optional_missing:
        return CheckResult(
            "memory",
            Status.WARN,
            f"required memory bank ready; {len(optional_missing)} optional file(s) missing",
            issues,
        )

    return CheckResult("memory", Status.PASS, "memory bank files and local ignore rules present")
