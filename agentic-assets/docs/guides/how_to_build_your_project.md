# How to Build Your Project with NeuroEdge AgentForge

**Version:** 1.4 — 2026-07-22
**Applies to:** any project using this AgentForge repo: greenfield products, legacy/brownfield systems, NeuroEdge Web, NeuroEdge Device, or your own consumer repo.

This is the complete, step-by-step build workflow. Each step lists the command to run, which agents are spawned, which skills they read, the hook or plugin support involved, and the artifact produced. Follow in order when the project is new; for legacy projects, start with the legacy audit gate before changing code.

For the exhaustive asset inventory, see [`agentforge_assets.md`](agentforge_assets.md). Keep this guide focused on **how to use** those assets through the SDLC.

The doc is organized for **two entry tracks**: a **New Project** (greenfield) and an **Existing Project** (brownfield). Both share the same memory bank foundation; they differ in which steps are required vs. skippable.

---

## Two Ways to Run This SDLC

Independent of which track you're on, there are two ways to actually drive the steps
below — pick per session, not once for the whole project. Both read the same memory
bank, the same domain plugins (see "Domain Plugins" below), and produce the same kind of
artifacts; they differ in who holds the state and how much of the SDLC is covered.

| | **Agentic Automated** | **Agentic Manual** |
|---|---|---|
| How you invoke it | One command: `/agentforge "<objective>"` | Each step's command run one at a time, in the order below |
| Coverage | S0 onboarding → S5 backlog (tasks) — stops before implementation | The full chain, Step 0 through Step 10 (research → PRD → epics → tasks → plan → implement → PR → deploy → regression) |
| State tracking | `run.json` + `gates.json`, written after every transition | None — you track progress yourself (or via `docs/context/ACTIVE.md`) |
| Resumability | `/agentforge --resume` restores exactly where it stopped | Re-run whichever command you left off at, pointing it at the right input file |
| Gates | S2 (PRD) and S3 (architecture) are **hard gates** — the orchestrator stops and asks Approve/Request changes/Reject | No enforced gate; you decide when a PRD or architecture doc is "good enough" to move on |
| Mid-pipeline entry | `/agentforge --stage <id>` joins at any of the six wired stages | Naturally supported — just run the command for the step you're on |
| Individual commands still work | Yes — every command below runs standalone even while `/agentforge` exists; the orchestrator just sequences the same agents for you | This *is* the individual-command path |
| Best for | A clean run from a stated objective, want the gate discipline and resumability | Fine-grained control per step, steps beyond S5 (implementation onward), ad hoc or partial work |
| Full reference | [`how_to_run_agentforge.md`](how_to_run_agentforge.md) | This document, Steps 0–10 below |

**They are not exclusive.** A common pattern: run `/agentforge` through S5 (requirements →
architecture → backlog, with gate discipline), then switch to Agentic Manual for Step 5
onward (`/prp-plan`, `/prp-implement`, `/prp-pr`, ...) since the orchestrator doesn't
reach implementation yet. Every command documented in the Steps below is always
available individually — nothing about `/agentforge` existing requires using it.

---

## Choose Your Track

The build workflow has two entry points. Pick one — most steps are shared, but the entry sequence and which steps are skippable differ.

### Track A — New Project (greenfield)

You are starting from a clean repo or a fresh scaffold. No production code yet. No deployed users.

**Recommended entry sequence:** Memory Bank Setup → Step 0 (Research) → Step 1 (Requirements) → Step 2 (PRD) → ... → Step 10 (Regression Testing). Run all steps in order.

### Track B — Existing Project (brownfield)

A codebase, deployed users, and tribal knowledge already exist. You are adding a feature, fixing bugs, refactoring, or modernizing.

**Recommended entry sequence:** Install AgentForge with `--type generic` unless the repo is a known NeuroEdge project → run `/legacy-audit --memory-bank --subfolder-claude --plan` → preserve the current baseline → create root and subfolder `CLAUDE.md` routing → skip Steps 1–4 only when the work fits an existing capability → start at Step 5 (Plan) or Step 6 (Implement). Always run Steps 7–10 (PR, Quality Gate, Deploy, Regression).

| Decision | New Project (Track A) | Existing Project (Track B) |
|---|---|---|
| Run `/research`? | Yes if technology choice is unknown | Only when introducing brand-new technology |
| Write a PRD (`/prp-prd`)? | Yes | Only for a major feature; small changes skip this |
| Build EPICs + stories? | Yes | Only for multi-sprint efforts |
| Implementation plan (`/prp-plan`)? | Yes | Yes for any non-trivial change |
| Memory Bank bootstrap | Installer creates initial files; fill in vision and commands | `/legacy-audit --memory-bank` reverse-engineers current state first |
| CLAUDE.md hierarchy | Usually root `CLAUDE.md` is enough at first | Root `CLAUDE.md` plus subfolder `CLAUDE.md` files for apps/services with different commands |
| First reviews | TDD-first via `tdd-guide` | Baseline + characterization tests first; use `legacy-modernizer`, then `code-explorer` |
| Typical sequence | 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 | `/legacy-audit` → Memory Bank → 5 → 6 → 7 → 8 → 9 → 10 |

---

## Memory Bank — Foundation for Both Tracks

> **Why this matters.** A persistent, file-based context system that survives across sessions is the single highest-leverage investment for agentic SDLC. Without it, Claude re-discovers your project on every session, re-litigates settled decisions, and forgets what's blocked. See `docs/audit/audit-sdlc-coverage-2026-06-04.md` for the gap analysis (memory bank is the #1 P0 gap).

The memory bank is a set of small markdown files at conventional paths that Claude reads at the start of each session and updates at the end of code-edit sessions. It complements — does not replace — Claude Code's built-in CLAUDE.md and typed auto-memory.

### Files and their purpose

| File | Purpose | When to update | Auto? | Size cap |
|---|---|---|---|---|
| `CLAUDE.md` (project root) | Stable project instructions: dispatch table, agents, hooks, conventions | Manual, when project shape changes | No | ~30 KB |
| `AGENTS.md` (project root) | Universal pointer — read by Claude Code, Cursor, Codex, Aider, Copilot, Gemini CLI, Windsurf | One-time | No | ~3 KB |
| `docs/context/ACTIVE.md` | Current focus: what we're doing now, recent changes, next 3 actions, blocked-on | Each session end | Future hook (manual today) | ~600 tokens |
| `docs/context/PROGRESS.md` | Done / In-progress / Blocked per workstream | After each `/prp-implement` session | Future hook (manual today) | ~1.5 KB per workstream |
| `docs/decisions/ADR-NNNN-*.md` | Append-only architecture decisions: context, decision, alternatives, status | After `/prp-prd` or `/prp-plan` produces a non-trivial choice | Future `/decision-log` command (manual today) | 1 ADR per file |
| `docs/context/REPO_MAP.md` | Auto-indexed package/module/class map | Weekly | Future skill (manual today) | ~400 lines |
| `docs/context/OPEN_QUESTIONS.md` | Known unknowns that block safe work | Whenever a fact is missing | Manual or `/legacy-audit` | short |
| `docs/context/GLOSSARY.md` | Stable project terms, acronyms, and domain names | When terminology stabilizes | Manual | short |
| User `CLAUDE.md` (`~/.claude/CLAUDE.md`) | Per-user preferences across all projects | Manual | No | ~2 KB |
| Auto-memory (`~/.claude/projects/<hash>/memory/`) | Claude Code's typed entries: user / feedback / project / reference | Auto by Claude | Yes | per-entry |
| `continuous-learning` instincts (`~/.claude/homunculus/`) | Atomic learned behaviors with confidence scores | Auto by hooks | Yes | per-instinct |

### Bootstrap for a NEW project (Track A)

Run the setup script on a fresh repo, before Step 0. The installer creates `.claude/`, hooks, agents, commands, runtime skills, plugin catalog, `CLAUDE.md`, `AGENTS.md`, and the shared memory-bank hierarchy.

```bash
# From the AgentForge checkout:
python -X utf8 setup_neuroedge_agentic_tools.py --project <target-repo> --type generic

# For known NeuroEdge repos:
python -X utf8 setup_neuroedge_agentic_tools.py --project "C:/Sanjeev_E/NeuroEdge Web" --type web
python -X utf8 setup_neuroedge_agentic_tools.py --project "C:/Sanjeev_E/NeuroEdge Device" --type device

# Then from the target project:
python health_check/cli.py --verbose
```

### Bootstrap for an EXISTING project (Track B)

For brownfield, bootstrap by reverse-engineering current state before changing behavior. The dedicated route is `/legacy-audit`; it uses the `legacy-modernizer` agent and `legacy-modernization` skill.

```bash
# 1. Install AgentForge into the legacy repo.
python -X utf8 setup_neuroedge_agentic_tools.py --project <legacy-repo> --type generic

# 2. Verify that commands, agents, hooks, runtime skills, and memory files resolve.
cd <legacy-repo>
python health_check/cli.py --verbose

# 3. In Claude Code, run the legacy gate before implementation.
/legacy-audit . --memory-bank --subfolder-claude --plan
```

The audit should produce or propose:

- `docs/audit/legacy-audit-<date>.md`
- root `CLAUDE.md` route preflight and dispatch table
- subfolder `CLAUDE.md` files for apps, services, packages, or domains with different commands
- `AGENTS.md` with canonical build/test/health commands
- `docs/context/ACTIVE.md`, `PROGRESS.md`, `REPO_MAP.md`, `OPEN_QUESTIONS.md`
- ADRs for non-obvious architecture, migration, or modernization decisions

### When to update the memory bank

