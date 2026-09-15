---
name: stories-to-tasks
description: Decompose User Stories into measurable, trackable tasks with sizing, component assignment, dependency ordering, and a definition of done. Produces a task board for sprint-level progress tracking. Use after /prd-to-epics, before /prp-plan.
origin: NeuroEdge
---

# Stories to Tasks — Sprint Decomposition

Turn User Stories into a trackable task board. Every task must be independently completable, have a falsifiable definition of done, and fit within one working session (≤ 8 hours).

## Where This Fits in the Workflow

```
/prp-prd          → PRD
/prd-to-epics     → EPICs + User Stories  (neuroedge/docs/project_related/<objective-slug>/02-project-plan/epics-and-user-stories.md)
/stories-to-tasks → Tasks                 (neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md)        ← this skill
/prp-plan         → Implementation Plan   (neuroedge/docs/project_related/<objective-slug>/02-project-plan/*.plan.md)
/prp-implement    → Execution + commit
```

Stories define WHAT and WHY. Tasks define the exact HOW — specific files to create, commands to run, and a binary done/not-done signal.

---

## Task Definition

A task is the smallest unit of work that is:

- **Completable in one session** — ≤ 8 hours; ideally 1–4 hours
- **Independently verifiable** — has a specific, binary definition of done
- **Scoped to one component** — touches one container, layer, or file set
- **Verb-first** — starts with an action word (Create, Implement, Configure, Write, Add, Fix, Run, Validate)

---

## Task ID Scheme

`TS-NN-SS-TT`

| Part | Meaning | Example |
|------|---------|---------|
| `TS` | Task prefix | fixed |
| `NN` | EPIC number (zero-padded) | `01` = EP-01 |
| `SS` | Story sequence within EPIC | `02` = US-01-02 |
| `TT` | Task sequence within story | `03` = third task |

Full example: `TS-01-02-03` = EPIC 1, Story 2, Task 3.

---

## Task Line Format

Each task is one markdown checkbox line:

```
- [ ] **TS-NN-SS-TT** `(Nh, type, component)` [Verb] [specific object] — **Done:** [verifiable outcome]
```

Fields:

| Field | Values | Notes |
|-------|--------|-------|
| `N h` | 1h, 2h, 4h, 8h | Round to nearest; never invent false precision |
| `type` | `code`, `test`, `config`, `infra`, `docs`, `security`, `validate` | One type per task |
| `component` | container name, layer, or file (e.g. `ne-data-plane`, `ne-control-plane`, `CI`) | Omit if obvious from context |
| Definition of done | One sentence, present tense, begins with a command or observable state | Add `[manual]` if not automatable |

Example:
```
- [ ] **TS-01-01-02** `(2h, code, ne-data-plane)` Write root `CMakeLists.txt` with `-std=c++17` stub target — **Done:** `cmake --preset x86` exits 0 with no warnings
```

---

## Task Sizing Rules

| Size | Hours | When to use |
|------|-------|-------------|
| Tiny | 1h | Edit one file, add one config entry, run one verification command |
| Small | 2h | Write one class or function, including its unit test |
| Medium | 4h | Implement a feature with multiple functions, integration test |
| Large | 8h | Implement a complete subsystem boundary **— MUST split if the story requires more than 2 large tasks** |

If a story produces > 10 tasks: the story was too big. Flag it and suggest splitting along the seams in the `prd-decomposition` skill.

---

## Task Type Taxonomy

| Type | What it covers | Typical done signal |
|------|---------------|---------------------|
| `code` | Production code (C++, Python, TS) | Test or build passes |
| `test` | Test code (unit, integration, E2E) | Test suite green |
| `config` | Config files (YAML, JSON, Dockerfile, CMake, Conan, Terraform) | Tool parses without error |
| `infra` | Cloud/CI resources (ECR, S3, IAM, GitHub Actions job) | Resource exists or pipeline runs |
| `docs` | Documentation (README, runbook, API docs, inline comments) | File exists at expected path [manual] |
| `security` | Certs, scanning, hardening (cosign, grype, ufw, Wazuh) | Scan passes or tool reports clean |
| `validate` | Manual or automated verification steps | Explicit pass/fail signal defined |

---

## Ordering Rules — Default Task Sequence Within a Story

Unless the story demands otherwise, tasks in a story follow this canonical order:

1. **infra / config** — create the scaffold that makes code possible (dirs, configs, Dockerfiles, CI jobs)
2. **code** — implement the production logic
3. **test** — write unit and integration tests
4. **security** — apply hardening or scanning
5. **docs** — write documentation
6. **validate** — run the final verification against the AC

This order minimises re-work: you configure before you code, you test after you code.

**Cross-story dependencies:** If a task in US-NN-SS-B depends on a task in US-NN-SS-A completing first, note it as `⊢ TS-NN-SS-01` at the end of the task line.

---

## Definition of Done — Writing Rules

Every task must have a definition of done (DoD). Rules:

- **Be specific:** `cmake --preset x86 exits 0` not `builds successfully`
- **Be binary:** it either passes or it doesn't — no partial credit
- **Prefer CLI commands** over prose descriptions
- **Add `[manual]`** when the check requires human judgment (e.g. "UI looks correct", "doc is readable")
- **Reference AC** where the task directly satisfies a story AC: `— **Done:** (satisfies AC-3: …)`

---

## Coverage Validation

After decomposing all stories in an EPIC, verify:

```
[ ] Every story AC maps to ≥ 1 task
[ ] Every task has a definition of done
[ ] No task exceeds 8 hours
[ ] No story has > 10 tasks (flag for story splitting if so)
[ ] The task sequence within each story follows the ordering rules
[ ] Cross-story dependencies are explicitly noted
[ ] Total EPIC hours are estimated and noted in the EPIC header
```

---

## Task Board Output Structure

The output file (`neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md`) must contain:

1. **Header block** — source file, date, status
2. **Progress Summary table** — per-EPIC: Total / Pending / In Progress / Done / % Done
3. **Per-EPIC sections** (H2) → per-story sub-sections (H3) → task checklist
4. **Effort Summary** — total hours per EPIC, grand total

Progress Summary table format:

```markdown
| EPIC | Stories | Tasks | ⬜ Pending | 🔄 In Progress | ✅ Done | Est. Hours |
|------|---------|-------|-----------|----------------|---------|------------|
| EP-01 | 4 | 16 | 16 | 0 | 0 | 32h |
```

---

## Non-Negotiable Rules

- Do not create tasks for WON'T items (they should already have exclusion notes in the stories file).
- Do not create tasks that cannot be traced back to a story AC — if a task is needed but has no AC parent, the AC is missing; flag it.
- Never write a task with "TBD" as the definition of done — if you can't define done now, the task is not ready to decompose.
- Task verbs are present-tense imperatives: `Create`, `Implement`, `Configure`, `Write`, `Add`, `Run`, `Validate` — not `Creating`, `Implemented`, `Should configure`.
