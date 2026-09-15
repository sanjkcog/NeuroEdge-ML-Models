---
name: trace-matrix
description: Render the full FR -> EPIC -> Story -> AC -> TC -> test -> result -> defect chain and fail loudly on any uncovered MUST-priority acceptance criterion, so coverage is enforced rather than decorative.
origin: NeuroEdge
---

# Trace Matrix

Produces `neuroedge/docs/project_related/<objective-slug>/05-quality/traceability.md`: the complete traceability chain from
a functional requirement all the way to an execution result and any linked defect. This
is what makes coverage **enforceable**, not merely visible — an uncovered MUST-priority
AC is a hard failure of this skill's own output, not a footnote in it.

## When to Activate

- `/trace-matrix` is invoked directly
- The orchestrator reaches a coverage-check point after test execution
- A human needs to answer "is this requirement actually tested, and did it pass?"
  without assembling the answer by hand

## Inputs

- `neuroedge/docs/project_related/<objective-slug>/02-project-plan/epics-and-user-stories.md` — the FR/EPIC/Story/AC set
- `neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md` — the TC-IDs generated against that set
  (`test-plan-generation` skill's output; `<track>` = the objective's PRD group)
- Any collected JUnit XML execution results, if present (optional — the matrix still
  renders without them, see below)

## Procedure

1. **Walk every FR → EPIC → Story → AC in order.** For each AC, find its `TC-NN-SS-TT`
   in `neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md` (via the `# @tc TC-NN-SS-TT`
   binding convention, D9).
2. **Attach execution results where they exist.** If JUnit XML results are available,
   correlate by TC-ID and record pass/fail/error per test case. **Do not hand-map
   function→TC-ID** — the JUnit XML records pytest *function* names, not TC-IDs, so
   `agentforge/src/qa/tc_results.py` (TD-001) does the join for you from the `# @tc`
   markers and writes a TC-ID-keyed log you read directly:
   ```bash
   python agentforge/src/qa/tc_results.py \
     --tests-dir agentforge/tests --junit .agentforge/junit/run.xml \
     --out-md neuroedge/docs/project_related/<objective-slug>/05-quality/tc-results.md \
     --out-json neuroedge/docs/project_related/<objective-slug>/05-quality/tc-results.json
   ```
   Each TC-ID resolves to `pass` / `fail` / `skipped` / `not-run` (bound to a test that
   didn't execute this run) / `not-automated` (no `@tc` marker anywhere — pass the test
   plan's TC-ID list via `--tc-plan` to surface these). Read `tc-results.md` and use its
   per-TC-ID result in the matrix rows. If no JUnit XML exists yet, the AC is still listed
   with its TC-ID and a `not yet executed` status — different from `unmapped` (Task 1's
   distinction) and must not be conflated with it.
3. **Render the full chain as a table.** Every row must be traceable end to end:
   `FR-NN → EP-NN → US-NN-SS → AC → TC-NN-SS-TT → test name → result → defect (if any)`.
4. **Fail loudly on uncovered MUST-priority ACs.** This is the one hard rule this skill
   exists to enforce: any **MUST**-priority AC with no `TC-NN-SS-TT` at all (not merely
   "not yet executed" — genuinely absent from the test plan) makes the whole render
   **fail**, naming every such AC and the specific reason it is unsatisfied. This is a
   hard fail, not a warning — do not soften it. (The one place a device-only gap
   *warns* instead of failing is S9c's coverage gate in a later phase, EP-06 — that
   boundary does not exist yet and must not be anticipated here.)
5. **Render with no vendor configured.** The matrix is a repo-local artifact by design
   (D12) — it must never fail or degrade because no Zephyr/TestRail adapter is set up.
6. **The verdict is binary: `PASS` or `FAILED`. There is no third state (TD-014).**
   Never close this stage with `PARTIAL`, `partial by design`, `deferred`, or any
   equivalent. If some EPICs are not yet built, the honest render is **`FAILED`** (their
   ACs are uncovered) — or the stage simply has not been attempted yet. It is never a
   qualified pass.

   This is not stylistic. On the ADR-0003 run this stage was completed with a "PARTIAL
   by design" note while EP-02..EP-06 were still unbuilt, and was never re-run after they
   landed. The backlog then diverged from reality by 118 acceptance criteria with nothing
   contradicting it, because the one control designed to catch that had already reported
   itself done. **A stage that is allowed to complete partially stops being a gate.**

   `run_state.py` now enforces this: completing `trace-matrix` is refused
   (`VerdictRequired`) unless an artifact carries the verdict **parenthesised**, e.g.
   `neuroedge/docs/project_related/<objective-slug>/05-quality/traceability.md (PASS)`. The parentheses are
   required deliberately — a bare `PASS` substring is satisfied by accident by any path
   containing COMPASS, BYPASS or PASSWORD, which would make the guard decorative. Write
   `(PASS)` only when the matrix genuinely passed.
7. **Re-run after later work lands.** This is a convergence check, so its verdict is only
   true as of the scope it saw. If tasks or ACs complete after it ran, the earlier verdict
   is stale and must be refreshed before release readiness means anything:
   ```bash
   python agentforge/src/state/run_state.py --path "$RUN" reopen trace-matrix
   ```
   `reopen` re-arms the stage while preserving its spawn history, so the superseded run
   stays visible in the audit trail rather than being erased.

## Output Format

```markdown
# Traceability Matrix

## Coverage Summary
| Priority | ACs | Covered (has a TC) | Executed | Passed |
|---|---|---|---|---|
| MUST | N | N (100% required) | N | N |
| SHOULD | N | N | N | N |
| COULD | N | N | N | N |

## Full Chain
| FR | EPIC | Story | AC | TC | Test | Result | Defect |
|---|---|---|---|---|---|---|---|
| FR-01 | EP-01 | US-01-03 | "..." | TC-01-03-01 | test_... | pass | - |

## FAILED — Uncovered MUST-priority ACs
| Story | AC | Reason |
|---|---|---|
| US-NN-SS | "..." | No TC generated — see neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md Unmapped section |
```

If the Coverage Summary's MUST column is not 100% covered, the whole matrix render is
a **failure**, and the report must say so explicitly at the top, not bury it in a table.

## Gate delegation

This skill does not itself call `AskUserQuestion` — it only reports, and its "fail
loudly" behavior is a report-time assertion, not an interactive gate. No delegation note
is needed beyond stating the failure plainly in the returned result when run inside a
subagent.
