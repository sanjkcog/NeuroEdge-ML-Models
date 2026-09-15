---
name: prp-plan
description: Implementation-plan generation procedure: codebase pattern extraction, task-board cross-reference, and a test-first (RED->GREEN) plan template.
origin: NeuroEdge
---

# PRP — Implementation Plan

The full `prp-plan` procedure. It is single-sourced here so the exact same steps run whether a human invokes `/prp-plan` or a subagent reads this skill. The invoking command passes its `$ARGUMENTS` through as this procedure's input.

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

Determine input type from `$ARGUMENTS`:

| Input Pattern | Detection | Action |
|---|---|---|
| Path ending in `.prd.md` | File path to PRD | Parse PRD, find next pending phase |
| Path to `.md` with "Implementation Phases" | PRD-like document | Parse phases, find next pending |
| Path to `task-board.md` | Task board | Ask which EPIC/story to plan for (or auto-select the EPIC with the most `[ ]` pending tasks); extract only that EPIC's tasks |
| Path to any other file | Reference file | Read file for context, treat as free-form |
| Free-form text | Feature description | Proceed directly to Phase 1 |
| Empty / blank | No input | Ask user what feature to plan |

### PRD Parsing (when input is a PRD)

1. Read the PRD file with `cat "$PRD_PATH"`
2. Parse the **Implementation Phases** section
3. Find phases by status:
   - Look for `pending` phases
   - Check dependency chains (a phase may depend on prior phases being `complete`)
   - Select the **next eligible pending phase**
4. Extract from the selected phase:
   - Phase name and description
   - Acceptance criteria
   - Dependencies on prior phases
   - Any scope notes or constraints
5. Use the phase description as the feature to plan

If no pending phases remain, report that all phases are complete.

### Task Board Cross-Reference (always attempted when input is a PRD or task-board.md)

This closes the traceability gap between `/stories-to-tasks` and `/prp-plan` — task IDs must land in the plan, not
just be cited by convention.

1. Determine `<track>` from the PRD path (or from the task-board path itself).
2. Look for a sibling file: `neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md`.
3. **If found:**
   - Read it. Match tasks whose story belongs to the EPIC/phase selected in PRD Parsing above (or the EPIC/story the
     user specified when the input was a task-board.md path).
   - Build a lookup: `story AC → task ID(s) (TS-NN-SS-TT)`.
   - Carry this lookup into Phase 6 GENERATE — every Step-by-Step Task in the plan that satisfies a story AC must cite
     its `TS-NN-SS-TT` id(s) in a **TASK ID** field (see Plan Template below).
4. **If not found:** proceed without task IDs, but note in the plan's `## Notes` section: "No task-board.md found at
   `backlog/task-board.md` — run `/stories-to-tasks` first for full Story → Task → Plan Step traceability."

---

## Phase 1 — PARSE

Extract and clarify the feature requirements.

### Feature Understanding

From the input (PRD phase or free-form description), identify:

- **What** is being built (concrete deliverable)
- **Why** it matters (user value)
- **Who** uses it (target user/system)
- **Where** it fits (which part of the codebase)

### User Story

Format as:
```
As a [type of user],
I want [capability],
So that [benefit].
```

### Complexity Assessment

| Level | Indicators | Typical Scope |
|---|---|---|
| **Small** | Single file, isolated change, no new dependencies | 1-3 files, <100 lines |
| **Medium** | Multiple files, follows existing patterns, minor new concepts | 3-10 files, 100-500 lines |
| **Large** | Cross-cutting concerns, new patterns, external integrations | 10+ files, 500+ lines |
| **XL** | Architectural changes, new subsystems, migration needed | 20+ files, consider splitting |

### Ambiguity Gate

If any of these are unclear, **STOP and ask the user** before proceeding:

- The core deliverable is vague
- Success criteria are undefined
- There are multiple valid interpretations
- Technical approach has major unknowns

Do NOT guess. Ask. A plan built on assumptions fails during implementation.

---

## Phase 2 — EXPLORE

