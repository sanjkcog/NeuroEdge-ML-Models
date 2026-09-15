# How AgentForge Manages Token Cost

> **Path convention.** Paths shown as `docs/…`, `agentforge/…` or `agentforge_custom_plugin/…` are in the AgentForge **Assets** repo. Only `docs/guides/` ships into a target (as `agentic-assets/docs/guides/`), so those are written as plain paths rather than links — a link would resolve in Assets and dangle in every target.

> **Scope.** Three questions, answered from the code rather than the pitch: how context is
> **scoped** so a prompt stays small (§1), how **memory** keeps an agent from re-reading the
> repo (§2), and how token cost is actually **measured** (§3).
>
> Where a mechanism is designed but not wired, this guide says so and names the tech-debt
> item. [`docs/guides/how_agentforge_improves_project_SDLC.md`](how_agentforge_improves_project_SDLC.md)
> is the longer conceptual treatment; this guide is the mechanics, including the gaps.

**Status legend used throughout:** ✅ implemented and wired · ⚠️ implemented but unenforced or
partially wired · ❌ designed only, not built.

---

## The economics in one line

An agent that lacks context does two expensive things: it **re-reads the repo** (input
tokens) and it **produces plausible-but-wrong output that must be redone** (the most
expensive tokens). Every mechanism below exists to prevent one or both.

---

## 1. How AgentForge manages context

### 1.1 Context is layered, and each layer has a load trigger

AgentForge never loads "the context" as one blob. Knowledge is partitioned by where it
belongs and assembled in layers, each admitted only when something in the route calls for
it. A project that never declares the `embedded` discipline never loads a byte of it; an
agent writing a PRD never pays for C++ idioms.

| Layer | Loads when | Carries | Status |
|---|---|---|---|
| **0 · Always on** | Every session | Root `CLAUDE.md` — **pointers, not content**: where things live, which route to take. Deliberately small, because every request pays for it. | ⚠️ see §2.4 |
| **1 · On route** | A command or agent **names** the skill paths it needs | `skills/**` files, lazy-loaded. The coding-standards skill loads when an agent is coding — never into a planning prompt. | ✅ |
| **2 · On declaration** | A manifest declares it — `requires_subjects` in a plugin, `active_disciplines` for an engineering discipline | Subject expertise and discipline packs. Undeclared means unloaded. | ✅ |
| **3 · On stage** | The SDLC stage calls for it, via `wiring.stage_context` | The per-product plugin's context, **sliced per stage**: requirements gets personas + regulatory; architecture gets integrations + constraints. | ✅ per stage — ❌ per task, see §1.3 |

The Layer-3 mechanism is `agentforge_custom_plugin/discover_plugins.py`.
An agent (or the orchestrator) asks it what to read:

```bash
python agentforge_custom_plugin/discover_plugins.py --stage requirements
python agentforge_custom_plugin/discover_plugins.py --list
```

**Presence is activation.** Any directory under `agentforge_custom_plugin/` holding a
`plugin.json` with `wiring.auto_load != false` is live — no install step, no registry.

### 1.2 The 2×2 that decides which layer a fact belongs to

Two axes. Is the knowledge **horizontal** (true for building any software) or **vertical**
(true only within one field)? Is it **generic** (reusable across projects) or **specific**
(true only of this repo or product)?

| Reuse ↓ · Breadth → | **Horizontal** — cross-domain | **Vertical** — field / domain-specific |
|---|---|---|
| **Generic**<br>reusable across every project | **① Software craft** — *"How do we build software?"*<br>Home: `skills/SDLC/`, `skills/SOFTWARE/`, base role agents.<br>Examples: `SDLC/development/coding-standards.md`, `SDLC/tdd/tdd-workflow.md`, `SOFTWARE/python/python-testing.md`; agents `developer`, `qa-engineer`, `code-reviewer`.<br>**Loads when:** the route names it (Layer 1). Written once, ships to every project. | **② Subject & domain expertise** — *"What does an expert in this field know?"*<br>Home: `skills/SUBJECTS/`, `skills/DOMAIN/`.<br>Examples: `SUBJECTS/Physics/radiotherapy-qa-physics.md`, `DOMAIN/healthcare/healthcare-phi-compliance.md`, `DOMAIN/retail/inventory-management.md`.<br>**Loads when:** a plugin declares `requires_subjects: ["Physics"]` (Layer 2). You pay for medical-physics knowledge only on a medical-physics project. |
| **Specific**<br>true only of this repo or product | **③ Project conventions & live state** — *"How does THIS repo work, right now?"*<br>Home: root + subfolder `CLAUDE.md`, the `docs/context/` memory bank, ADRs.<br>Examples: the commands that actually work here (*"`make` is Unix-only; call `ruff`/`pytest` directly on Windows"*), `ACTIVE.md` / `PROGRESS.md` / `REPO_MAP.md`, `docs/decisions/ADR-*.md`.<br>**Loads when:** every session as a bounded re-orientation read (Layer 0), plus the nearest subfolder `CLAUDE.md` for the module you touch. | **④ Product / client context** — *"What is true about THIS product or client?"*<br>Home: `agentforge_custom_plugin/<Name>/`, scaffolded as `Project_Specific_Context`.<br>Examples (from the shipped SunCHECK plugin): `plugin.json` → `domain: radiation-oncology`, `regulatory: ["IEC-62304"]`, personas *Medical Physicist* / *RTT*; `context/integrations/…/data-formats.md`; `context/constraints.md`, `workflows/`, `glossary.md`.<br>**Loads when:** the stage calls for it, sliced by `wiring.stage_context` (Layer 3). |

