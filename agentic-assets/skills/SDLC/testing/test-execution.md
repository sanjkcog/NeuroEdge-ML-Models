---
name: test-execution
description: Detect the test framework a repo actually uses (never assume, D10), run it via its own native TC-ID-filtered selection, and collect the JUnit XML every runner already emits natively — the procedure /test-run follows.
origin: NeuroEdge
---

# Test Execution

Produces one execution result: a JUnit XML file collected from whichever tier-1 runner
(pytest, Playwright, Catch2/CTest, JUnit5, Vitest) this repo actually uses, selected by
`TC-NN-SS-TT` identifier and handed off to `/trace-matrix` and the configured
test-management vendor. This is what makes the traceability matrix's "execution result"
column mean something, instead of reading "not yet run" forever.

## When to Activate

- `/test-run` is invoked directly
- A human needs real pass/fail results for a TC-ID selector, not just a rendered plan
- The orchestrator reaches a QA-execution point after `neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md`
  and generated tests already exist (no S10 role agent owns this yet — see Standalone vs. orchestrated)

## Inputs

- A TC-ID selector (e.g. `TC-01-03-*`), or none for the full suite
- `--target <name>` (optional) — a `test-env.json` environment name to provision before
  running
- `--push` (optional) — upload the collected JUnit XML via the configured
  test-management vendor afterward

## Procedure

1. **Detect.** Call `agentforge/src/qa/runner.py`'s `detect_all(root)` against the
   current repo root.
   - **`status == "none"`**: report "no framework detected" naming every runner
     inspected. Never default to a runner (D10).
   - **`status == "ambiguous"`**: surface both candidates and their confidence scores;
     prompt the operator to choose explicitly (`AskUserQuestion`, main session only,
     D1) — never silently pick the higher-scoring one.
   - **`status == "detected"`**: proceed with the named runner.
2. **Provision, if `--target` was given.** Load `test-env.json` via `TestEnvConfig.load`.
   - A target with a matching entry: call `provision(name)`. If the health probe never
     passes, abort the run with the probe's own failure detail — but still call
     `teardown(name)` from a `finally` block regardless of `provision()`'s outcome, so a
     partially-started environment is never left orphaned.
   - A target with **no** matching entry: run locally, no provisioning attempted — this
     is not a failure mode.
   - No `--target` given: skip this step entirely.
3. **Select.** Call the detected runner's `select(tc_ids)` with the TC-ID selector
   (parsed as glob patterns, e.g. `TC-01-03-*`). An empty selector list result when
   `tc_ids` was non-empty means the selector matched zero tests — this must be reported
   explicitly as "0 tests matched" and the run must **not** silently fall back to running
   the full suite (US-05-02's own boundary-case AC).
4. **Execute.** Call `prepare()` then `execute(selector, junit_path)`, writing to
   `.agentforge/junit/run.xml` unless a different path was given. Report the returned
   `RunResult` verbatim — a non-zero exit, a missing tool, or a timeout are all explicit
   failures here, never an unhandled exception reaching the caller.
5. **Collect.** Call `collect(junit_path)` to confirm the JUnit XML this runner already
   wrote (D5 — never regenerate or convert it). Hand the path to `/trace-matrix` for
   correlation against `neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md`.
6. **Push, only if `--push` was given.** Check `agentforge/src/qa/vendor_config.py`'s
   persisted choice. If unset, prompt (`AskUserQuestion`, main session only, D1) among
   Zephyr Scale / TestRail / none (repo-local) / decide later, and persist the answer.
   Attempt the upload via the configured adapter — a failure here is reported, never
   silently swallowed, and never blocks the JUnit XML or matrix from existing (D12).
7. **Always tear down.** If Step 2 provisioned an environment, call `teardown(name)`
   now if it has not already run — every code path through Steps 3-6, success or
   failure, must reach this.

## Output Format

```
## Test Execution

- Detected: <runner name> (confidence: <N> — <evidence>)
- Target: <none | name — provisioned | name — no test-env.json entry, ran locally>
- Selector: <TC-ID pattern(s) | none — full suite>
- Result: <N passed, M failed | 0 tests matched selector | aborted: <reason>>
- Collected: <path to JUnit XML | none>
- Vendor: <none | Zephyr Scale | TestRail> <push result if --push>

> Next: /trace-matrix — correlate this result against neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md.
```

## Gate delegation

This skill does not itself call `AskUserQuestion` — ambiguous detection (Step 1) and an
unconfigured vendor (Step 6) both require a prompt that only the main session can issue
(D1). A subagent running this skill must surface the exact question in its returned
result and stop there rather than guessing an answer.

## Standalone vs. orchestrated

- **Standalone (this skill, via `/test-run`):** the only way to run this today — no
  role agent owns S10 (execution) yet, unlike S9 (`qa-automation-engineer`, writing
  tests) or S11 (`test-triage`, classifying results). This mirrors `/test-plan`/
  `/trace-matrix` before any orchestrator wiring existed for S6/S12.
- **Orchestrated.** `test-run` is S10 in `run_state.STAGE_SEQUENCE`, between S9
  `test-automation` and S11 `triage`; `/agentforge` runs it through `/test-run` (see
  `commands/agentforge.md`).
