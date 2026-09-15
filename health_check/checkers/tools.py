"""Reports software AgentForge features need that pip cannot install (ADR-0020 D-3).

Python packages are declared and reached from agentic-assets/requirements-agentforge.txt. What is
left is software a person installs themselves -- this checker only looks for it on PATH and names
the feature each tool serves. It installs nothing.

Warn-only by design: every tool here serves an optional feature (hooks, PRs, video rendering), so
a missing one is a WARN naming that feature, never a FAIL that would block a healthy install.
An MQTT broker is not checked: it can run on another machine, so its absence locally proves nothing.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from health_check.checkers.base import CheckResult, Status

#: (executable, what needs it). Order is the order they are reported in.
TOOLS: tuple[tuple[str, str], ...] = (
    ("node", "Claude Code hooks in scripts/hooks/"),
    ("git", "commits, update and clean"),
    ("gh", "the PR workflow (/prp-pr)"),
    ("ffmpeg", "marketing video render (or set FFMPEG_BIN)"),
    ("ffprobe", "marketing video render (or set FFMPEG_BIN)"),
)

_FFMPEG_BIN_ENV = "FFMPEG_BIN"


def _found(tool: str) -> bool:
    """On PATH -- or, for ffmpeg/ffprobe, where FFMPEG_BIN points.

    Mirrors ``neuroedge_marketing.assembler.resolve_ffmpeg``: FFMPEG_BIN may name the folder or
    one of the two binaries, and the other binary is its sibling. Re-implemented rather than
    imported, because the health checker must run in a target whose Python deps are not installed.
    """
    if tool in ("ffmpeg", "ffprobe"):
        configured = os.environ.get(_FFMPEG_BIN_ENV, "").strip().strip('"')
        if configured:
            candidate = Path(configured)
            if candidate.is_dir():
                if shutil.which(tool, path=str(candidate)):
                    return True
            elif (candidate.parent / f"{tool}{candidate.suffix}").is_file():
                return True
    return shutil.which(tool) is not None


def check(root: Path) -> CheckResult:  # noqa: ARG001 -- same signature as every checker
    missing = [f"{tool} not found -- needed for {purpose}" for tool, purpose in TOOLS if not _found(tool)]
    if missing:
        return CheckResult(
            "tools",
            Status.WARN,
            f"{len(TOOLS) - len(missing)}/{len(TOOLS)} non-pip tools found -- install the rest yourself",
            missing,
        )
    return CheckResult("tools", Status.PASS, f"all {len(TOOLS)} non-pip tools found on PATH")
