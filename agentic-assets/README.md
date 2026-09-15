# NeuroEdge AgentForge

Shared Claude Code assets for the NeuroEdge platform — used by both the
**NeuroEdge Web** and **NeuroEdge Device** teams for Claude-assisted development.

These assets are the reason Claude behaves consistently across both repos:
reading the same coding standards, applying the same review criteria, and
announcing exactly what it is doing before it does it.

> **Provenance & attribution.** ~80% of the skill files in this repo are derived from [Effective Claude Code (ECC)](https://github.com/affaan-m/ECC) by Affaan Mustafa, under the MIT License. Full attribution and notice text in [NOTICE.md](NOTICE.md). Per-file provenance is recorded in each skill's `origin:` frontmatter field.

---

## What's in this repo

| Folder | Contents | Installs to |
|---|---|---|
| `agents/SDLC/` | 25 general SDLC agents: code-reviewer, security-reviewer, planner, architect, tdd-guide ... | `<project>/.claude/agents/` (flat) |
| `agents/SOFTWARE/` | 17 language reviewers: python-reviewer, typescript-reviewer, cpp-reviewer ... | `<project>/.claude/agents/` (flat) |
| `skills/` | Knowledge base: SDLC, SOFTWARE, ENGINEERING, DEPLOY-TARGETS, DOMAIN, SUPPORTING-TOOLS | **Not copied** — read directly from the submodule at `agentic-assets/skills/` |
| `commands/` | 16 general slash commands: `/quality-gate`, `/prp-commit`, `/prp-plan`, `/santa-loop` ... | `<project>/.claude/commands/` |
| `scripts/hooks/` | Hook JS files: py-lint, ts-accumulate, console-warn, typecheck, commit-quality | `<project>/scripts/hooks/` |
| `health_check/` | 3-checker health verifier (hooks, skills, agents) | `<project>/health_check/` |
| `hook-config.json` | Claude Code settings (hooks + schema) — copied as `settings.json` on first run, merged on re-runs | `<project>/.claude/settings.json` |
| `settings.local.json.example` | Blank API key template — copied as `settings.local.json` on first run only | `<project>/.claude/settings.local.json` |
| `projects/web/CLAUDE.md` | Claude project instructions for NeuroEdge Web | `<project>/CLAUDE.md` (overwritten each run) |
| `projects/web/commands/` | 6 web-specific slash commands: check-device, model_training, new-use-case ... | `<project>/.claude/commands/neuroedge/` |
| `projects/device/CLAUDE.md` | Claude project instructions for NeuroEdge Device | `<project>/CLAUDE.md` (future) |
| `projects/device/commands/` | Device-specific slash commands | `<project>/.claude/commands/neuroedge/` (future) |
| `plugins/mcp-servers.json` | MCP server catalog for reference | not installed — referenced directly |

**Setup scripts** (run from the Assets repo root):

| Script | Purpose |
|---|---|
| `setup_neuroedge_agentic_tools.py` | **Primary** — patch + install in one command |
| `cleanup_neuroedge_agentic_tools.py` | Dry-run-first cleanup/switch utility for Claude and Codex AgentForge assets |
| `patch_assets.py` | Injects skill-read instructions and status blocks into commands and agents |
| `install.py` | Copies commands, hooks, agents, and health_check into a target project |

---

## Clean up or switch assistants

Cleanup is dry-run by default:

```bash
python -X utf8 cleanup_neuroedge_agentic_tools.py --project "C:\path\to\project" --mode claude
```

Apply cleanup only with `--confirm`:

```bash
python -X utf8 cleanup_neuroedge_agentic_tools.py --project "C:\path\to\project" --mode claude --remove-guidance --remove-local-state --confirm
```

Switch a Claude-installed project to Codex:

```bash
python -X utf8 cleanup_neuroedge_agentic_tools.py --project "C:\path\to\project" --mode claude --remove-guidance --remove-local-state --switch-to codex --type generic --confirm
```

Add `--remove-memory-bank` only when you intentionally want to delete `docs/context/` and `docs/decisions/` bootstrap files. By default, the cleanup preserves that project knowledge so it can carry across assistants.

---

## How to set up (first time)

### Prerequisites

**The invariant, regardless of tool: every dependency this repo needs is recorded in its
manifest.** This repo's manifest is `pyproject.toml` + `uv.lock` (no `requirements.txt`
exists here), managed via [uv](https://docs.astral.sh/uv/) — that's what's already present,
not a mandate imposed on top of it. If a project you're integrating with uses
`requirements.txt` + pip instead, the same rule applies there: update the manifest, don't
install outside of it.

```bash
uv --version          # must resolve; the venv here was created by uv 0.11.3
uv sync               # create/refresh .venv from pyproject.toml + uv.lock
uv run pytest         # run the test suite inside that venv
```

Working in this repo:

- Add a dependency with `uv add <pkg>` / `uv add --dev <pkg>` so it lands in both
  `pyproject.toml` and `uv.lock` together — installing a package without that step means
  the next `uv sync` (including in CI) removes it again, since the lock is the source of truth.
- `uv run …` resolves `.venv` automatically; plain `python`/`pip` calls bypass the lock, which
  is the thing to avoid, not the commands themselves.
- Keep `pyproject.toml` at the repo root only. uv finds the project by walking *up* from the
  working directory, so `uv add` / `uv sync` / `uv run` work from anywhere in the tree —
  including `agentforge/`. A second `pyproject.toml` under a subfolder would stop that walk
  and silently split the project into two environments.
- CI runs `uv sync --locked`, so a stale `uv.lock` fails the build instead of quietly
  re-resolving.

A reproducible, locked environment is part of the deliverable: AgentForge installs into
other people's repos, and a verifiable install starts with a verifiable environment — in
whatever manifest format that project already tracks.

### Option A — Git submodule (recommended for teams)

```bash
# Clone the project (Assets included as a submodule)
git clone --recurse-submodules <your-project-url>

# Run setup — the same product-independent assets install into every project
python -X utf8 agentic-assets/setup_neuroedge_agentic_tools.py --project .
```

First time wiring a project to Assets:
```bash
git submodule add https://github.com/cognizant/neuroedge-agenticai-assets.git agentic-assets
python -X utf8 agentic-assets/setup_neuroedge_agentic_tools.py --project .
```

### Option B — Standalone clone (Assets repo only)

```bash
git clone https://github.com/cognizant/neuroedge-agenticai-assets.git C:\Sanjeev_E\NeuroEdge_AgenticAI_Assets
python -X utf8 "C:\Sanjeev_E\NeuroEdge_AgenticAI_Assets\setup_neuroedge_agentic_tools.py" --project "C:\Sanjeev_E\NeuroEdge Web"
python -X utf8 "C:\Sanjeev_E\NeuroEdge_AgenticAI_Assets\setup_neuroedge_agentic_tools.py" --project "C:\Sanjeev_E\NeuroEdge Device"
```

### Preview before installing

```bash
python -X utf8 agentic-assets/setup_neuroedge_agentic_tools.py --project . --dry-run
```

> **Windows note:** always run with `python -X utf8` — box-drawing characters in the
> output break CP1252 terminals without it.

---

## How Claude announces itself

Every agent and command outputs a status line before acting:

```
[ NeuroEdge Assets ]  Agent: python-reviewer · Skills: python-patterns, python-testing
[ NeuroEdge Assets ]  /quality-gate · Skills: coding-standards, plankton-code-quality
```

This is injected by `patch_assets.py` into every agent and command markdown file.
You always know what is running and what skill context it has loaded.

---

## Agents catalog

Agents are sub-processes Claude can spawn to handle specialized tasks. They have
their own tool sets, skill context, and instructions. The CLAUDE.md dispatch table
in each project defines which agents fire automatically vs. on demand.

### SDLC Agents (`agents/SDLC/`)

#### Planning & Architecture

---

**`architect`** · `agents/SDLC/architect.md`

Software architecture specialist for system design, scalability, and technical decision-making.

| | |
|---|---|
| **Skills loaded** | `hexagonal-architecture`, `agentic-engineering` |
| **Tools** | Read, Grep, Glob |
| **Activated** | On demand — Claude asks: *"Want me to plan this out with `architect` before we start?"* |
| **Trigger** | Before implementing a new pipeline stage, sub-system, or platform backend |
| **What it does** | Proposes system boundaries, interface contracts, and layering strategy; produces Architecture Decision Records (ADRs); evaluates trade-offs between coupling, cohesion, and testability using hexagonal-architecture principles |
| **Benefit** | Prevents costly rewrites by getting the structure right before writing any code |

---

**`code-architect`** · `agents/SDLC/code-architect.md`

Designs feature architectures by analyzing existing codebase patterns and conventions.

| | |
|---|---|
| **Skills loaded** | None (reads codebase directly) |
| **Tools** | Read, Grep, Glob, Bash |
| **Activated** | On demand when designing a new feature with complex internal structure |
| **What it does** | Reads existing patterns, then produces concrete implementation blueprints: file list, interfaces, data flow diagram, and build order |
| **Benefit** | New features follow the same conventions as existing code — no architectural drift |

---

**`code-explorer`** · `agents/SDLC/code-explorer.md`

Deeply analyzes existing codebase features by tracing execution paths and mapping dependencies.

| | |
|---|---|
| **Skills loaded** | None (reads codebase directly) |
| **Tools** | Read, Grep, Glob, Bash |
| **Activated** | On demand for understanding an unfamiliar area of the codebase |
| **What it does** | Traces execution paths from entry point to leaf, maps architecture layers, documents all internal and external dependencies, and produces a written summary |
| **Benefit** | Makes it safe to change code you don't fully understand by surfacing all touch points first |

---

**`planner`** · `agents/SDLC/planner.md`

Expert planning specialist for complex features and refactoring.

| | |
|---|---|
| **Skills loaded** | `agentic-engineering`, `product-capability` |
| **Tools** | Read, Grep, Glob |
| **Activated** | On demand — Claude asks before any new feature implementation |
| **What it does** | Breaks the request into phases, identifies critical files, estimates risk, and produces a step-by-step plan with checkpoints |
| **Benefit** | Reduces mid-implementation surprises; the plan becomes the prompt for `/prp-implement` |

---

#### Code Review & Quality

---

**`code-reviewer`** · `agents/SDLC/code-reviewer.md`

Expert code review for quality, security, and maintainability — runs on all code changes.

| | |
|---|---|
| **Skills loaded** | `coding-standards`, `plankton-code-quality` |
| **Tools** | Read, Grep, Glob, Bash |
| **Activated** | **Automatic** — after any feature implementation completes |
| **What it does** | Reviews for naming, structure, error handling, security, complexity, and test coverage against the project's defined coding standards |
| **Benefit** | Catches issues before commit; grounded in project standards, not generic defaults |

---

**`code-simplifier`** · `agents/SDLC/code-simplifier.md`

Simplifies and refines code for clarity, consistency, and maintainability while preserving behavior.

| | |
|---|---|
| **Skills loaded** | `coding-standards`, `plankton-code-quality` |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Activated** | On demand — Claude asks: *"Want me to clean this up with `code-simplifier`?"* |
| **What it does** | Removes unnecessary abstractions, renames for clarity, consolidates duplication, and verifies behavior is unchanged via tests |
| **Benefit** | Reduces cognitive load without touching functionality |

---

**`refactor-cleaner`** · `agents/SDLC/refactor-cleaner.md`

Dead code cleanup and consolidation specialist.

| | |
|---|---|
| **Skills loaded** | `coding-standards`, `plankton-code-quality` |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Activated** | On demand — Claude asks after a working implementation |
| **What it does** | Runs analysis tools (knip, depcheck, ts-prune) to find unused exports, dead imports, and duplicate code; removes them safely with test verification |
| **Benefit** | Keeps the codebase lean; removes code that raises questions but has no answers |

---

**`type-design-analyzer`** · `agents/SDLC/type-design-analyzer.md`

Analyzes type design for encapsulation, invariant expression, usefulness, and enforcement.

| | |
|---|---|
| **Skills loaded** | None |
| **Tools** | Read, Grep, Glob, Bash |
| **Activated** | On demand when designing domain types, DTOs, or API contracts |
| **What it does** | Reviews whether types enforce their invariants, whether primitives are overused, whether unions cover all cases, and whether the type system does work the runtime otherwise has to |
| **Benefit** | Moves validation from runtime to compile time; fewer bugs from invalid state |

---

**`silent-failure-hunter`** · `agents/SDLC/silent-failure-hunter.md`

Detects silent failures, swallowed errors, bad fallbacks, and missing error propagation.

| | |
|---|---|
| **Skills loaded** | None |
| **Tools** | Read, Grep, Glob, Bash |
| **Activated** | On demand when debugging mysterious behavior with no error output |
| **What it does** | Searches for bare `except`, empty `catch`, falsy fallbacks that mask errors, futures without await, and callbacks without error handlers |
| **Benefit** | Surfaces the bugs that are hardest to find because they fail without noise |

---

#### Security & Compliance

---

**`security-reviewer`** · `agents/SDLC/security-reviewer.md`

Security vulnerability detection and remediation specialist.

| | |
|---|---|
| **Skills loaded** | `security-review` |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Activated** | **Automatic** — before opening any PR |
| **Trigger** | Any code that handles user input, authentication, API endpoints, or sensitive data |
| **What it does** | Checks for OWASP Top 10 (injection, XSS, SSRF, broken auth, sensitive data exposure), secrets in code, unsafe crypto, insecure dependencies, and missing authorization checks |
| **Benefit** | Security gate before code reaches review; catches the issues that cause breaches |

---

**`healthcare-reviewer`** · `agents/SDLC/healthcare-reviewer.md`

Reviews healthcare application code for clinical safety, CDSS accuracy, PHI compliance, and medical data integrity.

| | |
|---|---|
| **Skills loaded** | `hipaa-compliance`, `healthcare-cdss-patterns` |
| **Tools** | Read, Grep, Glob |
| **Activated** | On demand for any code touching patient data, clinical logic, or health information systems |
| **What it does** | Audits PHI handling, de-identification, audit trails, CDSS accuracy, and EMR integration patterns against HIPAA rules and clinical safety standards |
| **Benefit** | Specialized for healthcare — generic security reviewers miss clinical-specific risks |

---

#### Testing

---

**`tdd-guide`** · `agents/SDLC/tdd-guide.md`

Test-Driven Development specialist enforcing write-tests-first methodology.

| | |
|---|---|
| **Skills loaded** | `tdd-workflow` (both `SDLC/tdd/` and `SDLC/testing/`) |
| **Tools** | Read, Write, Edit, Bash, Grep |
| **Activated** | On demand — Claude asks when writing new modules |
| **What it does** | Guides red-green-refactor cycle: writes failing test first, then implementation to pass it, then refactors; ensures 80%+ coverage on new code |
| **Benefit** | Forces interface design before implementation; tests that actually test rather than just pass |

---

**`pr-test-analyzer`** · `agents/SDLC/pr-test-analyzer.md`

Reviews pull request test coverage quality and completeness.

| | |
|---|---|
| **Skills loaded** | None |
| **Tools** | Read, Grep, Glob, Bash |
| **Activated** | On demand — Claude asks when a PR has failing CI checks |
| **What it does** | Evaluates behavioral coverage (not just line coverage), checks that tests exercise real edge cases, identifies tests that can pass while the bug remains, and suggests concrete missing tests |
| **Benefit** | The difference between 80% coverage that matters and 80% that doesn't |

---

**`e2e-runner`** · `agents/SDLC/e2e-runner.md`

End-to-end testing specialist using Agent Browser (preferred) with Playwright fallback.

| | |
|---|---|
| **Skills loaded** | None |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Activated** | On demand for generating, maintaining, and running E2E tests |
| **What it does** | Writes E2E test journeys for critical user flows, quarantines flaky tests, captures screenshots/videos/traces on failure, and ensures the golden path works end-to-end |
| **Benefit** | Catches integration bugs that unit tests cannot; provides visual proof that the UI works |

---

#### Documentation

---

**`doc-updater`** · `agents/SDLC/doc-updater.md`

Documentation and codemap specialist.

| | |
|---|---|
| **Skills loaded** | None |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Activated** | On demand — Claude asks after significant API or interface changes |
| **What it does** | Runs `/update-codemaps` and `/update-docs`, generates `docs/CODEMAPS/*`, updates READMEs and guides to reflect current code |
| **Benefit** | Documentation that tracks the code, not a snapshot from six months ago |

---

**`docs-lookup`** · `agents/SDLC/docs-lookup.md`

Fetches current library documentation via Context7 MCP.

| | |
|---|---|
| **Skills loaded** | None (uses Context7 MCP tools) |
| **Tools** | Read, Grep, `mcp__context7__resolve-library-id`, `mcp__context7__query-docs` |
| **Activated** | When you ask how to use a library, framework, or API |
| **What it does** | Resolves the library ID in Context7, fetches current documentation and code examples, returns answers grounded in the real API rather than training data |
| **Benefit** | No more hallucinated API signatures — answers reflect the version you're actually using |

---

#### Performance

---

**`performance-optimizer`** · `agents/SDLC/performance-optimizer.md`

Performance analysis and optimization specialist.

| | |
|---|---|
| **Skills loaded** | `plankton-code-quality`, `cost-aware-llm-pipeline` (ENGINEERING/ai-genai) |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Activated** | **Automatic** — when a benchmark reveals a bottleneck |
| **Trigger** | Benchmark results with unexpected latency, high memory, large bundle size |
| **What it does** | Profiles hot paths, identifies algorithmic improvements, optimizes React renders, reduces bundle sizes, and improves database query plans |
| **Benefit** | Fixes the actual bottleneck rather than guessing — profiling data drives decisions |

---

#### Process & Loops

---

**`loop-operator`** · `agents/SDLC/loop-operator.md`

Manages autonomous agent loops, monitors progress, and intervenes safely when loops stall.

| | |
|---|---|
| **Skills loaded** | None |
| **Tools** | Read, Grep, Glob, Bash, Edit |
| **Activated** | On demand — Claude asks when a long benchmark or training run is needed |
| **What it does** | Starts and monitors long-running task loops; detects stalls, infinite loops, and runaway costs; intervenes with corrective action or graceful stop |
| **Benefit** | Long tasks complete reliably without burning tokens on a stuck loop |

---

**`harness-optimizer`** · `agents/SDLC/harness-optimizer.md`

Analyzes and improves the local agent harness configuration for reliability, cost, and throughput.

| | |
|---|---|
| **Skills loaded** | None |
| **Tools** | Read, Grep, Glob, Bash, Edit |
| **Activated** | On demand when agent behavior feels inconsistent or expensive |
| **What it does** | Reviews `settings.json`, hook configs, and agent definitions for misconfiguration; suggests allowlist changes to reduce permission prompts; recommends model routing improvements |
| **Benefit** | Less friction from prompts; lower cost from smarter routing |

---

**`chief-of-staff`** · `agents/SDLC/chief-of-staff.md`

Personal communication triage across email, Slack, LINE, and Messenger.

| | |
|---|---|
| **Skills loaded** | None |
| **Tools** | Read, Grep, Glob, Bash, Edit, Write |
| **Activated** | On demand when managing multi-channel communication workflows |
| **What it does** | Classifies messages into 4 tiers (skip / info_only / meeting_info / action_required), generates draft replies, and enforces post-send follow-through via hooks |
| **Benefit** | Zero-inbox discipline across channels; nothing falls through the cracks |

---

**`seo-specialist`** · `agents/SDLC/seo-specialist.md`

SEO specialist for technical audits, on-page optimization, structured data, and Core Web Vitals.

| | |
|---|---|
| **Skills loaded** | `seo` |
| **Tools** | Read, Grep, Glob, Bash, WebSearch, WebFetch |
| **Activated** | On demand for site audits, meta tag reviews, schema markup, sitemap and robots issues |
| **What it does** | Audits technical SEO (crawlability, indexing, canonicals), on-page factors (title, H1, meta), structured data (JSON-LD), Core Web Vitals, and content/keyword mapping |
| **Benefit** | Catches SEO regressions before deploy; improves organic visibility |

---

#### GAN Harness (Three-Agent Validation Loop)

These three agents work together in a Planner → Generator → Evaluator loop, invoked via `/gan-build`.
Use when agent-generated outputs need iterative validation before being trusted.

---

**`gan-planner`** · `agents/ENGINEERING/ai-genai/gan-planner.md`

Expands a one-line prompt into a full product specification with features, sprints, and evaluation criteria.

| | |
|---|---|
| **Skills loaded** | `agentic-engineering`, `product-capability` |
| **Tools** | Read, Write, Grep, Glob |
| **Activated** | As step 1 of `/gan-build` |
| **What it does** | Interprets the build brief, researches the codebase, produces a full product spec with 12–16 features, sprint groupings, and explicit success criteria that the Evaluator will score against |
| **Benefit** | Generator has a clear spec; Evaluator has objective rubric — no ambiguity about "done" |

---

**`gan-generator`** · `agents/ENGINEERING/ai-genai/gan-generator.md`

Implements features according to the spec, reads evaluator feedback, and iterates until quality threshold is met.

| | |
|---|---|
| **Skills loaded** | `coding-standards`, `agentic-engineering` |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Activated** | As step 2 of `/gan-build`, and again after each Evaluator round |
| **What it does** | Implements each feature from the planner spec, then reads the evaluator's critique and makes targeted fixes — up to 3 rounds or until the score threshold is met |
| **Benefit** | Iterative refinement within the loop; output quality improves each round |

---

**`gan-evaluator`** · `agents/ENGINEERING/ai-genai/gan-evaluator.md`

Tests the live running application via Playwright, scores against rubric, and provides actionable feedback.

| | |
|---|---|
| **Skills loaded** | `verification-loop`, `ai-regression-testing` |
| **Tools** | Read, Write, Bash, Grep, Glob |
| **Activated** | As step 3 of `/gan-build`, after each Generator round |
| **What it does** | Runs the app in Playwright, exercises each feature from the planner spec, scores against the rubric (pass/fail per criterion), and writes a structured critique the Generator can act on |
| **Benefit** | Objective, automated QA within the build loop — no human needed for each round |

---

### SOFTWARE Agents (`agents/SOFTWARE/`)

Language-specific reviewers and build resolvers. Each reviewer reads skill files containing
idiomatic patterns and testing conventions for that language before reviewing.

#### Language Reviewers

| Agent | File | Skills loaded | Activated when | What it does |
|---|---|---|---|---|
| `python-reviewer` | `SOFTWARE/python-reviewer.md` | `python-patterns`, `python-testing` | **Auto** — any `.py` file edited | PEP 8, type hints, Pythonic idioms, security, performance, pytest conventions |
| `typescript-reviewer` | `SOFTWARE/typescript-reviewer.md` | `coding-style`, `nestjs-patterns` | **Auto** — any `.ts`/`.tsx` file edited | Type safety, async correctness, null checks, NestJS patterns, Node/web security |
| `cpp-reviewer` | `SOFTWARE/cpp-reviewer.md` | `cpp-coding-standards`, `cpp-testing` | **Auto** — any `.cpp`/`.cu` file edited | Memory safety, RAII, modern C++17/20 idioms, concurrency, UB detection |
| `go-reviewer` | `SOFTWARE/go-reviewer.md` | `golang-patterns`, `golang-testing` | **Auto** — any `.go` file edited | Idiomatic Go, goroutine safety, error wrapping, interface design, table-driven tests |
| `java-reviewer` | `SOFTWARE/java-reviewer.md` | `java-coding-standards`, `springboot-patterns` | **Auto** — any `.java` file edited | Spring Boot layering, JPA patterns, transaction boundaries, security, concurrency |
| `kotlin-reviewer` | `SOFTWARE/kotlin-reviewer.md` | `kotlin-patterns`, `kotlin-testing` | **Auto** — any `.kt` file edited | Coroutine safety, Compose best practices, null safety, clean architecture |
| `rust-reviewer` | `SOFTWARE/rust-reviewer.md` | `rust-patterns`, `rust-testing` | **Auto** — any `.rs` file edited | Ownership, lifetimes, unsafe usage, error propagation, idiomatic patterns |
| `csharp-reviewer` | `SOFTWARE/csharp-reviewer.md` | None (built-in .NET knowledge) | **Auto** — any `.cs` file edited | .NET conventions, async/await patterns, nullable reference types, security |
| `flutter-reviewer` | `SOFTWARE/flutter-reviewer.md` | None (built-in Flutter knowledge) | On demand — any Flutter/Dart code review | Widget best practices, state management patterns, accessibility, clean architecture |
| `database-reviewer` | `SOFTWARE/database-reviewer.md` | `postgres-patterns` | **Auto** — any SQL schema or migration edited | PostgreSQL query optimization, RLS policies, schema design, Supabase best practices |

#### Build Resolvers

Build resolvers activate **automatically on any build or test failure**. They make minimal,
surgical fixes — no architectural edits, no refactoring. Goal: get the build green fast.

| Agent | File | Skills loaded | Fixes |
|---|---|---|---|
| `build-error-resolver` | `SDLC/build-error-resolver.md` | `deployment-patterns` | TypeScript, general build errors |
| `pytorch-build-resolver` | `SOFTWARE/pytorch-build-resolver.md` | `pytorch-patterns` | Tensor shape mismatches, CUDA errors, gradient issues, DataLoader problems |
| `cpp-build-resolver` | `SOFTWARE/cpp-build-resolver.md` | None | CMake, linker errors, template instantiation failures |
| `java-build-resolver` | `SOFTWARE/java-build-resolver.md` | None | Maven/Gradle errors, annotation processor failures |
| `kotlin-build-resolver` | `SOFTWARE/kotlin-build-resolver.md` | None | Kotlin/Gradle compilation errors, KSP issues |
| `rust-build-resolver` | `SOFTWARE/rust-build-resolver.md` | None | Cargo build errors, borrow checker violations, lifetime errors |
| `go-build-resolver` | `SOFTWARE/go-build-resolver.md` | None | `go build`, `go vet`, linter warnings |
| `dart-build-resolver` | `SOFTWARE/dart-build-resolver.md` | None | `dart analyze`, Flutter failures, pub conflicts, build_runner issues |

---

## Commands catalog

Commands are slash commands you invoke directly. Each command reads skill files before
executing, grounding its output in project standards.

Invoke any command by typing it in Claude Code, or Claude will invoke the right one
at the appropriate workflow step.

### SDLC / General Commands (`commands/`)

#### Orchestrating a project with `/agentforge`

---

**`/agentforge`** · `commands/agentforge.md`

Orchestrates a project through the SDLC end to end, sequencing existing role agents
and persisting state to `run.json` after every transition.

| | |
|---|---|
| **Skills loaded** | `agentic-engineering`, `autonomous-loops` (ENGINEERING/ai-genai) |
| **When to use** | Starting a feature or project large enough that the sequence matters, or returning after a break and not knowing where things stand |
| **What it does** | Walks the S0–S17 stage graph (`run_state.STAGE_SEQUENCE`), spawning each stage's role agent (`legacy-modernizer → researcher → product-manager → epic-writer → task-writer → project-manager → qa-engineer → architect → developer → … → team-lead → devops`), and stops at each hard gate for human approval: S2 PRD, S5 sprint plan, S6 test plan, S7 HLD + LLD (each approved by a human architect, ADR-0013), and S13 PR review (tied to `gh pr create`, no override). `--stage <id>` joins the pipeline at any already-wired stage instead of starting at S0 — useful if you already have a PRD, epics, or a task board from outside the orchestrator. `--dry-run` previews the remaining sequence with zero side effects. `--status`/`--resume` re-orient or recover after a session break |
| **Output** | One objective folder, `neuroedge/docs/project_related/<objective-slug>/` (the docs root may differ per target): `03-execution-plan/run.json` + `gates.json` (resumable state and the approval ledger), plus each stage's artifact — `02-project-plan/PRD.md`, the epics and task board, `03-execution-plan/sprint-NN.json`, `05-quality/test-plan.md`, `04-development/hld.md` + `lld.md`, `05-quality/traceability.md` |
| **Benefit** | One command carries a multi-day run forward; you're interrupted only when a gate genuinely requires a decision |

Full walkthrough, the gate model, and a timed-onboarding checklist:
[`docs/guides/how_to_run_agentforge.html`](docs/guides/how_to_run_agentforge.html).

---

**`/prp-prd`** · `commands/prp-prd.md`

Interactive product requirements document generator.

| | |
|---|---|
| **Skills loaded** | `product-capability` |
| **When to use** | Before starting a new sub-system, feature area, or significant capability |
| **What it does** | Eight-phase PRD generation: initiate → stakeholder goals → grounding research → generate → validate → finalize. Produces a structured PRD saved to `.claude/PRPs/prds/` |
| **Output** | A PRD document ready to hand to `/prp-plan` |
| **Benefit** | Forces clarity on what you're building before writing any code |

---

**`/prp-plan`** · `commands/prp-plan.md`

Comprehensive feature implementation planner with codebase analysis.

| | |
|---|---|
| **Skills loaded** | `agentic-engineering`, `product-capability` |
| **When to use** | Before implementing any non-trivial feature |
| **What it does** | Eight-phase plan: analyze codebase → map patterns → design solution → identify risks → sequence steps → write plan. Saved to `.claude/PRPs/plans/` |
| **Output** | A phased implementation plan with file list and validation checkpoints |
| **Benefit** | Catches design problems before implementation; plan becomes the input to `/prp-implement` |

---

**`/prp-implement`** · `commands/prp-implement.md`

Executes an implementation plan step-by-step with validation loops.

| | |
|---|---|
| **Skills loaded** | `agentic-engineering`, `coding-standards` |
| **When to use** | After `/prp-plan` produces a plan |
| **What it does** | Reads the plan, implements each phase, runs 5 validation levels per phase (static analysis → unit tests → build → integration → edge cases), and pauses for human review at defined checkpoints |
| **Benefit** | Structured execution with automatic validation — prevents "works locally, breaks in CI" |

---

**`/prp-commit`** · `commands/prp-commit.md`

Smart staged commit with natural-language intent and conventional commit messages.

| | |
|---|---|
| **Skills loaded** | `git-workflow` |
| **When to use** | Any time you're ready to commit |
| **What it does** | Reads your staged diff, interprets intent (fix / feat / refactor / docs), generates a conventional commit message, checks for secrets and `console.log`, and commits |
| **Benefit** | Clean git history without manual commit message writing |

---

**`/prp-pr`** · `commands/prp-pr.md`

Creates a GitHub PR with push, template discovery, and change summary.

| | |
|---|---|
| **Skills loaded** | `git-workflow` |
| **When to use** | After committing — when you're ready to open a PR |
| **What it does** | Finds unpushed commits, pushes the branch, discovers PR templates, generates a change summary, and opens the PR via `gh` CLI |
| **Benefit** | One command from committed to PR; no forgetting to push or fill in the template |

---

#### Quality & Testing

---

**`/quality-gate`** · `commands/quality-gate.md`

Pre-commit lint, format, and type checking.

| | |
|---|---|
| **Skills loaded** | `coding-standards`, `plankton-code-quality` |
| **When to use** | Before any commit; Claude runs this automatically before PRs |
| **What it does** | Runs ruff (Python), ESLint + Biome (TypeScript), tsc (type-check), and any project-specific linters; reports all failures before you commit |
| **Benefit** | Nothing lands in git that fails the linter — CI is green before you push |

---

**`/test-coverage`** · `commands/test-coverage.md`

Test coverage analysis and missing test generation.

| | |
|---|---|
| **Skills loaded** | `tdd-workflow`, `verification-loop` |
| **When to use** | After writing or modifying code; Claude runs this after implementations |
| **What it does** | Runs the test suite with coverage, identifies uncovered lines and branches, writes missing tests to reach the 80% target, verifies they pass |
| **Benefit** | Coverage that closes actual gaps, not synthetic tests that inflate numbers |

---

**`/santa-loop`** · `commands/santa-loop.md`

Dual adversarial review: two independent Claude instances must both approve before code ships.

| | |
|---|---|
| **Skills loaded** | `verification-loop`, `ai-regression-testing` |
| **When to use** | Critical paths only — model dispatch, YAML validation, auth logic, payment flows |
| **What it does** | Spawns two independent reviewers with different prompts, collects their critiques, runs a convergence loop (up to 3 rounds), and only approves when both reviewers agree |
| **Benefit** | A single reviewer can miss subtle bugs; dual adversarial review catches the second-order issues |

---

#### Autonomous Loops

---

**`/loop-start`** · `commands/loop-start.md`

Starts a managed long-running task loop with safety defaults.

| | |
|---|---|
| **Skills loaded** | None |
| **When to use** | Benchmark runs, iterative training, multi-step data pipelines — Claude asks before launching |
| **What it does** | Sets up the loop with a cost cap, iteration limit, and stall detection; delegates to `loop-operator` agent for monitoring |
| **Benefit** | Long tasks complete reliably; the loop stops cleanly if something goes wrong |

---

**`/loop-status`** · `commands/loop-status.md`

Inspects loop state, progress, and failure signals.

| | |
|---|---|
| **Skills loaded** | None |
| **When to use** | While a `/loop-start` loop is running |
| **What it does** | Reads loop metadata, reports current phase, iteration count, cost so far, and any failure signals; optional `--watch` mode for live updates |
| **Benefit** | Visibility into what a long-running loop is doing without interrupting it |

---

#### GAN Harness

---

**`/gan-build`** · `commands/ENGINEERING/ai-genai/gan-build.md`

Orchestrates the Planner → Generator → Evaluator three-agent build loop.

| | |
|---|---|
| **Skills loaded** | `autonomous-loops`, `continuous-agent-loop` (ENGINEERING/ai-genai) |
| **When to use** | When you need iterative validation of a complex output (report, YAML, UI, analysis) |
| **What it does** | Starts `gan-planner` to write the spec, then alternates between `gan-generator` (implements) and `gan-evaluator` (tests and scores) for up to N rounds or until score threshold is met |
| **Benefit** | Self-improving output loop — quality guaranteed before you see the result |

---

#### Model & Session Management

---

**`/model-route`** · `commands/ENGINEERING/ai-genai/model-route.md`

Chooses the optimal Claude model for the current task.

| | |
|---|---|
| **Skills loaded** | `cost-aware-llm-pipeline` (ENGINEERING/ai-genai) |
| **When to use** | Before starting an expensive task, or when cost matters |
| **What it does** | Analyzes the task type and complexity, recommends Haiku (simple) / Sonnet (standard) / Opus (complex reasoning), and explains the cost-quality trade-off |
| **Benefit** | Spend Opus tokens on architecture decisions, not on file formatting |

---

**`/learn-eval`** · `commands/learn-eval.md`

Extracts reusable patterns from the current session into project memory.

| | |
|---|---|
| **Skills loaded** | `continuous-learning-v2`, `eval-harness` |
| **When to use** | End of any productive session where you solved something non-obvious |
| **What it does** | Reviews the conversation, extracts patterns worth keeping (quality-gated), classifies them as Save / Improve / Absorb / Drop, and writes them to memory |
| **Benefit** | Knowledge from today's session improves Claude's behavior in all future sessions |

---

#### Utilities

---

**`/pm2`** · `commands/pm2.md`

Auto-detects services and generates a PM2 ecosystem config.

| | |
|---|---|
| **Skills loaded** | None |
| **When to use** | Setting up process management for a multi-service project |
| **What it does** | Scans the project for Node, Python, and Go services; generates `ecosystem.config.cjs` with correct start commands, watch paths, and env vars |
| **Benefit** | All services start and restart consistently; no manual process management |

---

**`/promote`** · `commands/promote.md`

Promotes project-scoped instincts to global continuous learning.

| | |
|---|---|
| **Skills loaded** | None |
| **When to use** | When a pattern learned in this project is useful across all projects |
| **What it does** | Reads project-level memory entries, evaluates which are generalizable, and writes them to global `~/.claude/` memory |
| **Benefit** | Don't re-discover the same thing in every project |

---

**`/eval`** · `commands/eval.md`

Legacy shim for the eval-harness skill.

| | |
|---|---|
| **Skills loaded** | None (delegates to skill) |
| **When to use** | Backward compatibility — prefer `/learn-eval` for new sessions |

---

### NeuroEdge-Specific Commands (`commands/neuroedge/`)

These commands are specific to the NeuroEdge Web project. They install to
`.claude/commands/neuroedge/` and are updated by the plugin install scripts in each
`src/` module.

---

**`/neuroedge/new-use-case`** · `commands/neuroedge/new-use-case.md`

Creates a validated use case YAML from a natural language description.

| | |
|---|---|
| **Skills loaded** | None |
| **When to use** | When a user describes a new edge AI deployment in plain English |
| **Invoke** | `/neuroedge/new-use-case PPE detection on shop floor, Jetson Orin Nano, 25 FPS` |
| **What it does** | Extracts platform, task, FPS, camera, and model family from the prompt; asks one consolidated question for anything it can't infer; validates against the JSON schema; writes `use_cases/<name>.yaml` |
| **Output** | A validated YAML ready for `/neuroedge/check-device` |
| **Benefit** | Removes YAML authoring from the developer; the schema is always satisfied |

---

**`/neuroedge/check-device`** · `commands/neuroedge/check-device.md`

Assesses hardware capability for a use case (Part 1 of the NeuroEdge pipeline).

| | |
|---|---|
| **Skills loaded** | None |
| **When to use** | After defining a use case, or when assessing existing hardware |
| **Invoke** | `/neuroedge/check-device for the bottle-fill use case` |
| **What it does** | Resolves the use case, detects hardware via the appropriate platform agent (CpuAgent / NvidiaGpuAgent / JetsonAgent / QualcommEdgeAgent / RPiAgent), runs a YOLO benchmark, prints a model fit table, and saves `CapabilityManifest` to `data/output/manifests/` |
| **Output** | `capability_manifest.json` — required input for Part 2 |
| **Benefit** | Tells you exactly which YOLO variant fits your hardware before training |

---

**`/neuroedge/model_device_evaluate`** · `commands/neuroedge/model_device_evaluate.md`

Benchmarks any ML model on any target platform.

| | |
|---|---|
| **Skills loaded** | None |
| **When to use** | When evaluating model speed, latency, or throughput before committing to a model family |
| **Invoke** | `/neuroedge/model_device_evaluate yolov8n on jetson orin nano` |
| **What it does** | Looks up the model in the registry, selects the best backend for the platform, runs warmup + timed inference loop, projects target-platform performance for stub platforms (Jetson, Qualcomm, RPi), saves JSON to `data/output/benchmarks/` |
| **Output** | `benchmark_<model>_<platform>_<backend>.json` |
| **Benefit** | Data-driven model selection before any training investment |

---

**`/neuroedge/model_training`** · `commands/neuroedge/model_training.md`

Trains a model for a use case with full observability (Part 2 of the NeuroEdge pipeline).

| | |
|---|---|
| **Skills loaded** | None |
| **When to use** | After device capability assessment; when you're ready to train |
| **Invoke** | `/neuroedge/model_training use_cases/ppe_shopfloor_jetson.yaml` |
| **What it does** | Resolves the use case, checks data directory and CapabilityManifest, selects the correct trainer (YOLOTrainer / PyTorchTrainer / TimeSeriesTrainer), runs training with MLflow + TensorBoard + JSON logging, saves `ModelArtifact` |
| **Output** | `model_artifact.json`, trained weights, MLflow runs, TensorBoard events |
| **Benefit** | One command covers the full training pipeline; pauses cleanly if labeling is required |

---

**`/neuroedge/health_check`** · `commands/neuroedge/health_check.md`

Verifies that all NeuroEdge AgentForge assets are correctly installed.

| | |
|---|---|
| **Skills loaded** | None |
| **When to use** | After first setup; after any asset update; when something feels wrong |
| **Invoke** | `/neuroedge/health_check` or `make health-check` |
| **What it does** | Runs 3 checkers: (1) hooks present in `settings.json`, (2) skill files readable from `agentic-assets/skills/`, (3) agents installed in `.claude/agents/`. Prints PASS / WARN / FAIL per check |
| **Benefit** | Definitive answer to "is my setup correct?" in seconds |

---

**`/neuroedge/e2e_web_test`** · `commands/neuroedge/e2e_web_test.md`

End-to-end test of the NeuroEdge web portal (backend + frontend + nginx + Playwright).

| | |
|---|---|
| **Skills loaded** | None |
| **When to use** | Before PR; after infrastructure changes; when verifying the golden path |
| **Invoke** | `/neuroedge/e2e_web_test` |
| **What it does** | Verifies backend health, frontend build, nginx routing, then runs Playwright smoke tests against the full portal; captures screenshots on failure; hands off browser for manual inspection |
| **Benefit** | Full-stack confidence before merging — not just "it compiles" |

---

## Skills knowledge base (`skills/`)

Skills are markdown reference files that agents and commands read before acting.
They encode project conventions, language patterns, domain knowledge, and
architectural principles — grounding Claude's output in your specific standards
rather than generic defaults.

Skills are **not copied** into the project. Agents read them directly from
`agentic-assets/skills/` via the submodule path, so they always reflect the
latest version in the Assets repo.

### Reading skills manually

```bash
# Ask Claude to apply a specific skill
"Before refactoring, read agentic-assets/skills/SDLC/development/hexagonal-architecture.md"

# Or reference a skill area
"Check the deployment patterns before suggesting how to structure this service"
```

### Skills directory

```
skills/
├── SDLC/
│   ├── development/
│   │   ├── agentic-engineering.md          # Building reliable multi-agent systems
│   │   ├── coding-standards.md             # Project-wide code quality rules
│   │   ├── continuous-learning-v2.md       # Session pattern extraction and memory
│   │   ├── git-workflow.md                 # Commit conventions and branching rules
│   │   ├── hexagonal-architecture.md       # Ports-and-adapters system design
│   │   ├── plankton-code-quality.md        # Deep code quality heuristics
│   │   ├── product-capability.md           # Product thinking and requirements
│   │   ├── api-design.md                   # REST / GraphQL API design principles
│   │   ├── frontend-backend-patterns.md    # Full-stack interaction patterns
│   │   ├── mcp-patterns.md                 # MCP server and tool design
│   │   └── prompt-optimizer.md             # Writing effective prompts
│   ├── deployment/
│   │   ├── deployment-patterns.md          # Reliable service deployment
│   │   ├── database-migrations.md          # Safe schema migration patterns
│   │   ├── canary-watching.md              # Progressive rollout monitoring
│   │   └── docker-patterns.md              # Container best practices
│   ├── testing/
│   │   ├── ai-regression-testing.md        # LLM output regression testing
│   │   ├── benchmarking.md                 # Performance benchmark methodology
│   │   ├── e2e-testing.md                  # End-to-end test patterns
│   │   ├── eval-harness.md                 # Evaluation harness design
│   │   ├── security-review.md              # Security audit checklist (OWASP Top 10)
│   │   ├── tdd-workflow.md                 # Test-driven development workflow
│   │   └── verification-loop.md            # Output verification loop patterns
│   ├── requirements/
│   │   ├── product-capability.md           # Feature definition and PRD structure
│   │   ├── deep-research.md                # Technical research methodology
│   │   └── market-research.md              # Market and competitive analysis
│   └── tdd/
│       ├── tdd-workflow.md                 # TDD cycle (red-green-refactor)
│       └── springboot-tdd.md               # Spring Boot specific TDD patterns
│
├── ENGINEERING/                            # Discipline packs (ADR-0010) — peer to SOFTWARE/
│   └── ai-genai/                           # AI/GenAI/Agentic discipline pack (ADR-0011)
│       ├── manifest.md                     # Discipline manifest — reviewers, skills, artifacts
│       ├── mcp-server-patterns.md          # MCP server design (moved from SDLC/development/)
│       ├── autonomous-loops.md             # Safe autonomous task loops (moved)
│       ├── continuous-agent-loop.md        # Continuous GAN-style improvement loops (moved)
│       └── cost-aware-llm-pipeline.md      # LLM cost optimization patterns (moved from SDLC/deployment/)
│
├── SOFTWARE/
│   ├── python/
│   │   ├── python-patterns.md              # Pythonic idioms, PEP 8, type hints
│   │   └── python-testing.md              # pytest, fixtures, parametrize patterns
│   ├── typescript/
│   │   ├── rules/coding-style.md           # TypeScript style rules
│   │   └── nestjs-patterns.md              # NestJS module, controller, service patterns
│   ├── cpp/
│   │   ├── cpp-coding-standards.md         # Modern C++17/20, RAII, smart pointers
│   │   └── cpp-testing.md                  # Google Test, CMock patterns
│   ├── golang/
│   │   ├── golang-patterns.md              # Idiomatic Go, error handling
│   │   └── golang-testing.md               # Table-driven tests, testify
│   ├── java/
│   │   ├── java-coding-standards.md        # Clean Code, SOLID in Java
│   │   └── springboot-patterns.md          # Spring Boot layering and JPA
│   ├── kotlin/
│   │   ├── kotlin-patterns.md              # Coroutines, data classes, sealed classes
│   │   └── kotlin-testing.md               # Kotest, MockK patterns
│   ├── rust/
│   │   ├── rust-patterns.md                # Ownership, traits, error handling
│   │   └── rust-testing.md                 # Rust test module, cargo test
│   ├── pytorch/
│   │   └── pytorch-patterns.md             # Tensor ops, training loops, ONNX export
│   └── infrastructure/
│       └── postgres-patterns.md            # PostgreSQL queries, RLS, indexing
│
├── DEPLOY-TARGETS/
│   ├── Capabilities/
│   │   ├── cpu_only/                       # CPU model matrix and setup guide
│   │   └── nvidia_gpu/                     # CUDA setup and GPU model matrix
│   ├── nvidia-jetson/                      # TensorRT optimization, Jetson deployment
│   ├── qualcomm/                           # QNN deployment, Qualcomm AI Hub, SNPE
│   ├── raspberry-pi/                       # ARM optimization, RPi deployment
│   ├── cloud-aws/                          # AWS deployment patterns
│   └── foundation-models-on-device.md      # On-device LLM deployment patterns
│
├── DOMAIN/
│   ├── healthcare/
│   │   ├── hipaa-compliance.md             # PHI handling, audit trails, de-identification
│   │   ├── healthcare-cdss-patterns.md     # Clinical decision support patterns
│   │   ├── emr-patterns.md                 # EMR/EHR integration patterns
│   │   └── phi-compliance.md              # Protected health information rules
│   └── retail/
│       └── inventory-management.md         # Inventory domain patterns
│
└── SUPPORTING-TOOLS/
    ├── content/
    │   ├── seo.md                          # Technical SEO checklist and patterns
    │   ├── article-writing.md              # Technical article structure
    │   ├── brand-voice.md                  # Brand tone and voice guidelines
    │   └── crossposting.md                 # Multi-platform content distribution
    ├── design/
    │   ├── design-systems.md               # Component and token design systems
    │   └── frontend-design.md              # UI design principles
    └── demos/
        ├── code-tours.md                   # Interactive code tour creation
        └── codebase-onboarding.md          # New developer onboarding patterns
```

---

## Hooks (auto-enforced)

Hooks are shell scripts that fire automatically at specific Claude Code lifecycle
events. They are defined in `hook-config.json` and installed to `.claude/settings.json`.
Claude cannot bypass them — fix the underlying cause when a hook blocks an action.

### PreToolUse — fire before the tool call

| Hook ID | Trigger | What it enforces |
|---|---|---|
| `pre:bash:block-no-verify` | Any `Bash` tool call | Blocks `--no-verify` and `--no-gpg-sign` flags — fix the commit hook, don't skip it |
| `pre:bash:commit-quality` | Any `Bash` tool call | Runs ruff on staged `.py` files; checks staged `.ts`/`.js` for `console.log` before commit |

### PostToolUse — fire after the tool call

| Hook ID | Trigger | What it does |
|---|---|---|
| `post:edit:py-lint` | After any `Edit` or `Write` on a `.py` file | Runs ruff on the edited file; output prompts Claude to invoke `python-reviewer` if issues found |
| `post:edit:ts-accumulate` | After any `Edit` or `Write` on a `.ts`/`.tsx` file | Accumulates edited TypeScript paths for batch typecheck at session end |
| `post:edit:console-warn` | After any `Edit` or `Write` on a `.ts`/`.tsx`/`.js` file | Warns Claude when `console.log` appears in the edited file |

### Stop — fire when Claude finishes responding

| Hook ID | Trigger | What it does |
|---|---|---|
| `stop:typecheck` | End of any response where TypeScript files were edited | Runs `tsc --noEmit` on all accumulated `.ts`/`.tsx` files; type errors are surfaced before the session ends |

---

## Skill → agent/command wiring

All wiring is defined in `patch_assets.py`. When you run setup, `patch_assets.py`
injects a `## NeuroEdge Assets` block into each agent and command file, instructing
Claude to read the linked skills before acting.

```
Agent file → "Begin your response with: [ NeuroEdge Assets ]  Agent: <name> · Skills: <x>, <y>"
             "Read these skill files before starting: agentic-assets/skills/..."

Command file → "At the start output: [ NeuroEdge Assets ]  /<name> · Skills: <x>, <y>"
               "Then read these skill files before executing: agentic-assets/skills/..."
```

**Complete wiring map:**

| Agent / Command | Skills |
|---|---|
| `python-reviewer` | `SOFTWARE/python/python-patterns`, `SOFTWARE/python/python-testing` |
| `typescript-reviewer` | `SOFTWARE/typescript/rules/coding-style`, `SOFTWARE/typescript/nestjs-patterns` |
| `cpp-reviewer` | `SOFTWARE/cpp/cpp-coding-standards`, `SOFTWARE/cpp/cpp-testing` |
| `go-reviewer` | `SOFTWARE/golang/golang-patterns`, `SOFTWARE/golang/golang-testing` |
| `java-reviewer` | `SOFTWARE/java/java-coding-standards`, `SOFTWARE/java/springboot-patterns` |
| `kotlin-reviewer` | `SOFTWARE/kotlin/kotlin-patterns`, `SOFTWARE/kotlin/kotlin-testing` |
| `rust-reviewer` | `SOFTWARE/rust/rust-patterns`, `SOFTWARE/rust/rust-testing` |
| `code-reviewer` | `SDLC/development/coding-standards`, `SDLC/development/plankton-code-quality` |
| `security-reviewer` | `SDLC/testing/security-review` |
| `tdd-guide` | `SDLC/tdd/tdd-workflow`, `SDLC/testing/tdd-workflow` |
| `architect` | `SDLC/development/hexagonal-architecture`, `SDLC/development/agentic-engineering` |
| `planner` | `SDLC/development/agentic-engineering`, `SDLC/requirements/product-capability` |
| `performance-optimizer` | `SDLC/development/plankton-code-quality`, `ENGINEERING/ai-genai/cost-aware-llm-pipeline` |
| `refactor-cleaner` | `SDLC/development/coding-standards`, `SDLC/development/plankton-code-quality` |
| `code-simplifier` | `SDLC/development/coding-standards`, `SDLC/development/plankton-code-quality` |
| `build-error-resolver` | `SDLC/deployment/deployment-patterns` |
| `pytorch-build-resolver` | `SOFTWARE/pytorch/pytorch-patterns` |
| `database-reviewer` | `SOFTWARE/infrastructure/postgres-patterns` |
| `healthcare-reviewer` | `DOMAIN/healthcare/hipaa-compliance`, `DOMAIN/healthcare/healthcare-cdss-patterns` |
| `seo-specialist` | `SUPPORTING-TOOLS/content/seo` |
| `gan-planner` | `SDLC/development/agentic-engineering`, `SDLC/requirements/product-capability` |
| `gan-generator` | `SDLC/development/coding-standards`, `SDLC/development/agentic-engineering` |
| `gan-evaluator` | `SDLC/testing/verification-loop`, `SDLC/testing/ai-regression-testing` |
| `/quality-gate` | `SDLC/development/coding-standards`, `SDLC/development/plankton-code-quality` |
| `/prp-commit` | `SDLC/development/git-workflow` |
| `/prp-plan` | `SDLC/development/agentic-engineering`, `SDLC/requirements/product-capability` |
| `/prp-implement` | `SDLC/development/agentic-engineering`, `SDLC/development/coding-standards` |
| `/prp-pr` | `SDLC/development/git-workflow` |
| `/prp-prd` | `SDLC/requirements/product-capability` |
| `/test-coverage` | `SDLC/testing/tdd-workflow`, `SDLC/testing/verification-loop` |
| `/santa-loop` | `SDLC/testing/verification-loop`, `SDLC/testing/ai-regression-testing` |
| `/gan-build` | `ENGINEERING/ai-genai/autonomous-loops`, `ENGINEERING/ai-genai/continuous-agent-loop` |
| `/model-route` | `ENGINEERING/ai-genai/cost-aware-llm-pipeline` |
| `/learn-eval` | `SDLC/development/continuous-learning-v2`, `SDLC/testing/eval-harness` |

---

## Keeping assets up to date

When the Assets repo is updated (new skills, updated agents, revised commands):

```bash
# With submodule (from project root)
git submodule update --remote agentic-assets
python -X utf8 agentic-assets/setup_neuroedge_agentic_tools.py --project .

# With standalone clone (from Assets root)
git pull
python -X utf8 setup_neuroedge_agentic_tools.py --project "C:\Sanjeev_E\NeuroEdge Web"
python -X utf8 setup_neuroedge_agentic_tools.py --project "C:\Sanjeev_E\NeuroEdge Device"
```

The setup script is idempotent — it strips any existing NeuroEdge Assets block
before re-injecting, and skips hook entries already present in `settings.json`.

---

## What the project repos commit (not here)

Project repos (Web, Device) commit **zero Claude-specific files**.
Everything Claude-related is gitignored and created by the setup script.

| Asset | Committed in | Why |
|---|---|---|
| `src/`, `tests/`, `use_cases/`, `Makefile` etc. | NeuroEdge Web & Device | The actual project code |
| `.gitignore` | NeuroEdge Web & Device | Ensures Claude files stay out of git |
| `requirements.txt`, `pyproject.toml` etc. | NeuroEdge Web & Device | Python packaging |

Developers who don't use Claude Code clone the project and work normally — no setup
script needed, no `.claude/` directory, no `CLAUDE.md`. The project works without
any Claude dependency.

---

## Adding a new skill mapping

To wire a new skill file to an existing agent or command:

1. Edit `AGENT_SKILLS` or `COMMAND_SKILLS` in `patch_assets.py`
2. Run `python -X utf8 setup_neuroedge_agentic_tools.py --project <path>`
3. Restart Claude Code

To add a new agent or command to the Assets repo:

1. Add the `.md` file to `agents/SDLC/`, `agents/SOFTWARE/`, or `commands/`
2. Add its skill mapping to `patch_assets.py`
3. Follow the steps above

---

## Verifying your installation

After setup, run the health check from the project root:

```bash
make health-check
# or
python health_check/cli.py --verbose
```

PASS = ready | WARN = expected gaps on fresh clone | FAIL = re-run setup script

---

## Contributing

Changes to general SDLC agents, skills, or commands belong in this repo.
Changes to NeuroEdge-specific agents or skills belong in the relevant project repo.

Bump and tag a release after significant changes so teams can pin a version:
```bash
git tag v1.1.0 && git push origin v1.1.0
```