**Why this is a cost strategy, not a taxonomy:**

1. **No prompt carries everything.** Any request loads only the relevant quadrant at the
   relevant altitude.
2. **Reuse is banked at the right layer.** Craft (①) once for all projects; subject
   expertise (②) once per field; only ④ is genuinely per-product. Duplication is the root
   cause of both drift and wasted tokens.
3. **Right knowledge → less rework.** The expensive failure is plausible-but-wrong output
   from an agent that lacked a product constraint (④) or a domain fact (②). Stage-scoped
   infusion puts it in front of the agent *before* it acts.

### 1.3 Can product context live in a nested hierarchy? — verified

A direct question worth answering precisely: can quadrant-④ context be organised as
**SunCHECK → Patient QA → AdaptCheck**, and will AgentForge pick up the right part based on
the current task?

**Half yes — and the half that fails is the half the token argument depends on.** Verified
against `discover_plugins.py`:

| Question | Answer | Mechanism |
|---|---|---|
| Can context files nest arbitrarily deep inside a plugin? | ✅ **Yes.** A directory entry in `wiring.stage_context` expands via `rglob("*.md")`, so `context/integrations/suncheck/patient-qa/adaptcheck.md` is found with no extra config. | `_expand()` |
| Are non-Markdown files picked up? | ❌ **No.** `*.md` only. A `.json` schema or `.csv` sample under a context folder is silently skipped. | `_expand()` |
| Can a *nested plugin* be declared (`SunCHECK/PatientQA/plugin.json`)? | ❌ **No.** `active_plugins()` iterates one level, non-recursively. A nested `plugin.json` is never discovered and never errors. Sub-products must be **folders inside one plugin**, not plugins. | `active_plugins()` |
| Is selection driven by the current **task**? | ❌ **No — by the current *stage*.** `collect_for_stage()` returns **every** `.md` under that stage's directory entries. Nothing narrows by sub-product. | `collect_for_stage()` |

**Practical guidance today:** organise the hierarchy as folders inside a single plugin —

```text
agentforge_custom_plugin/SunCHECK/
  plugin.json                       ← one manifest, at the top level only
  context/
    integrations/suncheck/
      patient-qa/adaptcheck.md      ← found recursively ✅
      patient-qa/interfaces.md
      machine-qa/data-formats.md
```

— and be aware that an architecture-stage task touching only AdaptCheck currently loads the
**whole** `context/integrations` subtree, siblings included. That is a cost risk *and* a
correctness risk: an agent handed three sibling products' data-format docs can attribute a
constraint to the wrong one. Keep the tree shallow and the files small until per-task
selection exists.

> **Tech debt:** recorded as **aspect 4 of TD-016 (`decisions/TECH-DEBT.md`)**. Unlike the
> other three aspects it is *not* blocked on external access — it can be built today.

### 1.4 Connecting external knowledge sources — the framework (❌ not implemented)

The intended way quadrant-④ context gets populated is **not** by hand. ADR-0012 (`decisions/ADR-0012-integration-and-interop-boundary.md`)
defines a single bidirectional boundary between AgentForge and external systems of record —
Git/GitHub, Jira, Confluence, SharePoint/M365, S3 — with a canonical exchange record,
per-system adapters, and MCP-first transport where a system exposes one.

**The three directions:**

| Direction | What it does | Target artifacts |
|---|---|---|
| **Outbound** | Push canonical artifacts + run-state out, so external agentic apps can monitor and drive the SDLC without AgentForge shipping a UI | PRD, epics & user stories, task board, test plan, trace matrix, sprint reports, `run.json` state manifest |
| **Inbound** | Pull artifacts a project **already has** in the customer's system — "adopt, don't force" | The same set, mapped back onto canonical IDs (`FR-NN`, `TC-NN-SS-TT`) |
| **custom_context** | Scan SharePoint sites and Git repos, extract claims, and **auto-author** the product-context plugin | `Project_Specific_Context/context/` — `DOMAIN.md`, `personas.md`, `constraints.md`, `regulatory.md`, `glossary.md`, `integrations/`, `workflows/`, and `sources.md` for provenance |

**The intended custom_context pipeline:**

