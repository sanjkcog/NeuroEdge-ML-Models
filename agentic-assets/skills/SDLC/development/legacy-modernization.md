---
name: legacy-modernization
description: Audit, onboard, and modernize brownfield codebases safely by preserving behavior, building a memory bank, mapping architecture and ownership, and planning incremental change.
origin: AgentForge
---

# Legacy Modernization

Use this skill when AgentForge is being added to an existing project, when the codebase is poorly documented, when behavior must be preserved, or when a change touches old code with uncertain ownership, tests, dependencies, or deployment paths.

## Core Principles

- Preserve behavior first. Do not refactor before you know how the current system behaves.
- Create characterization tests around critical flows before changing internals.
- Prefer small vertical slices over big-bang rewrites.
- Map runtime entry points, data stores, queues, cron jobs, auth boundaries, and deployment targets before editing.
- Keep old and new paths side-by-side until rollback is obvious.
- Treat tribal knowledge as a first-class artifact in `docs/context/` and `docs/decisions/`.
- Document unknowns explicitly instead of guessing.

## Legacy Onboarding Workflow

1. Inventory the repo.
   - List languages, package managers, services, apps, libraries, generated folders, and test roots.
   - Identify build, test, lint, type-check, and deploy commands from README, CI, package files, Makefiles, scripts, and recent commits.
   - Record commands that are missing or broken as risks, not as assumptions.

2. Establish a baseline.
   - Run the safest available checks first.
   - Capture failing tests as the current baseline when the project already fails.
   - Do not "fix drive-by failures" until they are tied to the task.

3. Map architecture and ownership.
   - Identify entry points: UI routes, API handlers, CLIs, workers, scheduled jobs, event consumers, migrations, and deployment scripts.
   - Trace critical user journeys end-to-end.
   - Identify shared modules, high-churn files, and low-ownership code.

4. Build the memory bank.
   - `CLAUDE.md`: stable routing, commands, conventions, project-specific risks.
   - `AGENTS.md`: universal pointer with canonical build/test/health commands.
   - `docs/context/ACTIVE.md`: current focus, recent changes, next 3 actions.
   - `docs/context/PROGRESS.md`: workstreams and status.
   - `docs/context/REPO_MAP.md`: compact structure and entry-point map.
   - `docs/context/OPEN_QUESTIONS.md`: unresolved facts that block safe work.
   - `docs/decisions/ADR-*.md`: non-obvious decisions discovered or made during onboarding.

5. Create a risk register.
   - Critical flows with no tests.
   - Data migrations and schema drift.
   - Auth, permissions, billing, PHI/PII, secrets, and audit logs.
   - Manual deployment steps and environment-specific behavior.
   - Deprecated dependencies or unsupported runtimes.

6. Choose modernization lanes.
   - Stabilize: add tests, health checks, CI, observability, docs.
   - Encapsulate: add facades, ports, adapters, service boundaries.
   - Extract: move one vertical slice at a time.
   - Retire: remove dead code only after usage evidence and rollback review.

## CLAUDE.md Hierarchy for Legacy Projects

Use hierarchy to route Claude into the right subfolder without overloading the root file.

```text
CLAUDE.md
apps/web/CLAUDE.md
services/api/CLAUDE.md
packages/shared/CLAUDE.md
docs/context/ACTIVE.md
docs/context/PROGRESS.md
docs/context/REPO_MAP.md
docs/decisions/ADR-0000-template.md
```

Root `CLAUDE.md` should contain only project-wide rules, route preflight, command table, safety gates, and links to subfolder instructions. Subfolder `CLAUDE.md` files should contain local build/test commands, frameworks, ownership, conventions, and known hazards.

## Agent Routing

- Use `legacy-modernizer` for brownfield onboarding, memory-bank generation, modernization strategy, and risk register creation.
- Use `code-explorer` for detailed execution-path tracing inside one subsystem.
- Use `architect` or `code-architect` when the modernization introduces new boundaries.
- Use language reviewers after code edits: `python-reviewer`, `typescript-reviewer`, `java-reviewer`, `go-reviewer`, `cpp-reviewer`, `rust-reviewer`, etc.
- Use `security-reviewer` for auth, secrets, permissions, PII/PHI, supply chain, and pre-PR review.
- Use `database-reviewer` for schema, migration, indexes, query plans, and data backfills.
- Use `tdd-guide` for characterization tests and regression harnesses.

## Output Template

```markdown
# Legacy Audit: <project or subsystem>

## Executive Summary
- Current state:
- Main risk:
- Recommended first slice:

## Baseline Commands
| Purpose | Command | Status | Notes |
|---|---|---|---|

## Architecture Map
| Area | Entry points | Data stores | Tests | Owners/Risks |
|---|---|---|---|---|

## Memory Bank Updates
- `CLAUDE.md`:
- `AGENTS.md`:
- `docs/context/ACTIVE.md`:
- `docs/context/PROGRESS.md`:
- `docs/context/REPO_MAP.md`:
- `docs/decisions/`:

## Risk Register
| Risk | Severity | Evidence | Mitigation |
|---|---|---|---|

## Modernization Plan
1. Stabilize:
2. Encapsulate:
3. Extract:
4. Retire:

## Next 3 Actions
1.
2.
3.
```

## Best Practices Checklist

- [ ] There is a passing or recorded baseline before behavior changes.
- [ ] Root and subfolder `CLAUDE.md` files tell Claude where to navigate.
- [ ] Critical workflows have characterization tests or explicit manual validation.
- [ ] Database changes have rollback and backfill plans.
- [ ] Feature changes reuse existing local patterns unless an ADR approves divergence.
- [ ] Modernization is sequenced by blast radius and business value.
- [ ] The memory bank names uncertainties and stale documentation.
- [ ] Specialist agents are routed explicitly before high-risk edits.
