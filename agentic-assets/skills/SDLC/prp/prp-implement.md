---
name: prp-implement
description: Plan-execution procedure: per-task RED->GREEN TDD loop, five-level validation, implementation report, and PRD/EPIC/task-board trace sync.
origin: NeuroEdge
---

# PRP — Plan Execution

The full `prp-implement` procedure. It is single-sourced here so the exact same steps run whether a human invokes `/prp-implement` or a subagent reads this skill. The invoking command passes its `$ARGUMENTS` through as this procedure's input.

## Gate delegation

This procedure pauses at one or more points to ask the user a question and wait for the
answer (marked **GATE**, **STOP**, or **CHECKPOINT** below). Those questions can only be
asked from the main session: per decision D1 a subagent running this skill can neither
call `AskUserQuestion` nor spawn another agent. When this skill runs inside a subagent it
must surface each gate's question in its returned result and stop there; the main-session
orchestrator (`/agentforge`, or the human running the slash command) asks the user and
re-invokes the skill with the answer. Never silently skip a gate — dropping the question
would let a subagent bypass a control this procedure requires.

## Phase 0 — DETECT

### Package Manager Detection

| File Exists | Package Manager | Runner |
|---|---|---|
| `bun.lockb` | bun | `bun run` |
| `pnpm-lock.yaml` | pnpm | `pnpm run` |
| `yarn.lock` | yarn | `yarn` |
| `package-lock.json` | npm | `npm run` |
| `pyproject.toml` or `requirements.txt` | uv / pip | `uv run` or `python -m` |
| `Cargo.toml` | cargo | `cargo` |
| `go.mod` | go | `go` |

### Validation Scripts

Check `package.json` (or equivalent) for available scripts:

```bash
# For Node.js projects
cat package.json | grep -A 20 '"scripts"'
```

Note available commands for: type-check, lint, test, build.

---

## Phase 1 — LOAD

Read the plan file:

```bash
cat "$ARGUMENTS"
```

Extract these sections from the plan:
- **Summary** — What is being built
- **Patterns to Mirror** — Code conventions to follow
- **Files to Change** — What to create or modify
- **Step-by-Step Tasks** — Implementation sequence
- **Validation Commands** — How to verify correctness
- **Acceptance Criteria** — Definition of done

If the file doesn't exist or isn't a valid plan:
```
Error: Plan file not found or invalid.
Run /prp-plan <feature-description> to create a plan first.
```

**CHECKPOINT**: Plan loaded. All sections identified. Tasks extracted.

---

## Phase 2 — PREPARE

### Git State

```bash
git branch --show-current
git status --porcelain
```

### Branch Decision

| Current State | Action |
|---|---|
| On feature branch | Use current branch |
| On main, clean working tree | Create feature branch: `git checkout -b feat/{plan-name}` |
| On main, dirty working tree | **STOP** — Ask user to stash or commit first |
| In a git worktree for this feature | Use the worktree |

### Sync Remote

```bash
git pull --rebase origin $(git branch --show-current) 2>/dev/null || true
```

**CHECKPOINT**: On correct branch. Working tree ready. Remote synced.

---

## Phase 3 — EXECUTE

Process each task from the plan sequentially.

### Per-Task Loop (test-first — RED, GREEN, REFACTOR)

For each task in **Step-by-Step Tasks**, apply the `tdd-guide` methodology
(`agentic-assets/skills/SDLC/tdd/tdd-workflow.md`) directly in this loop — do not defer test-writing to Phase 4:

0. **Carry prior findings forward (TD-013)** — before writing code for a file, note the *specific* defects
   already found in it (earlier in this session, in recent `docs/decisions/TECH-DEBT.md` entries, or in
   `git log`), and name the existing helper to reuse rather than writing a variant. TD-013 measured this as
   the highest-leverage cost control available, at ~0 extra tokens: preventing a defect class is far cheaper
   than reviewing it back out. Two patterns it names from real escaped defects — a fix applied to one code
   path but not its sibling, and a regression test that passes without testing anything (done means
   *observed failing against the pre-fix code*, not merely green).

1. **Read MIRROR reference** — Open the pattern file referenced in the task's MIRROR field. Understand the convention
   before writing code.

2. **Write the failing test (RED)** — Use the task's `TEST FIRST (RED)` field. If the plan predates this field (older
   plan), write the test now, following the plan's Testing Strategy / Test Patterns instead. Run it and confirm it
   **fails for the expected reason** (missing implementation, not a syntax/import error).

3. **Implement minimally (GREEN)** — Use the task's `IMPLEMENT (GREEN)` field. Write only enough code to make the RED
   test pass — apply GOTCHA warnings, use specified IMPORTS, follow the MIRROR pattern exactly.