```text
SharePoint / Git repo / Confluence
        │  pull (adapter, MCP-first)
        ▼
   IngestedDoc  ──►  extract_claims  ──►  cited claim + confidence
        │                                   │
        │                          no citation → field stays TBD (never fabricate)
        ▼                                   ▼
   AppliedIntentLedger              Project_Specific_Context/context/*.md
   (per-doc idempotency)            + sources.md (provenance)
                                            │
                                            ▼
                                   human review gate  ──►  draft | binding
                                            │
                                   only `binding` may enter a regulated stage
```

**What exists versus what does not — be precise about this:**

| Piece | State |
|---|---|
| Fail-closed source allowlist, per-doc idempotency ledger, never-raise result objects | ✅ built and unit-tested |
| Never-fabricate contract (an uncited field falls through to `TBD`) | ✅ enforced by construction — `_write_field` is the only writer and is gated on a citation existing |
| Human-review gate + draft-vs-binding marker, derived from the gate and never hand-set | ✅ built |
| `GitLocalSource` inbound driver | ⚠️ **walks the local filesystem only** — `Path.rglob`, `.md/.txt/.rst`, zero auth. It is a local-directory reader named "Git"; it has never cloned or fetched. |
| GitHub Issues outbound adapter | ⚠️ built, but every test injects a fake `gh` runner; the real shell-out path has never run |
| Jira | ❌ **no client exists.** `push_sprint_backlog`/`push_issue_status` take an injected `jira_tool`; nothing constructs one, so both have only ever returned `"no Jira tool available — repo-local only"` |
| SharePoint / Confluence adapters | ❌ **do not exist** — named in the ADR, absent from the code |
| Claim extraction from unstructured content | ❌ `extract_claims` is, per its own docstring, *"a DETERMINISTIC reference implementation over already-provided source spans, not a live LLM call"* — the step that would produce claims from real SharePoint pages is unbuilt |

> **Tech debt:** **TD-016 (`decisions/TECH-DEBT.md`)**, Open — blocked on access. We have no
> credentialed GitHub org, Jira project, or SharePoint site, so none of this boundary has run
> against a real system. **Do not read the passing unit tests as evidence the integration
> works** — they pin the never-raise contract and the fail-closed allowlist, and say nothing
> about whether any external system accepts what we send.

---

## 2. How memory works

Memory is quadrant ③: what is true about *this repo, right now*. It is the difference
between an agent that re-orients in a four-file read and one that re-explores the tree.

### 2.1 `CLAUDE.md` per folder — nested scoping

The root `CLAUDE.md` is a **router**: project snapshot, the commands that actually work
here, hard rules, an architecture map of pointers. It is read every session, so it is kept
compact and pointer-heavy — content lives behind the pointers, not inside it.

Each subfolder may carry its **own** `CLAUDE.md`, read only when work touches that folder:

```text
CLAUDE.md                    ← always: routing, hard rules, critical commands
├── coded_tools/CLAUDE.md    ← only when editing coded tools
├── registries/CLAUDE.md     ← only when editing HOCON agent networks
├── tests/CLAUDE.md          ← only when editing tests
└── neuroedge/portal/CLAUDE.md   ← only for portal work (its own TS toolchain)
```

Why this saves tokens: module-specific rules — the portal's `tsc`/vitest commands, the
HOCON conventions, the `-p no:name_of_plugin` pytest trap — would bloat the root file for
every session that never touches those folders. Nesting keeps Layer 0 small while making
the detail available exactly where it applies.

Only the **root** `CLAUDE.md` is seeded by the installer (`projects/generic/CLAUDE.md`,
seeded once then owned by the project, so an update can never overwrite your content).
Subfolder files are generated on demand:

```bash
/legacy-audit . --memory-bank --subfolder-claude    # propose/create subfolder routers
/scope-context --modular                            # generate_subfolder_claude.py
```

### 2.2 `docs/context/` — the memory bank

| File | Holds | Read by |
|---|---|---|
| `ACTIVE.md` | Current focus, next 3 actions, recently changed | Every session, at start |
| `PROGRESS.md` | Done / in-progress / blocked / next, per workstream and sprint | Every session, at start |
| `REPO_MAP.md` | Where things live — module → path → purpose | Session start; refreshed after structural change |
| `OPEN_QUESTIONS.md`, `GLOSSARY.md` | Optional: unresolved decisions, shared vocabulary | As needed |
| `docs/decisions/ADR-*.md` | Why the architecture is the way it is | When a decision is being revisited |

`health_check` treats the first three plus `CLAUDE.md`, `AGENTS.md`, and the ADR template as
**required**; `OPEN_QUESTIONS.md` and `GLOSSARY.md` as optional.

### 2.3 Working across a team

The files are ordinary git-committed Markdown, so they **do** travel between engineers —
that part genuinely works, and is why this is worth fixing rather than replacing:

- A new joiner (or a new agent session) reads the same four files everyone else does.
- `PROGRESS.md` is the state `/agentforge --status` reads, so status and progress are meant
  to be the same story.
- Review and history apply — a memory change is diffed in a PR like any other change.

What is **missing** for multi-person use, verified in the code:

- **No authorship or timestamp per entry.** Neither file records who observed something or
  when, so a note from an hour ago reads identically to one from March.
