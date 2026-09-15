---
description: Decompose User Stories into measurable sprint tasks — reads epics-and-user-stories.md, breaks each story into sized/typed/ordered tasks with binary definitions of done, and writes neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md for progress tracking
argument-hint: [path/to/epics-and-user-stories.md] [--story US-NN-SS] [--epic EP-NN] [--update]
---

## Arguments

```
$ARGUMENTS:
  <stories-path>      Path to stories file (default: neuroedge/docs/project_related/<objective-slug>/02-project-plan/epics-and-user-stories.md)
  --story US-NN-SS    Decompose only this one story
  --epic EP-NN        Decompose all stories in this EPIC only
  --update            Add tasks only for stories not yet in task-board.md
```

---

## Phase 0 — DETECT

Resolve the input from `$ARGUMENTS`:

| Input pattern | Action |
|---|---|
| Path to `.md` file | Use directly as stories source |
| `--story US-NN-SS` only | Load existing task-board.md; regenerate only that story's tasks |
| `--epic EP-NN` only | Load existing task-board.md; regenerate tasks for all stories in that EPIC |
| `--update` only | Load both files; find stories that have no tasks in task-board.md yet |
| Empty / blank | Look for `neuroedge/docs/project_related/<objective-slug>/02-project-plan/epics-and-user-stories.md` — use if found, else ask |

Read the stories file fully before proceeding. Then check if `neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md` already exists (for `--update` mode).

---

## Phase 1 — PARSE

Extract and print a scope summary before generating:

```
Stories file:   <filename>
EPICs found:    <N> — <EP-01, EP-02, ...>
Stories found:  <N total> (<N with ACs>, <N without ACs>)
Scope:          <all | EP-NN only | US-NN-SS only | update-only>
Output file:    neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md (<new | updating existing>)
```

**GATE:** If any stories have no ACs, list them. Tasks cannot be generated without ACs.
If > 25% of stories are missing ACs, stop and ask the user to complete the stories first.

---

## Phase 2 — DECOMPOSE

Spawn the `task-writer` agent with the stories file path and scope flags.

The `task-writer` agent will:
1. For each story in scope: map every AC to one or more tasks
2. Size each task (1h / 2h / 4h / 8h), assign type and component
3. Order tasks within each story (infra → code → test → security → docs → validate)
4. Write a binary definition of done per task
5. Note cross-story dependencies
6. Compute per-story and per-EPIC hour totals
7. Validate coverage and return the complete task board markdown

---

## Phase 3 — GENERATE

Write output to `neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md`.

**Full generate** (default — creates the complete file):

The output file has this top-level structure:

```markdown
# [Project Name] — Task Board

**Source:** [epics-and-user-stories.md](neuroedge/docs/project_related/<objective-slug>/02-project-plan/epics-and-user-stories.md)
**Generated:** <today's date>
**Status:** Active — update task checkboxes as work completes

---

## Progress Summary

| EPIC | Stories | Tasks | ⬜ Pending | 🔄 In Progress | ✅ Done | Est. Hours |
|------|---------|-------|-----------|----------------|---------|------------|
| [EP-01 — Bootstrap](link) | N | N | N | 0 | 0 | Nh |
| [EP-02 — Data Plane](link) | N | N | N | 0 | 0 | Nh |
...
| **Total** | **N** | **N** | **N** | **0** | **0** | **Nh** |

---

## How to Use This Board

- Check off tasks with `[x]` as you complete them
- Update the Progress Summary after each sprint
- Run `/stories-to-tasks --update` after adding new stories to epics-and-user-stories.md
- Run `/stories-to-tasks --story US-NN-SS` to regenerate tasks for a revised story

---

[per-EPIC + per-story + task checklists from task-writer agent]

---

## Coverage Check

[coverage table from task-writer agent]
```

**`--story US-NN-SS`** — replace only the `### US-NN-SS` section; update Progress Summary totals.

**`--epic EP-NN`** — replace the full `## EP-NN` section; update Progress Summary totals.

**`--update`** — append task sections for stories not yet in the board; update Progress Summary.

---

## Phase 4 — VALIDATE

After writing the task board, run this check and report:

| Check | Result |
|---|---|
| All stories have ≥ 1 task | ✓ / ✗ |
| All tasks have a definition of done | ✓ / ✗ |
| No task exceeds 8h | ✓ / ✗ |
| No story exceeds 10 tasks | ✓ / ✗ |
| Total estimated hours per EPIC computed | ✓ / ✗ |

List any stories with missing ACs that were skipped.

---

## Phase 5 — OUTPUT

Report to the user:

```
✓ Task board written to neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md

  EPICs covered:   N
  Stories covered: N
  Tasks written:   N
  Est. total:      Nh

  Skipped (no ACs): US-NN-SS, ...  ← if any

  Next steps:
  → /prp-plan neuroedge/docs/project_related/<objective-slug>/02-project-plan/PRD.md           — generate Phase 0 implementation plan from tasks
  → /stories-to-tasks --update      — add tasks after new stories are added
  → /stories-to-tasks --epic EP-NN  — regenerate an EPIC's tasks after story changes
```

---

## Tracking Conventions

Once `neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md` is live, update it as work progresses:

| State | Markdown | When to set |
|---|---|---|
| Pending | `- [ ]` | Default — not started |
| In Progress | `- [~]` | Started but not done (non-standard but readable) |
| Done | `- [x]` | Definition of done verified |

After updating task status, regenerate the Progress Summary table:
- Count `[ ]` → Pending, `[~]` → In Progress, `[x]` → Done per EPIC
- Recompute % Done = Done / Total × 100

---

## Integration with PRP Workflow

```
/prp-prd            → PRD
/prd-to-epics       → EPICs + User Stories   (neuroedge/docs/project_related/<objective-slug>/02-project-plan/epics-and-user-stories.md)
/stories-to-tasks   → Task Board             (neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md)              ← you are here
/prp-plan           → Implementation Plan    (neuroedge/docs/project_related/<objective-slug>/02-project-plan/*.plan.md)
/prp-implement      → Execution + marking tasks [x]
/prp-commit         → Commit + update board
/prp-pr             → PR with task coverage summary
```

Tasks in `neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md` directly inform the Steps in `/prp-plan` implementation plans. When writing a plan step, reference the task ID (`TS-NN-SS-TT`) so the plan is traceable from Step → Task → Story AC → PRD FR.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /stories-to-tasks · Skills: stories-to-tasks, prd-decomposition`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/requirements/stories-to-tasks.md`
> - `agentic-assets/skills/SDLC/requirements/prd-decomposition.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->