Gather deep codebase intelligence. Search the codebase directly for each category below.

### Codebase Search (8 Categories)

For each category, search using grep, find, and file reading:

1. **Similar Implementations** — Find existing features that resemble the planned one. Look for analogous patterns, endpoints, components, or modules.

2. **Naming Conventions** — Identify how files, functions, variables, classes, and exports are named in the relevant area of the codebase.

3. **Error Handling** — Find how errors are caught, propagated, logged, and returned to users in similar code paths.

4. **Logging Patterns** — Identify what gets logged, at what level, and in what format.

5. **Type Definitions** — Find relevant types, interfaces, schemas, and how they're organized.

6. **Test Patterns** — Find how similar features are tested. Note test file locations, naming, setup/teardown patterns, and assertion styles.

7. **Configuration** — Find relevant config files, environment variables, and feature flags.

8. **Dependencies** — Identify packages, imports, and internal modules used by similar features.

### Codebase Analysis (5 Traces)

Read relevant files to trace:

1. **Entry Points** — How does a request/action enter the system and reach the area you're modifying?
2. **Data Flow** — How does data move through the relevant code paths?
3. **State Changes** — What state is modified and where?
4. **Contracts** — What interfaces, APIs, or protocols must be honored?
5. **Patterns** — What architectural patterns are used (repository, service, controller, etc.)?

### Unified Discovery Table

Compile findings into a single reference:

| Category | File:Lines | Pattern | Key Snippet |
|---|---|---|---|
| Naming | `src/services/userService.ts:1-5` | camelCase services, PascalCase types | `export class UserService` |
| Error | `src/middleware/errorHandler.ts:10-25` | Custom AppError class | `throw new AppError(...)` |
| ... | ... | ... | ... |

---

## Phase 3 — RESEARCH

If the feature involves external libraries, APIs, or unfamiliar technology:

1. Search the web for official documentation
2. Find usage examples and best practices
3. Identify version-specific gotchas

Format each finding as:

```
KEY_INSIGHT: [what you learned]
APPLIES_TO: [which part of the plan this affects]
GOTCHA: [any warnings or version-specific issues]
```

If the feature uses only well-understood internal patterns, skip this phase and note: "No external research needed — feature uses established internal patterns."

---

## Phase 4 — DESIGN

### UX Transformation (if applicable)

Document the before/after user experience:

**Before:**
```
┌─────────────────────────────┐
│  [Current user experience]  │
│  Show the current flow,     │
│  what the user sees/does    │
└─────────────────────────────┘
```

**After:**
```
┌─────────────────────────────┐
│  [New user experience]      │
│  Show the improved flow,    │
│  what changes for the user  │
└─────────────────────────────┘
```

### Interaction Changes

| Touchpoint | Before | After | Notes |
|---|---|---|---|
| ... | ... | ... | ... |

If the feature is purely backend/internal with no UX change, note: "Internal change — no user-facing UX transformation."

---

## Phase 5 — ARCHITECT

### Strategic Design

Define the implementation approach:

- **Approach**: High-level strategy (e.g., "Add new service layer following existing repository pattern")
- **Alternatives Considered**: What other approaches were evaluated and why they were rejected
- **Scope**: Concrete boundaries of what WILL be built
- **NOT Building**: Explicit list of what is OUT OF SCOPE (prevents scope creep during implementation)

---

## Phase 6 — GENERATE

Write the full plan document using the template below. Save to `neuroedge/docs/project_related/<objective-slug>/02-project-plan/{kebab-case-feature-name}.plan.md`.

`<track>` groups plans/epics/tasks so a track's whole backlog stays together. Framework tracks: `backend` (from
`prd/neuroedge-agentic-ai-backend.prd.md`) and `portal` (from `prd/neuroedge-agentic-ai-studio-portal.prd.md`).
Use-case tracks: `industries/<industry>/<use-case>` (e.g. `industries/automotive/connected-vehicle-oem`) for work
building a concrete use case on the framework. Pick the track from the source PRD / use-case brief; if it can't be
determined, ask the user rather than guessing.