- **Last-write-wins on a whole section.** `pm/refresh.py`'s `_upsert_section` replaces an
  entire `## Sprint <id>` block. Two engineers refreshing the same sprint get a merge
  conflict at best, a silently overwritten section at worst. (`sprint-NN.json` *was*
  hardened against this exact race via `merge_run_snapshot`; `PROGRESS.md` was not.)
- **No staleness signal at read time.** An agent reading a three-week-old `ACTIVE.md` is
  told nothing about its age, so stale context is consumed with the same confidence as
  fresh context.

### 2.4 Audit: is memory actually maintained and used? — ⚠️ no, and nothing checks

Two questions worth asking directly: **does every session auto-update the context files, and
does every session actually use them?** Audited 2026-07-29. The answer to both is **no**, and
the gap is enforcement, not design.

| Claim | Reality | Evidence |
|---|---|---|
| Sessions read the memory bank at start | ⚠️ **Prose only.** `hook-config.json` registers hooks on `PreToolUse`, `PostToolUse`, `Stop` — there is **no `SessionStart` hook**. Whether a session reads the files depends on whether the model follows the instruction. | `hook-config.json` |
| Sessions update it after meaningful work | ⚠️ **Unenforced.** The four `Stop` hooks are `hitl-gate`, `typecheck`, `code-review-reminder`, `native-review`. None looks at the memory bank. | `scripts/hooks/` |
| The PM lane refreshes `PROGRESS.md` on every stage transition | ❌ **`pm/refresh.py` has no production call site** — only tests. Yet `/sprint-report` and `/budget-report` both describe it as running. `commands/agentforge.md` never invokes it. | grep `refresh(` |
| `project-manager` keeps `PROGRESS.md` current on every transition | ❌ It is spawned at **S5 `sprint-plan`** and **S16 `sprint-close`** only — 2 of 17 stages — despite its definition saying "every stage transition" and "never batch updates to later". | stage table in `commands/agentforge.md` |
| `ACTIVE.md` is kept current | ❌ **No automated writer** outside `/legacy-audit` at bootstrap and one summary line from `/memory-audit`. `refresh()` never touches it. | grep `ACTIVE.md` |
| Something checks freshness | ⚠️ `health_check` checks **presence only** — never content or age. `/memory-audit` checks staleness properly (ACTIVE "next 3 actions" >14 days, PROGRESS sections >30 days) but is an **interactive command a human must remember to run**. | `health_check/checkers/memory.py`, `commands/memory-audit.md` |

**What this means for the token argument:** "re-orient from a bounded four-file read" holds
only when the four files are current and actually read. Neither is guaranteed, so the
fallback — whole-repo re-exploration at full input-token cost — is silently the real
behaviour some fraction of the time.

> **Tech debt:** filed as **TD-017 (`decisions/TECH-DEBT.md`)** (High, Open). The likely fix
> is a `SessionStart` hook that loads the bank (and surfaces its age) plus a warn-only `Stop`
> hook when source changed and memory did not — and, independently and immediately, correcting
> the three command docs that assert an unwired `refresh()`.
>
> **Until that lands, treat rule 9 (*update `ACTIVE.md` and `PROGRESS.md` after meaningful
> work*) as a manual discipline you have to keep, and run `/memory-audit --report-only`
> periodically.**

---

## 3. How token cost is calculated

### 3.1 Two ledgers, never summed

| Ledger | Covers | Lives in | Read by |
|---|---|---|---|
| **Orchestrated** | Work inside an `/agentforge` run, **per stage** | `run.json` → folded into `sprint-NN.json` at the sprint boundary | `run_state.py usage`, `/budget-report` |
| **Standalone** | Commands run **outside** a run (`/test-plan`, `/model-route`, … invoked directly) | `docs/project_related/misc/runlog-<command>-<arg-slug>.md`, one file per (command, args) | `usage_state.py report`, `/budget-report --commands` |

They are reported as **separate figures and never added together** — the standalone ledger
holds only non-orchestrated invocations, so there is no overlap and no double-counting.

The unit recorded in both is the same four-field `Usage`: `tokens_in`, `tokens_out`,
`api_calls`, `cost_usd`.

> **⚠️ The split has a hole in the other direction.** No double-counting is guaranteed; **no
> under-counting is not.** Ten of the eighteen SDLC stages also exist as slash commands
> (`/research`→S1, `/prp-prd`→S2, `/test-plan`→**S6**, `/trace-matrix`→S12, …). Run one of those
> directly — the documented fast-lane and `--stage` rejoin workflow — and its tokens go to the
> standalone ledger, while the run that later consumes its artifact reports **nothing** for that
> stage.
>
> Measured: `init --start-stage build` marks S1–S7 complete and `usage` then reports
> *"no token telemetry recorded yet"* — seven stages of real work, zero cost carried. `create_run`'s
> backfill records provenance for the artifact but nothing for the cost, and `usage_state` has **no
> run linkage at all** (no `run_id`, no `--run` flag), so it cannot be attributed by hand either.
>
> **Scoped decision (operator, 2026-07-29):** `/test-plan` is to roll into the run's cumulative,
> since S6 is hard-gated and the rest of the run depends on its artifact. **All other commands stay
> standalone-only for now** — a deliberate staging choice, not an oversight. See
> TD-018 (`decisions/TECH-DEBT.md`) Problem 6, including the invariant any fix must preserve: an
> invocation must land in **exactly one** ledger.