| Trigger | File to update | Done by |
|---|---|---|
| Start of session | Read ACTIVE.md + PROGRESS.md (Claude does this when configured) | Auto (when SessionStart hook ships) |
| End of code-edit session | Refresh ACTIVE.md, append to PROGRESS.md | Manual today; auto via Stop hook (P0 backlog) |
| `/prp-prd` or `/prp-plan` makes a non-trivial choice | New ADR in `docs/decisions/` | `/decision-log` (P0 backlog); manual today |
| Weekly | Refresh `REPO_MAP.md` | `/repo-map-refresh` (P1 backlog); manual today |
| Pattern repeats across sessions | Save as `continuous-learning` instinct | `/learn-eval` — existing |
| Settled decision you don't want re-litigated | Add ADR + cross-link from CLAUDE.md | Manual |

### Memory bank governance rules

1. **One source of truth per fact.** If a fact is in CLAUDE.md, it does not also belong in ACTIVE.md / ADR / PROGRESS.md.
2. **Cap each always-read file at ~600 tokens.** Every file is a context tax. Cursor's guidance: under 200 words for always-apply rules.
3. **Memory ages out.** Quarterly: archive resolved ADRs, compress old PROGRESS sections, prune low-confidence instincts.
4. **Git-tracked = shared team memory** (Cline pattern). Private per-developer scratch goes in `.notes/` (gitignored) or Claude Code's auto-memory dir.
5. **Auto-update has one path.** Either a hook writes or you write — not both, never both.

> **Status of auto-update hooks.** The Stop-hook that writes ACTIVE.md/PROGRESS.md and the `/decision-log` command are on the P0 backlog of the SDLC audit (`docs/audit/audit-sdlc-coverage-2026-06-04.md`). Until they ship, update these files manually at session end. Even manual updates are higher-leverage than no memory bank at all.

---

## Legacy Project Route

AgentForge is useful for legacy projects only if routing is explicit. The assistant will not always infer the right agent, skill, plugin, or hook from file names alone, so Track B starts with a route declaration and a baseline audit.

### Installed legacy assets

| Asset | Path | Purpose |
|---|---|---|
| Command | `commands/legacy-audit.md` | Brownfield onboarding, memory-bank generation, route hierarchy, risk register, modernization plan |
| Agent | `agents/SDLC/legacy-modernizer.md` | Reads old code safely, maps architecture, identifies blast radius, routes specialist agents |
| Skill | `skills/SDLC/development/legacy-modernization.md` | Behavior-preserving modernization playbook |
| Hook | `scripts/hooks/post-edit-legacy-risk.js` | Warns after edits to migrations, auth, billing, deploy, infra, package locks, and other high-risk legacy surfaces |
| Plugin profile | `plugins/legacy-project-onboarding.json` | Recommended MCP set for legacy onboarding: filesystem, github, memory, context7, playwright, optional devfleet |

### Required route preflight

Before non-trivial work, Claude should state:

```text
Route: command=/legacy-audit; agent=legacy-modernizer; skills=legacy-modernization, agentic-engineering, coding-standards; mcp=filesystem/github/memory as needed; hooks=legacy-risk, quality, typecheck
```

If no AgentForge route applies, Claude should say that explicitly and continue with normal engineering judgment.

### Root and subfolder CLAUDE.md hierarchy

Use one root file for project-wide routing and smaller subfolder files for local differences:

```text
CLAUDE.md
AGENTS.md
docs/context/ACTIVE.md
docs/context/PROGRESS.md
docs/context/REPO_MAP.md
docs/context/OPEN_QUESTIONS.md
docs/decisions/ADR-0000-template.md
apps/web/CLAUDE.md
services/api/CLAUDE.md
packages/shared/CLAUDE.md
```

Root `CLAUDE.md` should contain the route preflight, canonical commands, agent dispatch table, hooks, plugin/MCP policy, and links to subfolder files. Subfolder `CLAUDE.md` files should contain only local commands, framework conventions, data stores, owners, and hazards.

Do not hand-write the subfolder files for a modular repo. Run `/scope-context` (or the Scope step of the installer) to auto-generate a nested `CLAUDE.md` per package — it extracts each module's purpose, public surface, entry points, and file inventory, and is idempotent (rewrites only content between `SCOPE:AUTO` markers). For legacy monolithic code with no package seams, use `/scope-context --monolith` (agent `context-scoper`) to run the TODO-driven segment-scoping workflow before editing. See the `context-scoping` skill.

### Legacy relevance checklist

Run this checklist before using AgentForge for legacy implementation:

| Question | Required answer |
|---|---|
| Are commands installed? | `python health_check/cli.py --verbose` passes `skills` |
| Are agents installed? | health check passes `agents`; `legacy-modernizer` exists |
| Are runtime skills available? | `agentic-assets/skills/SDLC/development/legacy-modernization.md` exists |
| Are hooks active? | health check passes `hooks`; `.claude/settings.json` contains `post:edit:legacy-risk` |
| Is memory present? | health check passes `memory` |
| Is plugin guidance present? | `agentic-assets/plugins/legacy-project-onboarding.json` exists |
| Is baseline known? | build/test/lint/typecheck commands are recorded, including current failures |
| Is routing hierarchical? | root `CLAUDE.md` links subfolder `CLAUDE.md` files where needed |

### Legacy workflow

1. Install AgentForge with `--type generic`.
2. Run `python health_check/cli.py --verbose`.
3. Run `/legacy-audit . --memory-bank --subfolder-claude --plan`.
4. Accept or edit the proposed memory-bank and `CLAUDE.md` hierarchy.
5. Add characterization tests for the first critical flow.
6. Run `/prp-plan` for the first low-blast-radius slice.
7. Implement with `/prp-implement`, language reviewers, `/quality-gate`, and `/test-coverage`.
8. Use `/memory-audit` after the first few sessions to remove stale or duplicated context.

---

## Workflow at a Glance

```
Legacy  Brownfield Audit        →  docs/audit/legacy-audit-<date>.md + memory bank + CLAUDE hierarchy
Step 0  Pre-project Research     →  docs/research/<topic>.md + Decision Brief
Step 1  Requirements Discovery   →  problem + evidence + personas
Step 2  PRD                      →  neuroedge/docs/project_related/prd/<name>.prd.md
Step 3  EPICs & User Stories      →  neuroedge/docs/project_related/plan/<track>/epics-and-user-stories.md
Step 4  Task Board               →  neuroedge/docs/project_related/plan/<track>/task-board.md
Step 5  Implementation Plan      →  neuroedge/docs/project_related/plan/<track>/<phase>.plan.md
Step 6  Development Loop
        6a  Architecture Design
        6b  Code Implementation
        6c  Code Patterns
        6d  Code Review (auto)
        6e  TDD
        6f  Security Review (auto before PR)
        6g  Deployment Scripts
Step 7  PR                       →  GitHub Pull Request
Step 8  Quality Gate             →  lint + type-check + format report
Step 9  Deployment               →  running service / container stack
Step 10 Regression Testing       →  test report + E2E coverage
```

---

## SDLC Command Chain — I/O Reference (verified 2026-07-17, gaps closed 2026-07-17)

The table below traces the exact chain used for FW-EP-01 and wired for FW-EP-02 onward:
`prd → prd-to-epics → stories-to-tasks → prp-plan → prp-implement → tdd → code-review (hooks) → quality-gate → commit → pr`.
Each row's **Output** is the next row's **Input** — this is what makes the pipeline traceable end to end (PRD FR code →
story AC → task ID → plan step → commit → PR).

This table was checked against the files actually installed in this repo (`.claude/commands/*.md`,
`.claude/agents/*.md`, `.claude/settings.json`) on 2026-07-17. The three gaps found that day (see **Gaps Closed**
below) were fixed the same day — the ⚠️ markers below Step 6d/6e/6f/7 further down in this guide are now historical
callouts documenting what changed and why, not open issues.