Create the directory if it doesn't exist:
```bash
mkdir -p neuroedge/docs/project_related/<objective-slug>/02-project-plan
```

### Plan Template

````markdown
# Plan: [Feature Name]

## Summary
[2-3 sentence overview]

## User Story
As a [user], I want [capability], so that [benefit].

## Problem → Solution
[Current state] → [Desired state]

## Metadata
- **Complexity**: [Small | Medium | Large | XL]
- **Source PRD**: [path or "N/A"]
- **PRD Phase**: [phase name or "N/A"]
- **Estimated Files**: [count]

---

## UX Design

### Before
[ASCII diagram or "N/A — internal change"]

### After
[ASCII diagram or "N/A — internal change"]

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|

---

## Mandatory Reading

Files that MUST be read before implementing:

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 (critical) | `path/to/file` | 1-50 | Core pattern to follow |
| P1 (important) | `path/to/file` | 10-30 | Related types |
| P2 (reference) | `path/to/file` | all | Similar implementation |

## External Documentation

| Topic | Source | Key Takeaway |
|---|---|---|
| ... | ... | ... |

---

## Patterns to Mirror

Code patterns discovered in the codebase. Follow these exactly.

### NAMING_CONVENTION
// SOURCE: [file:lines]
[actual code snippet showing the naming pattern]

### ERROR_HANDLING
// SOURCE: [file:lines]
[actual code snippet showing error handling]

### LOGGING_PATTERN
// SOURCE: [file:lines]
[actual code snippet showing logging]

### REPOSITORY_PATTERN
// SOURCE: [file:lines]
[actual code snippet showing data access]

### SERVICE_PATTERN
// SOURCE: [file:lines]
[actual code snippet showing service layer]

### TEST_STRUCTURE
// SOURCE: [file:lines]
[actual code snippet showing test setup]

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `path/to/file.ts` | CREATE | New service for feature |
| `path/to/existing.ts` | UPDATE | Add new method |

## NOT Building

- [Explicit item 1 that is out of scope]
- [Explicit item 2 that is out of scope]

---

## Step-by-Step Tasks

Each task is written test-first (RED → GREEN) so `/prp-implement` can execute it as real TDD, not just
implement-then-test. `TASK ID` traces back to `/stories-to-tasks`' output — see Task Board Cross-Reference above.

### Task 1: [Name]
- **TASK ID**: [`TS-NN-SS-TT` from task-board.md, or "N/A — no task board for this plan"]
- **ACTION**: [What to do]
- **TEST FIRST (RED)**: [The specific failing test to write before any implementation — test name + assertion]
- **IMPLEMENT (GREEN)**: [Minimal code/logic to make that test pass]
- **MIRROR**: [Pattern from Patterns to Mirror section to follow]
- **IMPORTS**: [Required imports]
- **GOTCHA**: [Known pitfall to avoid]
- **VALIDATE**: [Run the test — confirm it fails before IMPLEMENT, passes after; refactor if needed]

### Task 2: [Name]
- **TASK ID**: ...
- **ACTION**: ...
- **TEST FIRST (RED)**: ...
- **IMPLEMENT (GREEN)**: ...
- **MIRROR**: ...
- **IMPORTS**: ...
- **GOTCHA**: ...
- **VALIDATE**: ...

[Continue for all tasks...]

---

## Testing Strategy

### Unit Tests

| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| ... | ... | ... | ... |

### Edge Cases Checklist
- [ ] Empty input
- [ ] Maximum size input
- [ ] Invalid types
- [ ] Concurrent access
- [ ] Network failure (if applicable)
- [ ] Permission denied

---

## Validation Commands

### Static Analysis
```bash
# Run type checker
[project-specific type check command]
```
EXPECT: Zero type errors

### Unit Tests
```bash
# Run tests for affected area
[project-specific test command]
```
EXPECT: All tests pass

### Full Test Suite
```bash
# Run complete test suite
[project-specific full test command]
```
EXPECT: No regressions