### 3.2 Where the numbers come from — read this before trusting a figure

**AgentForge does not measure tokens. It records what the caller supplies.** There is no
meter, no interception, no price table.

Inside a run, the orchestrator records a stage's usage as flags on `complete`:

```bash
python agentforge/src/state/run_state.py --path "$RUN" complete <stage> \
  --artifact <path> \
  --tokens-in <in> --tokens-out <out> --api-calls <n> --cost-usd <c>
```

The numbers come from **each subagent spawn's own returned usage**, passed through by the
orchestrator. `commands/agentforge.md` states the rule plainly: *"Omit any you don't have —
each defaults to 0… Do **not** fabricate figures: if a spawn reports no usage, pass
nothing."*

Standalone commands do the same through a separate CLI:

```bash
python agentforge/src/state/usage_state.py record \
  --command test-plan --args "<slug>" \
  --tokens-in 12000 --tokens-out 3400 --api-calls 7 --cost-usd 0.21
```

**Three honest consequences:**

1. **Cost is caller-provided.** No model price table is embedded, deliberately — a stale
   hardcoded price would be worse than an explicit input.
2. **Capture is not automatic.** Claude Code does not hand token counts to hooks, so
   recording is an explicit call at command completion. Per-command adoption is incremental
   (TD-002).
3. **A zero is ambiguous.** An unrecorded stage and a genuinely free stage both read as `0`.
   `/budget-report --monthly` addresses this by **naming** sprints with never-refreshed usage
   rather than treating them as zero spend — the same fail-loud posture as the missing-rate
   case.

### 3.2a The complete in/out trace — from the API to the runlog

This is the full path a token count travels, traced live against `run_state.py` on 2026-07-29.
Every observation below was **executed**, not inferred from reading the source.

#### The chain

```text
┌── ROOT ─────────────────────────────────────────────────────────────────┐
│ Anthropic Messages API response                                         │
│   usage: { input_tokens, output_tokens,                                 │
│            cache_creation_input_tokens, cache_read_input_tokens }       │
│   Server-computed. Authoritative. This is what billing uses.            │
└─────────────────────────────────────────────────────────────────────────┘
     ↓  MEASURED — Claude Code is the API client; it receives usage on every
     ↓  response and accumulates it natively. AgentForge is not in this path.
┌─────────────────────────────────────────────────────────────────────────┐
│ Claude Code session accounting                                          │
└─────────────────────────────────────────────────────────────────────────┘
     ↓  SURFACED — on a subagent spawn completing, the harness reports that
     ↓  spawn's token total.  commands/agentforge.md:454 — "Each subagent
     ↓  spawn returns its usage… Read them from the spawned agent's result"
┌─────────────────────────────────────────────────────────────────────────┐
│ The orchestrating model reads the figure                                │
└─────────────────────────────────────────────────────────────────────────┘
     ↓  TRANSCRIBED — re-typed as --tokens-in / --tokens-out
┌─────────────────────────────────────────────────────────────────────────┐
│ run_state.py complete <stage> --tokens-in N --tokens-out M …            │
│   argparse            run_state.py:1023-1026   type=int, default=0      │
│   validation          run_state.py:1133-1139   <0 or non-finite → exit 1│
│   Usage(...)          run_state.py:1140-1145   4-field dataclass        │
│   complete_stage()    run_state.py:566         st.usage = outcome.usage │
│   state.save(path)                                                      │
└─────────────────────────────────────────────────────────────────────────┘
     ↓
run.json → stages.<stage>.usage {tokens_in, tokens_out, …}   ← the split lives HERE
     ↓  usage_rollup()   run_state.py:810-859
`usage` table (In/Out columns) · `status` one-liner
     ↓  TRANSCRIBED AGAIN — orchestrator hand-types a markdown row
<objective-slug>/runlog.md                                    ← the split is lost HERE
```

**There is no derivation anywhere in that chain.** Nothing parses an API response, reads a
meter, or computes an estimate. The script's entire contribution is validate → store → sum.
AgentForge's figures are **reported, never measured** — which is not a defect but a boundary:
`run_state.py` runs as a subprocess outside the API client, so it can only be *told*.

#### Observed: a normal recording

```console
$ run_state.py --path run.json complete research --artifact docs/research.md \
    --tokens-in 71506 --tokens-out 8210 --api-calls 12 --cost-usd 0.94
research: complete (79,716 tokens)
```

That suffix is just `tokens_in + tokens_out` (`run_state.py:1155`). run.json received exactly what
was passed:

