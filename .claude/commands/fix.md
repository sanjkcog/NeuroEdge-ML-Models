# /fix — Fix a defect the fast-lane way (triage → failing test → fix → review → PR)

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /fix · Skills: defect-fix, tdd-workflow`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/development/defect-fix.md`
> - `agentic-assets/skills/SDLC/tdd/tdd-workflow.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Arguments

`$ARGUMENTS` — the defect in plain language, ideally with a repro or failing-test output / stack trace
(e.g. `"login returns 500 when email has a plus sign — see test_auth.py::test_plus_addressing"`).
Optional `--no-pr` to stop after review (commit only, no PR).

## What this does

The standalone entry to the **defect-fix fast lane**. It runs the canonical
`skills/SDLC/development/defect-fix.md` procedure — the identical flow that `/agentforge --fix` runs,
so the two front doors behave the same. This is a fast lane: it fixes one defect and ships it, and does
**not** enter the full S0–S17 pipeline / `run.json`.

## Procedure

Execute the `defect-fix` skill's phases in order (read it first):

1. **Triage** — spawn `test-triage`; stop if it's a flake/environment issue (not a code change).
2. **Reproduce** — spawn `tdd-guide` to write the **failing test** before touching product code.
3. **Fix** — route by type: a **build-resolver** (build/type error), **`developer`** (logic bug), or
   **`silent-failure-hunter`** (swallowed failure) — minimal diff to green.
4. **Verify** — re-run the suite: the red test passes, nothing regresses.
5. **Review** — `code-reviewer` (+ `security-reviewer` if input/auth/secrets touched).
6. **Ship** — `/prp-commit` then `/prp-pr` (unless `--no-pr`); the PR clears the hard gate via
   `AskUserQuestion` in the main session, with the triage + test + review evidence shown.

## Run in the main session

Do **not** delegate `/fix` to a subagent — it spawns agents and opens the PR gate, which only the main
session can do (D1).

## Related

- `/agentforge --fix <defect>` — the same flow from inside the orchestrator.
- [docs/guides/fast_lane_and_defect_fixing.md](../docs/guides/fast_lane_and_defect_fixing.md) — when to
  use full `/agentforge` vs the PRP fast lane vs `/fix`.
