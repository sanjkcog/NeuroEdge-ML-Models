#!/usr/bin/env python3
"""runner.py — the pluggable test-runner registry (EP-05, US-05-01/US-05-02, ADR-0004).

`TestRunner` mirrors `PLUGGABLE_PROTOCOL_SHAPE` (agentforge/src/qa/adapter.py): an
explicit result object, never a raised exception for an expected failure mode (no
framework detected, zero tests matched, non-zero exit with no JUnit XML produced).

`detect()` must NEVER assume — this is D10's own named failure (an audit assumed
GoogleTest where the repo actually used Catch2 v3 + CTest). Every runner's `detect()`
returns a confidence score and the evidence it found, never a bare boolean, so
`detect_all()` can rank candidates and surface a near-tie as ambiguous rather than
silently picking one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# Below this, a candidate is not considered a real match at all (Task 2's boundary).
_MIN_CONFIDENCE = 0.05
# Two candidates within this margin of each other are "too close to call" (Task 8's
# boundary) — surfaced as ambiguous rather than silently picking the higher one.
_AMBIGUITY_MARGIN = 0.15


def glob_to_regex(pattern: str) -> str:
    """Turn a TC-ID glob like `TC-01-03-*` into a regex fragment for a runner's native
    `--grep`/`-R`/`-t`-style selector. Shared by every runner whose native selector is
    regex-based (Playwright, Catch2/CTest, Vitest — pytest and JUnit5 use their own
    non-regex selector syntax instead), so the escaping is correct in exactly one
    place rather than re-derived (and potentially under-escaped) per runner."""
    return re.escape(pattern).replace(r"\*", ".*")


_TC_COMMENT = re.compile(r"#\s*@tc\s+(TC-\d{2}-\d{2}-\d{2})")
_TEST_DEF = re.compile(r"^\s*def\s+(test_\w+)\s*\(")


def scan_tc_id_bindings(root: Path = Path(".")) -> dict[str, str]:
    """Scan `.py` files under `root` for the `# @tc TC-NN-SS-TT` source-comment
    convention (D9), bound to a `def test_name(): ...` on the same line. Returns
    `{test_function_name: tc_id}`.

    Shared by `pytest_runner.select()` (building a `-k` expression from a TC-ID glob)
    and `testrail_adapter._inject_test_id_properties` (falling back to this mapping
    when a JUnit `<testcase>`'s own `name`/`classname` doesn't already embed a TC-ID —
    the D9 convention is a source-only annotation, so a JUnit report generated from a
    plainly-named test carries no TC-ID unless something maps it back like this).

    The result is keyed by bare function name only, with no file/module qualifier —
    two different files defining a same-named test bound to two *different* TC-IDs is
    a genuine ambiguity this scan cannot resolve on function name alone. Rather than
    let whichever file `rglob` visits last silently win (attaching a plausible-looking
    but possibly wrong TC-ID), a name seen with conflicting TC-IDs is dropped from the
    result entirely — callers see "no binding for this name" instead of a coin-flip
    answer, matching this module's own D10 "never guess" discipline.
    """
    bindings: dict[str, str] = {}
    ambiguous: set[str] = set()
    for path in Path(root).rglob("*.py"):
        if ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            comment_match = _TC_COMMENT.search(line)
            if not comment_match:
                continue
            def_match = _TEST_DEF.match(line.split("#", 1)[0])
            if not def_match:
                continue
            name = def_match.group(1)
            tc_id = comment_match.group(1)
            if name in ambiguous:
                continue
            if name in bindings and bindings[name] != tc_id:
                del bindings[name]
                ambiguous.add(name)
                continue
            bindings[name] = tc_id
    return bindings


@dataclass
class DetectResult:
    """What one runner's `detect()` found. `confidence` is 0.0 (nothing found) to 1.0
    (unambiguous); `evidence` names the files/markers inspected, so a "no framework
    detected" report can say what was actually looked for, not just that it failed."""

    confidence: float
    evidence: list[str] = field(default_factory=list)


@dataclass
class RunResult:
    """The outcome of one `execute()` call. Never an exception — a non-zero exit or a
    missing tool is reported here, so a caller never depends on catching a
    runner-specific exception type."""

    success: bool
    junit_xml_path: Path | None = None
    detail: str = ""