```json
"usage": { "tokens_in": 71506, "tokens_out": 8210, "api_calls": 12, "cost_usd": 0.94 }
```

#### Observed: what the guards catch — malformed, never wrong

| Input | Result |
|---|---|
| `--tokens-in -5` | ✅ refused, exit 1 — `INVALID usage: --tokens-in must be a finite number >= 0` |
| `--cost-usd nan` | ✅ refused, exit 1 — needs the explicit `isfinite` check since `nan < 0` is `False`; NaN is contagious in the cost sum and would contaminate every future rollup |
| `--tokens-in 12.5` | ✅ refused by argparse — `invalid int value` |
| `--tokens-in 999999999` | ❌ **accepted silently**, exit 0 |

A billion tokens on one stage is indistinguishable from an accurate figure.

#### Observed: an unrecorded stage is invisible, not zero

```console
$ run_state.py --path run.json complete requirements --artifact docs/PRD.md
requirements: complete                    ← no token suffix, no warning

$ run_state.py --path run.json usage
Stage                     In         Out       Total   Calls    Cost $
research              71,506       8,210      79,716      12    0.9400
TOTAL                 71,506       8,210      79,716      12    0.9400
Top consumer: research - target optimization here first.
```

`requirements` is **absent — not listed as zero**. `usage_rollup:832` emits a row only
`if stage_tokens or u.api_calls or stage_cost`. You cannot tell from this output whether a stage
was free or never recorded, because an unrecorded stage produces no row to notice. The `reported`
flag guarding the "no telemetry yet" message is run-level, so one metered stage out of eighteen
makes the report look populated.

#### Observed: the ledger depends on phase closure — and loses cost when a phase reopens

**`complete` is the only subcommand that accepts usage flags.** `fail` accepts none:

```console
$ run_state.py --path run.json fail --help
positional arguments:  {onboarding,research,requirements,…}
options:  -h, --help
```

So a stage that fails — and `fail` retries once, escalating on the second consecutive failure —
burns its tokens **unrecordably**. Any path that does not end in `complete` contributes zero to
every reported figure, however much it consumed.

Worse, re-completing a reopened stage **erases** the first pass:

```console
$ complete build --tokens-in 200000 --tokens-out 40000 --cost-usd 3.50
build: complete (240,000 tokens)

$ reopen build                       # the TD-014 re-runnability path
build: reopened (pending) — spawn history preserved; re-run it
   run.json still shows 200000 / 40000 at this point

$ complete build --tokens-in 15000 --tokens-out 3000 --cost-usd 0.30
build: complete (18,000 tokens)

$ usage
build                 15,000       3,000      18,000       4    0.3000
TOTAL                 15,000       3,000      18,000       4    0.3000
```

**240,000 tokens and $3.50 gone.** `complete_stage` does `st.usage = outcome.usage` — assignment,
not accumulation. `reopen_stage` preserves the **spawn** history by design; it does not preserve
the **cost**. The audit trail says the stage ran twice; the ledger reports only the second pass —
and under-reports most on exactly the runs that needed rework.

> **Practical consequence for anyone reading a budget figure:** every total is a **lower bound of
> unknown tightness**. Failures, escalations, abandoned runs and reopened stages are structurally
> missing, and unrecorded stages are invisible rather than flagged.

#### Forensic check: are the recorded figures real?

Correlating stage owner against the token figure across all four runlogs in this repo:

| Owner | Figures recorded | Pattern |
|---|---|---|
| Named subagent (`researcher`, `product-manager`, `epic-writer`, `task-writer`, `qa-engineer`, `developer`, `team-lead`) | 71,506 · 31,038 · 35,543 · 76,980 · 75,466 · 240,868 · 71,627 | **7/7 precise, none round** |
| `(orch)` — the orchestrator's own work | 19,000 · 28,500 · 22,500 · 26,000 | **4/4 round** |

And the round figures **repeat verbatim across two independent runs** with different objectives
and different scope:

| Stage | `ai-assisted-ingestion` | `engineering-discipline-layer` |
|---|---|---|
| `sprint-plan` `(orch)` | **19,000** | **19,000** |
| `trace-matrix` `(orch)` | **22,500** | **22,500** |

The cause is mechanical, not carelessness: a subagent's usage is reported when the spawn
*completes*, but the orchestrator's own work has no completion event — **a model cannot observe
its own token consumption mid-turn.** The harness knows; the model does not. So for `(orch)`
stages there is nothing to read, and `commands/agentforge.md:459` says what to do about it —
*"Do **not** fabricate figures: if a spawn reports no usage, pass nothing."* That rule was not
followed; round estimates were passed instead.

**Read the ledger accordingly:** a precise figure traces to a real API-reported count two
transcription hops away. A round figure against an `(orch)`-owned stage is an estimate.

**And the stated grand total does not cross-check any of it — it is circular.** Both runs close with
a `**Total N tokens**` line that reads like an independent figure. It is exactly the sum of the
column, estimates included:

