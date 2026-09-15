#!/usr/bin/env python3
"""tc_results.py — TC-ID-keyed test results from JUnit XML + `@tc` markers (TD-001).

The gap this closes: `pytest --junitxml` records results at the **pytest-function** level
(`<testcase name="test_foo">`), not at the **test-case** level (`TC-NN-SS-TT`). The TC-ID
bindings live only as source comments — `def test_foo():   # @tc TC-01-03-02` (D9, ADR-0003)
— so the JUnit file alone can't answer "which *test cases* passed/failed", and the S12
trace-matrix has to cross-map function→TC-ID by hand.

This module does that join automatically:
  1. scan the test sources for `@tc TC-…` markers → {function → {TC-IDs}}
  2. parse the JUnit XML → {function → passed/failed/skipped}
  3. emit a TC-ID-keyed result log (markdown + JSON): each TC-ID → pass/fail/skipped/
     not-run/not-automated, aggregated across every test bound to it.

TC-ID dialect follows ADR-0003 (`TC-NN-SS-TT`, and the shorter `TC-NN-SS` form both appear
in-repo); the marker grammar is the D9 `# @tc <TC-ID>[ note]` comment.
"""

from __future__ import annotations

import argparse
import json
import re
import token as _tok
import tokenize
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_JUNIT = ".agentforge/junit/run.xml"

# A TC-ID is TC- followed by two or more numeric segments (TC-01-05 and TC-01-01-03 both
# occur in-repo). The `@tc` marker may carry a trailing note after the id (e.g. "TC-01-05 export").
_TC_ID = r"TC-[0-9]+(?:-[0-9]+)+"
_MARKER = re.compile(rf"@tc\s+(?P<tc>{_TC_ID})")
_PARAM_SUFFIX = re.compile(r"\[.*\]$")  # parametrized-case suffix on a JUnit name

# Result precedence when several tests back one TC-ID (worst wins for pass/fail).
PASS, FAIL, SKIPPED, NOT_RUN, NOT_AUTOMATED = (
    "pass", "fail", "skipped", "not-run", "not-automated",
)


@dataclass
class TCResult:
    tc_id: str
    result: str
    tests: list[str] = field(default_factory=list)


def _scan_file(path: Path) -> dict[str, set[str]]:
    """Scan one test file via the tokenizer so `@tc` markers are read ONLY from real
    comment tokens — never from inside a string literal or docstring (a line-based scan
    would wrongly bind markers embedded in a test-fixture string, e.g. this module's own
    tests).

    Binds each marker to the innermost enclosing `def test_…` using the **column** of each
    token as scope, so:
      * a `@tc` on the def line or anywhere inside the test's indented body binds to it,
      * a marker after a nested (non-test) helper `def` inside the body still binds to the
        enclosing test (the helper does not steal or drop the binding),
      * a marker that has dedented back out to the test's own column or shallower (a
        trailing module-level comment, or a sibling) does NOT bind to the previous test.
    """
    func_to_tcs: dict[str, set[str]] = {}
    current: str | None = None
    current_col = -1
    expect_name = False
    def_col = 0
    line_indent = 0
    at_line_start = True
    try:
        with path.open("rb") as fh:
            for t in tokenize.tokenize(fh.readline):
                if t.type in (tokenize.NEWLINE, tokenize.NL):
                    at_line_start = True
                    continue
                if t.type in (tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING):
                    continue
                if at_line_start:
                    line_indent = t.start[1]   # true indentation of this logical line
                    at_line_start = False
                if t.type == _tok.NAME and t.string == "def":
                    expect_name = True
                    def_col = line_indent      # the def line's indent, not the `def` token
                    # column — so `async def` (line starts with `async`) isn't inflated.
                elif expect_name and t.type == _tok.NAME:
                    expect_name = False
                    if t.string.startswith("test_"):
                        current = t.string
                        current_col = def_col
                        func_to_tcs.setdefault(current, set())
                    # a non-test `def` (a helper) leaves the enclosing test's binding intact
                elif expect_name and t.type == _tok.OP:
                    expect_name = False
                elif t.type == tokenize.COMMENT and current is not None:
                    if t.start[1] > current_col:      # still inside the test's body/def line
                        for tc in _MARKER.findall(t.string):
                            func_to_tcs[current].add(tc)
                    else:                              # dedented out of the test — stop binding
                        current = None
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # A test file that won't tokenize won't run either; skip rather than crash the report.
        pass
    return {f: tcs for f, tcs in func_to_tcs.items() if tcs}


def scan_markers(tests_dir: str | Path) -> dict[str, set[str]]:
    """Map each test function name → the set of TC-IDs bound to it by a `@tc` marker,
    across all `test_*.py` under `tests_dir`. Markers are read from comment tokens only.
    One function may carry several TC-IDs; one TC-ID may be shared by several functions."""
    func_to_tcs: dict[str, set[str]] = {}
    for path in sorted(Path(tests_dir).rglob("test_*.py")):
        for func, tcs in _scan_file(path).items():
            func_to_tcs.setdefault(func, set()).update(tcs)
    return func_to_tcs