| # | Command / Agent | Purpose | Input | Output |
|---|---|---|---|---|
| 1 | `/prp-prd [idea \| project_objectives.md]` | Problem-first PRD: personas, MoSCoW capabilities, phases table | Feature idea (free text), a `project_objectives.md` path (or found at repo root), or blank → interactive discovery | `neuroedge/docs/project_related/prd/<name>.prd.md`, citing the objectives file as source when one seeded it |
| 2 | `/prd-to-epics <prd.md>` | Decompose PRD phases into EPICs; group FRs into User Stories with traceable ACs | PRD file path | `neuroedge/docs/project_related/plan/<track>/epics-and-user-stories.md` — `US-NN-SS` stories, each AC cites a PRD `FR-*` code |
| 3 | `/stories-to-tasks [stories.md]` | Break each story into sized (1–8h), typed, dependency-ordered tasks with a binary definition of done | `epics-and-user-stories.md` (defaults to the same `<track>`) | `neuroedge/docs/project_related/plan/<track>/task-board.md` — `TS-NN-SS-TT` tasks, each mapped to ≥1 story AC |
| 4 | `/prp-plan <prd.md \| feature \| task-board.md>` | Turn a PRD phase (or free-form feature) into a step-by-step plan: patterns to mirror, files to change, test-first task breakdown, validation commands | PRD path (auto-picks next pending phase), feature text, or a `task-board.md` path. **Now reads the sibling `task-board.md`** for the selected `<track>` and cross-references task IDs — Gap 1 closed | `neuroedge/docs/project_related/plan/<track>/<feature>.plan.md` — every task cites its `TASK ID` (`TS-NN-SS-TT`) plus a `TEST FIRST (RED)` / `IMPLEMENT (GREEN)` pair; PRD phase flips `pending → in-progress` |
| 5 | `/prp-implement <plan.md>` | Execute the plan test-first: per-task RED → GREEN → REFACTOR loop (mirrors `tdd-guide` methodology inline), then 5-level validation (static analysis → unit tests → build → integration → edge cases) | Plan file path | Working code + tests written test-first; `neuroedge/docs/project_related/plan/<track>/reports/<plan>-report.md`; plan archived to `plan/<track>/completed/` |
| 6 | `tdd-guide` agent (no slash command) | Red-Green-Refactor discipline; targets 80%+ coverage | Feature/task description — `/prp-implement`'s per-task loop now applies this methodology directly (reads `agentic-assets/skills/SDLC/tdd/tdd-workflow.md`); spawn the agent itself for Large/XL tasks or ambiguous `TEST FIRST` fields — Gap 2 closed | Failing test → minimal passing implementation → refactor, written into the same files `/prp-implement` is editing |
| 7 | Hooks: `post-edit-py-lint.js`, `post-edit-ts-accumulate.js` + `stop-typecheck.js`, **`post-edit-source-accumulate.js` + `stop-code-review-reminder.js`** (all auto, `.claude/settings.json`) | Run linter/typechecker on every edited file and force the matching reviewer; separately, force a holistic `code-reviewer` pass for **any** source-code language edited this session | Any source file edited via Edit or Write during step 5 (test files excluded) | Console `[REQUIRED ACTION]` → forces `python-reviewer` (per-file, immediate) / `typescript-reviewer` (batched at Stop) / **`code-reviewer`** (batched at Stop, all languages) — Gap 3 closed |
| 8 | `/quality-gate [path] [--fix] [--strict]` | Operator-invoked formatter/lint/type-check sweep | Target path (default `.`), optional `--fix`/`--strict` | Console remediation list. Still not merge-blocking and not hook-triggered — the command's own doc says "mirrors hook behavior but is operator-invoked" (unchanged, not a gap — intentional design) |
| 9 | `/prp-commit [description]` | Stage + commit with a conventional-commit message | Natural-language target description (blank = stage all changes) | A git commit; `pre-commit-quality.js` (real `PreToolUse` hook) re-checks staged `.py`/`.ts` files immediately before the `git commit` runs — warns on ruff/`console.log`, **blocks** (exit 2) only if `AGENTFORGE_COMMIT_TEST_CMD` is set and fails |
| 10 | `/prp-pr [base-branch]` | **New Phase 0 SECURITY GATE** spawns `security-reviewer` (blocking on high/critical findings) and `pr-test-analyzer` (advisory) against the diff, then pushes the branch and opens a GitHub PR with an auto-filled body including Security Notes / Test Coverage Notes sections | Base branch (default `main`) | GitHub PR via `gh pr create`, referencing the step 5 report + plan and the Phase 0 security/coverage findings in the body — Gap 3 closed |

### Gaps Closed (2026-07-17)

1. **`/prp-plan` now ingests `task-board.md`.** Phase 0 DETECT recognizes a `task-board.md` path directly; when the
   input is a PRD, a new "Task Board Cross-Reference" step looks for the sibling `plan/<track>/task-board.md`, matches
   tasks to the selected phase's stories, and requires every generated task to cite its `TASK ID`. If no task board
   exists yet, the plan says so explicitly and points at `/stories-to-tasks` instead of silently omitting it.
2. **TDD is now wired into `/prp-implement`.** The plan template (`/prp-plan`) now has `TEST FIRST (RED)` /
   `IMPLEMENT (GREEN)` fields per task; `/prp-implement`'s Per-Task Loop was rewritten to actually run RED → GREEN →
   REFACTOR per task (reading `tdd-workflow.md` directly), instead of writing tests only in the old Phase 4 "Level 2."
   Phase 4 now re-runs the full suite for regressions rather than writing tests for the first time.
3. **Code review / security review are now hook-enforced beyond Python/TypeScript, and `/prp-pr` has a real gate.**
   Two new hooks — `post-edit-source-accumulate.js` (PostToolUse, all source languages, test files excluded) and
   `stop-code-review-reminder.js` (Stop) — force a holistic `code-reviewer` pass whenever any source file was edited,
   regardless of language. Separately, `commands/prp-pr.md` gained a mandatory **Phase 0 — SECURITY GATE** that spawns
   `security-reviewer` (STOP on high/critical findings) and `pr-test-analyzer` (advisory) before Phase 1, and the PR
   body template now carries their findings forward.
4. **Bonus fix — `.claude/settings.json` (the hook config itself) was never committed.** `.gitignore` had a bare
   `settings.json` pattern intended for `.vscode/settings.json` that also matched `.claude/settings.json` — so every
   hook in this repo, old and new, existed only on whichever machine configured it and was never shared via git.
   Rescoped the pattern to `.vscode/settings.json`; `.claude/settings.json` is now trackable. **This still needs an
   explicit `git add .claude/settings.json` + commit** — it wasn't committed as part of this fix, since committing
   wasn't requested.

Steps 6 (tdd), 7 (code-review), and the security gate in step 10 (pr) are now real hook/command automation, not just
agent descriptions you have to remember to invoke. `/quality-gate` (step 8) remains intentionally operator-invoked —
that was never a gap, it's a deliberate manual checkpoint.

---

## Asset Location Reference

| Asset type | Source (AgentForge) | Installed to (target project) |
|---|---|---|
| Agents | `agents/SDLC/<name>.md` | `.claude/agents/<name>.md` |
| Agents | `agents/SOFTWARE/<name>.md` | `.claude/agents/<name>.md` |
| Agents | `agents/MARKETING/<name>.md` | `.claude/agents/<name>.md` |
| Commands | `commands/<name>.md` | `.claude/commands/<name>.md` |
| Project commands | `projects/<type>/commands/<name>.md` | `.claude/commands/neuroedge/<name>.md` |
| Skills | `skills/<category>/<name>.md` | `agentic-assets/skills/<category>/<name>.md` |
| Hooks | `scripts/hooks/*.js` and `hook-config.json` | `scripts/hooks/*.js` and `.claude/settings.json` |
| Plugin/MCP catalog | `plugins/*.json` and `plugins/README.md` | `agentic-assets/plugins/` |
| Subject-expertise skills | `skills/SUBJECTS/<Subject>/*.md` | `agentic-assets/skills/SUBJECTS/<Subject>/*.md` |
| Custom domain plugins | `agentforge_custom_plugin/<Name>/` | `agentforge_custom_plugin/<Name>/` (installed via `patch_custom_plugin.py --install`, not `install.py`) |
| Shared docs | `docs/`, `README.md`, `NOTICE.md` | `agentic-assets/` |
| Health checker | `health_check/` | `health_check/` |

**Status line format** — every agent and command outputs this at the start of its response:  
`[ NeuroEdge Assets ]  Agent: <name> · Skills: <skill1>, <skill2>`  
`[ NeuroEdge Assets ]  /<command> · Skills: <skill1>, <skill2>`

---

## Domain Plugins — Product/Client Context, Auto-Discovered

Every step below draws on generic SDLC skills and, where relevant, generic **subject**
skills (`skills/SUBJECTS/`, e.g. medical physics). Neither knows anything about *your*
product or client. That third layer — proprietary, product-specific context — lives in a
**custom plugin** and is picked up automatically, in both usage modes above, with no
install step.

### Why this exists

A generic SDLC pipeline can produce a technically correct PRD or architecture doc that is
still domain-blind: it won't know that a radiotherapy QA product must treat Machine QA
and Patient QA as separate capabilities, or what file formats a specific vendor product
exchanges. That knowledge doesn't belong in the base SDLC assets (it isn't reusable
across projects) and it doesn't belong nowhere (then every session re-derives it, or
worse, invents it). A custom plugin is where it lives.

### The three knowledge layers

| Layer | Question it answers | Reusable? | Lives in |
|---|---|---|---|
| Generic SDLC craft | How do we build software? | Any project | `skills/SDLC/`, `skills/SOFTWARE/`, base agents |
| Subject expertise | What does an expert in this *field* know? | Any project in the field | `skills/SUBJECTS/<Subject>/` (e.g. `Physics`) |
| Custom plugin | What is true about *this product/client*? | No — one product | `agentforge_custom_plugin/<Name>/` |

### How auto-discovery works

**Presence is activation.** Any `agentforge_custom_plugin/<Name>/plugin.json` whose
`wiring.auto_load` is not explicitly `false` is active — no registry, no per-project
setup. Each plugin's `plugin.json` declares a `wiring.stage_context` map: which of its
context files a given SDLC stage should read, plus any `requires_subjects` (reusable
subject skills it depends on).

- **In Agentic Automated mode:** before spawning each stage's agent, `/agentforge` runs
  `python agentforge_custom_plugin/discover_plugins.py --stage <id>` and passes every
  file it prints into that stage's spawn as binding domain context.
- **In Agentic Manual mode:** the pipeline role agents (`product-manager`, `architect`,
  `qa-engineer`, `researcher`, `epic-writer`, `task-writer`) self-discover the same way
  via `Glob` when invoked directly — no orchestrator required.
- **A plugin can also ship its own command** (e.g. `/suncheck`) for consulting it
  directly, outside any SDLC step.

The user's only job is to **fill or add files** inside the plugin folder — no base SDLC
asset ever needs to change when a plugin is added, extended, or removed.

### Working with plugins

```bash
# See what's currently active
python agentforge_custom_plugin/discover_plugins.py --list

# See exactly what a given stage will read
python agentforge_custom_plugin/discover_plugins.py --stage requirements

# Scaffold a new plugin
python agentforge_custom_plugin/patch_custom_plugin.py --new <Name>

# Install an existing plugin (+ its declared subject skills) into another project
python agentforge_custom_plugin/patch_custom_plugin.py --install <Name> --project <path>
```