### Database Validation (if applicable)
```bash
# Verify schema/migrations
[project-specific db command]
```
EXPECT: Schema up to date

### Browser Validation (if applicable)
```bash
# Start dev server and verify
[project-specific dev server command]
```
EXPECT: Feature works as designed

### Manual Validation
- [ ] [Step-by-step manual verification checklist]

---

## Acceptance Criteria
- [ ] All tasks completed
- [ ] All validation commands pass
- [ ] Tests written and passing
- [ ] No type errors
- [ ] No lint errors
- [ ] Matches UX design (if applicable)

## Completion Checklist
- [ ] Code follows discovered patterns
- [ ] Error handling matches codebase style
- [ ] Logging follows codebase conventions
- [ ] Tests follow test patterns
- [ ] No hardcoded values
- [ ] Documentation updated (if needed)
- [ ] No unnecessary scope additions
- [ ] Self-contained — no questions needed during implementation

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| ... | ... | ... | ... |

## Notes
[Any additional context, decisions, or observations]
```

---

## Output

### Save the Plan

Write the generated plan to:
```
neuroedge/docs/project_related/<objective-slug>/02-project-plan/{kebab-case-feature-name}.plan.md
```

### Update PRD (if input was a PRD)

If this plan was generated from a PRD phase:
1. Update the phase status from `pending` to `in-progress`
2. Add the plan file path as a reference in the phase
3. If a sibling `epics-and-user-stories.md` exists for this `<track>` (same lookup as the Task Board
   Cross-Reference in Phase 0), also flip the matching EPIC's `Status` in its EPIC INDEX table from `pending` to
   `in-progress`. This keeps the PRD phase and the EPIC status from drifting apart the moment planning starts,
   instead of only syncing once `/prp-implement` finishes. If no matching stories file is found, skip silently.

### Report to User

```
## Plan Created

- **File**: neuroedge/docs/project_related/<objective-slug>/02-project-plan/{kebab-case-feature-name}.plan.md
- **Source PRD**: [path or "N/A"]
- **Phase**: [phase name or "standalone"]
- **Complexity**: [level]
- **Scope**: [N files, M tasks]
- **Task Board Coverage**: [N of M tasks cite a TASK ID from task-board.md, or "No task-board.md found — run /stories-to-tasks first"]
- **Key Patterns**: [top 3 discovered patterns]
- **External Research**: [topics researched or "none needed"]
- **Risks**: [top risk or "none identified"]
- **Confidence Score**: [1-10] — likelihood of single-pass implementation

> Next step: Run `/prp-implement neuroedge/docs/project_related/<objective-slug>/02-project-plan/{name}.plan.md` to execute this plan.
```

---

## Verification

Before finalizing, verify the plan against these checklists:

### Context Completeness
- [ ] All relevant files discovered and documented
- [ ] Naming conventions captured with examples
- [ ] Error handling patterns documented
- [ ] Test patterns identified
- [ ] Dependencies listed

### Implementation Readiness
- [ ] Every task has ACTION, IMPLEMENT, MIRROR, and VALIDATE
- [ ] No task requires additional codebase searching
- [ ] Import paths are specified
- [ ] GOTCHAs documented where applicable

### Pattern Faithfulness
- [ ] Code snippets are actual codebase examples (not invented)
- [ ] SOURCE references point to real files and line numbers
- [ ] Patterns cover naming, errors, logging, data access, and tests
- [ ] New code will be indistinguishable from existing code

### Validation Coverage
- [ ] Static analysis commands specified
- [ ] Test commands specified
- [ ] Build verification included

### UX Clarity
- [ ] Before/after states documented (or marked N/A)
- [ ] Interaction changes listed
- [ ] Edge cases for UX identified

### No Prior Knowledge Test
A developer unfamiliar with this codebase should be able to implement the feature using ONLY this plan, without searching the codebase or asking questions. If not, add the missing context.

---

## Next Steps

- Run `/prp-implement <plan-path>` to execute this plan
- Run `/plan` for quick conversational planning without artifacts
- Run `/prp-prd` to create a PRD first if scope is unclear
````
