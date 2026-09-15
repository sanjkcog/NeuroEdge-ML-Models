#!/usr/bin/env python3
"""pytest_runner.py — the pytest tier-1 runner (EP-05, US-05-01/US-05-02, ADR-0004).

The one runner tested against a real, live invocation: this repo IS a pytest project
(`pyproject.toml`'s `[tool.pytest.ini_options]`), so `detect()` is exercised against the
actual repo root rather than a fixture — every other tier-1 runner is fixture-only (no
live Playwright/Catch2/JUnit5/Vitest project exists in this repo or reachable from it).
"""

from __future__ import annotations

import fnmatch
import subprocess
import tomllib
from pathlib import Path

from runner import DetectResult, RunResult, scan_tc_id_bindings

# A -k expression guaranteed to match zero collected tests, used when a TC-ID selector
# is given but nothing in the repo binds to it — pytest's own "no tests collected" exit
# code (5) then becomes the explicit zero-match signal, never a silent full-suite run.
_NEVER_MATCHES = "__test_run_no_tc_match_found__"
_NO_TESTS_COLLECTED_EXIT_CODE = 5


class PytestRunner:
    name = "pytest"

    def detect(self, root: Path) -> DetectResult:
        evidence: list[str] = []
        confidence = 0.0

        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            try:
                data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError:
                data = {}
            if "pytest" in data.get("tool", {}) and "ini_options" in data["tool"].get(
                "pytest", {}
            ):
                evidence.append(f"{pyproject} [tool.pytest.ini_options]")
                confidence = max(confidence, 0.95)

        if (root / "pytest.ini").is_file():
            evidence.append(str(root / "pytest.ini"))
            confidence = max(confidence, 0.9)

        if (root / "conftest.py").is_file():
            evidence.append(str(root / "conftest.py"))
            confidence = max(confidence, 0.6)

        return DetectResult(confidence=confidence, evidence=evidence)

    def select(self, tc_ids: list[str]) -> list[str]:
        """Build a `-k` expression from TC-ID-bound test names (the `# @tc
        TC-NN-SS-TT` convention, D9). An empty `tc_ids` means "no filter, run
        everything" — different from a filter that matches nothing."""
        if not tc_ids:
            return []

        names = self._matching_test_names(tc_ids)
        if not names:
            return ["-k", _NEVER_MATCHES]
        return ["-k", " or ".join(sorted(names))]

    def prepare(self) -> None:
        return None

    def execute(self, selector: list[str], junit_path: Path) -> RunResult:
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["pytest", *selector, f"--junitxml={junit_path}"]
        try:
            proc = subprocess.run(cmd, check=False, timeout=600, capture_output=True, text=True)
        except FileNotFoundError:
            return RunResult(
                success=False,
                junit_xml_path=None,
                detail="pytest is not on PATH — install it before running this suite.",
            )
        except subprocess.TimeoutExpired:
            return RunResult(
                success=False,
                junit_xml_path=None,
                detail=f"pytest timed out after 600s: {' '.join(cmd)}",
            )

        if proc.returncode == _NO_TESTS_COLLECTED_EXIT_CODE:
            detail = (
                "0 tests matched the TC-ID selector — refusing to silently run the full suite."
                if selector
                else "0 tests collected — no TC-ID selector was applied, the repo has nothing to run."
            )
            return RunResult(success=False, junit_xml_path=None, detail=detail)
        if proc.returncode != 0:
            return RunResult(
                success=False,
                junit_xml_path=junit_path if junit_path.is_file() else None,
                detail=f"pytest exited {proc.returncode}: {proc.stdout[-2000:]}{proc.stderr[-2000:]}",
            )
        return RunResult(
            success=True,
            junit_xml_path=junit_path,
            detail=f"pytest passed: {' '.join(cmd)}",
        )

    def collect(self, junit_path: Path) -> Path | None:
        """pytest already wrote the JUnit XML at `junit_path` (D5) — locate it, never
        regenerate or convert it."""
        return junit_path if junit_path.is_file() else None

    def _matching_test_names(self, tc_ids: list[str]) -> set[str]:
        bindings = scan_tc_id_bindings(Path("."))
        return {
            name
            for name, tc_id in bindings.items()
            if any(fnmatch.fnmatch(tc_id, pattern) for pattern in tc_ids)
        }