```text
ai-assisted-ingestion:         sum(parts) = 673,028   stated total = 673,028   → CIRCULAR
engineering-discipline-layer:  sum(parts) = 595,058   stated total = 595,058   → CIRCULAR
```

So there is no independent anchor in the recorded data, and the cleanest estimator — the residual,
`orchestrator cost = harness session total − Σ measured spawns` — cannot be applied retroactively.
It works going forward, if a harness-reported session total is captured alongside the parts.

**Estimating is legitimate; estimating without a method is not.** The problem with `19,000` is not
that it is an estimate — it is that it carries no label, no method, and no band, in a column readers
treat as measurement. It is not even self-consistent: `trace-matrix` was recorded at 22,500 for a
1,484-byte artifact while `sprint-plan` got 19,000 for a 3,723-byte artifact. Evidence that survives
every run makes a defensible estimate constructible today:

| `(orch)` stage | Artifact bytes (on disk) | Output-token floor (÷4) | Figure recorded |
|---|---|---|---|
| `sprint-plan` | 3,723 | ~930 | 19,000 |
| `architecture` (hld+lld) | 8,758 | ~2,189 | 28,500 |
| `trace-matrix` | 1,484 | ~371 | 22,500 |

The recorded figures sit 10–60× above the output floor, which is plausible — orchestrator turns are
input-dominated. Plausible is simply all anyone can currently say. A calibrated estimator (artifact
floor × the per-run in:out ratio taken from that run's *measured* spawns, which `run.json` still
holds) would let the ledger say something defensible, stamped `estimated` with a band.

#### Consistency warning: the runlog column means two different things

| Runlog | `Tokens` column | Evidence |
|---|---|---|
| `ai-assisted-ingestion`, `engineering-discipline-layer` | **Per-stage** | Values rise and fall (240,868 at build, 22,500 at trace-matrix) |
| `ai-genai-engineering-discipline`, `regulatory-format-adaptation` | **Cumulative running total** | Monotonically increasing, repeating unchanged where a stage consumed nothing (`test-run` 919,284 = `triage` 919,284) |

Neither file states which convention it uses, so **cross-run comparison of that column is
invalid**. `commands/agentforge.md:479` mandates *both* "the stage tokens, and the cumulative
total" — no runlog has both columns. The in/out split is likewise preserved in `run.json` and
lost at the runlog layer, because `complete` echoes the sum and the sum is what gets transcribed.

**If you need in/out per stage, read `run.json` or `run_state.py usage` — not the runlog.**

> **⚠ But do not trust the historical split itself.** Checked across all four archived runs:
> `in/(in+out)` sits at **0.797 ± 0.007** for **all 44 stages** (min 0.769, max 0.807), and 12 of
> `ai-genai`'s 14 are **exactly 0.8000** with non-round `in` values — i.e. `in = 0.8 × total`,
> `out = total − in`. A measured ratio cannot be that flat across research, build, review and deploy.
> **The totals are real; the in/out split was derived from them by a fixed ~80/20 assumption.** Treat
> pre-2026-07-29 splits as reconstruction, not measurement — and note this is why the calibrated
> estimator for orchestrator-owned stages is blocked: its intended calibration source is synthetic.

#### Two gaps at the root

- **Cache tokens cannot survive the model.** The API splits input into fresh / cache-creation /
  cache-read, billed at very different rates. `Usage` has one `tokens_in` field, so whatever the
  harness reports is flattened into it. Cost inference from that number is structurally lossy, and
  more so the more prompt caching is in play.
- **`cost_usd` has no source inside AgentForge.** `pm/budget.py` knows only a `$/story-point` rate
  for *delivery* cost; there is no model price table (deliberately — a stale one would be worse).
  `--cost-usd` is either the harness's modelled figure or a guess, and nothing distinguishes them.

> **Tech debt:** all of the above is filed as **TD-018 (`decisions/TECH-DEBT.md`)** (High, Open) —
> closure-dependent recording, cost loss on reopen, unmethodical `(orch)` figures, a circular grand
> total, invisible unrecorded stages, and the runlog-column inconsistency.
>
> The keystone fix is a **`source` field on `Usage`** (`measured` | `estimated` | `unrecorded`)
> surfaced in every rollup row. It makes every other item on that list visible rather than silent —
> **and it is what licenses estimation**: once provenance is on the record, a calibrated estimate is
> an asset rather than a contaminant. Estimates are wanted here; unlabelled ones are not.

### 3.3 The commands

**There is no `/usage` or `/utilization` slash command in AgentForge.** The surfaces are:

| Surface | What it shows |
|---|---|
| `run_state.py --path "$RUN" usage` | Per-stage table: tokens in/out/total, API calls, cost, plus a TOTAL row — this is what names the top-consuming stage |
| `run_state.py --path "$RUN" status` | Stage cursor plus a **one-line running token summary** when telemetry has been recorded |
| `/budget-report` | The active sprint's two figures (see §3.4) |
| `/budget-report --commands` | Rolls up the standalone ledger, per command and total |
| `/budget-report --monthly` | AI runtime cost across the calendar month, stating the two-sprints-per-month assumption and naming incomplete sprints |
| `/sprint-report --burndown` | Burndown from the snapshots appended on each PM-lane refresh |

