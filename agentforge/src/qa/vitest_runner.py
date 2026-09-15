#!/usr/bin/env python3
"""vitest_runner.py — the Vitest tier-1 runner (EP-05, US-05-01/US-05-02).

Fixture-tested only. `detect()` checks both `vitest.config.{ts,js,mjs}` and a
`vitest` devDependency in `package.json` — when both signals are present this is
still ONE confident detection (`max`, never summed/double-counted). This repo's own
Node tests use the built-in `node:test` runner, not Vitest — `node --test` is out of
scope for this plan (no story requests it); do not conflate the two.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from runner import DetectResult, RunResult, glob_to_regex

_CONFIG_NAMES = ("vitest.config.ts", "vitest.config.js", "vitest.config.mjs")


class VitestRunner:
    name = "vitest"

    def detect(self, root: Path) -> DetectResult:
        confidence = 0.0
        evidence: list[str] = []

        for config_name in _CONFIG_NAMES:
            config = root / config_name
            if config.is_file():
                confidence = max(confidence, 0.9)
                evidence.append(str(config))
                break

        package_json = root / "package.json"
        if package_json.is_file():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if "vitest" in deps:
                confidence = max(confidence, 0.7)
                evidence.append(f"{package_json} devDependency 'vitest'")

        return DetectResult(confidence=confidence, evidence=evidence)

    def select(self, tc_ids: list[str]) -> list[str]:
        """Build a `-t` name filter — an empty `tc_ids` means no filter."""
        if not tc_ids:
            return []
        pattern = "|".join(glob_to_regex(tc_id) for tc_id in tc_ids)
        return ["-t", pattern]

    def prepare(self) -> None:
        return None

    def execute(self, selector: list[str], junit_path: Path) -> RunResult:
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["npx", "vitest", "run", *selector, "--reporter=junit", f"--outputFile={junit_path}"]
        try:
            proc = subprocess.run(cmd, check=False, timeout=1800, capture_output=True, text=True)
        except FileNotFoundError:
            return RunResult(
                success=False,
                junit_xml_path=None,
                detail="npx (Node.js) is not on PATH — install Node before running Vitest.",
            )
        except subprocess.TimeoutExpired:
            return RunResult(
                success=False,
                junit_xml_path=None,
                detail=f"vitest run timed out after 1800s: {' '.join(cmd)}",
            )

        if proc.returncode != 0:
            return RunResult(
                success=False,
                junit_xml_path=junit_path if junit_path.is_file() else None,
                detail=f"vitest run exited {proc.returncode}: {proc.stdout[-2000:]}{proc.stderr[-2000:]}",
            )
        return RunResult(
            success=True,
            junit_xml_path=junit_path,
            detail=f"vitest run passed: {' '.join(cmd)}",
        )

    def collect(self, junit_path: Path) -> Path | None:
        return junit_path if junit_path.is_file() else None