def parse_junit(junit_path: str | Path) -> dict[str, str]:
    """Parse a JUnit XML into {function_name → pass|fail|skipped}.

    Parametrized cases (`test_x[case]`) collapse to their base name with worst-wins
    precedence, so a TC-ID bound to `test_x` reflects a failure in any of its params.
    """
    path = Path(junit_path)
    results: dict[str, str] = {}
    if not path.exists():
        return results
    root = ET.parse(path).getroot()
    for tc in root.iter("testcase"):
        name = _PARAM_SUFFIX.sub("", tc.get("name", "")).strip()
        if not name:
            continue
        if tc.find("failure") is not None or tc.find("error") is not None:
            status = FAIL
        elif tc.find("skipped") is not None:
            status = SKIPPED
        else:
            status = PASS
        prior = results.get(name)
        results[name] = _worse(prior, status) if prior else status
    return results


_RANK = {FAIL: 3, PASS: 2, SKIPPED: 1}


def _worse(a: str, b: str) -> str:
    """Worst-wins for a single test's parametrized cases: fail > pass > skipped."""
    return a if _RANK.get(a, 0) >= _RANK.get(b, 0) else b


def _aggregate_tc(statuses: list[str]) -> str:
    """A TC-ID's result across all tests bound to it: fail if any fails, else pass if any
    passes, else skipped (all skipped)."""
    if FAIL in statuses:
        return FAIL
    if PASS in statuses:
        return PASS
    return SKIPPED


def build_results(
    tests_dir: str | Path,
    junit_path: str | Path,
    tc_plan: list[str] | None = None,
) -> list[TCResult]:
    """Join markers + JUnit into per-TC-ID results.

    `tc_plan` (optional) is the full universe of TC-IDs from the test plan; any that carry
    no `@tc` marker are reported `not-automated` — the honest "no test covers this yet"
    signal the trace-matrix needs. Without it, only marker-bound TC-IDs are reported.
    """
    func_to_tcs = scan_markers(tests_dir)
    junit = parse_junit(junit_path)

    tc_to_funcs: dict[str, list[str]] = {}
    for func, tcs in func_to_tcs.items():
        for tc in tcs:
            tc_to_funcs.setdefault(tc, []).append(func)

    all_tcs = set(tc_to_funcs) | set(tc_plan or [])
    out: list[TCResult] = []
    for tc in sorted(all_tcs):
        funcs = sorted(tc_to_funcs.get(tc, []))
        if not funcs:
            out.append(TCResult(tc, NOT_AUTOMATED, []))
            continue
        statuses = [junit[f] for f in funcs if f in junit]
        result = NOT_RUN if not statuses else _aggregate_tc(statuses)
        out.append(TCResult(tc, result, funcs))
    return out


def render_markdown(results: list[TCResult]) -> str:
    counts: dict[str, int] = {}
    for r in results:
        counts[r.result] = counts.get(r.result, 0) + 1
    order = [PASS, FAIL, SKIPPED, NOT_RUN, NOT_AUTOMATED]
    summary = " | ".join(f"{k}: {counts[k]}" for k in order if k in counts) or "no TC-IDs"

    lines = [
        "# TC-ID Test Results (TD-001)",
        "",
        "Test-case-level results, joined from the JUnit XML and the `# @tc` source markers.",
        "Generated by `agentforge/src/qa/tc_results.py` -- do not hand-edit.",
        "",
        f"**Summary:** {summary}",
        "",
        "| TC-ID | Result | Bound tests |",
        "|---|---|---|",
    ]
    for r in results:
        tests = ", ".join(r.tests) if r.tests else "-"
        lines.append(f"| {r.tc_id} | {r.result} | {tests} |")
    return "\n".join(lines) + "\n"


def render_json(results: list[TCResult]) -> str:
    return json.dumps([r.__dict__ for r in results], indent=2) + "\n"


def _load_tc_plan(path: str | None) -> list[str] | None:
    """Read a TC-ID plan file (one TC-ID per line, or any file with TC-IDs in it)."""
    if not path:
        return None
    text = Path(path).read_text(encoding="utf-8-sig")
    return sorted(set(re.findall(_TC_ID, text)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests-dir", default="agentforge/tests",
                        help="root to scan for test_*.py with @tc markers")
    parser.add_argument("--junit", default=DEFAULT_JUNIT, help=f"JUnit XML (default: {DEFAULT_JUNIT})")
    parser.add_argument("--tc-plan", default=None,
                        help="optional file listing all TC-IDs; unmarked ones report not-automated")
    parser.add_argument("--out-md", default=None, help="write the markdown report here")
    parser.add_argument("--out-json", default=None, help="write the JSON report here")
    args = parser.parse_args(argv)

    results = build_results(args.tests_dir, args.junit, _load_tc_plan(args.tc_plan))
    md = render_markdown(results)

    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(md, encoding="utf-8")
        print(f"wrote {args.out_md}")
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(render_json(results), encoding="utf-8")
        print(f"wrote {args.out_json}")
    if not args.out_md and not args.out_json:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