The orchestrator is also instructed to surface cost **as it goes**, not only at the end —
after each stage: `Stage research: 75,102 tok · SDLC total so far: 75,102 tok`.

**Not to be confused with the harness's own telemetry.** Claude Code provides session- and
plan-level usage views of its own (`/cost`, `/usage`). Those are **harness-scoped and
ephemeral** — they describe your session or your plan, not a project's SDLC run, and nothing
writes them into `run.json` or a sprint container. AgentForge's ledgers are the durable,
per-stage, per-project record; the harness views are a live read on your own consumption.
Use the harness view to sanity-check a figure you are about to record by hand.

### 3.4 Delivery cost and AI runtime cost are different numbers

`/budget-report` produces **two figures that are never blended**:

- **Delivery cost** — completed story points × a configured `$X per point` rate. If no rate
  is configured it is reported **unavailable, never defaulted to zero**. Zero completed
  points *with* a rate configured is a real, computed `$0` — the two cases are
  distinguishable on purpose.
- **AI runtime cost** — the `cost_usd` accumulated from the ledgers above.

Aggregation is by sprint; a by-model or by-stage breakdown at the sprint level is
**deferred, not fabricated** — per-stage detail stays in `run.json` where it was recorded.

### 3.5 Known gaps in the cost picture

| Gap | Effect | Item |
|---|---|---|
| Standalone capture is a manual `record` call | Commands that never call it are invisible to `--commands` | TD-002 (implemented, adoption incremental) |
| `--stage bootstrap` writes no runlog and no telemetry | One measured bootstrap consumed **448,270 subagent tokens** across 4 spawns with **zero** of it captured anywhere | TD-010 (Open) |
| Per-round review cost is only visible by reading the runlog by hand | Review was **~38% of one run's 1.03M tokens**; the structural loop is still open | TD-013 (partially implemented) |
| Whole-subtree product context loads per stage regardless of task | Cost grows with the product family, exactly as ingestion succeeds | TD-016 aspect 4 (Open) |
| Memory bank not guaranteed loaded or current | Silent fallback to whole-repo re-exploration | TD-017 (Open) |
| Usage attaches only at `complete` — `fail` records nothing, `reopen` + re-complete **erases** the prior pass | Every total is a lower bound of unknown tightness; measured 240,000 → 18,000 | TD-018 (Open) |
| An unrecorded stage is absent from the rollup, not shown as `0` | Free and unrecorded are indistinguishable; "top consumer" ranks only metered stages | TD-018 (Open) |
| `(orch)`-owned stages have no observable token source | Round estimates recorded against the anti-fabrication rule (19,000 / 22,500 repeat verbatim across two runs) | TD-018 (Open) |
| The runlog `Tokens` column is per-stage in some runs, cumulative in others | Cross-run comparison of that column is invalid | TD-018 (Open) |
| SDLC-stage commands run standalone (`/test-plan` = S6) never reach the run's cumulative; `--stage` rejoin backfills at zero | Measured: rejoin at `build` marks 7 stages complete and reports "no telemetry recorded yet" | TD-018 Problem 6 — `/test-plan` scoped for fix, others deferred |

---

## Summary — claim versus enforcement

| Mechanism | Designed | Wired | Where it stands |
|---|---|---|---|
| Layered loading (0–3) | ✅ | ✅ | Layers 1–2 are enforced by manifests; Layer 0 depends on §2.4 |
| 2×2 quadrant homes | ✅ | ✅ | Real directories, real manifests |
| Stage-scoped product context | ✅ | ✅ | `wiring.stage_context` + `discover_plugins.py` |
| **Task-scoped** product context | ❌ | ❌ | TD-016 aspect 4 — not access-blocked, buildable today |
| External-source ingestion & auto-population | ✅ ADR-0012 | ❌ | TD-016 — never run against a real system |
| Per-folder `CLAUDE.md` nesting | ✅ | ✅ | Root seeded once; subfolders on demand |
| Memory bank read/update discipline | ✅ | ⚠️ | TD-017 — prose, no `SessionStart`/`Stop` enforcement |
| Two-ledger token telemetry | ✅ | ✅ | But numbers are **caller-supplied**, not measured |
| Token figures survive failure / reopen | ✅ intent | ❌ | TD-018 — recording is closure-dependent; reopen erases the prior pass |
| `0` distinguishable from `unrecorded` | ❌ | ❌ | TD-018 — the smallest high-value fix; makes every other TD-018 item visible |
| Delivery vs AI runtime cost separation | ✅ | ✅ | Never summed; missing rate never defaults to zero |

**Related:** [`how_agentforge_improves_project_SDLC.md`](how_agentforge_improves_project_SDLC.md) ·
`decisions/TECH-DEBT.md` ·
`ADR-0012` (`decisions/ADR-0012-integration-and-interop-boundary.md`)
