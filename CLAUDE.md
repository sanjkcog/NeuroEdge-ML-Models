# CLAUDE.md - AgentForge Starter

<!-- CUSTOMIZE: This file is copied by `setup_neuroedge_agentic_tools.py`. Keep root CLAUDE.md short. Put detail in README, docs/context/REPO_MAP.md, ADRs, or subfolder CLAUDE.md files. -->

## Project Snapshot

<!-- CUSTOMIZE: Replace these TODOs for the target project. -->
- **Project:** TODO project name
- **Purpose:** TODO one sentence
- **Stack:** TODO languages, frameworks, package managers, database, deploy target
- **Status:** TODO greenfield | active | legacy | maintenance

## Session Start

Before non-trivial work, read:

1. `AGENTS.md`
2. `docs/context/ACTIVE.md`
3. `docs/context/PROGRESS.md`
4. `docs/context/REPO_MAP.md`
5. The nearest subfolder `CLAUDE.md` for files you will touch

If behavior seems wrong, run `/memory` before changing rules.

## Route Preflight

Before planning, editing, reviewing, researching, committing, or opening a PR, state:

```text
Route: command=<name-or-none>; agent=<name-or-none>; skills=<paths-or-none>; mcp=<servers-or-none>; hooks=<expected-hooks-or-none>
```

Use this order:

1. Prefer a matching command in `.claude/commands/`.
2. Use a matching agent in `.claude/agents/`.
3. Confirm skill paths exist under `agentic-assets/skills/`.
4. Use MCP only for external state: GitHub, Jira, Confluence, current docs, Playwright, or memory.
5. If no route applies, say `Route: no AgentForge route applies`.

## Response Header

When using an AgentForge command or agent, begin with:

```text
[ NeuroEdge Assets ]  <command-or-agent> · Skills: <skill1>, <skill2>
```

Examples:

```text
[ NeuroEdge Assets ]  /legacy-audit · Skills: legacy-modernization, agentic-engineering, coding-standards
[ NeuroEdge Assets ]  Agent: code-explorer · Skills: agentic-engineering, coding-standards
```

This central rule prevents listing every status line here. Keep exact skill paths and tool permissions in the command/agent markdown files.

## Critical Commands

<!-- CUSTOMIZE: Replace TODO commands with real commands. Delete rows that do not apply. -->

| Purpose | Command |
|---|---|
| AgentForge health | `python health_check/cli.py --verbose` |
| Build | TODO |
| Test | TODO — or let `/test-run` auto-detect your framework (pytest, Playwright, Catch2/CTest, JUnit5, Vitest); no framework is hardcoded by this template (D10) |
| Lint | TODO |
| Type check | TODO |
| Run locally | TODO |

AgentForge routes:

- Legacy repo: `/legacy-audit . --memory-bank --subfolder-claude --plan`
- New product: `/research "<topic>" --type combined`, then `/prp-prd`
- Orchestrate a feature end to end: `/agentforge "<objective>"` (or `--stage <id>` to
  join at an already-wired stage if you already have a PRD/epics/tasks from outside the
  orchestrator; `--dry-run` to preview; `--status`/`--resume` to check in or recover
  after a break)
- Plan work: `/prp-plan "<feature or bug>"`
- Implement plan: `/prp-implement <plan>`
- Test plan + coverage: `/test-plan`, `/trace-matrix`, `/test-run`
- Validate: `/quality-gate .` and `/test-coverage`
- Commit/PR: `/prp-commit "<message>"`, then `/prp-pr`
- Memory cleanup: `/memory-audit --report-only`

## QA and PM Configuration

<!-- CUSTOMIZE: these files are created on first use (each command prompts once and
persists the choice, per D16) — nothing here is required before you start. -->

| Concern | File | Notes |
|---|---|---|
| Test-management vendor | `.claude/qa/test-management.json` | Zephyr Scale / none (repo-local) / decide later — prompted once by `/test-plan --push` |
| Test environment provisioning | `test-env.json` | Per-target up / health-probe / seed / teardown; a target with no entry runs locally, no provisioning |
| Jira sync (if PM delivery assets are installed) | `.claude/pm/jira-config.json` | Jira / none (repo-local) / decide later — nothing is blocked on this being unset |
| Budget rate (if PM delivery assets are installed) | `.claude/pm/budget-config.json` | `$/story-point` rate for modelled delivery-cost reporting; AI runtime cost never needs it |

None of these are required to start — every command above renders fully with no
vendor/rate configured (D12), same as the framework auto-detection above.

## Architecture Map

<!-- CUSTOMIZE: Keep this compact. Put the full map in docs/context/REPO_MAP.md. -->

| Area | Path | Notes |
|---|---|---|
| Entry points | TODO | TODO |
| Core logic | TODO | TODO |
| API / transport | TODO | TODO |
| Data / persistence | TODO | TODO |
| Tests | TODO | TODO |
| Deploy / infra | TODO | TODO |

<!-- CUSTOMIZE: Add subfolder CLAUDE.md files where rules differ, for example apps/web/CLAUDE.md, services/api/CLAUDE.md, packages/shared/CLAUDE.md, infra/CLAUDE.md. -->

## Hard Rules

<!-- CUSTOMIZE: Keep under 15 rules. Every rule should prevent a real mistake. -->

1. IMPORTANT: Never commit secrets, tokens, `.env`, or `.claude/settings.local.json`.
2. IMPORTANT: Do not bypass hooks with `--no-verify` or `--no-gpg-sign`.
3. Use the commands in this file instead of guessing build/test/lint commands.
4. Preserve legacy behavior unless the plan explicitly changes it.
5. Record or establish baseline behavior before legacy refactors.
6. Add or update tests for behavior changes.
7. Record non-trivial architecture decisions in `docs/decisions/ADR-*.md`.
8. Update `docs/context/ACTIVE.md` and `docs/context/PROGRESS.md` after meaningful work.

## Human Approval Required

<!-- CUSTOMIZE: Add protected project paths. -->

Ask before editing production deployment, billing, auth, permissions, migrations, CI/CD, generated files, public APIs, or broad refactors outside the requested scope.

Protected paths:

```text
TODO path/to/generated/
TODO path/to/migrations/
TODO path/to/infra/
TODO path/to/security-sensitive-code/
```

## Hooks, MCP, And Maintenance

Installed hooks may require specialist routing:

- Python edit or ruff finding -> `python-reviewer`
- TypeScript edit or typecheck failure -> `typescript-reviewer`
- SQL/schema/migration edit -> `database-reviewer`
- High-risk legacy surface -> `/legacy-audit --risk-only` or `legacy-modernizer`
- Build/test failure -> `build-error-resolver`
- Before PR -> `security-reviewer`, then `/prp-pr`

<!-- CUSTOMIZE: Enable only the MCP servers this repo needs. Good defaults: filesystem, github, memory or omega-memory, context7, playwright. -->

Review this file quarterly. Remove rules Claude can infer, rules already enforced by CI, and details that belong in README, ADRs, `REPO_MAP.md`, or subfolder `CLAUDE.md`.

Full workflow: `agentic-assets/docs/guides/how_to_build_your_project.md`  
Asset inventory: `agentic-assets/docs/guides/agentforge_assets.md`  
Install guide: `agentic-assets/docs/guides/how_to_install_agentforge.md`
