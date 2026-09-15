#!/usr/bin/env python3
"""playwright_runner.py — the Playwright tier-1 runner (EP-05, US-05-01/US-05-02).

Fixture-tested only — no live Playwright project exists in this repo or reachable
from it. `detect()`/`select()` are real; `execute()`'s subprocess call is mocked in
tests, mirroring the Zephyr-mocking precedent in `test_qa_adapter.py`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from runner import DetectResult, RunResult, glob_to_regex

_CONFIG_NAMES = ("playwright.config.ts", "playwright.config.js", "playwright.config.mjs")


class PlaywrightRunner:
    name = "playwright"

    def detect(self, root: Path) -> DetectResult:
        for config_name in _CONFIG_NAMES:
            config = root / config_name
            if config.is_file():
                return DetectResult(confidence=0.9, evidence=[str(config)])
        return DetectResult(confidence=0.0, evidence=[])

    def select(self, tc_ids: list[str]) -> list[str]:
        """Build a `--grep` regex from TC-ID glob patterns — an empty `tc_ids` means
        no filter (run everything)."""
        if not tc_ids:
            return []
        pattern = "|".join(glob_to_regex(tc_id) for tc_id in tc_ids)
        return ["--grep", pattern]

    def prepare(self) -> None:
        return None

    def execute(self, selector: list[str], junit_path: Path) -> RunResult:
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["npx", "playwright", "test", *selector, "--reporter=junit"]
        env = {**os.environ, "PLAYWRIGHT_JUNIT_OUTPUT_NAME": str(junit_path)}
        try:
            proc = subprocess.run(
                cmd, check=False, timeout=1800, capture_output=True, text=True, env=env
            )
        except FileNotFoundError:
            return RunResult(
                success=False,
                junit_xml_path=None,
                detail="npx (Node.js) is not on PATH — install Node before running Playwright tests.",
            )
        except subprocess.TimeoutExpired:
            return RunResult(
                success=False,
                junit_xml_path=None,
                detail=f"playwright test timed out after 1800s: {' '.join(cmd)}",
            )

        if proc.returncode != 0:
            return RunResult(
                success=False,
                junit_xml_path=junit_path if junit_path.is_file() else None,
                detail=f"playwright test exited {proc.returncode}: {proc.stdout[-2000:]}{proc.stderr[-2000:]}",
            )
        return RunResult(
            success=True,
            junit_xml_path=junit_path,
            detail=f"playwright test passed: {' '.join(cmd)}",
        )

    def collect(self, junit_path: Path) -> Path | None:
        return junit_path if junit_path.is_file() else None
