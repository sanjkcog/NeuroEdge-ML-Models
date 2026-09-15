#!/usr/bin/env python3
"""junit5_runner.py — the JUnit5 (Maven Surefire / Gradle) tier-1 runner (EP-05).

Fixture-tested only. `detect()` requires a JUnit5 dependency/plugin marker, never a
bare `pom.xml`/`build.gradle*` presence — a Maven or Gradle project that doesn't
actually use JUnit5 must not be misdetected. Surefire's/Gradle's test reports **are
already** JUnit XML (D5) — `collect()` only locates and merges them, never
re-generates or transforms their content.

`detect()` records which build tool actually matched (`self._build_tool`) and resets
that state on every call (including a failed one) so a reused instance never carries
a stale build-tool assumption from a previous root. `select()`/`execute()`/`collect()`
all branch on `self._build_tool` — a Gradle project must not be confidently detected
and then silently run through the Maven-only path (a prior review caught exactly that
gap: `detect()` alone cannot promise the run will work); and `execute()` refuses to
guess a build tool at all if `detect()` was never run or never matched (D10).
"""

from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from runner import DetectResult, RunResult

_JUNIT5_MARKER = re.compile(r"junit-jupiter|junit5|org\.junit\.jupiter", re.IGNORECASE)


class JUnit5Runner:
    name = "junit5"

    def __init__(self) -> None:
        self._build_tool: str | None = None
        self._project_root: Path = Path(".")
        # Snapshot of {report_path: mtime} taken immediately before the most recent
        # execute() attempt (success or failure) — collect() treats a report as
        # "produced by this run" only if it's new or its mtime advanced past this
        # snapshot, comparing each file to its own prior state rather than to a
        # wall-clock timestamp. This avoids the specific clock-skew failure mode a
        # tolerance window has, though on a filesystem with coarse mtime resolution a
        # report rewritten within the same quantization tick as the snapshot could
        # still compare equal rather than greater and be excluded — not a fully
        # immune mechanism, just a better-founded one.
        self._pre_execute_mtimes: dict[Path, float] | None = None

    def detect(self, root: Path) -> DetectResult:
        # Reset on every call — including a non-match — so a reused instance never
        # carries a stale build-tool/root assumption from a previous, different root.
        self._build_tool = None
        self._project_root = root

        pom = root / "pom.xml"
        if pom.is_file():
            try:
                text = pom.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = ""
            if _JUNIT5_MARKER.search(text):
                self._build_tool = "maven"
                return DetectResult(confidence=0.9, evidence=[f"{pom} declares a JUnit5 dependency"])

        for gradle_name in ("build.gradle", "build.gradle.kts"):
            gradle = root / gradle_name
            if gradle.is_file():
                try:
                    text = gradle.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if _JUNIT5_MARKER.search(text) or "useJUnitPlatform" in text:
                    self._build_tool = "gradle"
                    return DetectResult(
                        confidence=0.9, evidence=[f"{gradle} declares JUnit5/JUnit Platform"]
                    )

        return DetectResult(confidence=0.0, evidence=[])

    def select(self, tc_ids: list[str]) -> list[str]:
        """Build a Maven `-Dtest=` filter or a Gradle `--tests` filter, depending on
        which build tool `detect()` actually found — an empty `tc_ids` means no
        filter."""
        if not tc_ids:
            return []
        if self._build_tool == "gradle":
            args: list[str] = []
            for tc_id in tc_ids:
                args += ["--tests", tc_id]
            return args
        return [f"-Dtest={','.join(tc_ids)}"]

    def prepare(self) -> None:
        return None

    def execute(self, selector: list[str], junit_path: Path) -> RunResult:
        if self._build_tool is None:
            return RunResult(
                success=False,
                junit_xml_path=None,
                detail="detect() was never run (or found neither Maven nor Gradle) — "
                "refusing to guess a build tool.",
            )

        if self._build_tool == "gradle":
            gradlew = self._project_root / "gradlew"
            gradlew_bat = self._project_root / "gradlew.bat"
            if gradlew_bat.is_file():
                executable = str(gradlew_bat)
            elif gradlew.is_file():
                executable = str(gradlew)
            else:
                executable = "gradle"
            cmd = [executable, "test", *selector]
            missing_tool_detail = (
                f"{executable} is not available — install Gradle (or commit the "
                "Gradle wrapper) before running this suite."
            )
        else:
            cmd = ["mvn", "test", *selector]
            missing_tool_detail = "mvn is not on PATH — install Maven before running this suite."

        # Snapshot before the subprocess call, unconditionally — even a run that fails
        # to start (missing binary, timeout) still marks "an execute was attempted",
        # so a later standalone collect() never falls back to treating leftover
        # reports from a prior, unrelated run as fresh.
        self._pre_execute_mtimes = self._snapshot_report_mtimes()

        try:
            proc = subprocess.run(
                cmd,
                check=False,
                timeout=1800,
                capture_output=True,
                text=True,
                cwd=self._project_root,
            )
        except (FileNotFoundError, PermissionError) as exc:
            return RunResult(
                success=False,
                junit_xml_path=None,
                detail=f"{missing_tool_detail} ({exc})",
            )
        except subprocess.TimeoutExpired:
            return RunResult(
                success=False,
                junit_xml_path=None,
                detail=f"{cmd[0]} timed out after 1800s: {' '.join(cmd)}",
            )

        collected = self.collect(junit_path)
        if proc.returncode != 0:
            return RunResult(
                success=False,
                junit_xml_path=collected,
                detail=f"{cmd[0]} exited {proc.returncode}: {proc.stdout[-2000:]}{proc.stderr[-2000:]}",
            )
        return RunResult(
            success=True,
            junit_xml_path=collected,
            detail=f"{cmd[0]} passed: {' '.join(cmd)}",
        )

    def _report_dirs(self) -> list[Path]:
        maven_dir = self._project_root / "target" / "surefire-reports"
        gradle_dir = self._project_root / "build" / "test-results" / "test"
        # Once detect() has identified the build tool, only that tool's own report
        # location is relevant — a repo carrying stale artifacts from having
        # previously used the other build tool (or a hybrid module layout) must not
        # have those unrelated reports folded into this run's merged output. With no
        # known build tool (a standalone collect() call, no prior detect()), both
        # locations are checked, matching this method's pre-existing behavior.
        if self._build_tool == "maven":
            return [maven_dir]
        if self._build_tool == "gradle":
            return [gradle_dir]
        return [maven_dir, gradle_dir]

    def _find_reports(self) -> list[Path]:
        reports: list[Path] = []
        for reports_dir in self._report_dirs():
            if not reports_dir.is_dir():
                continue
            try:
                reports.extend(reports_dir.glob("*.xml"))
            except OSError:
                continue
        return reports

    def _snapshot_report_mtimes(self) -> dict[Path, float]:
        snapshot: dict[Path, float] = {}
        for path in self._find_reports():
            try:
                snapshot[path] = path.stat().st_mtime
            except OSError:
                continue
        return snapshot

    def collect(self, junit_path: Path) -> Path | None:
        """Surefire/Gradle write one JUnit XML report **per test class** — merge every
        report belonging to this run into a single `<testsuites>` document at
        `junit_path`, never picking just one and silently discarding the rest.

        If `execute()` ran immediately before this call, only reports that are new or
        whose mtime advanced past the pre-execute snapshot count as "this run's"
        (compared to the file's own prior state, not a wall-clock cutoff — see
        `_pre_execute_mtimes`). Called standalone (no prior `execute()` on this
        instance), every report currently on disk is merged, matching the pre-existing
        behavior for a bare `collect()` call.
        """
        candidates = self._find_reports()
        if not candidates:
            return None

        if self._pre_execute_mtimes is not None:
            fresh: list[Path] = []
            for path in candidates:
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                if mtime > self._pre_execute_mtimes.get(path, 0.0):
                    fresh.append(path)
            if not fresh:
                return None
            candidates = fresh

        merged = self._merge_reports(sorted(candidates))
        if merged is None:
            return None

        try:
            junit_path.parent.mkdir(parents=True, exist_ok=True)
            merged.write(junit_path, encoding="utf-8", xml_declaration=True)
        except OSError:
            return None
        return junit_path

    def _merge_reports(self, paths: list[Path]) -> ET.ElementTree | None:
        """Combine every report's `<testsuite>` elements under one `<testsuites>`
        root — a byte-level concatenation of the source reports' test-case data,
        never a re-derivation of it (D5). Each `<testsuite>` keeps its own counts;
        the merged root additionally carries summed `tests`/`failures`/`errors`/
        `skipped` so a consumer computing `passed = tests - failures - errors -
        skipped` from root-level totals (rather than iterating children) gets a
        correct count, not an overcount from treating skipped tests as passed. `time`
        is deliberately not summed — a total duration is a much weaker signal than
        pass/fail/skip accounting and is left to whichever child `<testsuite>` a
        caller inspects directly. Each child's `id` is renumbered to stay unique
        across the merge (Gradle's own per-file reports each start at `id="0"`)."""
        merged_root = ET.Element("testsuites")
        suites: list[ET.Element] = []
        for path in paths:
            try:
                tree = ET.parse(path)
            except (ET.ParseError, OSError):
                continue
            node = tree.getroot()
            if node.tag == "testsuites":
                suites.extend(list(node))
            else:
                suites.append(node)

        if not suites:
            return None

        totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
        for index, suite in enumerate(suites):
            suite.set("id", str(index))
            for key in totals:
                try:
                    totals[key] += int(suite.get(key, 0))
                except (TypeError, ValueError):
                    pass
            merged_root.append(suite)

        for key, value in totals.items():
            merged_root.set(key, str(value))

        return ET.ElementTree(merged_root)
