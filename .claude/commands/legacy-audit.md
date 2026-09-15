# Legacy Audit Command

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /legacy-audit · Skills: legacy-modernization, risk-assessment, agentic-engineering, coding-standards`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/development/legacy-modernization.md`
> - `agentic-assets/skills/SDLC/development/risk-assessment.md`
> - `agentic-assets/skills/SDLC/development/agentic-engineering.md`
> - `agentic-assets/skills/SDLC/development/coding-standards.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Domain plugins (auto-discovered)

Product/client-specific context lives in custom plugins under
`agentforge_custom_plugin/<Name>/`. Before auditing, self-discover: run
`python agentforge_custom_plugin/discover_plugins.py --stage onboarding` (or find
`agentforge_custom_plugin/*/plugin.json` directly and read any plugin whose
`wiring.auto_load` is not `false`), and read what it prints — `context/DOMAIN.md`,
integration data-formats, `context/constraints.md`, `context/regulatory.md` — so the
repo map and risk register reflect real domain constraints, not a generic audit. Absence
of plugins is normal — never a blocker.

## Usage

`/legacy-audit [scope] [--memory-bank] [--subfolder-claude] [--risk-only] [--plan]`

Examples:

```text
/legacy-audit .
/legacy-audit services/billing --risk-only
/legacy-audit apps/web --memory-bank --subfolder-claude
/legacy-audit "prepare this legacy repo for AgentForge SDLC" --plan
```

## Purpose

Use this command when AgentForge is introduced into an existing project or when a change touches legacy code with unclear tests, ownership, deployment, or architecture.

This command is read-only by default. It may propose memory-bank and `CLAUDE.md` updates, but it should only write files when the user explicitly asks for `--memory-bank`, `--subfolder-claude`, or direct edits.

## Pipeline

| Phase | Action |
|---|---|
| 1. ROUTE | State command, agent, skills, MCP/plugin needs, and active hooks before doing work |
| 2. INVENTORY | Identify languages, apps, services, tests, package managers, CI, scripts, deployment assets |
| 3. BASELINE | Find canonical build/test/lint/type-check/health commands and record current pass/fail status |
| 4. TRACE | Use `code-explorer` style mapping for critical entry points and data flows |
| 5. MEMORY | Create or update root memory-bank hierarchy when requested |
| 6. CLAUDE HIERARCHY | Recommend root and subfolder `CLAUDE.md` files for accurate routing |
| 7. RISK | Build a risk register for tests, data, auth, security, deploy, dependencies, ownership |
| 8. PLAN | Recommend stabilize/encapsulate/extract/retire modernization sequence |

## Required Routing

Use the `legacy-modernizer` agent for the main audit. Route follow-up work as follows:

| Trigger | Agent |
|---|---|
| Need deeper execution tracing | `code-explorer` |
| New architecture boundary or strangler plan | `architect` or `code-architect` |
| Need characterization tests | `tdd-guide` |
| Auth, secrets, permissions, PII/PHI, supply chain | `security-reviewer` |
| Schema, migrations, data backfills | `database-reviewer` |
| Language-specific code edit/review | Matching language reviewer |

## Plugin/MCP Recommendations

Use only what the task requires:

| Need | Plugin/MCP |
|---|---|
| Local project files outside Claude context | `filesystem` |
| PRs, issues, commit history | `github` |
| Persistent cross-session context | `memory` or `omega-memory` |
| Library/framework docs | `context7` |
| Web/UI regression validation | `playwright` |
| Long-running multi-agent exploration | `devfleet` |

## Output Artifact

Write or propose:

- `docs/audit/legacy-audit-<date>.md`
- `docs/context/REPO_MAP.md`
- `docs/context/ACTIVE.md`
- `docs/context/PROGRESS.md`
- `docs/context/OPEN_QUESTIONS.md`
- root `CLAUDE.md`
- subfolder `CLAUDE.md` files when needed
- ADRs for non-obvious modernization decisions

## Arguments

`$ARGUMENTS` may include:

- `scope`: repo path, subsystem, app, service, package, or natural-language scope
- `--memory-bank`: write missing memory-bank files after confirming existing content
- `--subfolder-claude`: propose or create subfolder `CLAUDE.md` routing files
- `--risk-only`: skip modernization plan and produce risk register only
- `--plan`: include a modernization plan with first vertical slice
