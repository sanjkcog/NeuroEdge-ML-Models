# AgentForge Assets Inventory

**Version:** 1.3 - 2026-07-27 (summary counts re-counted from disk; added the [Role → ADLC Phase → Asset Map](#role--adlc-phase--asset-map). Per-asset tables regenerate via `/product-doc`.)

This is the inventory catalog for AgentForge assets. Use this document to discover what exists. Use `how_to_build_your_project.md` for the end-to-end workflow and when to apply these assets.

## Summary

| Asset type | Count | Where it lives | How to use |
|---|---:|---|---|
| Agents | 67 | `agents/` -> `.claude/agents/` | Ask Claude to use the named agent, or let route preflight select it. (35 `SDLC` + 20 `SOFTWARE` + 10 `ENGINEERING` (`ai-ml` 3, `ai-genai` 5, `embedded` 2) + 2 `MARKETING`.) |
| Commands | 42 | `commands/` -> `.claude/commands/` | Run the slash command in Claude Code. (35 top-level + 7 under `commands/ENGINEERING/`.) |
| Skills/reference files | 222 | `skills/` -> `agentic-assets/skills/` | Loaded by commands/agents; manually ask Claude to read the path when needed. |
| Hook groups | 15 | `hook-config.json`, `scripts/hooks/` | Automatic after setup; do not run manually unless debugging. Includes per-language reviewer nudges: Python (ruff→python-reviewer), C++/C# (→cpp-reviewer/csharp-reviewer), the ai-ml leakage/blob guards, plus the holistic code-reviewer gate. |
| Plugin/profile files | 3 | `plugins/` -> `agentic-assets/plugins/` | Use as MCP/plugin catalog and task-specific profiles. |
| MCP servers | 27 | `plugins/mcp-servers.json` | Copy selected entries to `~/.claude.json` and fill placeholders. |
| Project template | 1 (`generic`) | `projects/generic/` | The one neutral `CLAUDE.md` template installed into every project. Product-independent — the core repo carries no per-product scaffold. |
| Subject-expertise skills | 2 files (Physics) — subset of Skills/reference files above | `skills/SUBJECTS/` -> `agentic-assets/skills/SUBJECTS/` | Generic, reusable field knowledge; **auto-discovered** by any active custom plugin's `requires_subjects`, and readable directly like any skill. |
| Custom domain plugins | 2 (`Project_Specific_Context` template, auto-scaffolded into every project + `SunCHECK` worked example) | `agentforge_custom_plugin/<Name>/` | **Auto-discovered** — presence + `plugin.json` is enough; no install step. See [Custom Domain Plugins](#custom-domain-plugins-agentforge_custom_plugin). |

## How To Read This Catalog

- **Purpose** is taken from asset frontmatter where available, otherwise from the first heading.
- **How to use** is intentionally short. The detailed procedure belongs in `how_to_build_your_project.md`.
- Installed target paths assume running `setup_neuroedge_agentic_tools.py`.
- Most rows below say "manually ask Claude to read the path" — that's still true for the
  base `skills/` and `plugins/` trees. **`skills/SUBJECTS/` and
  `agentforge_custom_plugin/` are the exception**: both are auto-discovered at runtime
  (no manual read needed) — see [Custom Domain Plugins](#custom-domain-plugins-agentforge_custom_plugin).

## ⭐ Engineering Disciplines — the USP (recent additions, 2026-07-25)

AgentForge's headline differentiator over generic agent tools: **product-domain discipline packs**
under `skills/ENGINEERING/`, each a manifest-first bundle of agents + commands + skills + hooks that a
project activates by declaring `active_disciplines: [<name>]`. A non-declaring project loads none of a
pack (files ship dormant), so the core stays lean while these make AgentForge span **software, AI/ML,
GenAI, and embedded** from one toolkit — see the "Why it is different → wider coverage" panel on the
landing page and the USP section in [`how_agentforge_improves_project_SDLC.md`](how_agentforge_improves_project_SDLC.md).

| Discipline | ADR | Build what | Key commands / agents |
|---|---|---|---|
| **`ai-ml`** | ADR-0014 | Train-ready ML models (CNN/DNN/recommender) — objective in, `.py`/`.tf` model + training script out; only GPU training runs outside | `/dataset-scout`, `/auto-label`, `/synth-data`, `/model-select`, `/model-build`; `ml-data-engineer`, `ml-modeler`, `ml-eval-reviewer` |
| **`ai-genai`** | ADR-0011 | GenAI/agentic products — MCP servers, autonomous loops, cost-aware routing | `/gan-build`, `/model-route`; `ai-app-reviewer`, `llm-security-reviewer`, `gan-planner/generator/evaluator` |
| **`embedded`** | ADR-0010 | Firmware — MISRA/CERT-C, linker/startup/vector-table, RTOS/ISR, HIL ladder | `embedded-c-reviewer`, `embedded-build-resolver` |

**Other recent additions:** `/fix "<defect>"` and `/agentforge --fix` (defect fast lane: triage →
failing test → fix → review → PR); `/marketing-video --demo-overlay` (sensor-gauge / data-flow overlay
video, footage or AI-gen base); `/budget-report --commands` + `usage_state.py` (standalone command
cost telemetry); TC-ID-keyed test results (`qa/tc_results.py`) for the trace matrix.

> The per-asset tables below are the full inventory as of v1.1; the `ai-ml` pack and the commands
> named above are the newest and may not each have an individual row yet — this section is the
> authoritative list for them until the inventory is regenerated.

## Role → ADLC Phase → Asset Map

> **67 agents · 42 commands · 222 skills · 27 MCP servers · 15 hooks** — mapped to every phase of the
> Agentic Development Lifecycle.

One row per **role × ADLC phase**. Roles are the canonical stage owners defined in
ADR-0008 (`decisions/ADR-0008-canonical-sdlc-stages.md`) — see the stage → owner → gate table in
[`how_to_run_agentforge.md`](how_to_run_agentforge.md#canonical-stage--code-stage--owner--gate) — plus the
three **engineering-discipline packs**, whose rows are dormant until a project declares
`active_disciplines`.

How to read the columns:

- **Commands / Agents** — what you actually invoke at that phase. `/agentforge` (Agentic Automated) spawns
  these in order; in Agentic Manual mode you run them yourself.
- **Skills** — the skill files those commands and agents are wired to read, taken from `COMMAND_SKILLS` /
  `AGENT_SKILLS` in `patch_assets.py`. Shown as basenames; every one resolves under
  `agentic-assets/skills/` in the installed project.
- **Gates & hooks** — 🔒 marks a **hard human-approval gate**: the run stops until a named person approves,
  and the decision is recorded with identity and timestamp. Hook IDs follow the [Hooks](#hooks) table
  convention; they are deterministic scripts, so the agent cannot talk its way past one.

| Role | ADLC Phase | Commands | Agents | Skills | Gates & hooks (guardrails) |
|---|---|---|---|---|---|
| **Legacy Modernizer** | **S0** Onboarding *(brownfield only)* | `/legacy-audit`, `/scope-context` | `legacy-modernizer`, `context-scoper`, `code-explorer` | legacy-modernization, risk-assessment, context-scoping, coding-standards, agentic-engineering | soft gate · `post:edit:legacy-risk` (high-risk legacy edit forces specialist routing) |
| **Researcher** | **S1** Research | `/research` | `researcher`, `docs-lookup` | deep-research, market-research, extraction-with-citation | — · sources must be cited-or-TBD (MCP: `exa-web-search`, `context7`) |
| **Product Manager** | **S2** Requirements → PRD | `/prp-prd` | `product-manager` | prp-prd, product-capability, agentic-engineering | **🔒 PRD gate** · `stop:hitl-gate`, `pre:write-hitl-gate` |
| **Product / BA** | **S3** Epics & user stories | `/prd-to-epics` | `epic-writer` | prd-decomposition, product-capability | — · `pre:write-hitl-gate` keeps the sealed PRD read-only |
| **Product / BA** | **S4** Tasks | `/stories-to-tasks` | `task-writer` | stories-to-tasks, prd-decomposition | — |
| **Project Manager** | **S5** Sprint plan | `/sprint-plan` | `project-manager` | sprint-planning, agentic-engineering | **🔒 Sprint gate** · `stop:hitl-gate` |
| **Architect** | **D1** Architecture / component design | `/architecture`, `/prp-plan` | `architect`, `code-architect`, `planner` | architecture-design, architecture-diagrams, interface-specification, hexagonal-architecture, risk-assessment | soft ADR review · `pre:write-hitl-gate` |
| **Developer** + `tdd-guide` | **D2** Failing unit tests first (TDD) | `/prp-implement` | `developer`, `tdd-guide` | prp-implement, tdd-workflow | `post:edit:py-lint` → nudges `python-reviewer` |
| **Developer** | **D3** Implementation | `/prp-implement`, `/fix` | `developer`, `build-error-resolver`, per-language `*-build-resolver` | prp-implement, coding-standards, agentic-engineering, defect-fix | `pre:bash:block-no-verify` (no `--no-verify` / `--no-gpg-sign`), `pre:bash:commit-quality`, `post:edit:source-accumulate`, `post:edit:native-accumulate`, `post:edit:console-warn` |
| **Developer** | **D4** Unit tests green | `/test-run`, `/test-coverage`, `/quality-gate` | `tdd-guide`, `test-triage` | test-execution, verification-loop, coding-standards, plankton-code-quality | `stop:typecheck` (`tsc --noEmit` on edited TS) |
| **Reviewers** (Dev lane) | **D5** Code + security review | `/santa-loop` | `code-reviewer`, `security-reviewer`, `code-simplifier`, `silent-failure-hunter`, `type-design-analyzer`, `refactor-cleaner`, `performance-optimizer`, per-language `*-reviewer` | coding-standards, plankton-code-quality, security-review, verification-loop, ai-regression-testing | `stop:code-review-reminder` (**forces** a holistic review pass if any source file was edited), `stop:native-review` |
| **Developer** | **D6** Traceability — code ↔ PRD & stories | `/trace-matrix` | `qa-engineer`, `project-manager` | trace-matrix | — |
| **Tech Lead** | **D7** Pull request | `/prp-commit`, `/prp-pr` | `team-lead`, `pr-test-analyzer`, `security-reviewer` | prp-commit, prp-pr, git-workflow, security-review, plankton-code-quality | **🔒 PR gate — no override** · `pre:write-hitl-gate` blocks `gh pr create` while unresolved, `pre:bash:block-no-verify` |
| **QA Engineer** | **Q1–Q2** Test plan → plan gate | `/test-plan` | `qa-engineer` | test-plan-generation, tdd-workflow, verification-loop | **🔒 Test-plan gate** · `stop:hitl-gate` |
| **QA Engineer** | **Q3** Test-case design (TC-IDs) | `/test-plan` | `qa-engineer` | test-plan-generation, verification-loop | — |
| **QA Automation Engineer** | **Q4** Test automation | `/test-run`, `/eval` | `qa-automation-engineer`, `e2e-runner` | tdd-workflow, e2e-testing, eval-harness | — · tests bound to TC-IDs (`qa/tc_results.py`) |
| **QA Engineer** | **Q5** Traceability — tests ↔ stories / AC | `/trace-matrix` | `qa-engineer` | trace-matrix | — |
| **QA Engineer** | **Q6** Execution → triage → defect log | `/test-run`, `/fix` | `test-triage`, `qa-engineer` | test-execution, verification-loop, defect-fix | — · failures classified bug / test-bug / env / flake with evidence |
| **QA Engineer** | **Q7** Regression | `/test-run`, `/santa-loop` | `pr-test-analyzer`, `gan-evaluator` | ai-regression-testing, verification-loop | — |
| **Project Manager** | **Release readiness** — overall traceability | `/trace-matrix` | `project-manager` | trace-matrix, agentic-engineering | — · requirements ↔ code ↔ tests ↔ results; both lanes must pass |
| **DevOps** | **Deploy** — staging → prod | `/pm2`, `/quality-gate` | `devops`, `build-error-resolver` | deployment-patterns | — · runs only after *both* lanes clear · `pre:bash:block-no-verify` |
| **Project Manager** | **Sprint close** — burndown, schedule, budget | `/sprint-report`, `/budget-report` | `project-manager` | sprint-reporting, budget-reporting, agentic-engineering | — · per-stage token/cost from `run.json usage` |
| **Enablement** | **Enablement** — product doc, video, deck | `/product-doc`, `/marketing-video`, `/cognizant-ppt` | `doc-updater`, `marketing-script-writer`, `marketing-storyboard-planner`, `seo-specialist` | documentation-patterns, marketing-video-builder, cognizant-ppt, seo | — |
| **ML Data Engineer** *(`ai-ml`)* | Data lane — before model build | `/dataset-scout`, `/auto-label`, `/synth-data` | `ml-data-engineer` | dataset-sourcing, data-labeling, synthetic-data | `post:edit:ml-leakage`, `pre:bash:ml-artifact` |
| **ML Modeler** *(`ai-ml`)* | Model build → cloud-GPU handoff | `/model-select`, `/model-build` | `ml-modeler` | pretrained-and-transfer, model-architectures, model-codegen | `pre:bash:ml-artifact` blocks committed weight blobs |
| **ML Eval Reviewer** *(`ai-ml`)* | Eval-methodology review | `/eval` | `ml-eval-reviewer` | model-codegen, model-architectures, eval-harness | `post:edit:ml-leakage` (train/test leakage guard) |
| **GenAI Engineer** *(`ai-genai`)* | Agentic build loop + model routing | `/gan-build`, `/model-route`, `/loop-start`, `/loop-status` | `gan-planner`, `gan-generator`, `gan-evaluator`, `loop-operator`, `harness-optimizer` | autonomous-loops, continuous-agent-loop, cost-aware-llm-pipeline, context-budget | rubric-threshold convergence gate inside `/gan-build` |
| **GenAI Reviewer** *(`ai-genai`)* | AI-app design + LLM security review (at D5) | *(review pass)* | `ai-app-reviewer`, `llm-security-reviewer` | agentic-engineering, context-budget | `stop:code-review-reminder` · OWASP-LLM: prompt injection, excessive agency |
| **Embedded Engineer** *(`embedded`)* | Firmware build + MISRA/CERT review + HIL ladder | `/simulator` | `embedded-c-reviewer`, `embedded-build-resolver`, `simulator-builder` | misra-cert, linker-and-startup, rtos-isr-safety, simulator-patterns | `post:edit:native-accumulate` → `stop:native-review` |

**Cross-cutting, every phase:** `/agentforge` persists stage + gate state to `run.json` / `gates.json`
after each transition (`--status`, `--resume`, `--dry-run`, `--stage`); `/memory-audit` and `/learn-eval`
keep the memory bank honest; `discover_plugins.py --stage <id>` injects any active
[custom domain plugin's](#custom-domain-plugins-agentforge_custom_plugin) context before the stage runs.

## Agents

| Name | Purpose | Source path | How to use |
|---|---|---|---|
| `marketing-script-writer` | Marketing video script specialist for 3-minute B2B explainers targeting business owners. Takes a one-paragraph brief and produces a 180-second script following the canonical 6-beat structure (hook → problem → solution → how → proof → CTA). Use for marketing video scripts, LinkedIn/YouTube cuts, sales explainers. Output is timing-locked at 150 wpm (~450 words total). | `agents/MARKETING/marketing-script-writer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `marketing-storyboard-planner` | Marketing video storyboard specialist. Takes a 6-beat script and produces a scene-by-scene plan with Pexels/Pixabay search queries, timing, captions, and music mood per scene. Use after marketing-script-writer to convert a script into a renderable storyboard JSON consumed by the Python ffmpeg assembler. Output is a strict JSON schema. | `agents/MARKETING/marketing-storyboard-planner.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `architect` | Software architecture specialist for system design, scalability, and technical decision-making. Use PROACTIVELY when planning new features, refactoring large systems, or making architectural decisions. | `agents/SDLC/architect.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `build-error-resolver` | Build and TypeScript error resolution specialist. Use PROACTIVELY when build fails or type errors occur. Fixes build/type errors only with minimal diffs, no architectural edits. Focuses on getting the build green quickly. | `agents/SDLC/build-error-resolver.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `chief-of-staff` | Personal communication chief of staff that triages email, Slack, LINE, and Messenger. Classifies messages into 4 tiers (skip/info_only/meeting_info/action_required), generates draft replies, and enforces post-send follow-through via hooks. Use when managing multi-channel communication workflows. | `agents/SDLC/chief-of-staff.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `code-architect` | Designs feature architectures by analyzing existing codebase patterns and conventions, then providing implementation blueprints with concrete files, interfaces, data flow, and build order. | `agents/SDLC/code-architect.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `code-explorer` | Deeply analyzes existing codebase features by tracing execution paths, mapping architecture layers, and documenting dependencies to inform new development. | `agents/SDLC/code-explorer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `code-reviewer` | Expert code review specialist. Proactively reviews code for quality, security, and maintainability. Use immediately after writing or modifying code. MUST BE USED for all code changes. | `agents/SDLC/code-reviewer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `code-simplifier` | Simplifies and refines code for clarity, consistency, and maintainability while preserving behavior. Focus on recently modified code unless instructed otherwise. | `agents/SDLC/code-simplifier.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `context-scoper` | Guides a TODO-driven process to scope Claude's context to one segment of a legacy monolithic codebase. Manufactures a boundary (segment map) via execution tracing, adds characterization tests, and drops a segment-scoped CLAUDE.md. For modular codebases, defers to the automated walker. | `agents/SDLC/context-scoper.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `developer` | Implements code and tests per task at stage S8 of the AgentForge SDLC, working in tandem with tdd-guide. Use PROACTIVELY when the orchestrator reaches the build stage with a task ID from the backlog. | `agents/SDLC/developer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `devops` | Produces a CI workflow and deploy plan at stage S15 of the AgentForge SDLC. Use PROACTIVELY when the orchestrator reaches the deploy stage, or when a project needs its first CI/CD workflow. | `agents/SDLC/devops.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `docs-lookup` | When the user asks how to use a library, framework, or API or needs up-to-date code examples, use Context7 MCP to fetch current documentation and return answers with examples. Invoke for docs/API/setup questions. | `agents/SDLC/docs-lookup.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `doc-updater` | Documentation and codemap specialist. Use PROACTIVELY for updating codemaps and documentation. Runs /update-codemaps and /update-docs, generates docs/CODEMAPS/*, updates READMEs and guides. | `agents/SDLC/doc-updater.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `e2e-runner` | End-to-end testing specialist using Vercel Agent Browser (preferred) with Playwright fallback. Use PROACTIVELY for generating, maintaining, and running E2E tests. Manages test journeys, quarantines flaky tests, uploads artifacts (screenshots, videos, traces), and ensures critical user flows work. | `agents/SDLC/e2e-runner.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `epic-writer` | PRD decomposition specialist. Reads a PRD and produces implementation-ready EPICs and User Stories with traceable acceptance criteria, persona-aligned story format, and MoSCoW priority mapping. Use when converting any PRD into a sprint-ready backlog. Spawned automatically by /prd-to-epics. | `agents/SDLC/epic-writer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `gan-evaluator` | GAN Harness — Evaluator agent. Tests the live running application via Playwright, scores against rubric, and provides actionable feedback to the Generator. | `agents/ENGINEERING/ai-genai/gan-evaluator.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `gan-generator` | GAN Harness — Generator agent. Implements features according to the spec, reads evaluator feedback, and iterates until quality threshold is met. | `agents/ENGINEERING/ai-genai/gan-generator.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `gan-planner` | GAN Harness — Planner agent. Expands a one-line prompt into a full product specification with features, sprints, evaluation criteria, and design direction. | `agents/ENGINEERING/ai-genai/gan-planner.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `harness-optimizer` | Analyze and improve the local agent harness configuration for reliability, cost, and throughput. | `agents/SDLC/harness-optimizer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `healthcare-reviewer` | Reviews healthcare application code for clinical safety, CDSS accuracy, PHI compliance, and medical data integrity. Specialized for EMR/EHR, clinical decision support, and health information systems. | `agents/SDLC/healthcare-reviewer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `legacy-modernizer` | Brownfield codebase onboarding and modernization specialist. Use PROACTIVELY when installing AgentForge into an existing project, auditing undocumented systems, creating memory-bank hierarchy, planning safe refactors, or touching legacy code with unclear tests or ownership. | `agents/SDLC/legacy-modernizer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `loop-operator` | Operate autonomous agent loops, monitor progress, and intervene safely when loops stall. | `agents/SDLC/loop-operator.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `performance-optimizer` | Performance analysis and optimization specialist. Use PROACTIVELY for identifying bottlenecks, optimizing slow code, reducing bundle sizes, and improving runtime performance. Profiling, memory leaks, render optimization, and algorithmic improvements. | `agents/SDLC/performance-optimizer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `planner` | Expert planning specialist for complex features and refactoring. Use PROACTIVELY when users request feature implementation, architectural changes, or complex refactoring. Automatically activated for planning tasks. | `agents/SDLC/planner.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `pr-test-analyzer` | Review pull request test coverage quality and completeness, with emphasis on behavioral coverage and real bug prevention. | `agents/SDLC/pr-test-analyzer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `product-manager` | Produces the gated requirements artifact (PRD) at stage S2 of the AgentForge SDLC. Use PROACTIVELY when the orchestrator reaches the requirements stage, or when a human needs a problem-first, hypothesis-driven PRD without running /prp-prd interactively. | `agents/SDLC/product-manager.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `project-manager` | Maintains PROGRESS.md and backlog state as the AgentForge run advances. Use PROACTIVELY on every stage transition to keep status and backlog from drifting apart, and at sprint boundaries once sprint mechanics exist (EP-08). | `agents/SDLC/project-manager.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `qa-automation-engineer` | Produces automated tests bound to TC-IDs at stage S9 of the AgentForge SDLC. Use PROACTIVELY when the orchestrator reaches the test-automation stage after the S6 test plan exists. | `agents/SDLC/qa-automation-engineer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `qa-engineer` | Produces the gated test-plan (S6) and traceability (S12) artifacts of the AgentForge SDLC. Use PROACTIVELY when the orchestrator reaches the test-plan stage, or when a human needs a tool-neutral test plan traced to acceptance criteria. | `agents/SDLC/qa-engineer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `refactor-cleaner` | Dead code cleanup and consolidation specialist. Use PROACTIVELY for removing unused code, duplicates, and refactoring. Runs analysis tools (knip, depcheck, ts-prune) to identify dead code and safely removes it. | `agents/SDLC/refactor-cleaner.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `researcher` | Pre-project research specialist. Conducts market analysis, competitive landscape, technology evaluation, and vendor diligence before a PRD is written. Produces cited research reports and a decision brief that feeds directly into /prp-prd. Use at the start of any new product, feature, or platform decision. | `agents/SDLC/researcher.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `security-reviewer` | Security vulnerability detection and remediation specialist. Use PROACTIVELY after writing code that handles user input, authentication, API endpoints, or sensitive data. Flags secrets, SSRF, injection, unsafe crypto, and OWASP Top 10 vulnerabilities. | `agents/SDLC/security-reviewer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `seo-specialist` | SEO specialist for technical SEO audits, on-page optimization, structured data, Core Web Vitals, and content/keyword mapping. Use for site audits, meta tag reviews, schema markup, sitemap and robots issues, and SEO remediation plans. | `agents/SDLC/seo-specialist.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `silent-failure-hunter` | Review code for silent failures, swallowed errors, bad fallbacks, and missing error propagation. | `agents/SDLC/silent-failure-hunter.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `task-writer` | Sprint decomposition specialist. Reads a User Stories file and produces a measurable task board — each story broken into sized, typed, dependency-ordered tasks with binary definitions of done. Use when converting User Stories into a sprint-trackable task list. Spawned automatically by /stories-to-tasks. | `agents/SDLC/task-writer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `tdd-guide` | Test-Driven Development specialist enforcing write-tests-first methodology. Use PROACTIVELY when writing new features, fixing bugs, or refactoring code. Ensures 80%+ test coverage. | `agents/SDLC/tdd-guide.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `team-lead` | Fans in the existing reviewer agents at stage S13 of the AgentForge SDLC and emits one adjudicated verdict. Use PROACTIVELY when the orchestrator reaches the review stage after a build, or when multiple reviewer reports need a single ranked outcome. | `agents/SDLC/team-lead.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `test-triage` | Classifies test failures as product bug, test bug, environment, or flake with attached evidence, and files or quarantines accordingly. Use PROACTIVELY when a test run produces failures that need routing before Monday-morning manual triage. | `agents/SDLC/test-triage.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `type-design-analyzer` | Analyze type design for encapsulation, invariant expression, usefulness, and enforcement. | `agents/SDLC/type-design-analyzer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `cpp-build-resolver` | C++ build, CMake, and compilation error resolution specialist. Fixes build errors, linker issues, and template errors with minimal changes. Use when C++ builds fail. | `agents/SOFTWARE/cpp-build-resolver.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `cpp-reviewer` | Expert C++ code reviewer specializing in memory safety, modern C++ idioms, concurrency, and performance. Use for all C++ code changes. MUST BE USED for C++ projects. | `agents/SOFTWARE/cpp-reviewer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `csharp-reviewer` | Expert C# code reviewer specializing in .NET conventions, async patterns, security, nullable reference types, and performance. Use for all C# code changes. MUST BE USED for C# projects. | `agents/SOFTWARE/csharp-reviewer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `dart-build-resolver` | Dart/Flutter build, analysis, and dependency error resolution specialist. Fixes `dart analyze` errors, Flutter compilation failures, pub dependency conflicts, and build_runner issues with minimal, surgical changes. Use when Dart/Flutter builds fail. | `agents/SOFTWARE/dart-build-resolver.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `database-reviewer` | PostgreSQL database specialist for query optimization, schema design, security, and performance. Use PROACTIVELY when writing SQL, creating migrations, designing schemas, or troubleshooting database performance. Incorporates Supabase best practices. | `agents/SOFTWARE/database-reviewer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `flutter-reviewer` | Flutter and Dart code reviewer. Reviews Flutter code for widget best practices, state management patterns, Dart idioms, performance pitfalls, accessibility, and clean architecture violations. Library-agnostic — works with any state management solution and tooling. | `agents/SOFTWARE/flutter-reviewer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `go-build-resolver` | Go build, vet, and compilation error resolution specialist. Fixes build errors, go vet issues, and linter warnings with minimal changes. Use when Go builds fail. | `agents/SOFTWARE/go-build-resolver.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `go-reviewer` | Expert Go code reviewer specializing in idiomatic Go, concurrency patterns, error handling, and performance. Use for all Go code changes. MUST BE USED for Go projects. | `agents/SOFTWARE/go-reviewer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `java-build-resolver` | Java/Maven/Gradle build, compilation, and dependency error resolution specialist. Fixes build errors, Java compiler errors, and Maven/Gradle issues with minimal changes. Use when Java or Spring Boot builds fail. | `agents/SOFTWARE/java-build-resolver.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `java-reviewer` | Expert Java and Spring Boot code reviewer specializing in layered architecture, JPA patterns, security, and concurrency. Use for all Java code changes. MUST BE USED for Spring Boot projects. | `agents/SOFTWARE/java-reviewer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `kotlin-build-resolver` | Kotlin/Gradle build, compilation, and dependency error resolution specialist. Fixes build errors, Kotlin compiler errors, and Gradle issues with minimal changes. Use when Kotlin builds fail. | `agents/SOFTWARE/kotlin-build-resolver.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `kotlin-reviewer` | Kotlin and Android/KMP code reviewer. Reviews Kotlin code for idiomatic patterns, coroutine safety, Compose best practices, clean architecture violations, and common Android pitfalls. | `agents/SOFTWARE/kotlin-reviewer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `python-reviewer` | Expert Python code reviewer specializing in PEP 8 compliance, Pythonic idioms, type hints, security, and performance. Use for all Python code changes. MUST BE USED for Python projects. | `agents/SOFTWARE/python-reviewer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `pytorch-build-resolver` | PyTorch runtime, CUDA, and training error resolution specialist. Fixes tensor shape mismatches, device errors, gradient issues, DataLoader problems, and mixed precision failures with minimal changes. Use when PyTorch training or inference crashes. | `agents/SOFTWARE/pytorch-build-resolver.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `rust-build-resolver` | Rust build, compilation, and dependency error resolution specialist. Fixes cargo build errors, borrow checker issues, and Cargo.toml problems with minimal changes. Use when Rust builds fail. | `agents/SOFTWARE/rust-build-resolver.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `rust-reviewer` | Expert Rust code reviewer specializing in ownership, lifetimes, error handling, unsafe usage, and idiomatic patterns. Use for all Rust code changes. MUST BE USED for Rust projects. | `agents/SOFTWARE/rust-reviewer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |
| `typescript-reviewer` | Expert TypeScript/JavaScript code reviewer specializing in type safety, async correctness, Node/web security, and idiomatic patterns. Use for all TypeScript and JavaScript code changes. MUST BE USED for TypeScript/JavaScript projects. | `agents/SOFTWARE/typescript-reviewer.md` | Use the named agent via route preflight or ask Claude: use this agent for the task. |

## Core Slash Commands

| Name | Purpose | Source path | How to use |
|---|---|---|---|
| `/agentforge` | Orchestrate onboarding → research → requirements → architecture → backlog end to end, sequencing existing role agents and persisting state to run.json after every transition. | `commands/agentforge.md` | Run this slash command in Claude Code. |
| `/architecture` | Architecture | `commands/architecture.md` | Run this slash command in Claude Code. |
| `/budget-report` | Budget Report | `commands/budget-report.md` | Run this slash command in Claude Code. |
| `/cognizant-ppt` | Cognizant PPT | `commands/cognizant-ppt.md` | Run this slash command in Claude Code. |
| `/eval` | Legacy slash-entry shim for the eval-harness skill. Prefer the skill directly. | `commands/eval.md` | Run this slash command in Claude Code. |
| `/gan-build` | /gan-build — GAN-Style Harness Build Loop | `commands/ENGINEERING/ai-genai/gan-build.md` | Run this slash command in Claude Code. |
| `/learn-eval` | Extract reusable patterns from the session, self-evaluate quality before saving, and determine the right save location (Global vs Project). | `commands/learn-eval.md` | Run this slash command in Claude Code. |
| `/legacy-audit` | Legacy Audit Command | `commands/legacy-audit.md` | Run this slash command in Claude Code. |
| `/loc-count` | Count and categorize source files across NeuroEdge projects (Web, Device, or both). | `commands/loc-count.md` | Run this slash command in Claude Code. |
| `/loop-start` | Loop Start Command | `commands/loop-start.md` | Run this slash command in Claude Code. |
| `/loop-status` | Loop Status Command | `commands/loop-status.md` | Run this slash command in Claude Code. |
| `/marketing-video` | /marketing-video — Build a 3-minute B2B marketing video from a brief | `commands/marketing-video.md` | Run this slash command in Claude Code. |
| `/memory-audit` | Memory Audit Command | `commands/memory-audit.md` | Run this slash command in Claude Code. |
| `/model-route` | Model Route Command | `commands/ENGINEERING/ai-genai/model-route.md` | Run this slash command in Claude Code. |
| `/pm2` | PM2 Init | `commands/pm2.md` | Run this slash command in Claude Code. |
| `/prd-to-epics` | Decompose a PRD into EPICs and User Stories — reads a PRD file, maps phases to EPICs, writes stories with traceable acceptance criteria, and saves the output as docs/epics-and-user-stories.md | `commands/prd-to-epics.md` | Run this slash command in Claude Code. |
| `/promote` | Promote project-scoped instincts to global scope | `commands/promote.md` | Run this slash command in Claude Code. |
| `/prp-commit` | Quick commit with natural language file targeting — describe what to commit in plain English | `commands/prp-commit.md` | Run this slash command in Claude Code. |
| `/prp-implement` | Execute an implementation plan with rigorous validation loops | `commands/prp-implement.md` | Run this slash command in Claude Code. |
| `/prp-plan` | Create comprehensive feature implementation plan with codebase analysis and pattern extraction | `commands/prp-plan.md` | Run this slash command in Claude Code. |
| `/prp-pr` | Create a GitHub PR from current branch with unpushed commits — discovers templates, analyzes changes, pushes | `commands/prp-pr.md` | Run this slash command in Claude Code. |
| `/prp-prd` | Interactive PRD generator - problem-first, hypothesis-driven product spec with back-and-forth questioning | `commands/prp-prd.md` | Run this slash command in Claude Code. |
| `/quality-gate` | Quality Gate Command | `commands/quality-gate.md` | Run this slash command in Claude Code. |
| `/research` | Pre-project research — conducts market, competitive, and technology research before writing a PRD. Produces a cited report and decision brief saved to docs/research/. Run before /prp-prd on any new product, platform, or major feature. | `commands/research.md` | Run this slash command in Claude Code. |
| `/santa-loop` | Adversarial dual-review convergence loop — two independent model reviewers must both approve before code ships. | `commands/santa-loop.md` | Run this slash command in Claude Code. |
| `/scope-context` | Scope Claude's context to the active subfolder. Modular codebases: auto-generate a nested CLAUDE.md per package + slim root router (walker: `scripts/scope/generate_subfolder_claude.py`). Monolithic: guide a TODO-driven segment-scoping process. | `commands/scope-context.md` | Run this slash command in Claude Code. |
| `/sprint-plan` | Sprint Plan | `commands/sprint-plan.md` | Run this slash command in Claude Code. |
| `/sprint-report` | Sprint Report | `commands/sprint-report.md` | Run this slash command in Claude Code. |
| `/stories-to-tasks` | Decompose User Stories into measurable sprint tasks — reads epics-and-user-stories.md, breaks each story into sized/typed/ordered tasks with binary definitions of done, and writes docs/task-board.md for progress tracking | `commands/stories-to-tasks.md` | Run this slash command in Claude Code. |
| `/test-coverage` | Test Coverage | `commands/test-coverage.md` | Run this slash command in Claude Code. |
| `/test-plan` | Test Plan | `commands/test-plan.md` | Run this slash command in Claude Code. |
| `/test-run` | Test Run | `commands/test-run.md` | Run this slash command in Claude Code. |
| `/trace-matrix` | Trace Matrix | `commands/trace-matrix.md` | Run this slash command in Claude Code. |

## Product-specific commands

The core repo carries no client- or product-specific commands — it is product-independent.
Product-specific commands belong in a **custom plugin** under
`agentforge_custom_plugin/<Name>/commands/`, which is auto-discovered and kept separate from
the generic assets (see [Custom Domain Plugins](#custom-domain-plugins-agentforge_custom_plugin)).
The auto-scaffolded `Project_Specific_Context` plugin is the place to add them.

## Hooks

| Hook ID | Purpose | Script | How to use |
|---|---|---|---|
| `pre:write-hitl-gate` | Block writes to approved-and-sealed gated artifacts and `gh pr create` while the PR gate is unresolved (D3 warn-with-override) | `scripts/hooks/pre-write-hitl-gate.js` | Automatic on PreToolUse when matcher is 'Write\|Edit\|Bash' |
| `pre:bash:block-no-verify` | Block --no-verify / --no-gpg-sign flags on git commands | `npx block-no-verify@1.1.2` | Automatic on PreToolUse when matcher is 'Bash' |
| `pre:bash:commit-quality` | Pre-commit: ruff on staged .py, console.log check on staged .ts/.js | `scripts/hooks/pre-commit-quality.js` | Automatic on PreToolUse when matcher is 'Bash' |
| `post:edit:py-lint` | Run ruff on any .py file just edited — output prompts Claude to invoke python-reviewer | `scripts/hooks/post-edit-py-lint.js` | Automatic on PostToolUse when matcher is 'Edit\|Write' |
| `post:edit:ts-accumulate` | Accumulate edited .ts/.tsx paths for batch typecheck at Stop | `scripts/hooks/post-edit-ts-accumulate.js` | Automatic on PostToolUse when matcher is 'Edit\|Write' |
| `post:edit:console-warn` | Warn when console.log appears in an edited .ts/.tsx/.js file | `scripts/hooks/post-edit-console-warn.js` | Automatic on PostToolUse when matcher is 'Edit\|Write' |
| `post:edit:legacy-risk` | Warn on high-risk legacy edits and require explicit legacy/specialist routing | `scripts/hooks/post-edit-legacy-risk.js` | Automatic on PostToolUse when matcher is 'Edit\|Write' |
| `post:edit:source-accumulate` | Accumulate any edited source-code file (all languages) for a holistic code-review nudge at Stop | `scripts/hooks/post-edit-source-accumulate.js` | Automatic on PostToolUse when matcher is 'Edit\|Write' |
| `stop:hitl-gate` | Exit 2 while any `gates.json` entry is pending, forcing the `AskUserQuestion` approval flow into the main session (D1) | `scripts/hooks/stop-hitl-gate.js` | Automatic on Stop when matcher is '*' |
| `stop:typecheck` | Run tsc --noEmit on frontend once per response if any .ts/.tsx files were edited | `scripts/hooks/stop-typecheck.js` | Automatic on Stop when matcher is '*' |
| `stop:code-review-reminder` | Force a holistic `code-reviewer` pass if any source file was edited this session — this is the gate that produced the review passes on `agentforge_custom_plugin/` this session | `scripts/hooks/stop-code-review-reminder.js` | Automatic on Stop when matcher is '*' |

## Plugin And Profile Files

| Name | Purpose | Source path | How to use |
|---|---|---|---|
| `legacy-project-onboarding.json` | Recommended MCP/plugin profile for applying AgentForge to brownfield or legacy codebases. | `plugins/legacy-project-onboarding.json` | Read this profile/catalog; copy selected MCP entries to Claude config when needed. |
| `mcp-servers.json` | mcp-servers | `plugins/mcp-servers.json` | Read this profile/catalog; copy selected MCP entries to Claude config when needed. |
| `README.md` | Plugins (MCP Servers) | `plugins/README.md` | Read this profile/catalog; copy selected MCP entries to Claude config when needed. |

> **Not the same thing as a custom domain plugin.** These are a static MCP-server/profile
> catalog you copy entries from by hand. `agentforge_custom_plugin/` (next section) is
> live, per-project, auto-discovered domain context — unrelated mechanism, same word.

## Custom Domain Plugins (`agentforge_custom_plugin/`)

**What it's for.** The base SDLC is generic — it knows nothing about *your* product or
client. A custom plugin holds proprietary, product-specific context (a vendor product you
integrate with, a regulated domain's constraints, real sample data formats) that the SDLC
role agents need but that must never live in the shared, installable base assets.

**Why a separate folder, not `docs/context/`.** The base memory bank (`docs/context/`) is
per-project *state* (what's happening now). A custom plugin is per-project *reference
knowledge* (what's permanently true about this product), structured so it can be
scaffolded, installed into another project, and read by name from any SDLC stage.

### The three knowledge layers

| Layer | Question it answers | Reusable? | Lives in |
|---|---|---|---|
| Generic SDLC craft | How do we build software? | Any project | `skills/SDLC/`, `skills/SOFTWARE/`, base agents |
| Subject expertise | What does an expert in this *field* know? | Any project in the field | `skills/SUBJECTS/<Subject>/` |
| Custom plugin | What is true about *this product/client*? | No — one product | `agentforge_custom_plugin/<Name>/` |

"Generic" is not limited to software craft — reusable **subject-matter expertise** (e.g.
medical physics) is equally generic and lives in the base `skills/SUBJECTS/` tree, not
inside a plugin. A plugin references a subject via `plugin.json`'s `requires_subjects`
rather than copying it.

### Layout

```
agentforge_custom_plugin/
  discover_plugins.py           # auto-discovery: given a stage, prints what to read
  patch_custom_plugin.py        # scaffolder: --new <Name> / --install <Name> --project <path> / --list
  <Name>/
    plugin.json                 # manifest: requires_subjects, personas, regulatory, wiring
    agents/                     # plugin-scoped agent(s) — a deep-dive domain expert
    commands/                   # plugin-scoped command (e.g. /suncheck) for direct consult
    skills/                     # product-specific integration knowledge (proprietary)
    context/                    # the context pack itself
      DOMAIN.md                 # index — read this first
      glossary.md  personas.md  regulatory.md  constraints.md
      workflows/                # domain process, as-is
      integrations/<product>/   # product.md, data-formats.md, interfaces.md, samples/
      sources.md                # provenance + confidence per fact
```

### How auto-discovery works — presence is activation

No install step, no registry. Any `agentforge_custom_plugin/<Name>/plugin.json` whose
`wiring.auto_load` is not explicitly `false` is active. Each manifest carries a
`wiring.stage_context` map:

```json
"wiring": {
  "auto_load": true,
  "stage_context": {
    "requirements": ["context/personas.md", "context/regulatory.md", "context/constraints.md"],
    "architecture": ["context/integrations/<product>/interfaces.md", "context/constraints.md"]
  }
}
```

`discover_plugins.py --stage <id>` reads every active plugin's map and prints the exact
files that stage should read, plus any `requires_subjects` skill paths — with path-safety
validation (no `..`, no absolute-path injection) on every value, since a `plugin.json` can
be authored by one person and installed by another.

- **`/agentforge` (Agentic Automated)** runs this before every stage spawn and passes the
  files in as binding domain context.
- **Pipeline role agents (Agentic Manual)** — `product-manager`, `architect`,
  `qa-engineer`, `researcher`, `epic-writer`, `task-writer` — self-discover the same way
  via `Glob` when run standalone, so the wiring works with or without the orchestrator.

The user's only job is to **fill or add files** inside the plugin folder. Deactivate
without deleting by setting `"auto_load": false`.

### Commands

```bash
python agentforge_custom_plugin/discover_plugins.py --list                        # what's active
python agentforge_custom_plugin/discover_plugins.py --stage requirements          # what a stage will read
python agentforge_custom_plugin/patch_custom_plugin.py --new <Name>               # scaffold a plugin
python agentforge_custom_plugin/patch_custom_plugin.py --install <Name> --project <path>  # copy into another project (+ its subject skills)
```

### Current plugins

| Plugin | Domain | Subject dep. | Regulatory | Integration | Source |
|---|---|---|---|---|---|
| `SunCHECK` | Radiation oncology QA | `Physics` | IEC-62304 | Mirion SunCHECK (Machine QA + Patient QA) | `agentforge_custom_plugin/SunCHECK/` |

See `agentforge_custom_plugin/README.md` for the full authoring reference, and
[`how_to_run_agentforge.md`](how_to_run_agentforge.md#domain-plugins-auto-discovered-in-both-modes)
for how discovery fits into an orchestrated run.

## MCP Servers

| Name | Purpose | Source path | How to use |
|---|---|---|---|
| `browserbase` | Cloud browser sessions via Browserbase | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `browser-use` | AI browser agent for web tasks | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `clickhouse` | ClickHouse analytics queries | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `cloudflare-docs` | Cloudflare documentation search | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `cloudflare-observability` | Cloudflare observability/logs | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `cloudflare-workers-bindings` | Cloudflare Workers bindings | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `cloudflare-workers-builds` | Cloudflare Workers builds | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `confluence` | Confluence Cloud integration — search pages, retrieve content, explore spaces | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `context7` | Live documentation lookup — use with /docs command and documentation-lookup skill (resolve-library-id, query-docs). | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `devfleet` | Multi-agent orchestration — dispatch parallel Claude Code agents in isolated worktrees. Plan projects, auto-chain missions, read structured reports. Repo: https://github.com/LEC-AI/claude-devfleet | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `evalview` | AI agent regression testing — snapshot behavior, detect regressions in tool calls and output quality. 8 tools: create_test, run_snapshot, run_check, list_tests, validate_skill, generate_skill_tests, run_skill_test, generate_visual_report. API key optional — deterministic checks (tool diff, output hash) work without it. Install: pip install "evalview>=0.5,<1" | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `exa-web-search` | Web search, research, and data ingestion via Exa API — prefer task-scoped use for broader research after GitHub search and primary docs | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `fal-ai` | AI image/video/audio generation via fal.ai models | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `filesystem` | Filesystem operations (set your path) | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `firecrawl` | Web scraping and crawling | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `github` | GitHub operations - PRs, issues, repos | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `jira` | Jira issue tracking — search, create, update, comment, transition issues | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `laraplugins` | Laravel plugin discovery — search packages by keyword, health score, Laravel/PHP version compatibility. Use with laravel-plugin-discovery skill. | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `magic` | Magic UI components | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `memory` | Persistent memory across sessions | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `omega-memory` | Persistent agent memory with semantic search, multi-agent coordination, and knowledge graphs — run via uvx (richer than the basic memory store) | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `playwright` | Browser automation and testing via Playwright | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `railway` | Railway deployments | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `sequential-thinking` | Chain-of-thought reasoning | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `supabase` | Supabase database operations | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `token-optimizer` | Token optimization for 95%+ context reduction via content deduplication and compression | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |
| `vercel` | Vercel deployments and projects | `plugins/mcp-servers.json` | Copy the server entry from `plugins/mcp-servers.json` into `~/.claude.json`; fill env placeholders. |

## Project Template

AgentForge ships **one** product-neutral project template, installed into every target.
The core repo carries no per-product (web/device/client) scaffold.

| Name | Purpose | Source path | How to use |
|---|---|---|---|
| `CLAUDE` | CLAUDE.md — AgentForge Starter (the neutral template) | `projects/generic/CLAUDE.md` | Installed by setup into the target's `CLAUDE.md` (seeded once, then project-owned); fill in the `<!-- CUSTOMIZE -->` lines after install. |

Product- or client-specific templates, commands, and context now live in a **custom
plugin** (`agentforge_custom_plugin/<Name>/`), auto-scaffolded as `Project_Specific_Context`
and kept out of the generic core — see [Custom Domain Plugins](#custom-domain-plugins-agentforge_custom_plugin).

## Skills And Reference Files

> **SUBJECTS is a distinct category from DOMAIN**, added alongside SDLC/SOFTWARE/DOMAIN/DEPLOY-TARGETS:
> reusable subject-matter expertise (e.g. medical physics) rather than an industry vertical's
> application patterns. See [Custom Domain Plugins](#custom-domain-plugins-agentforge_custom_plugin)
> for how a plugin references a SUBJECTS skill via `requires_subjects`, and note that SUBJECTS
> skills are the one skill category that's **auto-discovered**, not just manually read.

| Name | Purpose | Source path | How to use |
|---|---|---|---|
| `README` | SUBJECTS — subject-matter expertise skills (category index: SUBJECT vs DOMAIN vs a custom plugin) | `skills/SUBJECTS/README.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `radiotherapy-qa-physics` | Medical-physics subject expertise for radiotherapy and diagnostic-imaging QA. Machine QA vs Patient QA distinction, LINAC output/geometry checks (TG-142), patient-specific IMRT/VMAT QA and the gamma index (TG-218). Product-neutral. | `skills/SUBJECTS/Physics/radiotherapy-qa-physics.md` | **Auto-discovered** by any plugin declaring `Physics` in `requires_subjects`; also readable directly like any skill. |
| `healthcare-cdss-patterns` | Clinical Decision Support System (CDSS) development patterns. Drug interaction checking, dose validation, clinical scoring (NEWS2, qSOFA), alert severity classification, and integration into EMR workflows. | `skills/DOMAIN/healthcare/healthcare-cdss-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `healthcare-emr-patterns` | EMR/EHR development patterns for healthcare applications. Clinical safety, encounter workflows, prescription generation, clinical decision support integration, and accessibility-first UI for medical data entry. | `skills/DOMAIN/healthcare/healthcare-emr-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `healthcare-phi-compliance` | Protected Health Information (PHI) and Personally Identifiable Information (PII) compliance patterns for healthcare applications. Covers data classification, access control, audit trails, encryption, and common leak vectors. | `skills/DOMAIN/healthcare/healthcare-phi-compliance.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hipaa-compliance` | HIPAA-specific entrypoint for healthcare privacy and security work. Use when a task is explicitly framed around HIPAA, PHI handling, covered entities, BAAs, breach posture, or US healthcare compliance requirements. | `skills/DOMAIN/healthcare/hipaa-compliance.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `inventory-management` | > | `skills/DOMAIN/retail/inventory-management.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `README` | hw_cpu_only | `skills/DEPLOY-TARGETS/Capabilities/cpu_only/README.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `cpu_model_matrix` | CPU YOLO Model Performance Matrix | `skills/DEPLOY-TARGETS/Capabilities/cpu_only/references/cpu_model_matrix.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `cpu_setup_guide` | CPU-Only PyTorch & Ultralytics Setup Guide | `skills/DEPLOY-TARGETS/Capabilities/cpu_only/references/cpu_setup_guide.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `SKILL` | > | `skills/DEPLOY-TARGETS/Capabilities/cpu_only/SKILL.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `README` | hw_nvidia_local_gpu | `skills/DEPLOY-TARGETS/Capabilities/nvidia_gpu/README.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `cuda_setup_guide` | CUDA Setup Guide — Local NVIDIA GPU (Windows & Linux) | `skills/DEPLOY-TARGETS/Capabilities/nvidia_gpu/references/cuda_setup_guide.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `gpu_model_matrix` | GPU Model Fit Matrix | `skills/DEPLOY-TARGETS/Capabilities/nvidia_gpu/references/gpu_model_matrix.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `SKILL` | > | `skills/DEPLOY-TARGETS/Capabilities/nvidia_gpu/SKILL.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `README` | DEPLOY-TARGETS / cloud-aws | `skills/DEPLOY-TARGETS/cloud-aws/README.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `foundation-models-on-device` | FoundationModels: On-Device LLM (iOS 26) | `skills/DEPLOY-TARGETS/foundation-models-on-device.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `cuda-patterns` | CUDA Patterns | `skills/DEPLOY-TARGETS/nvidia-jetson/cuda-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `jetson-deployment` | Jetson Deployment | `skills/DEPLOY-TARGETS/nvidia-jetson/jetson-deployment.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `README` | DEPLOY-TARGETS / nvidia-jetson | `skills/DEPLOY-TARGETS/nvidia-jetson/README.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `tensorrt-optimization` | TensorRT Optimization | `skills/DEPLOY-TARGETS/nvidia-jetson/tensorrt-optimization.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `qnn-deployment` | QNN Deployment | `skills/DEPLOY-TARGETS/qualcomm/qnn-deployment.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `qualcomm-ai-hub` | Qualcomm AI Hub | `skills/DEPLOY-TARGETS/qualcomm/qualcomm-ai-hub.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `README` | DEPLOY-TARGETS / qualcomm | `skills/DEPLOY-TARGETS/qualcomm/README.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `snpe-patterns` | SNPE Patterns | `skills/DEPLOY-TARGETS/qualcomm/snpe-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `arm-optimization` | ARM Optimization | `skills/DEPLOY-TARGETS/raspberry-pi/arm-optimization.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `README` | DEPLOY-TARGETS / raspberry-pi | `skills/DEPLOY-TARGETS/raspberry-pi/README.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `rpi-deployment` | RPi Deployment | `skills/DEPLOY-TARGETS/raspberry-pi/rpi-deployment.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `canary-watch` | Use this skill to monitor a deployed URL for regressions after deploys, merges, or dependency upgrades. | `skills/SDLC/deployment/canary-watch.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `context-budget` | Audits Claude Code context window consumption across agents, skills, MCP servers, and rules. Identifies bloat, redundant components, and produces prioritized token-savings recommendations. | `skills/SDLC/deployment/context-budget.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `cost-aware-llm-pipeline` | Cost optimization patterns for LLM API usage — model routing by task complexity, budget tracking, retry logic, and prompt caching. | `skills/ENGINEERING/ai-genai/cost-aware-llm-pipeline.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `database-migrations` | Database migration best practices for schema changes, data migrations, rollbacks, and zero-downtime deployments across PostgreSQL, MySQL, and common ORMs (Prisma, Drizzle, Kysely, Django, TypeORM, golang-migrate). | `skills/SDLC/deployment/database-migrations.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `deployment-patterns` | Deployment workflows, CI/CD pipeline patterns, Docker containerization, health checks, rollback strategies, and production readiness checklists for web applications. | `skills/SDLC/deployment/deployment-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `docker-patterns` | Docker and Docker Compose patterns for local development, container security, networking, volume strategies, and multi-service orchestration. | `skills/SDLC/deployment/docker-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `agentic-engineering` | Operate as an agentic engineer using eval-first execution, decomposition, and cost-aware model routing. | `skills/SDLC/development/agentic-engineering.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `api-design` | REST API design patterns including resource naming, status codes, pagination, filtering, error responses, versioning, and rate limiting for production APIs. | `skills/SDLC/development/api-design.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `architecture-design` | Produce a gated architecture artifact for a feature before implementation — component and sequence diagrams, interface contracts, data flow, state transitions, chosen patterns, and the ADRs that record why. Use at the S3 architecture stage, after the PRD gate and before planning and build. | `skills/SDLC/development/architecture-design.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `autonomous-loops` | Patterns and architectures for autonomous Claude Code loops — from simple sequential pipelines to RFC-driven multi-agent DAG systems. | `skills/ENGINEERING/ai-genai/autonomous-loops.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `backend-patterns` | Backend architecture patterns, API design, database optimization, and server-side best practices for Node.js, Express, and Next.js API routes. | `skills/SDLC/development/backend-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-standards` | Baseline cross-project coding conventions for naming, readability, immutability, and code-quality review. Use detailed frontend or backend skills for framework-specific patterns. | `skills/SDLC/development/coding-standards.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `context-scoping` | Keep only the active subfolder's code in Claude's context. Auto-generate nested CLAUDE.md files for modular codebases; guide a TODO-driven segment-scoping process for legacy monolithic code. Soft enforcement via conventions and subagent delegation. | `skills/SDLC/development/context-scoping.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `continuous-agent-loop` | Patterns for continuous autonomous agent loops with quality gates, evals, and recovery controls. | `skills/ENGINEERING/ai-genai/continuous-agent-loop.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `continuous-learning-v2` | Instinct-based learning system that observes sessions via hooks, creates atomic instincts with confidence scoring, and evolves them into skills/commands/agents. v2.1 adds project-scoped instincts to prevent cross-project contamination. | `skills/SDLC/development/continuous-learning-v2.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `documentation-patterns` | Patterns for writing and maintaining project documentation — READMEs, API docs, architecture codemaps, runbooks, and inline comments. Use when generating, reviewing, or updating any documentation artifact. | `skills/SDLC/development/documentation-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `frontend-patterns` | Frontend development patterns for React, Next.js, state management, performance optimization, and UI best practices. | `skills/SDLC/development/frontend-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `git-workflow` | Git workflow patterns including branching strategies, commit conventions, merge vs rebase, conflict resolution, and collaborative development best practices for teams of all sizes. | `skills/SDLC/development/git-workflow.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hexagonal-architecture` | Design, implement, and refactor Ports & Adapters systems with clear domain boundaries, dependency inversion, and testable use-case orchestration across TypeScript, Java, Kotlin, and Go services. | `skills/SDLC/development/hexagonal-architecture.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `legacy-modernization` | Audit, onboard, and modernize brownfield codebases safely by preserving behavior, building a memory bank, mapping architecture and ownership, and planning incremental change. | `skills/SDLC/development/legacy-modernization.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `logger_for_app` | Centralised application logging framework covering log levels (DEBUG/INFO/WARN/ERROR), structured JSON output, contextual enrichment (correlation IDs, request tracing), multi-destination routing, security filtering, and async performance patterns. Includes reference implementations for Python, TypeScript, and Java. | `skills/SDLC/development/logger_for_app.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `mcp-server-patterns` | Build MCP servers with Node/TypeScript SDK — tools, resources, prompts, Zod validation, stdio vs Streamable HTTP. Use Context7 or official MCP docs for latest API. | `skills/ENGINEERING/ai-genai/mcp-server-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `plankton-code-quality` | Plankton Code Quality Skill | `skills/SDLC/development/plankton-code-quality.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `prompt-optimizer` | Prompt Optimizer | `skills/SDLC/development/prompt-optimizer.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `risk-assessment` | Produce a gated risk artifact for a feature before implementation — implementation, regression, and security risks, each with an ID, likelihood, impact, and mitigation, and each traceable into the test plan. Use at the S3 architecture stage alongside architecture-design, before planning and build. | `skills/SDLC/development/risk-assessment.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `budget-reporting` | Report delivery cost and AI runtime cost as two separate, never-blended figures for the active sprint, with a monthly rollup assuming two sprints per month — the procedure /budget-report and the project-manager agent both follow. | `skills/SDLC/pm/budget-reporting.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `sprint-planning` | Open or enrol into a cross-run sprint container, commit a capacity-bound backlog with the one-story-one-sprint split rule, and open the S5 sprint-plan hard gate — the procedure /sprint-plan and the project-manager agent both follow. | `skills/SDLC/pm/sprint-planning.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `sprint-reporting` | Render burn-down and velocity for the active sprint, or close a sprint into a committed-vs-delivered completion report — the procedure /sprint-report and the project-manager agent both follow. | `skills/SDLC/pm/sprint-reporting.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `prp-commit` | Natural-language commit procedure: interpret a plain-English target into a staged, single-line conventional-commit change set. | `skills/SDLC/prp/prp-commit.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `prp-implement` | Plan-execution procedure: per-task RED->GREEN TDD loop, five-level validation, implementation report, and PRD/EPIC/task-board trace sync. | `skills/SDLC/prp/prp-implement.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `prp-plan` | Implementation-plan generation procedure: codebase pattern extraction, task-board cross-reference, and a test-first (RED->GREEN) plan template. | `skills/SDLC/prp/prp-plan.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `prp-pr` | Pull-request creation procedure: mandatory security-review gate, PR-template discovery, push, and PR body assembly with security and coverage notes. | `skills/SDLC/prp/prp-pr.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `prp-prd` | Problem-first, hypothesis-driven PRD generation procedure: interactive discovery, grounding research, and a full PRD template with stable FR-NN requirement numbering. | `skills/SDLC/prp/prp-prd.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `deep-research` | Multi-source deep research using firecrawl and exa MCPs. Searches the web, synthesizes findings, and delivers cited reports with source attribution. Use when the user wants thorough research on any topic with evidence and citations. | `skills/SDLC/requirements/deep-research.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `market-research` | Conduct market research, competitive analysis, investor due diligence, and industry intelligence with source attribution and decision-oriented summaries. Use when the user wants market sizing, competitor comparisons, fund research, technology scans, or research that informs business decisions. | `skills/SDLC/requirements/market-research.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `prd-decomposition` | Decompose a PRD into implementation-ready EPICs and User Stories with traceable acceptance criteria, MoSCoW priority mapping, and persona-aligned story format. Use when converting a PRD into a sprint-ready backlog. | `skills/SDLC/requirements/prd-decomposition.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `product-capability` | Translate PRD intent, roadmap asks, or product discussions into an implementation-ready capability plan that exposes constraints, invariants, interfaces, and unresolved decisions before multi-service work starts. Use when the user needs an ECC-native PRD-to-SRS lane instead of vague planning prose. | `skills/SDLC/requirements/product-capability.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `stories-to-tasks` | Decompose User Stories into measurable, trackable tasks with sizing, component assignment, dependency ordering, and a definition of done. Produces a task board for sprint-level progress tracking. Use after /prd-to-epics, before /prp-plan. | `skills/SDLC/requirements/stories-to-tasks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `springboot-tdd` | Test-driven development for Spring Boot using JUnit 5, Mockito, MockMvc, Testcontainers, and JaCoCo. Use when adding features, fixing bugs, or refactoring. | `skills/SDLC/tdd/springboot-tdd.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `tdd-workflow` | Use this skill when writing new features, fixing bugs, or refactoring code. Enforces test-driven development with 80%+ coverage including unit, integration, and E2E tests. | `skills/SDLC/tdd/tdd-workflow.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `ai-regression-testing` | Regression testing strategies for AI-assisted development. Sandbox-mode API testing without database dependencies, automated bug-check workflows, and patterns to catch AI blind spots where the same model writes and reviews code. | `skills/SDLC/testing/ai-regression-testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `benchmark` | Use this skill to measure performance baselines, detect regressions before/after PRs, and compare stack alternatives. | `skills/SDLC/testing/benchmark.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `e2e-testing` | Playwright E2E testing patterns, Page Object Model, configuration, CI/CD integration, artifact management, and flaky test strategies. | `skills/SDLC/testing/e2e-testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `eval-harness` | Formal evaluation framework for Claude Code sessions implementing eval-driven development (EDD) principles | `skills/SDLC/testing/eval-harness.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security-review` | Use this skill when adding authentication, handling user input, working with secrets, creating API endpoints, or implementing payment/sensitive features. Provides comprehensive security checklist and patterns. | `skills/SDLC/testing/security-review.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `tdd-workflow` | Use this skill when writing new features, fixing bugs, or refactoring code. Enforces test-driven development with 80%+ coverage including unit, integration, and E2E tests. | `skills/SDLC/testing/tdd-workflow.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `test-execution` | Detect the test framework a repo actually uses (never assume, D10), run it via its own native TC-ID-filtered selection, and collect the JUnit XML every runner already emits natively — the procedure /test-run follows. | `skills/SDLC/testing/test-execution.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `test-plan-generation` | Generate a tool-neutral test plan with TC-NN-SS-TT identifiers traced to acceptance criteria, before any test is written — the procedure /test-plan and the qa-engineer agent both follow. | `skills/SDLC/testing/test-plan-generation.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `trace-matrix` | Render the full FR -> EPIC -> Story -> AC -> TC -> test -> result -> defect chain and fail loudly on any uncovered MUST-priority acceptance criterion, so coverage is enforced rather than decorative. | `skills/SDLC/testing/trace-matrix.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `verification-loop` | A comprehensive verification system for Claude Code sessions. | `skills/SDLC/testing/verification-loop.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `cpp-coding-standards` | C++ coding standards based on the C++ Core Guidelines (isocpp.github.io). Use when writing, reviewing, or refactoring C++ code to enforce modern, safe, and idiomatic practices. | `skills/SOFTWARE/cpp/cpp-coding-standards.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `cpp-testing` | Use only when writing/updating/fixing C++ tests, configuring GoogleTest/CTest, diagnosing failing or flaky tests, or adding coverage/sanitizers. | `skills/SOFTWARE/cpp/cpp-testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-style` | C++ Coding Style | `skills/SOFTWARE/cpp/rules/coding-style.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hooks` | C++ Hooks | `skills/SOFTWARE/cpp/rules/hooks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `patterns` | C++ Patterns | `skills/SOFTWARE/cpp/rules/patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security` | C++ Security | `skills/SOFTWARE/cpp/rules/security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `testing` | C++ Testing | `skills/SOFTWARE/cpp/rules/testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `csharp-testing` | C# Testing Patterns | `skills/SOFTWARE/csharp/csharp-testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `dotnet-patterns` | .NET Development Patterns | `skills/SOFTWARE/csharp/dotnet-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-style` | C# Coding Style | `skills/SOFTWARE/csharp/rules/coding-style.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hooks` | C# Hooks | `skills/SOFTWARE/csharp/rules/hooks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `patterns` | C# Patterns | `skills/SOFTWARE/csharp/rules/patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security` | C# Security | `skills/SOFTWARE/csharp/rules/security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `testing` | C# Testing | `skills/SOFTWARE/csharp/rules/testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-style` | Dart/Flutter Coding Style | `skills/SOFTWARE/dart/rules/coding-style.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hooks` | Dart/Flutter Hooks | `skills/SOFTWARE/dart/rules/hooks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `patterns` | Dart/Flutter Patterns | `skills/SOFTWARE/dart/rules/patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security` | Dart/Flutter Security | `skills/SOFTWARE/dart/rules/security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `testing` | Dart/Flutter Testing | `skills/SOFTWARE/dart/rules/testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `compose-multiplatform` | Compose Multiplatform and Jetpack Compose patterns for KMP projects — state management, navigation, theming, performance, and platform-specific UI. | `skills/SOFTWARE/dart-flutter/compose-multiplatform.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `dart-flutter-patterns` | Production-ready Dart and Flutter patterns covering null safety, immutable state, async composition, widget architecture, popular state management frameworks (BLoC, Riverpod, Provider), GoRouter navigation, Dio networking, Freezed code generation, and clean architecture. | `skills/SOFTWARE/dart-flutter/dart-flutter-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-style` | Dart/Flutter Coding Style | `skills/SOFTWARE/dart-flutter/rules/coding-style.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hooks` | Dart/Flutter Hooks | `skills/SOFTWARE/dart-flutter/rules/hooks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `patterns` | Dart/Flutter Patterns | `skills/SOFTWARE/dart-flutter/rules/patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security` | Dart/Flutter Security | `skills/SOFTWARE/dart-flutter/rules/security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `testing` | Dart/Flutter Testing | `skills/SOFTWARE/dart-flutter/rules/testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `golang-patterns` | Idiomatic Go patterns, best practices, and conventions for building robust, efficient, and maintainable Go applications. | `skills/SOFTWARE/golang/golang-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `golang-testing` | Go testing patterns including table-driven tests, subtests, benchmarks, fuzzing, and test coverage. Follows TDD methodology with idiomatic Go practices. | `skills/SOFTWARE/golang/golang-testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-style` | Go Coding Style | `skills/SOFTWARE/golang/rules/coding-style.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hooks` | Go Hooks | `skills/SOFTWARE/golang/rules/hooks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `patterns` | Go Patterns | `skills/SOFTWARE/golang/rules/patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security` | Go Security | `skills/SOFTWARE/golang/rules/security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `testing` | Go Testing | `skills/SOFTWARE/golang/rules/testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `docker-patterns` | Docker and Docker Compose patterns for local development, container security, networking, volume strategies, and multi-service orchestration. | `skills/SOFTWARE/infrastructure/docker-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `postgres-patterns` | PostgreSQL database patterns for query optimization, schema design, indexing, and security. Based on Supabase best practices. | `skills/SOFTWARE/infrastructure/postgres-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `java-coding-standards` | Java coding standards for Spring Boot services: naming, immutability, Optional usage, streams, exceptions, generics, and project layout. | `skills/SOFTWARE/java/java-coding-standards.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-style` | Java Coding Style | `skills/SOFTWARE/java/rules/coding-style.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hooks` | Java Hooks | `skills/SOFTWARE/java/rules/hooks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `patterns` | Java Patterns | `skills/SOFTWARE/java/rules/patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security` | Java Security | `skills/SOFTWARE/java/rules/security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `testing` | Java Testing | `skills/SOFTWARE/java/rules/testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `springboot-patterns` | Spring Boot architecture patterns, REST API design, layered services, data access, caching, async processing, and logging. Use for Java Spring Boot backend work. | `skills/SOFTWARE/java/springboot-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `springboot-security` | Spring Security best practices for authn/authz, validation, CSRF, secrets, headers, rate limiting, and dependency security in Java Spring Boot services. | `skills/SOFTWARE/java/springboot-security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `springboot-tdd` | Test-driven development for Spring Boot using JUnit 5, Mockito, MockMvc, Testcontainers, and JaCoCo. Use when adding features, fixing bugs, or refactoring. | `skills/SOFTWARE/java/springboot-tdd.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `springboot-verification` | Verification loop for Spring Boot projects: build, static analysis, tests with coverage, security scans, and diff review before release or PR. | `skills/SOFTWARE/java/springboot-verification.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `kotlin-coroutines-flows` | Kotlin Coroutines and Flow patterns for Android and KMP — structured concurrency, Flow operators, StateFlow, error handling, and testing. | `skills/SOFTWARE/kotlin/kotlin-coroutines-flows.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `kotlin-exposed-patterns` | JetBrains Exposed ORM patterns including DSL queries, DAO pattern, transactions, HikariCP connection pooling, Flyway migrations, and repository pattern. | `skills/SOFTWARE/kotlin/kotlin-exposed-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `kotlin-ktor-patterns` | Ktor server patterns including routing DSL, plugins, authentication, Koin DI, kotlinx.serialization, WebSockets, and testApplication testing. | `skills/SOFTWARE/kotlin/kotlin-ktor-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `kotlin-patterns` | Idiomatic Kotlin patterns, best practices, and conventions for building robust, efficient, and maintainable Kotlin applications with coroutines, null safety, and DSL builders. | `skills/SOFTWARE/kotlin/kotlin-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `kotlin-testing` | Kotlin testing patterns with Kotest, MockK, coroutine testing, property-based testing, and Kover coverage. Follows TDD methodology with idiomatic Kotlin practices. | `skills/SOFTWARE/kotlin/kotlin-testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-style` | Kotlin Coding Style | `skills/SOFTWARE/kotlin/rules/coding-style.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hooks` | Kotlin Hooks | `skills/SOFTWARE/kotlin/rules/hooks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `patterns` | Kotlin Patterns | `skills/SOFTWARE/kotlin/rules/patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security` | Kotlin Security | `skills/SOFTWARE/kotlin/rules/security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `testing` | Kotlin Testing | `skills/SOFTWARE/kotlin/rules/testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-style` | PHP Coding Style | `skills/SOFTWARE/php/rules/coding-style.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hooks` | PHP Hooks | `skills/SOFTWARE/php/rules/hooks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `patterns` | PHP Patterns | `skills/SOFTWARE/php/rules/patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security` | PHP Security | `skills/SOFTWARE/php/rules/security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `testing` | PHP Testing | `skills/SOFTWARE/php/rules/testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `laravel-patterns` | Laravel architecture patterns, routing/controllers, Eloquent ORM, service layers, queues, events, caching, and API resources for production apps. | `skills/SOFTWARE/php-laravel/laravel-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `laravel-security` | Laravel security best practices for authn/authz, validation, CSRF, mass assignment, file uploads, secrets, rate limiting, and secure deployment. | `skills/SOFTWARE/php-laravel/laravel-security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `laravel-tdd` | Test-driven development for Laravel with PHPUnit and Pest, factories, database testing, fakes, and coverage targets. | `skills/SOFTWARE/php-laravel/laravel-tdd.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `laravel-verification` | Verification loop for Laravel projects: env checks, linting, static analysis, tests with coverage, security scans, and deployment readiness. | `skills/SOFTWARE/php-laravel/laravel-verification.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-style` | PHP Coding Style | `skills/SOFTWARE/php-laravel/rules/coding-style.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hooks` | PHP Hooks | `skills/SOFTWARE/php-laravel/rules/hooks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `patterns` | PHP Patterns | `skills/SOFTWARE/php-laravel/rules/patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security` | PHP Security | `skills/SOFTWARE/php-laravel/rules/security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `testing` | PHP Testing | `skills/SOFTWARE/php-laravel/rules/testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `django-patterns` | Django architecture patterns, REST API design with DRF, ORM best practices, caching, signals, middleware, and production-grade Django apps. | `skills/SOFTWARE/python/django-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `django-security` | Django security best practices, authentication, authorization, CSRF protection, SQL injection prevention, XSS prevention, and secure deployment configurations. | `skills/SOFTWARE/python/django-security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `django-tdd` | Django testing strategies with pytest-django, TDD methodology, factory_boy, mocking, coverage, and testing Django REST Framework APIs. | `skills/SOFTWARE/python/django-tdd.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `django-verification` | Verification loop for Django projects: migrations, linting, tests with coverage, security scans, and deployment readiness checks before release or PR. | `skills/SOFTWARE/python/django-verification.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `python-patterns` | Pythonic idioms, PEP 8 standards, type hints, and best practices for building robust, efficient, and maintainable Python applications. | `skills/SOFTWARE/python/python-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `python-testing` | Python testing strategies using pytest, TDD methodology, fixtures, mocking, parametrization, and coverage requirements. | `skills/SOFTWARE/python/python-testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-style` | Python Coding Style | `skills/SOFTWARE/python/rules/coding-style.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hooks` | Python Hooks | `skills/SOFTWARE/python/rules/hooks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `patterns` | Python Patterns | `skills/SOFTWARE/python/rules/patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security` | Python Security | `skills/SOFTWARE/python/rules/security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `testing` | Python Testing | `skills/SOFTWARE/python/rules/testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `pytorch-patterns` | PyTorch deep learning patterns and best practices for building robust, efficient, and reproducible training pipelines, model architectures, and data loading. | `skills/SOFTWARE/pytorch/pytorch-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-style` | Rust Coding Style | `skills/SOFTWARE/rust/rules/coding-style.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hooks` | Rust Hooks | `skills/SOFTWARE/rust/rules/hooks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `patterns` | Rust Patterns | `skills/SOFTWARE/rust/rules/patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security` | Rust Security | `skills/SOFTWARE/rust/rules/security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `testing` | Rust Testing | `skills/SOFTWARE/rust/rules/testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `rust-patterns` | Idiomatic Rust patterns, ownership, error handling, traits, concurrency, and best practices for building safe, performant applications. | `skills/SOFTWARE/rust/rust-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `rust-testing` | Rust testing patterns including unit tests, integration tests, async testing, property-based testing, mocking, and coverage. Follows TDD methodology. | `skills/SOFTWARE/rust/rust-testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-style` | Swift Coding Style | `skills/SOFTWARE/swift/rules/coding-style.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hooks` | Swift Hooks | `skills/SOFTWARE/swift/rules/hooks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `patterns` | Swift Patterns | `skills/SOFTWARE/swift/rules/patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security` | Swift Security | `skills/SOFTWARE/swift/rules/security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `testing` | Swift Testing | `skills/SOFTWARE/swift/rules/testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `swift-actor-persistence` | Thread-safe data persistence in Swift using actors — in-memory cache with file-backed storage, eliminating data races by design. | `skills/SOFTWARE/swift/swift-actor-persistence.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `swift-concurrency` | Swift 6.2 Approachable Concurrency — single-threaded by default, @concurrent for explicit background offloading, isolated conformances for main actor types. | `skills/SOFTWARE/swift/swift-concurrency.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `swift-protocol-di` | Protocol-based dependency injection for testable Swift code — mock file system, network, and external APIs using focused protocols and Swift Testing. | `skills/SOFTWARE/swift/swift-protocol-di.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `bun-runtime` | Bun as runtime, package manager, bundler, and test runner. When to choose Bun vs Node, migration notes, and Vercel support. | `skills/SOFTWARE/typescript/bun-runtime.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `nestjs-patterns` | NestJS architecture patterns for modules, controllers, providers, DTO validation, guards, interceptors, config, and production-grade TypeScript backends. | `skills/SOFTWARE/typescript/nestjs-patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `nextjs-turbopack` | Next.js 16+ and Turbopack — incremental bundling, FS caching, dev speed, and when to use Turbopack vs webpack. | `skills/SOFTWARE/typescript/nextjs-turbopack.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `coding-style` | TypeScript/JavaScript Coding Style | `skills/SOFTWARE/typescript/rules/coding-style.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `hooks` | TypeScript/JavaScript Hooks | `skills/SOFTWARE/typescript/rules/hooks.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `patterns` | TypeScript/JavaScript Patterns | `skills/SOFTWARE/typescript/rules/patterns.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `security` | TypeScript/JavaScript Security | `skills/SOFTWARE/typescript/rules/security.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `testing` | TypeScript/JavaScript Testing | `skills/SOFTWARE/typescript/rules/testing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `article-writing` | Write articles, guides, blog posts, tutorials, newsletter issues, and other long-form content in a distinctive voice derived from supplied examples or brand guidance. Use when the user wants polished written content longer than a paragraph, especially when voice consistency, structure, and credibility matter. | `skills/SUPPORTING-TOOLS/content/article-writing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `brand-voice` | Build a source-derived writing style profile from real posts, essays, launch notes, docs, or site copy, then reuse that profile across content, outreach, and social workflows. Use when the user wants voice consistency without generic AI writing tropes. | `skills/SUPPORTING-TOOLS/content/brand-voice.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `cognizant-ppt` | Generate brand-compliant Cognizant PowerPoint decks from a structured content brief. Self-contained — uses python-pptx and builds slides from scratch using the brand palette extracted from a real Cognizant deck. No external template assets required. Use for one-pagers, sales decks, customer-facing presentations, internal briefings, and competitive analyses. | `skills/SUPPORTING-TOOLS/content/cognizant-ppt.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `crosspost` | Multi-platform content distribution across X, LinkedIn, Threads, and Bluesky. Adapts content per platform using content-engine patterns. Never posts identical content cross-platform. Use when the user wants to distribute content across social platforms. | `skills/SUPPORTING-TOOLS/content/crosspost.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `investor-materials` | Create and update pitch decks, one-pagers, investor memos, accelerator applications, financial models, and fundraising materials. Use when the user needs investor-facing documents, projections, use-of-funds tables, milestone plans, or materials that must stay internally consistent across multiple fundraising assets. | `skills/SUPPORTING-TOOLS/content/investor-materials.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `seo` | Audit, plan, and implement SEO improvements across technical SEO, on-page optimization, structured data, Core Web Vitals, and content strategy. Use when the user wants better search visibility, SEO remediation, schema markup, sitemap/robots work, or keyword mapping. | `skills/SUPPORTING-TOOLS/content/seo.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `codebase-onboarding` | Analyze an unfamiliar codebase and generate a structured onboarding guide with architecture map, key entry points, conventions, and a starter CLAUDE.md. Use when joining a new project or setting up Claude Code for the first time in a repo. | `skills/SUPPORTING-TOOLS/demos/codebase-onboarding.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `code-tour` | Create CodeTour `.tour` files — persona-targeted, step-by-step walkthroughs with real file and line anchors. Use for onboarding tours, architecture walkthroughs, PR tours, RCA tours, and structured "explain how this works" requests. | `skills/SUPPORTING-TOOLS/demos/code-tour.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `design-system` | Use this skill to generate or audit design systems, check visual consistency, and review PRs that touch styling. | `skills/SUPPORTING-TOOLS/design/design-system.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `frontend-design` | Create distinctive, production-grade frontend interfaces with high design quality. Use when the user asks to build web components, pages, or applications and the visual direction matters as much as the code quality. | `skills/SUPPORTING-TOOLS/design/frontend-design.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `frontend-slides` | Create stunning, animation-rich HTML presentations from scratch or by converting PowerPoint files. Use when the user wants to build a presentation, convert a PPT/PPTX to web, or create slides for a talk/pitch. Helps non-designers discover their aesthetic through visual exploration rather than abstract choices. | `skills/SUPPORTING-TOOLS/design/frontend-slides.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `manim-video` | Build reusable Manim explainers for technical concepts, graphs, system diagrams, and product walkthroughs, then hand off to the wider ECC video stack if needed. Use when the user wants a clean animated explainer rather than a generic talking-head script. | `skills/SUPPORTING-TOOLS/video/manim-video.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `marketing-video-builder` | Produce a 3-minute high-impact B2B marketing video from a natural-language brief, using real stock footage (Pexels/Pixabay — no AI-generated imagery), AI voiceover, auto-captions, and ffmpeg assembly. Use when the user wants to build a marketing video, explainer, product demo, or LinkedIn/YouTube cut from a written brief. Reusable across Cognizant AI products. | `skills/SUPPORTING-TOOLS/video/marketing-video-builder.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `remotion-video-creation` | Best practices for Remotion - Video creation in React. 29 domain-specific rules covering 3D, animations, audio, captions, charts, transitions, and more. | `skills/SUPPORTING-TOOLS/video/remotion-video-creation.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |
| `video-editing` | AI-assisted video editing workflows for cutting, structuring, and augmenting real footage. Covers the full pipeline from raw capture through FFmpeg, Remotion, ElevenLabs, fal.ai, and final polish in Descript or CapCut. Use when the user wants to edit video, cut footage, create vlogs, or build video content. | `skills/SUPPORTING-TOOLS/video/video-editing.md` | Referenced by agents/commands; manually ask Claude to read `agentic-assets/<path>` when needed. |

## Memory Bank

Claude starts every session with no recollection of prior sessions. The **memory bank** is how
AgentForge carries project context forward: a set of plain-markdown files, committed to git, that
both humans and Claude read at session start. `setup_neuroedge_agentic_tools.py` bootstraps them
(the "Memory bank bootstrap" install step). They ship as templates — fill them with real project
facts to make them useful. Distinct from the `memory` MCP server (an optional runtime key/value
store); the memory bank is the in-repo, human-readable, version-controlled layer.

There are three related layers people call "memory":

| Layer | Where | What it is |
|---|---|---|
| Instructions | `CLAUDE.md`, `AGENTS.md` (repo root) | Standing rules: how Claude should behave, routing, build/test commands. Note: `CLAUDE.md` lives at the **repo root**, not inside `.claude/`. |
| Memory bank | `docs/context/`, `docs/decisions/` | The running journal of *where the work stands* and *why decisions were made*. |
| MCP memory | `memory` / `omega-memory` server | Optional runtime store persisted outside the repo (see MCP Servers table). |

### Memory bank files

| File | Purpose | How to use |
|---|---|---|
| `docs/context/ACTIVE.md` | Current focus, recent changes, next 3 actions, blockers | Update at the start/end of each work session. |
| `docs/context/PROGRESS.md` | Done / in-progress / blocked / next | Keep the status board current as milestones move. |
| `docs/context/REPO_MAP.md` | Module map — entry points, tests, ownership | Refresh after major structure changes. |
| `docs/context/GLOSSARY.md` | Project-specific terms | Add terms as they stabilize. |
| `docs/context/OPEN_QUESTIONS.md` | Unresolved decisions | Resolve into ADRs or CLAUDE.md as answers land. |
| `docs/decisions/ADR-*.md` | Architecture Decision Records — context, decision, alternatives, consequences | Copy `ADR-0000-template.md` for each significant decision. |

### Related assets

- **`/memory-audit`** command — audit and clean up memory content.
- **`legacy-modernizer`** agent — creates the memory-bank hierarchy when onboarding a brownfield repo.
- **`legacy-modernization`** skill (`skills/SDLC/development/legacy-modernization.md`) — building a memory bank as part of safe onboarding.

### Session-start convention
The installed `CLAUDE.md` instructs Claude to read, before non-trivial work: `AGENTS.md`,
`docs/context/ACTIVE.md`, `docs/context/PROGRESS.md`, `docs/context/REPO_MAP.md`, and the nearest
subfolder `CLAUDE.md`. Keeping the memory bank current is what makes that preflight worthwhile.

## Relationship To Workflow Docs

- Use this catalog to discover available assets.
- Use `how_to_install_agentforge.md` to install and verify AgentForge readiness.
- Use `how_to_build_your_project.md` to decide which asset to run at each SDLC step, and
  for the **Agentic Automated vs Agentic Manual** mode comparison.
- Use `how_to_run_agentforge.md` for the `/agentforge` orchestrator itself (Agentic
  Automated mode) — flags, gates, and per-stage domain-plugin discovery in detail.
- Use [`fast_lane_and_defect_fixing.md`](fast_lane_and_defect_fixing.md) to choose between the full
  `/agentforge` run, the PRP fast lane, `--stage` re-entry, and `/fix` for defects.
- Use [`how_to_build_ml_model.md`](how_to_build_ml_model.md) for the `ai-ml` discipline — objective in,
  train-ready model and training code out.
- Use [`how_to_create_marketing_video.md`](how_to_create_marketing_video.md) to build a marketing video
  offline, without the portal.
- Use [`review_surplus_files_to_target.md`](review_surplus_files_to_target.md) for the packaging review —
  what ships to a target, what is surplus, and what is ignored.
- Use [`how_agentforge_manages_tokencost.md`](how_agentforge_manages_tokencost.md) for how context is
  scoped, how memory avoids re-reading the repo, and how token cost is measured — including the gaps.
- Use [`how_to_integrate_agentforge_to_external_tools.md`](how_to_integrate_agentforge_to_external_tools.md)
  to connect AgentForge to GitHub, Jira, Confluence, Zephyr or another system of record.
- Use [`incident-response.md`](incident-response.md) for the severity matrix, triage flow, comms
  templates and post-incident review when responding to a production issue.