4. **Validate immediately** — After EVERY file change:
   ```bash
   # Run type-check (adjust command per project)
   [type-check command from Phase 0]
   # Run the test written in step 2 — must now pass
   [test command scoped to this test]
   ```
   If type-check fails or the test doesn't turn GREEN → fix before moving on.

5. **Refactor** — With the test GREEN, clean up (naming, duplication, structure) while keeping it passing. Skip if
   there's nothing to improve.

6. **Track progress** — Log: `[done] Task N: [task name] (TS-NN-SS-TT) — RED → GREEN → complete`. If the task
   cites a `TASK ID` (`TS-NN-SS-TT`), immediately flip that task's checkbox in
   `neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md` from `- [ ]` to `- [x]`. There is one backlog per project,
   shared by every plan track. Keep the board live task-by-task rather than only syncing it at the end;
   if a run is interrupted, completed work still shows as done.

For Large/XL-complexity tasks, or when a task's `TEST FIRST` field is ambiguous, spawn the `tdd-guide` agent for that
task instead of running this abbreviated loop yourself.

### Handling Deviations

If implementation must deviate from the plan:
- Note **WHAT** changed
- Note **WHY** it changed
- Continue with the corrected approach
- These deviations will be captured in the report

**CHECKPOINT**: All tasks executed. Deviations logged.

---

## Phase 4 — VALIDATE

Run all validation levels from the plan. Fix issues at each level before proceeding.

### Level 1: Static Analysis

```bash
# Type checking — zero errors required
[project type-check command]

# Linting — fix automatically where possible
[project lint command]
[project lint-fix command]
```

If lint errors remain after auto-fix, fix manually.

### Level 2: Unit Tests

Tests were already written test-first per task in Phase 3 (RED → GREEN). This level re-runs the **full** suite for
the affected area to catch cross-task regressions, then checks coverage against the plan's Testing Strategy.

```bash
[project test command for affected area]
```