class TestRunner(Protocol):
    """The registry contract every tier-1 runner implements: `detect() · select(tc_ids)
    · prepare() · execute() · collect()` (project_objectives.md §9's own runner
    contract)."""

    name: str

    def detect(self, root: Path) -> DetectResult: ...

    def select(self, tc_ids: list[str]) -> list[str]:
        """Build this runner's native selection expression (pytest `-k`, ctest `-R`,
        Playwright `--grep`, ...) from a list of TC-ID glob patterns."""
        ...

    def prepare(self) -> None:
        """Anything a runner needs before `execute()` — most runners have nothing to
        do here; this exists so environment-dependent runners have a hook without
        changing the protocol shape later."""
        ...

    def execute(self, selector: list[str], junit_path: Path) -> RunResult: ...

    def collect(self, junit_path: Path) -> Path | None:
        """Return the JUnit XML path this runner's `execute()` already produced — never
        a format conversion (D5: every runner emits JUnit XML natively)."""
        ...


def default_registry() -> dict[str, TestRunner]:
    """The five tier-1 runners (ADR-0004), keyed by name.

    Imports the concrete runner modules lazily, inside the function body, so importing
    `runner` itself never requires all five runner modules to exist or be
    import-clean — a broken runner module only surfaces when `detect_all()` actually
    runs with the default registry, not merely when this module is imported.
    """
    from catch2_runner import Catch2Runner
    from junit5_runner import JUnit5Runner
    from playwright_runner import PlaywrightRunner
    from pytest_runner import PytestRunner
    from vitest_runner import VitestRunner

    runners: list[TestRunner] = [
        PytestRunner(),
        PlaywrightRunner(),
        Catch2Runner(),
        JUnit5Runner(),
        VitestRunner(),
    ]
    return {r.name: r for r in runners}


@dataclass
class DetectAllResult:
    """The outcome of running every registered runner's `detect()` against one
    directory. `status` is one of "detected" / "ambiguous" / "none" — a caller
    branches on this, never on `runner_name is None` alone, since that's also true for
    "none"."""

    status: str
    runner_name: str | None
    confidence: float
    detail: str
    candidates: list[tuple[str, DetectResult]] = field(default_factory=list)


def detect_all(
    root: Path, registry: dict[str, TestRunner] | None = None
) -> DetectAllResult:
    """Run every registered runner's `detect()` against `root`, rank by confidence, and
    return the top match only when it clears an unambiguous margin over the runner-up.

    Never guesses (D10): zero matches is reported as "none" naming every runner
    inspected; a near-tie is reported as "ambiguous" naming both candidates, for the
    caller to resolve (prompting via `AskUserQuestion`, main session only, D1) rather
    than being silently picked here.
    """
    registry = default_registry() if registry is None else registry

    inspected: list[str] = sorted(registry.keys())
    scored: list[tuple[str, DetectResult]] = []
    for name in inspected:
        result = registry[name].detect(root)
        if result.confidence >= _MIN_CONFIDENCE:
            scored.append((name, result))

    if not scored:
        return DetectAllResult(
            status="none",
            runner_name=None,
            confidence=0.0,
            detail=(
                f"No framework detected in {root} — inspected: {', '.join(inspected)}."
            ),
        )

    scored.sort(key=lambda pair: pair[1].confidence, reverse=True)
    top_name, top = scored[0]

    if len(scored) > 1:
        second_name, second = scored[1]
        if (top.confidence - second.confidence) < _AMBIGUITY_MARGIN:
            return DetectAllResult(
                status="ambiguous",
                runner_name=None,
                confidence=top.confidence,
                detail=(
                    f"Ambiguous detection: {top_name} (confidence {top.confidence:.2f}) "
                    f"and {second_name} (confidence {second.confidence:.2f}) are too "
                    "close to call — choose explicitly rather than guessing."
                ),
                candidates=scored,
            )

    return DetectAllResult(
        status="detected",
        runner_name=top_name,
        confidence=top.confidence,
        detail=f"Detected {top_name} (confidence {top.confidence:.2f}): {'; '.join(top.evidence)}",
        candidates=scored,
    )