To deactivate a plugin without deleting it, set `"auto_load": false` in its
`plugin.json`. Full detail and the current `SunCHECK` (radiotherapy QA) example: see
[`agentforge_assets.md`](agentforge_assets.md#custom-domain-plugins-agentforge_custom_plugin)
and [`how_to_run_agentforge.md`](how_to_run_agentforge.md#domain-plugins-auto-discovered).

> **Not to be confused with:** `plugins/*.json` (`plugins/mcp-servers.json`,
> `plugins/legacy-project-onboarding.json`) is a static MCP-server/profile catalog you
> copy entries from by hand — unrelated to `agentforge_custom_plugin/`, which is live,
> auto-discovered, project-authored domain context.

---

## Step 0 — Pre-project Research

**What:** Before writing a PRD, gather cited evidence about the market landscape, competitive products, and technology trade-offs. Research produces a Decision Brief — three bullets that seed the PRD's Evidence section, Key Hypothesis, and Risk catalogue. Skip only if the decision is already settled with existing evidence.

**Command:** `/research <topic> [--type market|technology|competitive|combined]`

```
/research "edge AI runtime platform landscape" --type combined
/research "EMQX vs Mosquitto for 8 GB ARM64 devices" --type technology
/research "OEM edge AI certification programs Dell HP Lenovo" --type market
```

**Status line:**
```
[ NeuroEdge Assets ]  /research · Skills: deep-research, market-research
```

### When to run which type

| Type | Use when | Skills applied |
|---|---|---|
| `--type technology` | Choosing between frameworks, protocols, SDKs, or libraries | `deep-research` (multi-source, cited) |
| `--type market` | Validating market size, OEM opportunity, pricing models | `market-research` (TAM/SAM, competitive) |
| `--type competitive` | Understanding what's already built and where gaps are | Both |
| `--type combined` (default) | Full pre-project research for any new product or platform | Both |

### Agent spawned

| Agent | Source | Status line |
|---|---|---|
| `researcher` | `agents/SDLC/researcher.md` | `[ NeuroEdge Assets ]  Agent: researcher · Skills: deep-research, market-research` |

### Skills read

| Skill | Path | Purpose |
|---|---|---|
| `deep-research` | `agentic-assets/skills/SDLC/requirements/deep-research.md` | Multi-source web synthesis, firecrawl/exa MCPs, cited reports |
| `market-research` | `agentic-assets/skills/SDLC/requirements/market-research.md` | Market sizing, competitive analysis, vendor diligence, decision framing |

### What the researcher agent does

| Phase | Action |
|---|---|
| Clarify | Confirms what decision the research must support |
| Plan | Defines 3–5 sub-questions (technical + market dimensions) |
| Execute | Searches 8–15 sources per sub-question; deep-reads 3–5 key ones |
| Synthesize | Produces structured report with comparison tables and inline citations |
| Decision Brief | 3-bullet brief: chosen direction + top constraint + open question for `/prp-prd` |

### Output artifact
`docs/research/<topic-slug>-<date>.md` — full cited report + Decision Brief.

### How it feeds the PRD

| Research output | → | PRD section |
|---|---|---|
| Key findings + citations | → | §2 Evidence |
| Recommendation | → | §4 Key Hypothesis |
| Risks & Gaps | → | §12 Risks |
| Open question | → | §17 Open Questions |

---

## Step 1 — Requirements Discovery

**What:** Translate the research findings and raw problem understanding into personas, success criteria, and constraints. This is the bridge between research and the formal PRD. Done conversationally with `planner` + `architect`, or directly within `/prp-prd` Phases 1–3.

**How:** Either discuss research findings with `planner`/`architect`, or jump straight to Step 2 (`/prp-prd`) which embeds its own discovery questions.

### Agents

| Agent | Source file | Status line |
|---|---|---|
| `planner` | `agents/SDLC/planner.md` | `[ NeuroEdge Assets ]  Agent: planner · Skills: agentic-engineering, product-capability` |
| `architect` | `agents/SDLC/architect.md` | `[ NeuroEdge Assets ]  Agent: architect · Skills: hexagonal-architecture, agentic-engineering` |

### Skills read

| Skill | Path |
|---|---|
| `product-capability` | `agentic-assets/skills/SDLC/requirements/product-capability.md` |
| `market-research` | `agentic-assets/skills/SDLC/requirements/market-research.md` |
| `deep-research` | `agentic-assets/skills/SDLC/requirements/deep-research.md` |

### Output
Informal notes, constraint list, or a `REQUIREMENTS.md` — feeds directly into Step 2.

---

## Step 2 — PRD (Product Requirements Document)

**What:** Turn the problem + evidence + personas into a structured, hypothesis-driven PRD with MoSCoW capabilities, success metrics, phases, and open questions.

**Command:** `/prp-prd [feature/product idea | path/to/project_objectives.md]`

```
/prp-prd Edge AI runtime for Jetson + Qualcomm + RPi 5
/prp-prd project_objectives.md                          # explicit path
/prp-prd                                                 # blank — looks for project_objectives.md at repo root first
```

**Status line:**
```
[ NeuroEdge Assets ]  /prp-prd · Skills: product-capability
```

### `project_objectives.md` as an input (wired 2026-07-17)

A user-authored `project_objectives.md` can seed the PRD instead of starting from a blank slate or a one-line idea.
Phase 0 detects it (explicit path, or found at the repo root when `$ARGUMENTS` is blank), extracts whatever of
problem/mission, target users, goals/KPIs, constraints, non-goals, and priorities is present, and shows the
extraction back to the user for confirmation before continuing. Phases 1 (INITIATE), 2 (FOUNDATION), 4 (DEEP DIVE),
and 6 (DECISIONS) then **skip any question already answered** by the objectives file and only ask what's missing —
the objectives file doesn't have to follow any fixed structure, extraction is by content/intent. No
`project_objectives.md` found → behaves exactly as before (full discovery questions or free-form idea).

### What the command does

| Phase | Action |
|---|---|
| DETECT | Look for `project_objectives.md` (explicit path or repo root); extract and confirm with user if found |
| INITIATE | Confirm problem statement (pre-filled from objectives file if loaded) |
| FOUNDATION | Ask problem-discovery questions — only the ones not already answered |
| GROUNDING | Research market + codebase in parallel |
| DEEP DIVE | Vision, primary user, JTBD, constraints — only the ones not already answered |
| DECISIONS | MVP scope, MoSCoW, key hypothesis, out-of-scope — only the ones not already answered |
| GENERATE | Write PRD to `neuroedge/docs/project_related/prd/<name>.prd.md`, citing the objectives file as its source |

### Agents (spawned within the command)

| Agent | When | Status line |
|---|---|---|
| `planner` | Scoping and feature breakdown | `[ NeuroEdge Assets ]  Agent: planner · Skills: agentic-engineering, product-capability` |

### Skills read

| Skill | Path |
|---|---|
| `product-capability` | `agentic-assets/skills/SDLC/requirements/product-capability.md` |

### Output artifact
`neuroedge/docs/project_related/prd/<kebab-case-name>.prd.md` — contains sections §1–§13 including phases table.

---

## Step 3 — EPICs & User Stories (Functional Requirements)

**What:** Decompose the PRD into EPICs (one per phase) and User Stories (one per capability cluster) with traceable Acceptance Criteria. Every AC references a PRD FR code.

**Command:** `/prd-to-epics [path/to/prd.md]`

```
/prd-to-epics neuroedge/docs/project_related/prd/neuroedge-device.prd.md
/prd-to-epics                    # defaults to docs/PRD.md
/prd-to-epics --epic EP-03       # regenerate one EPIC after PRD change
/prd-to-epics --update           # add stories for new phases only
```

**Status line:**
```
[ NeuroEdge Assets ]  /prd-to-epics · Skills: prd-decomposition, product-capability
```

### Agent spawned

| Agent | Source | Status line |
|---|---|---|
| `epic-writer` | `agents/SDLC/epic-writer.md` | `[ NeuroEdge Assets ]  Agent: epic-writer · Skills: prd-decomposition, product-capability` |

### Skills read

| Skill | Path |
|---|---|
| `prd-decomposition` | `agentic-assets/skills/SDLC/requirements/prd-decomposition.md` |
| `product-capability` | `agentic-assets/skills/SDLC/requirements/product-capability.md` |

### Output artifact
`neuroedge/docs/project_related/plan/<track>/epics-and-user-stories.md` — EPIC INDEX table + per-EPIC/per-story H2/H3 sections + story map + open questions.

### Story format produced
```
### US-NN-SS — [Story Title]
> As a [Persona], I want [capability], so that [value].
**Acceptance Criteria:**
- [ ] [outcome] (FR-9a-1)
```

---

## Step 4 — Task Board

**What:** Break each User Story into sprint-sized tasks (1–8 h each), typed (`code`/`test`/`config`/`infra`/`docs`/`security`/`validate`), dependency-ordered, with a binary definition of done per task.

**Command:** `/stories-to-tasks [path/to/stories.md]`

```
/stories-to-tasks                        # defaults to neuroedge/docs/project_related/plan/<track>/epics-and-user-stories.md
/stories-to-tasks --epic EP-01           # task-board only for Phase 0
/stories-to-tasks --story US-01-02       # single story only
/stories-to-tasks --update               # add tasks for new stories
```

**Status line:**
```
[ NeuroEdge Assets ]  /stories-to-tasks · Skills: stories-to-tasks, prd-decomposition
```

### Agent spawned

| Agent | Source | Status line |
|---|---|---|
| `task-writer` | `agents/SDLC/task-writer.md` | `[ NeuroEdge Assets ]  Agent: task-writer · Skills: stories-to-tasks, prd-decomposition` |

### Skills read

| Skill | Path |
|---|---|
| `stories-to-tasks` | `agentic-assets/skills/SDLC/requirements/stories-to-tasks.md` |
| `prd-decomposition` | `agentic-assets/skills/SDLC/requirements/prd-decomposition.md` |

### Output artifact
`neuroedge/docs/project_related/plan/<track>/task-board.md` — Progress Summary table + per-EPIC/per-story checkbox task lists + effort totals.

### Task format produced
```
- [ ] **TS-01-01-02** `(2h, code, ne-data-plane)` Write root CMakeLists.txt with -std=c++17 — **Done:** cmake --preset x86 exits 0
```

### Tracking conventions
- `- [ ]` = Pending · `- [~]` = In Progress · `- [x]` = Done
- Update the Progress Summary table after each sprint
- The task board is the single source of truth for "what's been built"

---

## Step 5 — Implementation Plan

**What:** For each phase (or task group), produce a step-by-step plan with file paths, code patterns to mirror, validation commands, and acceptance criteria linked to story ACs.

**Command:** `/prp-plan [path/to/prd.md | feature description | path/to/task-board.md]`

```
/prp-plan docs/PRD.md              # auto-picks next pending phase
/prp-plan neuroedge/docs/project_related/prd/neuroedge-device.prd.md
/prp-plan "Add TensorRT backend for ne-data-plane"
/prp-plan neuroedge/docs/project_related/plan/backend/task-board.md   # plan for one EPIC's tasks directly
```

When the input is a PRD, `/prp-plan` also looks for a sibling `plan/<track>/task-board.md` and cross-references
`TS-NN-SS-TT` task IDs into the generated plan automatically — see **SDLC Command Chain — Gaps Closed** above.

**Status line:**
```
[ NeuroEdge Assets ]  /prp-plan · Skills: agentic-engineering, product-capability
```

### Agents involved

| Agent | When | Status line |
|---|---|---|
| `planner` | Step breakdown and risk analysis | `[ NeuroEdge Assets ]  Agent: planner · Skills: agentic-engineering, product-capability` |
| `architect` | On-demand: complex architectural decisions | `[ NeuroEdge Assets ]  Agent: architect · Skills: hexagonal-architecture, agentic-engineering` |
| `code-architect` | On-demand: feature-level architecture | `[ NeuroEdge Assets ]  Agent: code-architect · Skills: hexagonal-architecture, backend-patterns` |

### Skills read

| Skill | Path |
|---|---|
| `agentic-engineering` | `agentic-assets/skills/SDLC/development/agentic-engineering.md` |
| `product-capability` | `agentic-assets/skills/SDLC/requirements/product-capability.md` |
| `hexagonal-architecture` | `agentic-assets/skills/SDLC/development/hexagonal-architecture.md` |
| `backend-patterns` | `agentic-assets/skills/SDLC/development/backend-patterns.md` |
| `api-design` | `agentic-assets/skills/SDLC/development/api-design.md` |

### Output artifact
`neuroedge/docs/project_related/plan/<track>/<kebab-case-feature>.plan.md` — per-step tasks with a `TASK ID`
(traced to `task-board.md`), `TEST FIRST (RED)` / `IMPLEMENT (GREEN)` fields, MIRROR references, IMPORTS, GOTCHA
notes, and VALIDATE commands.

---

## Step 6 — Development Loop

The development loop runs `/prp-implement` to execute the plan test-first, with agents auto-dispatched by hooks
after each file edit and at Stop.

### 6a — Architecture Design (on-demand)

Use before implementing a new subsystem boundary, container, or cross-cutting concern.

| Agent | Status line | When to invoke |
|---|---|---|
| `architect` | `[ NeuroEdge Assets ]  Agent: architect · Skills: hexagonal-architecture, agentic-engineering` | New platform, new container, or cross-repo API decision |
| `code-architect` | `[ NeuroEdge Assets ]  Agent: code-architect · Skills: hexagonal-architecture, backend-patterns` | Feature-level design within an existing subsystem |
| `code-explorer` | `[ NeuroEdge Assets ]  Agent: code-explorer · Skills: agentic-engineering, coding-standards` | Understanding existing codebase before changing it |

Skills referenced:

| Skill | Path |
|---|---|
| `hexagonal-architecture` | `agentic-assets/skills/SDLC/development/hexagonal-architecture.md` |
| `backend-patterns` | `agentic-assets/skills/SDLC/development/backend-patterns.md` |
| `frontend-patterns` | `agentic-assets/skills/SDLC/development/frontend-patterns.md` |
| `api-design` | `agentic-assets/skills/SDLC/development/api-design.md` |

---

### 6b — Code Implementation

**Command:** `/prp-implement [path/to/plan.md]`

```
/prp-implement neuroedge/docs/project_related/plan/<track>/phase-0-bootstrap.plan.md
```

**Status line:**
```
[ NeuroEdge Assets ]  /prp-implement · Skills: agentic-engineering, coding-standards, tdd-workflow
```

**What the command does:**

| Phase | Action |
|---|---|
| LOAD | Read plan file, extract tasks, validation commands |
| PREPARE | Check git state, create feature branch |
| EXECUTE | Per-task loop, test-first: mirror → **write failing test (RED)** → **implement minimally (GREEN)** → validate immediately → refactor |
| VALIDATE | Static analysis → unit tests (regression re-run, not first-write) → build → integration → edge cases |
| REPORT | Write implementation report to `neuroedge/docs/project_related/plan/<track>/reports/<plan>-report.md` |

Skills read:

| Skill | Path |
|---|---|
| `agentic-engineering` | `agentic-assets/skills/SDLC/development/agentic-engineering.md` |
| `coding-standards` | `agentic-assets/skills/SDLC/development/coding-standards.md` |
| `tdd-workflow` | `agentic-assets/skills/SDLC/tdd/tdd-workflow.md` |

---

### 6c — Code Patterns (applied during 6b)

These skills are read by the implementation command and inform how code is structured. No separate invocation needed.

| Pattern | Skill path | Use for |
|---|---|---|
| Backend patterns | `agentic-assets/skills/SDLC/development/backend-patterns.md` | Services, APIs, data access |
| Frontend patterns | `agentic-assets/skills/SDLC/development/frontend-patterns.md` | UI components, state management |
| API design | `agentic-assets/skills/SDLC/development/api-design.md` | REST endpoints, contracts |
| Logger patterns | `agentic-assets/skills/SDLC/development/logger_for_app.md` | Structured logging |
| C++ standards | `agentic-assets/skills/SOFTWARE/cpp/cpp-coding-standards.md` | ne-data-plane |
| Python patterns | `agentic-assets/skills/SOFTWARE/python/python-patterns.md` | ne-control-plane, ne-external |

---

### 6d — Code Review (auto-dispatched by hooks)

**MANDATORY:** Hooks auto-dispatch the correct reviewer after every file edit. Do NOT skip.

> ✅ **Closed 2026-07-17:** the Python row (`post-edit-py-lint.js`) and TypeScript row (`post-edit-ts-accumulate.js` +
> `stop-typecheck.js`) were already real hooks. The "feature/module complete → `code-reviewer`" row is now also
> hook-enforced: `post-edit-source-accumulate.js` (PostToolUse, all source languages, test files excluded) +
> `stop-code-review-reminder.js` (Stop) force a holistic `code-reviewer` pass whenever any source file was edited
> this session, regardless of language. Per-language reviewer rows below (`cpp-reviewer`, `go-reviewer`, etc.) and
> `database-reviewer`/`healthcare-reviewer` still have no dedicated hook — `code-reviewer`'s holistic pass is the
> catch-all until those are added. See **SDLC Command Chain — Gaps Closed** above.

| Trigger | Agent | Status line |
|---|---|---|
| Any `.py` file edited | `python-reviewer` | `[ NeuroEdge Assets ]  Agent: python-reviewer · Skills: python-patterns, python-testing` |
| Any `.ts`/`.tsx` edited | `typescript-reviewer` | `[ NeuroEdge Assets ]  Agent: typescript-reviewer · Skills: coding-style, nestjs-patterns` |
| Any `.cpp`/`.cu` edited | `cpp-reviewer` | `[ NeuroEdge Assets ]  Agent: cpp-reviewer · Skills: cpp-coding-standards, cpp-testing` |
| Any `.go` edited | `go-reviewer` | `[ NeuroEdge Assets ]  Agent: go-reviewer · Skills: golang-patterns, golang-testing` |
| Any `.java`/`.kt` edited | `java-reviewer` / `kotlin-reviewer` | `[ NeuroEdge Assets ]  Agent: java-reviewer · Skills: java-coding-standards, springboot-patterns` |
| Any `.rs` edited | `rust-reviewer` | `[ NeuroEdge Assets ]  Agent: rust-reviewer · Skills: rust-patterns, rust-testing` |
| Feature/module complete | `code-reviewer` | `[ NeuroEdge Assets ]  Agent: code-reviewer · Skills: coding-standards, plankton-code-quality` |
| SQL/schema/migration file | `database-reviewer` | `[ NeuroEdge Assets ]  Agent: database-reviewer · Skills: postgres-patterns` |
| Healthcare use case code | `healthcare-reviewer` | `[ NeuroEdge Assets ]  Agent: healthcare-reviewer · Skills: hipaa-compliance, healthcare-cdss-patterns` |

On-demand reviewers (invoke when needed):

| Agent | Status line | When |
|---|---|---|
| `silent-failure-hunter` | `[ NeuroEdge Assets ]  Agent: silent-failure-hunter · Skills: coding-standards, plankton-code-quality` | After error-handling code |
| `performance-optimizer` | `[ NeuroEdge Assets ]  Agent: performance-optimizer · Skills: plankton-code-quality, cost-aware-llm-pipeline` | After profiling identifies bottlenecks |
| `refactor-cleaner` | `[ NeuroEdge Assets ]  Agent: refactor-cleaner · Skills: coding-standards, plankton-code-quality` | After a feature ships, to remove dead code |
| `code-simplifier` | `[ NeuroEdge Assets ]  Agent: code-simplifier · Skills: coding-standards, plankton-code-quality` | When code has grown complex |
| `type-design-analyzer` | `[ NeuroEdge Assets ]  Agent: type-design-analyzer · Skills: coding-standards, agentic-engineering` | When designing shared types/interfaces |

---

### 6e — Test-Driven Development

**MANDATORY:** Write tests before or alongside implementation. Use `tdd-guide` when starting any new feature. Run `/test-coverage` after writing tests.

> ✅ **Closed 2026-07-17:** `/prp-implement`'s Per-Task Loop (Phase 3) now runs test-first RED → GREEN → REFACTOR
> directly, reading `tdd-workflow.md` per task. `/prp-plan`'s task template carries `TEST FIRST (RED)` /
> `IMPLEMENT (GREEN)` fields so the plan and the implementation stay in sync. Phase 4's old "Level 2: Unit Tests" now
> re-runs the full suite for regressions instead of writing tests for the first time. Spawn the `tdd-guide` agent
> itself for Large/XL tasks or when a task's `TEST FIRST` field is ambiguous. See **SDLC Command Chain — Gaps Closed**
> above.

| Action | Command / Agent | Status line |
|---|---|---|
| Before writing a new feature | Ask: "Use `tdd-guide` for test-first approach?" | — |
| During new feature | `tdd-guide` agent | `[ NeuroEdge Assets ]  Agent: tdd-guide · Skills: tdd-workflow, tdd-workflow` |
| After writing tests | `/test-coverage` | `[ NeuroEdge Assets ]  /test-coverage · Skills: tdd-workflow, verification-loop` |
| Critical paths (dual review) | `/santa-loop` | `[ NeuroEdge Assets ]  /santa-loop · Skills: verification-loop, ai-regression-testing` |

Skills read:

| Skill | Path |
|---|---|
| `tdd-workflow` | `agentic-assets/skills/SDLC/tdd/tdd-workflow.md` |
| `tdd-workflow` (testing) | `agentic-assets/skills/SDLC/testing/tdd-workflow.md` |
| `verification-loop` | `agentic-assets/skills/SDLC/testing/verification-loop.md` |
| `ai-regression-testing` | `agentic-assets/skills/SDLC/testing/ai-regression-testing.md` |

---

### 6f — Security Review (auto before PR)

**MANDATORY:** Hook auto-dispatches `security-reviewer` before any `gh pr create`. Do NOT bypass.

> ✅ **Closed 2026-07-17:** this is now a real command-level gate, not a hook. `commands/prp-pr.md` gained a mandatory
> **Phase 0 — SECURITY GATE** that spawns `security-reviewer` against the branch diff before any other phase runs and
> **stops** on high/critical findings; `pr-test-analyzer` runs alongside (advisory). Both summaries are carried into
> the PR body's Security Notes / Test Coverage Notes sections. See **SDLC Command Chain — Gaps Closed** above.

| Agent | Source | Status line |
|---|---|---|
| `security-reviewer` | `agents/SDLC/security-reviewer.md` | `[ NeuroEdge Assets ]  Agent: security-reviewer · Skills: security-review` |

Skills read:

| Skill | Path |
|---|---|
| `security-review` | `agentic-assets/skills/SDLC/testing/security-review.md` |

What the agent checks: secrets in code, SSRF, injection, OWASP IoT Top 10, unsafe crypto, SBOM drift, cosign signing coverage.

---

### 6g — Deployment Scripts

**What:** Write Dockerfiles, CI pipelines, docker-compose files, Terraform modules, and startup scripts as part of the implementation.

| Asset | Skill | Path |
|---|---|---|
| Docker / containers | `docker-patterns` | `agentic-assets/skills/SDLC/deployment/docker-patterns.md` |
| CI / CD pipelines | `deployment-patterns` | `agentic-assets/skills/SDLC/deployment/deployment-patterns.md` |
| Database migrations | `database-migrations` | `agentic-assets/skills/SDLC/deployment/database-migrations.md` |
| Canary rollout | `canary-watch` | `agentic-assets/skills/SDLC/deployment/canary-watch.md` |
| Jetson/TRT deployment | `jetson-deployment` | `agentic-assets/skills/DEPLOY-TARGETS/nvidia-jetson/jetson-deployment.md` |
| Qualcomm deployment | `qnn-deployment` | `agentic-assets/skills/DEPLOY-TARGETS/qualcomm/qnn-deployment.md` |
| RPi deployment | `rpi-deployment` | `agentic-assets/skills/DEPLOY-TARGETS/raspberry-pi/rpi-deployment.md` |

Build error recovery (auto-dispatched when a build or test command fails):

| Trigger | Agent | Status line |
|---|---|---|
| Build/test command fails | `build-error-resolver` | `[ NeuroEdge Assets ]  Agent: build-error-resolver · Skills: deployment-patterns` |
| C++/CMake build fails | `cpp-build-resolver` | `[ NeuroEdge Assets ]  Agent: cpp-build-resolver · Skills: cpp-coding-standards, deployment-patterns` |
| PyTorch/ONNX error | `pytorch-build-resolver` | `[ NeuroEdge Assets ]  Agent: pytorch-build-resolver · Skills: pytorch-patterns` |
| Go build fails | `go-build-resolver` | `[ NeuroEdge Assets ]  Agent: go-build-resolver · Skills: golang-patterns, deployment-patterns` |
| Java/Gradle fails | `java-build-resolver` | `[ NeuroEdge Assets ]  Agent: java-build-resolver · Skills: java-coding-standards, deployment-patterns` |
| Rust build fails | `rust-build-resolver` | `[ NeuroEdge Assets ]  Agent: rust-build-resolver · Skills: rust-patterns, deployment-patterns` |

---

### Documentation (during or after development)

| Action | Agent | Status line |
|---|---|---|
| After API/interface changes | Ask: "Update docs with `doc-updater`?" | — |
| When updating docs | `doc-updater` | `[ NeuroEdge Assets ]  Agent: doc-updater · Skills: documentation-patterns, coding-standards` |

Skills read:

| Skill | Path |
|---|---|
| `documentation-patterns` | `agentic-assets/skills/SDLC/development/documentation-patterns.md` |

---

## Step 7 — PR (Pull Request)

**What:** Push the feature branch, create a GitHub PR with a structured summary, and run final checks.

**Command:** `/prp-pr`

```
/prp-pr
```

**Status line:**
```
[ NeuroEdge Assets ]  /prp-pr · Skills: git-workflow, security-review
```

**What the command does:**

0. **Phase 0 — SECURITY GATE (mandatory):** spawns `security-reviewer` against `git diff origin/<base>...HEAD`; STOPs
   on high/critical findings. Spawns `pr-test-analyzer` against the same diff (advisory — reported, not blocking).
1. Checks git state (uncommitted files, unpushed commits)
2. Discovers a PR template and analyzes commits/files
3. Pushes branch
4. Opens `gh pr create` with a structured body — including Security Notes / Test Coverage Notes sections populated
   from Phase 0
5. Verifies and logs the PR URL

| Agent | Status line | When |
|---|---|---|
| `security-reviewer` | `[ NeuroEdge Assets ]  Agent: security-reviewer · Skills: security-review` | Phase 0 — before any git/push action (mandatory) |
| `pr-test-analyzer` | `[ NeuroEdge Assets ]  Agent: pr-test-analyzer · Skills: verification-loop, ai-regression-testing` | Phase 0, alongside `security-reviewer` |

> ✅ **Closed 2026-07-17:** `commands/prp-pr.md` now has a real **Phase 0 — SECURITY GATE** doing exactly this, ahead
> of the pre-existing Phase 1 VALIDATE / Phase 2 DISCOVER / Phase 3 PUSH / Phase 4 CREATE / Phase 5 VERIFY / Phase 6
> OUTPUT phases (renumbered nowhere — Phase 0 was inserted, not spliced in). See **SDLC Command Chain — Gaps Closed**
> above.

Skills read:

| Skill | Path |
|---|---|
| `git-workflow` | `agentic-assets/skills/SDLC/development/git-workflow.md` |

**Commit (before PR):** `/prp-commit` — natural-language file targeting + format check

```
/prp-commit "add TensorRT backend for ne-data-plane"
```

**Status line:** `[ NeuroEdge Assets ]  /prp-commit · Skills: git-workflow`

---

## Step 8 — Quality Gate

**What:** Run lint, format, type-check across all modified files. Block merge if any check fails.

**Command:** `/quality-gate [path|.] [--fix] [--strict]`

```
/quality-gate .            # check entire project
/quality-gate src/ --fix   # auto-fix formatting
/quality-gate --strict     # fail on warnings too
```

**Status line:**
```
[ NeuroEdge Assets ]  /quality-gate · Skills: coding-standards, plankton-code-quality
```

Skills read:

| Skill | Path |
|---|---|
| `coding-standards` | `agentic-assets/skills/SDLC/development/coding-standards.md` |
| `plankton-code-quality` | `agentic-assets/skills/SDLC/development/plankton-code-quality.md` |

**Checks performed by language:**

| Language | Formatter | Linter | Type checker |
|---|---|---|---|
| Python | `ruff format` | `ruff check` | `mypy` |
| TypeScript | `biome` / `prettier` | `eslint` | `tsc --noEmit` |
| C++ | `clang-format` | `clang-tidy` | compiler warnings |
| Go | `gofmt` | `golint` | `go vet` |
| Rust | `rustfmt` | `clippy` | `cargo check` |

**Optional: dual adversarial review for critical paths:**

```
/santa-loop   # two independent model reviewers must both approve
```

`[ NeuroEdge Assets ]  /santa-loop · Skills: verification-loop, ai-regression-testing`

---

## Step 9 — Deployment

**What:** Deploy the container stack to the target environment using the deployment scripts written in Step 6g.

No dedicated command — use the Makefile targets or deployment scripts written during development. Skills guide what those scripts should contain.

| Deployment type | Skill | Path |
|---|---|---|
| Docker compose | `docker-patterns` | `agentic-assets/skills/SDLC/deployment/docker-patterns.md` |
| CI/CD pipeline | `deployment-patterns` | `agentic-assets/skills/SDLC/deployment/deployment-patterns.md` |
| Canary / rolling | `canary-watch` | `agentic-assets/skills/SDLC/deployment/canary-watch.md` |
| Jetson OTA | `jetson-deployment` | `agentic-assets/skills/DEPLOY-TARGETS/nvidia-jetson/jetson-deployment.md` |
| Qualcomm OTA | `qnn-deployment` | `agentic-assets/skills/DEPLOY-TARGETS/qualcomm/qnn-deployment.md` |
| RPi | `rpi-deployment` | `agentic-assets/skills/DEPLOY-TARGETS/raspberry-pi/rpi-deployment.md` |
| Database migrations | `database-migrations` | `agentic-assets/skills/SDLC/deployment/database-migrations.md` |

If deployment fails → `build-error-resolver` agent auto-dispatched.

---

## Step 10 — Regression Testing

**What:** Run the full E2E test suite against the deployed environment. Quarantine flaky tests. Verify no regressions against previous passing state.

| Action | Asset | Status line |
|---|---|---|
| E2E test generation/run | `e2e-runner` agent | `[ NeuroEdge Assets ]  Agent: e2e-runner · Skills: e2e-testing, verification-loop` |
| Coverage report | `/test-coverage` | `[ NeuroEdge Assets ]  /test-coverage · Skills: tdd-workflow, verification-loop` |
| Iterative validation loop | `/gan-build` | `[ NeuroEdge Assets ]  /gan-build · Skills: autonomous-loops, continuous-agent-loop` |
| AI-specific regression | `ai-regression-testing` skill | `agentic-assets/skills/SDLC/testing/ai-regression-testing.md` |

Skills read:

| Skill | Path |
|---|---|
| `e2e-testing` | `agentic-assets/skills/SDLC/testing/e2e-testing.md` |
| `verification-loop` | `agentic-assets/skills/SDLC/testing/verification-loop.md` |
| `ai-regression-testing` | `agentic-assets/skills/SDLC/testing/ai-regression-testing.md` |
| `benchmark` | `agentic-assets/skills/SDLC/testing/benchmark.md` |

---

## Session Learning

After any productive session — especially after solving a non-obvious problem or discovering a project-specific pattern:

```
/learn-eval
```

`[ NeuroEdge Assets ]  /learn-eval · Skills: continuous-learning-v2, eval-harness`

This extracts reusable patterns and saves them to `~/.claude/skills/learned/` (global) or `.claude/skills/learned/` (project-scoped).

---

## Complete Asset Map (All Steps)

### Commands (23 total) → `.claude/commands/`

| Command | Step | Source | Status line |
|---|---|---|---|
| `/research` | 0 | `commands/research.md` | `[ NeuroEdge Assets ]  /research · Skills: deep-research, market-research` |
| `/legacy-audit` | Legacy | `commands/legacy-audit.md` | `[ NeuroEdge Assets ]  /legacy-audit · Skills: legacy-modernization, agentic-engineering, coding-standards` |
| `/prp-prd` | 2 | `commands/prp-prd.md` | `[ NeuroEdge Assets ]  /prp-prd · Skills: product-capability` |
| `/prd-to-epics` | 3 | `commands/prd-to-epics.md` | `[ NeuroEdge Assets ]  /prd-to-epics · Skills: prd-decomposition, product-capability` |
| `/stories-to-tasks` | 4 | `commands/stories-to-tasks.md` | `[ NeuroEdge Assets ]  /stories-to-tasks · Skills: stories-to-tasks, prd-decomposition` |
| `/prp-plan` | 5 | `commands/prp-plan.md` | `[ NeuroEdge Assets ]  /prp-plan · Skills: agentic-engineering, product-capability` |
| `/prp-implement` | 6b | `commands/prp-implement.md` | `[ NeuroEdge Assets ]  /prp-implement · Skills: agentic-engineering, coding-standards, tdd-workflow` |
| `/test-coverage` | 6e, 10 | `commands/test-coverage.md` | `[ NeuroEdge Assets ]  /test-coverage · Skills: tdd-workflow, verification-loop` |
| `/santa-loop` | 6e, 8 | `commands/santa-loop.md` | `[ NeuroEdge Assets ]  /santa-loop · Skills: verification-loop, ai-regression-testing` |
| `/prp-commit` | 7 | `commands/prp-commit.md` | `[ NeuroEdge Assets ]  /prp-commit · Skills: git-workflow` |
| `/prp-pr` | 7 | `commands/prp-pr.md` | `[ NeuroEdge Assets ]  /prp-pr · Skills: git-workflow, security-review` |
| `/quality-gate` | 8 | `commands/quality-gate.md` | `[ NeuroEdge Assets ]  /quality-gate · Skills: coding-standards, plankton-code-quality` |
| `/gan-build` | 10 | `commands/ENGINEERING/ai-genai/gan-build.md` | `[ NeuroEdge Assets ]  /gan-build · Skills: autonomous-loops, continuous-agent-loop` |
| `/learn-eval` | any | `commands/learn-eval.md` | `[ NeuroEdge Assets ]  /learn-eval · Skills: continuous-learning-v2, eval-harness` |
| `/memory-audit` | any | `commands/memory-audit.md` | `[ NeuroEdge Assets ]  /memory-audit · Skills: continuous-learning-v2` |
| `/model-route` | any | `commands/ENGINEERING/ai-genai/model-route.md` | `[ NeuroEdge Assets ]  /model-route · Skills: cost-aware-llm-pipeline` |
| `/eval` | evaluation | `commands/eval.md` | `[ NeuroEdge Assets ]  /eval · Skills: eval-harness` |
| `/loop-start` | long runs | `commands/loop-start.md` | `[ NeuroEdge Assets ]  /loop-start · Skills: autonomous-loops, continuous-agent-loop` |
| `/loop-status` | long runs | `commands/loop-status.md` | `[ NeuroEdge Assets ]  /loop-status · Skills: continuous-agent-loop` |
| `/pm2` | operations | `commands/pm2.md` | `[ NeuroEdge Assets ]  /pm2 · Skills: deployment-patterns` |
| `/promote` | learning | `commands/promote.md` | `[ NeuroEdge Assets ]  /promote · Skills: continuous-learning-v2` |
| `/marketing-video` | marketing | `commands/marketing-video.md` | `[ NeuroEdge Assets ]  /marketing-video · Skills: marketing-video-builder` |
| `/cognizant-ppt` | content | `commands/cognizant-ppt.md` | `[ NeuroEdge Assets ]  /cognizant-ppt · Skills: cognizant-ppt` |

### Agents → `.claude/agents/`

| Agent | Step | Source | Status line |
|---|---|---|---|
| `researcher` | 0 | `agents/SDLC/researcher.md` | `[ NeuroEdge Assets ]  Agent: researcher · Skills: deep-research, market-research` |
| `planner` | 1, 5 | `agents/SDLC/planner.md` | `[ NeuroEdge Assets ]  Agent: planner · Skills: agentic-engineering, product-capability` |
| `architect` | 1, 5, 6a | `agents/SDLC/architect.md` | `[ NeuroEdge Assets ]  Agent: architect · Skills: hexagonal-architecture, agentic-engineering` |
| `code-architect` | 5, 6a | `agents/SDLC/code-architect.md` | `[ NeuroEdge Assets ]  Agent: code-architect · Skills: hexagonal-architecture, backend-patterns` |
| `code-explorer` | 6a | `agents/SDLC/code-explorer.md` | `[ NeuroEdge Assets ]  Agent: code-explorer · Skills: agentic-engineering, coding-standards` |
| `legacy-modernizer` | Legacy | `agents/SDLC/legacy-modernizer.md` | `[ NeuroEdge Assets ]  Agent: legacy-modernizer · Skills: legacy-modernization, agentic-engineering, coding-standards` |
| `epic-writer` | 3 | `agents/SDLC/epic-writer.md` | `[ NeuroEdge Assets ]  Agent: epic-writer · Skills: prd-decomposition, product-capability` |
| `task-writer` | 4 | `agents/SDLC/task-writer.md` | `[ NeuroEdge Assets ]  Agent: task-writer · Skills: stories-to-tasks, prd-decomposition` |
| `python-reviewer` | 6d | `agents/SOFTWARE/python-reviewer.md` | `[ NeuroEdge Assets ]  Agent: python-reviewer · Skills: python-patterns, python-testing` |
| `typescript-reviewer` | 6d | `agents/SOFTWARE/typescript-reviewer.md` | `[ NeuroEdge Assets ]  Agent: typescript-reviewer · Skills: coding-style, nestjs-patterns` |
| `cpp-reviewer` | 6d | `agents/SOFTWARE/cpp-reviewer.md` | `[ NeuroEdge Assets ]  Agent: cpp-reviewer · Skills: cpp-coding-standards, cpp-testing` |
| `go-reviewer` | 6d | `agents/SOFTWARE/go-reviewer.md` | `[ NeuroEdge Assets ]  Agent: go-reviewer · Skills: golang-patterns, golang-testing` |
| `java-reviewer` | 6d | `agents/SOFTWARE/java-reviewer.md` | `[ NeuroEdge Assets ]  Agent: java-reviewer · Skills: java-coding-standards, springboot-patterns` |
| `kotlin-reviewer` | 6d | `agents/SOFTWARE/kotlin-reviewer.md` | `[ NeuroEdge Assets ]  Agent: kotlin-reviewer · Skills: kotlin-patterns, kotlin-testing` |
| `rust-reviewer` | 6d | `agents/SOFTWARE/rust-reviewer.md` | `[ NeuroEdge Assets ]  Agent: rust-reviewer · Skills: rust-patterns, rust-testing` |
| `csharp-reviewer` | 6d | `agents/SOFTWARE/csharp-reviewer.md` | `[ NeuroEdge Assets ]  Agent: csharp-reviewer · Skills: dotnet-patterns, csharp-testing` |
| `flutter-reviewer` | 6d | `agents/SOFTWARE/flutter-reviewer.md` | `[ NeuroEdge Assets ]  Agent: flutter-reviewer · Skills: dart-flutter-patterns` |
| `database-reviewer` | 6d | `agents/SOFTWARE/database-reviewer.md` | `[ NeuroEdge Assets ]  Agent: database-reviewer · Skills: postgres-patterns` |
| `healthcare-reviewer` | 6d | `agents/SDLC/healthcare-reviewer.md` | `[ NeuroEdge Assets ]  Agent: healthcare-reviewer · Skills: hipaa-compliance, healthcare-cdss-patterns` |
| `code-reviewer` | 6d | `agents/SDLC/code-reviewer.md` | `[ NeuroEdge Assets ]  Agent: code-reviewer · Skills: coding-standards, plankton-code-quality` |
| `silent-failure-hunter` | 6d | `agents/SDLC/silent-failure-hunter.md` | `[ NeuroEdge Assets ]  Agent: silent-failure-hunter · Skills: coding-standards, plankton-code-quality` |
| `performance-optimizer` | 6d | `agents/SDLC/performance-optimizer.md` | `[ NeuroEdge Assets ]  Agent: performance-optimizer · Skills: plankton-code-quality, cost-aware-llm-pipeline` |
| `refactor-cleaner` | 6d | `agents/SDLC/refactor-cleaner.md` | `[ NeuroEdge Assets ]  Agent: refactor-cleaner · Skills: coding-standards, plankton-code-quality` |
| `code-simplifier` | 6d | `agents/SDLC/code-simplifier.md` | `[ NeuroEdge Assets ]  Agent: code-simplifier · Skills: coding-standards, plankton-code-quality` |
| `type-design-analyzer` | 6d | `agents/SDLC/type-design-analyzer.md` | `[ NeuroEdge Assets ]  Agent: type-design-analyzer · Skills: coding-standards, agentic-engineering` |
| `tdd-guide` | 6e | `agents/SDLC/tdd-guide.md` | `[ NeuroEdge Assets ]  Agent: tdd-guide · Skills: tdd-workflow, tdd-workflow` |
| `security-reviewer` | 6f, 7 | `agents/SDLC/security-reviewer.md` | `[ NeuroEdge Assets ]  Agent: security-reviewer · Skills: security-review` |
| `doc-updater` | 6g | `agents/SDLC/doc-updater.md` | `[ NeuroEdge Assets ]  Agent: doc-updater · Skills: documentation-patterns, coding-standards` |
| `build-error-resolver` | 6g, 9 | `agents/SDLC/build-error-resolver.md` | `[ NeuroEdge Assets ]  Agent: build-error-resolver · Skills: deployment-patterns` |
| `cpp-build-resolver` | 6g | `agents/SOFTWARE/cpp-build-resolver.md` | `[ NeuroEdge Assets ]  Agent: cpp-build-resolver · Skills: cpp-coding-standards, deployment-patterns` |
| `pytorch-build-resolver` | 6g | `agents/SOFTWARE/pytorch-build-resolver.md` | `[ NeuroEdge Assets ]  Agent: pytorch-build-resolver · Skills: pytorch-patterns` |
| `go-build-resolver` | 6g | `agents/SOFTWARE/go-build-resolver.md` | `[ NeuroEdge Assets ]  Agent: go-build-resolver · Skills: golang-patterns, deployment-patterns` |
| `java-build-resolver` | 6g | `agents/SOFTWARE/java-build-resolver.md` | `[ NeuroEdge Assets ]  Agent: java-build-resolver · Skills: java-coding-standards, deployment-patterns` |
| `rust-build-resolver` | 6g | `agents/SOFTWARE/rust-build-resolver.md` | `[ NeuroEdge Assets ]  Agent: rust-build-resolver · Skills: rust-patterns, deployment-patterns` |
| `pr-test-analyzer` | 7 | `agents/SDLC/pr-test-analyzer.md` | `[ NeuroEdge Assets ]  Agent: pr-test-analyzer · Skills: verification-loop, ai-regression-testing` |
| `e2e-runner` | 10 | `agents/SDLC/e2e-runner.md` | `[ NeuroEdge Assets ]  Agent: e2e-runner · Skills: e2e-testing, verification-loop` |
| `loop-operator` | long runs | `agents/SDLC/loop-operator.md` | `[ NeuroEdge Assets ]  Agent: loop-operator · Skills: autonomous-loops, continuous-agent-loop` |
| `gan-planner` | iterative | `agents/ENGINEERING/ai-genai/gan-planner.md` | `[ NeuroEdge Assets ]  Agent: gan-planner · Skills: agentic-engineering, product-capability` |
| `gan-generator` | iterative | `agents/ENGINEERING/ai-genai/gan-generator.md` | `[ NeuroEdge Assets ]  Agent: gan-generator · Skills: coding-standards, agentic-engineering` |
| `gan-evaluator` | iterative | `agents/ENGINEERING/ai-genai/gan-evaluator.md` | `[ NeuroEdge Assets ]  Agent: gan-evaluator · Skills: verification-loop, ai-regression-testing` |

---

## Setup — Deploying Assets to Any Project

```bash
# 1. Clone or open the target project
git clone --recurse-submodules <project-url>

# 2. From the AgentForge checkout, install into the target project.
# Use generic for most non-NeuroEdge projects, including legacy projects.
python -X utf8 setup_neuroedge_agentic_tools.py --project <target-project> --type generic

# NeuroEdge-specific templates:
python -X utf8 setup_neuroedge_agentic_tools.py --project "C:/Sanjeev_E/NeuroEdge Web" --type web
python -X utf8 setup_neuroedge_agentic_tools.py --project "C:/Sanjeev_E/NeuroEdge Device" --type device

# 3. Fill in API keys
# Edit .claude/settings.local.json in the target project if the enabled hooks or MCP tools need secrets.

# 4. Verify installation
cd <target-project>
python health_check/cli.py --verbose

# 5. Restart Claude Code to pick up new agents and commands
```

For legacy projects, immediately run:

```text
/legacy-audit . --memory-bank --subfolder-claude --plan
```

Do not start refactoring until the audit records baseline commands, current failures, the memory-bank hierarchy, and a first low-blast-radius slice.

### Re-deploying after AgentForge updates

```bash
# From the AgentForge root — re-patch + re-install both projects
python -X utf8 setup_neuroedge_agentic_tools.py --project "c:/Sanjeev_E/NeuroEdge Web" --type web
python -X utf8 setup_neuroedge_agentic_tools.py --project "c:/Sanjeev_E/NeuroEdge Device" --type device
```

### Adding a new agent/command/skill/hook/plugin

This section is for extending the **base** AgentForge assets shared by every project. If
what you actually need is proprietary, product-specific context for one project (a
vendor integration, a regulated domain's constraints), don't add it here — scaffold a
**custom domain plugin** instead (`patch_custom_plugin.py --new <Name>`, see "Domain
Plugins" above); it needs none of these steps and never touches base assets.

1. Create the source asset:
   - Agent: `agents/SDLC/<name>.md`, `agents/SOFTWARE/<name>.md`, or `agents/MARKETING/<name>.md`
   - Command: `commands/<name>.md`
   - Skill: `skills/<category>/<name>.md`
   - Hook: `scripts/hooks/<name>.js`
   - Plugin/MCP profile: `plugins/<name>.json`
2. Add agents and commands to `AGENT_SKILLS` or `COMMAND_SKILLS` in `patch_assets.py`.
3. Add hooks to `hook-config.json` with a stable `id`.
4. Run `python -X utf8 patch_assets.py` to inject skill-reading blocks.
5. Run `node --check scripts/hooks/<name>.js` for any new hook.
6. Run `setup_neuroedge_agentic_tools.py` to deploy to target projects.
7. Run `python health_check/cli.py --verbose` in the target project.
8. Restart Claude Code.

---

## Quick Reference — "What do I run for X?"

| I want to... | Run |
|---|---|
| Run the whole SDLC automatically from an objective | `/agentforge "<objective>"` (Agentic Automated — see [`how_to_run_agentforge.md`](how_to_run_agentforge.md)) |
| See which domain plugins are active | `python agentforge_custom_plugin/discover_plugins.py --list` |
| Add proprietary product/client context (e.g. a vendor integration) | `python agentforge_custom_plugin/patch_custom_plugin.py --new <Name>`, then fill the files it creates |
| Add AgentForge to a legacy project safely | `setup_neuroedge_agentic_tools.py --project <repo> --type generic`, then `/legacy-audit . --memory-bank --subfolder-claude --plan` |
| Audit an old subsystem before changing it | `/legacy-audit <path-or-scope> --risk-only` |
| Create root and subfolder Claude routing | `/legacy-audit . --memory-bank --subfolder-claude` |
| Check whether agents, commands, hooks, skills, and memory resolve | `python health_check/cli.py --verbose` |
| Research a market, technology, or competitor before writing PRD | `/research <topic>` |
| Write a PRD from scratch | `/prp-prd` |
| Break PRD into EPICs + stories | `/prd-to-epics docs/PRD.md` |
| Create a sprint task board | `/stories-to-tasks` |
| Plan a specific phase | `/prp-plan docs/PRD.md` |
| Execute a plan | `/prp-implement neuroedge/docs/project_related/plan/<track>/<name>.plan.md` |
| Check test coverage | `/test-coverage` |
| Review security before PR | `security-reviewer` agent |
| Open a PR | `/prp-pr` |
| Run lint + type-check | `/quality-gate .` |
| Fix a build error | `build-error-resolver` agent (or language-specific) |
| Run E2E tests | `e2e-runner` agent |
| Update documentation | `doc-updater` agent |
| Extract session learnings | `/learn-eval` |
| Design architecture | `architect` agent |
| Review Python code | `python-reviewer` agent |
| Review C++ code | `cpp-reviewer` agent |
