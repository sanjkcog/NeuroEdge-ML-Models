---
name: test-plan-generation
description: Generate a tool-neutral test plan with TC-NN-SS-TT identifiers traced to acceptance criteria, before any test is written — the procedure /test-plan and the qa-engineer agent both follow.
origin: NeuroEdge
---

# Test Plan Generation

Produces `neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md`: a test plan derived from
requirements, not retrofitted after the build. Every generated test case carries a
`TC-NN-SS-TT` identifier tracing back to the acceptance criteria it verifies, extending
the existing `FR → EPIC → Story → AC` chain by one more link.

`<track>` is the PRD group the objective belongs to (`backend`, `portal`, `industries`, …),
matching the existing `plan/<group>/` names — never an objective slug. The plan is
track-scoped so parallel tracks each keep their own, rather than overwriting one
project-wide file.

## When to Activate

- `/test-plan` is invoked directly
- The orchestrator spawns `qa-engineer` at stage S6
- A human needs a test plan traced to requirements before writing any test code

## Inputs

Read `neuroedge/docs/project_related/<objective-slug>/02-project-plan/epics-and-user-stories.md` (or the path given) for
the story/AC set to trace against. If a sibling `task-board.md` exists for the same
track, cross-reference it the same way `/prp-plan` does, so generated test cases can
also cite a `TS-NN-SS-TT` task ID where one exists — this is optional context, not a
requirement (not every AC has a task yet).

## Procedure

1. **Parse every story's acceptance criteria.** For each AC, determine whether a test
   case can be generated from it directly (a concrete, checkable behavior) or whether it
   is aspirational/manual (e.g. a `[manual]` AC) and cannot be automated yet.
2. **Assign `TC-NN-SS-TT` identifiers.** The numbering mirrors the AC's own EPIC/Story
   numbering (`NN` = EPIC number, `SS` = Story number within it), with `TT` incrementing
   per test case generated for that story, starting at `01`. IDs are assigned once and
   never renumbered — a later edit appends new IDs rather than shifting existing ones,
   the same stability rule `/prp-prd`'s `FR-NN` codes already follow.
3. **List unmapped ACs explicitly.** An AC that cannot be mapped to a test case (vague,
   manual, or genuinely untestable) is listed in a dedicated "Unmapped" section with the
   reason — **never silently dropped**. This is the single most important rule in this
   skill: a test plan that quietly excludes what it can't cover isn't a plan, it's a
   guess dressed up as one.
4. **Bind the convention into every test case description.** Each planned test names the
   exact binding comment it expects the eventual test to carry:
   ```python
   def test_ppe_helmet_detected_at_25fps():   # @tc TC-01-03-02
   ```
   This is what lets `/trace-matrix` later correlate a written test back to this plan
   without any separate registry.
5. **Work with no vendor configured.** This plan and its TC-IDs are tool-neutral by
   design (D12) — never assume Zephyr Scale, TestRail, or any other vendor is present.
   Vendor translation is `agentforge/src/qa/`'s concern at export time, not this skill's.
6. **Enter the S6 hard gate.** `neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md` is a gated
   artifact — state this explicitly in the output; do not imply the plan is final before it's approved.

## Output Format

```markdown
# Test Plan: <track/feature name>

## Coverage Summary
| Metric | Count |
|---|---|
| Stories covered | N |
| ACs mapped | N |
| ACs unmapped | N |

## Test Cases

### TC-01-03-01
- **Traces to**: US-01-03, AC "..."
- **Task**: TS-01-03-02 (if a task board exists, else "N/A")
- **Binding**: `# @tc TC-01-03-01`
- **Description**: <what this test verifies>

...

## Unmapped Acceptance Criteria
| Story | AC | Reason unmapped |
|---|---|---|
| US-NN-SS | "..." | e.g. `[manual]`, no checkable behavior yet |
```

## Gate delegation

`neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md` enters a hard gate (S6). This skill does not itself call
`AskUserQuestion` — approving the gate is the main session's job (D1), via
`gate_state.py`'s `open`/`decide` commands, exactly as documented for the other
hard-gated artifacts (S2/S3) in `commands/agentforge.md`. A subagent running this skill
must surface "ready for the S6 gate" in its returned result and stop there.