- Confirm every function has at least one test (cross-check against Phase 3's per-task RED tests)
- Cover edge cases listed in the plan — write any that were missed during the per-task loop
- If a test fails → fix the implementation (not the test, unless the test is wrong)

### Level 3: Build Check

```bash
[project build command]
```

Build must succeed with zero errors.

### Level 4: Integration Testing (if applicable)

```bash
# Start server, run tests, stop server
[project dev server command] &
SERVER_PID=$!

# Wait for server to be ready (adjust port as needed)
SERVER_READY=0
for i in $(seq 1 30); do
  if curl -sf http://localhost:PORT/health >/dev/null 2>&1; then
    SERVER_READY=1
    break
  fi
  sleep 1
done

if [ "$SERVER_READY" -ne 1 ]; then
  kill "$SERVER_PID" 2>/dev/null || true
  echo "ERROR: Server failed to start within 30s" >&2
  exit 1
fi

[integration test command]
TEST_EXIT=$?

kill "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true

exit "$TEST_EXIT"
```

### Level 5: Edge Case Testing

Run through edge cases from the plan's Testing Strategy checklist.

**CHECKPOINT**: All 5 validation levels pass. Zero errors.

---

## Phase 5 — REPORT

### Create Implementation Report

```bash
mkdir -p neuroedge/docs/project_related/<objective-slug>/02-project-plan/reports
```

Write report to `neuroedge/docs/project_related/<objective-slug>/02-project-plan/reports/{plan-name}-report.md`:

```markdown
# Implementation Report: [Feature Name]

## Summary
[What was implemented]

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | [from plan] | [actual] |
| Confidence | [from plan] | [actual] |
| Files Changed | [from plan] | [actual count] |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | [task name] | [done] Complete | |
| 2 | [task name] | [done] Complete | Deviated — [reason] |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static Analysis | [done] Pass | |
| Unit Tests | [done] Pass | N tests written |
| Build | [done] Pass | |
| Integration | [done] Pass | or N/A |
| Edge Cases | [done] Pass | |

## Files Changed

| File | Action | Lines |
|---|---|---|
| `path/to/file` | CREATED | +N |
| `path/to/file` | UPDATED | +N / -M |

## Deviations from Plan
[List any deviations with WHAT and WHY, or "None"]

## Issues Encountered
[List any problems and how they were resolved, or "None"]

## Tests Written

| Test File | Tests | Coverage |
|---|---|---|
| `path/to/test` | N tests | [area covered] |

## Next Steps
- [ ] Code review via `/code-review`
- [ ] Create PR via `/prp-pr`
```

### Update PRD (if applicable)

If this implementation was for a PRD phase:
1. Update the phase status from `in-progress` to `complete`
2. Add report path as reference

### Update Task Board & EPIC Status (if applicable)

Close the loop back through the full PRD → EPIC → Story → Task chain, not just the PRD:

1. In `neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md`:
   - Confirm every task cited by a `TASK ID` in this plan is checked `[x]` (Phase 3 should have already flipped
     each one live; catch any missed here — e.g. a task added mid-run without a matching plan step).
   - Recompute the Progress Summary table: per-EPIC Pending / In Progress / Done counts and remaining Est. Hours.
2. In `neuroedge/docs/project_related/<objective-slug>/02-project-plan/epics-and-user-stories.md`:
   - If every task belonging to a story is now `[x]` in the task board, that story is implementation-complete.
   - If every story in the EPIC this plan covered is now fully task-complete, update that EPIC's `Status` in the
     EPIC INDEX table from `in-progress` to `done` — mirroring the PRD phase update above. If this plan only
     covered some of the EPIC's stories, leave the EPIC status as `in-progress`.
3. If either file isn't found for this `<track>`, skip silently — not every plan traces back to a stories/task-board
   pair (e.g. a standalone plan created from free-form input).

### Archive Plan

```bash
mkdir -p neuroedge/docs/project_related/<objective-slug>/02-project-plan/completed
mv "$ARGUMENTS" neuroedge/docs/project_related/<objective-slug>/02-project-plan/completed/
```

**CHECKPOINT**: Report created. PRD updated. Plan archived.

---

## Phase 6 — OUTPUT

Report to user:

```
## Implementation Complete

- **Plan**: [plan file path] → archived to completed/
- **Branch**: [current branch name]
- **Status**: [done] All tasks complete

### Validation Summary

| Check | Status |
|---|---|
| Type Check | [done] |
| Lint | [done] |
| Tests | [done] (N written) |
| Build | [done] |
| Integration | [done] or N/A |

### Files Changed
- [N] files created, [M] files updated

### Deviations
[Summary or "None — implemented exactly as planned"]

### Artifacts
- Report: `neuroedge/docs/project_related/<objective-slug>/02-project-plan/reports/{name}-report.md`
- Archived Plan: `neuroedge/docs/project_related/<objective-slug>/02-project-plan/completed/{name}.plan.md`

### PRD Progress (if applicable)
| Phase | Status |
|---|---|
| Phase 1 | [done] Complete |
| Phase 2 | [next] |
| ... | ... |

### Trace Sync (if applicable)
- **Task Board**: [N] tasks flipped to `[x]` in `task-board.md` (or "no task-board.md found for this track")
- **EPIC Status**: `EP-NN` → `in-progress` / `done` in `epics-and-user-stories.md` (or "N/A — plan not sourced from a stories file")

> Next step: Run `/prp-pr` to create a pull request, or `/code-review` to review changes first.
```

---

## Handling Failures

### Type Check Fails
1. Read the error message carefully
2. Fix the type error in the source file
3. Re-run type-check
4. Continue only when clean

### Tests Fail
1. Identify whether the bug is in the implementation or the test
2. Fix the root cause (usually the implementation)
3. Re-run tests
4. Continue only when green

### Lint Fails
1. Run auto-fix first
2. If errors remain, fix manually
3. Re-run lint
4. Continue only when clean

### Build Fails
1. Usually a type or import issue — check error message
2. Fix the offending file
3. Re-run build
4. Continue only when successful

### Integration Test Fails
1. Check server started correctly
2. Verify endpoint/route exists
3. Check request format matches expected
4. Fix and re-run

---

## Success Criteria

- **TASKS_COMPLETE**: All tasks from the plan executed
- **TYPES_PASS**: Zero type errors
- **LINT_PASS**: Zero lint errors
- **TESTS_PASS**: All tests green, new tests written
- **BUILD_PASS**: Build succeeds
- **REPORT_CREATED**: Implementation report saved
- **PLAN_ARCHIVED**: Plan moved to `completed/`

---

## Next Steps

- Run `/code-review` to review changes before committing — **one reviewer by default**, working from the
  **diff** (`git show <sha>`) and opening whole files only where a finding requires it. Add
  `security-reviewer` alongside it only when the change touches a trust boundary, authn, secrets, or
  untrusted input. TD-013 measured two reviewers at 213K tokens against 96K for one, which still found
  2 HIGH. Cap at two rounds: if a second still returns blocking findings, escalate rather than loop.
  This reduces cost **per round** — never the number of gates, and never a reason to skip the review.
- Run `/prp-commit` to commit with a descriptive message
- Run `/prp-pr` to create a pull request
- Run `/prp-plan <next-phase>` if the PRD has more phases
