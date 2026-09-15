#!/usr/bin/env python3
"""catch2_runner.py — the Catch2/CTest tier-1 runner (EP-05, US-05-01/US-05-02).

Fixture-tested only. `detect()` requires BOTH a Catch2 reference in `CMakeLists.txt`
AND a CTest project marker (`CTestTestfile.cmake`, directly or under `build/`) —
never a GoogleTest-only heuristic. This is the exact D10 audit mistake this runner
must not repeat: NeuroEdge-Device uses Catch2 v3 + CTest, not GoogleTest, and an
audit once assumed the latter. `test_catch2_detected_not_googletest_on_catch2_only_
fixture` is this runner's own regression guard for that incident — do not weaken it
later without re-reading why it exists.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from runner import DetectResult, RunResult, glob_to_regex

_CATCH2_REFERENCE = re.compile(r"catch2", re.IGNORECASE)
_GOOGLETEST_REFERENCE = re.compile(r"googletest|gtest", re.IGNORECASE)


class Catch2Runner:
    name = "catch2_ctest"

    def detect(self, root: Path) -> DetectResult:
        cmake_lists = root / "CMakeLists.txt"
        if not cmake_lists.is_file():
            return DetectResult(confidence=0.0, evidence=[])

        text = cmake_lists.read_text(encoding="utf-8", errors="ignore")
        has_catch2 = bool(_CATCH2_REFERENCE.search(text))
        has_googletest_only = bool(_GOOGLETEST_REFERENCE.search(text)) and not has_catch2
        if has_googletest_only or not has_catch2:
            # Either a GoogleTest-only project, or CMakeLists.txt names neither —
            # this runner must never claim a Catch2 project it did not actually find.
            return DetectResult(confidence=0.0, evidence=[])

        ctest_marker = self._find_ctest_marker(root)
        if ctest_marker is None:
            # Catch2 referenced but no CTest project marker — CTest is what this
            # runner actually invokes, so a project without it is not a full match.
            return DetectResult(
                confidence=0.3,
                evidence=[f"{cmake_lists} references Catch2, but no CTestTestfile.cmake found"],
            )

        return DetectResult(
            confidence=0.9,
            evidence=[f"{cmake_lists} references Catch2", str(ctest_marker)],
        )

    def select(self, tc_ids: list[str]) -> list[str]:
        if not tc_ids:
            return []
        pattern = "|".join(glob_to_regex(tc_id) for tc_id in tc_ids)
        return ["-R", pattern]

    def prepare(self) -> None:
        return None

    def execute(self, selector: list[str], junit_path: Path) -> RunResult:
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ctest", "--output-junit", str(junit_path), *selector]
        try:
            proc = subprocess.run(cmd, check=False, timeout=1800, capture_output=True, text=True)
        except FileNotFoundError:
            return RunResult(
                success=False,
                junit_xml_path=None,
                detail="ctest is not on PATH — install CMake/CTest before running this suite.",
            )
        except subprocess.TimeoutExpired:
            return RunResult(
                success=False,
                junit_xml_path=None,
                detail=f"ctest timed out after 1800s: {' '.join(cmd)}",
            )

        if proc.returncode != 0:
            return RunResult(
                success=False,
                junit_xml_path=junit_path if junit_path.is_file() else None,
                detail=f"ctest exited {proc.returncode}: {proc.stdout[-2000:]}{proc.stderr[-2000:]}",
            )
        return RunResult(
            success=True,
            junit_xml_path=junit_path,
            detail=f"ctest passed: {' '.join(cmd)}",
        )

    def collect(self, junit_path: Path) -> Path | None:
        return junit_path if junit_path.is_file() else None

    def _find_ctest_marker(self, root: Path) -> Path | None:
        direct = root / "CTestTestfile.cmake"
        if direct.is_file():
            return direct
        build_dir = root / "build"
        if build_dir.is_dir():
            matches = list(build_dir.rglob("CTestTestfile.cmake"))
            if matches:
                return matches[0]
        return None
