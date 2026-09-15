# How AgentForge Improves the Project SDLC

> **Prime objective:** run a structured, best-practice SDLC that **minimizes token cost
> and rework**. Every design choice below trades a small, one-time cost (writing a rule, a
> map, a decision record) for a large, repeated saving (not re-reading the repo, not
> re-deriving a decision, not redoing work an agent got wrong for lack of context).

This guide explains the three mechanisms that do most of that work — the target
`CLAUDE.md`, the `docs/context/` memory bank, and the 2×2 context-infusion model — and
then lists AgentForge's differentiators and concrete further-optimization ideas.

---

## The economics in one paragraph

An LLM agent is **stateless and amnesiac**: every session starts from zero, and the only
way it knows anything about your repo is what lands in its context window. Two failure
modes follow directly, and both cost tokens:

1. **Re-discovery.** Without a durable map, the agent re-reads large parts of the codebase
   every session to reconstruct what it already "knew" yesterday. That is raw input tokens,
   paid again and again.
2. **Rework.** Acting without the right context (a convention, a past decision, a product
   constraint) produces wrong output that must be caught, explained, and redone — the most
   expensive tokens of all, because they include the human round-trip.

AgentForge attacks both by making the *right* knowledge **durable, compact, and loaded on
demand** rather than re-derived or dumped wholesale. The rest of this guide is that
sentence, expanded.

---

## 1. The target `CLAUDE.md` — a compact, routed "boot sector"

When AgentForge installs into a project it seeds a root `CLAUDE.md` (from
`projects/generic/CLAUDE.md`) — **seeded once, then owned by the project**. It is
deliberately short and load-bearing, not a data dump. Its sections and the job each does:

| Section | Contents | How it helps the user | How it saves tokens |
|---|---|---|---|
| **Project Snapshot** | Project, purpose, stack, status — 4 lines | Instant orientation for any human or agent | The agent stops guessing the stack; no exploratory reads to infer it |
| **Session Start** | An ordered read-list (`AGENTS.md` → `docs/context/ACTIVE.md` → `PROGRESS.md` → `REPO_MAP.md` → nearest subfolder `CLAUDE.md`) | One reliable ritual to "get current" | Replaces open-ended repo crawling with a **bounded, 4-file** load — the single biggest per-session saving |
| **Route Preflight** | Forces the agent to declare `command / agent / skills / mcp / hooks` before acting | Predictable, reviewable routing; fewer wrong turns | Picks the pre-built command/agent instead of improvising a solution from scratch (which re-loads context the command already encodes) |
| **Response Header** | One line naming the active command + skills | Traceability of what ran | *Centralizes* the status convention so every command file need not repeat it — less duplicated instruction text |
| **Critical Commands** | Canonical build / test / lint / typecheck / run | Nobody re-invents commands | Agent runs the known command instead of trial-and-error discovery of the toolchain |
| **Architecture Map** | A *compact* pointer table — detail lives in `docs/context/REPO_MAP.md` | Fast "where does X live" | Keeps `CLAUDE.md` small so it is cheap to load **every** turn; the big map is loaded only when needed |
| **Hard Rules** | ≤15 rules, each preventing a *real* mistake | Guardrails that match this repo | Prevents rework-class errors (secrets committed, hooks bypassed, tests skipped) |
| **Human Approval / Protected paths** | Where the agent must stop and ask | Safety on billing, auth, migrations, infra | Averts the most expensive rework: a wrong change to a high-blast-radius surface |

**The core token principle here is *altitude*.** `CLAUDE.md` is loaded on essentially every
turn, so it is kept **short and mostly pointers**. Volume is pushed down to files that are
read only when relevant — `REPO_MAP.md`, ADRs, and **subfolder `CLAUDE.md` files**. The
scope walker (`setup_neuroedge_agentic_tools.py` Step 4) generates a nested `CLAUDE.md` per
package, so when an agent works in `services/api/` it loads *that* scope's rules, not the
whole repo's. The explicit maintenance rule — *"Review quarterly. Remove rules Claude can
infer or that CI already enforces"* — is a token-hygiene rule: a bloated `CLAUDE.md` is a
tax on every single request.

---

## 2. The `docs/context/` memory bank — durable state that defeats amnesia

AgentForge bootstraps a **shared memory bank** on install (`_bootstrap_memory_bank` in
`install.py`). It is the project's persistent brain between sessions:

| File | Role | Rework / amnesia it prevents |
|---|---|---|
| `docs/context/ACTIVE.md` | **Working set** — current focus, recently changed, next 3 actions, blockers, last-updated | The "where were we?" reload. An agent reads one file instead of reconstructing intent from git history and diffs |
| `docs/context/PROGRESS.md` | **Ledger** — done / in-progress / blocked / next | Stops re-doing finished work and re-starting abandoned threads |
| `docs/context/REPO_MAP.md` | **Structure** — modules, entry points, tests, ownership | Replaces repeated whole-tree exploration with one compact map |
| `docs/context/OPEN_QUESTIONS.md` | **Unknowns** — decisions not yet made | Prevents agents from silently assuming an answer and building on it (a rework generator) |
| `docs/context/GLOSSARY.md` | **Shared vocabulary** | Stops misinterpretation of domain terms across agents/sessions |
| `docs/decisions/ADR-*.md` | **Decision records** — context, decision, alternatives, consequences | Stops re-litigating settled choices; the *why* is captured once, not re-argued each session |

**Why this saves tokens, concretely:**

- **Amnesia → one bounded read.** Instead of `N` exploratory tool calls to rebuild
  situational awareness, the agent reads ~4 small, purpose-built files. Input tokens drop
  from "a slice of the codebase" to "a page of notes."
- **Rework → captured decisions.** An ADR turns a decision into a *fact* the agent honors,
  rather than a judgment it re-makes (often differently, causing churn). The
  `CLAUDE.md` Hard Rules even mandate updating `ACTIVE.md`/`PROGRESS.md` after meaningful
  work and recording non-trivial decisions as ADRs — so the memory bank stays true.
- **Write-once, read-many.** The memory bank is the cheapest possible cache: plain markdown
  the agent updates as a side effect of work, then reloads for pennies next session.

`/memory-audit` keeps it honest by flagging stale or duplicated context — because a memory
bank that has silently gone wrong is worse than none (it produces confidently-wrong work).

---

## 3. Context infusion — the 2×2 knowledge model

The deepest idea in AgentForge is **where a given piece of knowledge lives**, so that it is
infused at the right altitude and loaded only when it applies. Two axes:

- **Horizontal ↔ Vertical** — is the knowledge *cross-domain* (true for building any kind
  of software) or *field/domain-specific* (true within one problem domain)?
- **Generic ↔ Specific** — is it *reusable across projects*, or *true only of this
  project/product/client*?

That yields four quadrants, each with a real home in the toolkit:

|                          | **Horizontal** (cross-domain)                                             | **Vertical** (field / domain-specific)                                                     |
|--------------------------|---------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| **Generic** (reusable)   | **① Software craft** — *"How do we build software?"*<br>`skills/SDLC/`, `skills/SOFTWARE/`, base agents | **② Subject / domain expertise** — *"What does an expert in this field know?"*<br>`skills/SUBJECTS/`, `skills/DOMAIN/` |
| **Specific** (this repo) | **③ Project conventions & state** — *"How does THIS repo work, right now?"*<br>root + subfolder `CLAUDE.md`, `docs/context/` memory bank | **④ Product / client context** — *"What is true about THIS product/client?"*<br>`agentforge_custom_plugin/<Name>/` (`Project_Specific_Context`) |

**Read the diagonal to understand the design:**

- **① Generic + Horizontal** — software craft. Written once, ships to *every* project.
  Delivered as **skills referenced by path** and lazy-loaded per route, so an agent pulls
  the coding-standards skill only when it is actually coding — not into every prompt.
- **② Generic + Vertical** — subject expertise (e.g. radiotherapy QA physics, PHI patterns).
  Reusable, but only *within a field*. A plugin declares what it needs via
  `requires_subjects`, so a project pays for medical-physics knowledge only if it is a
  medical-physics project.
- **③ Specific + Horizontal** — this repo's conventions and live state. This is exactly §1
  and §2 above: `CLAUDE.md` + the memory bank.
- **④ Specific + Vertical** — the single most proprietary quadrant: this product's file
  formats, APIs, personas, regulatory frame, workflows. It lives in an auto-scaffolded
  `Project_Specific_Context/` plugin and is **fed per-SDLC-stage** via the plugin's
  `wiring.stage_context` map (`discover_plugins.py`): the requirements stage gets personas
  + regulatory + constraints; the architecture stage gets integrations + constraints; and
  so on. Each role agent receives **only the slice its stage needs**, as binding domain
  context.

**Why the 2×2 is a token/rework strategy, not just taxonomy:**

1. **No prompt carries everything.** Knowledge is partitioned so any one request loads only
   the relevant quadrant(s) at the relevant altitude. You never pay to stuff software-craft
   *and* product internals *and* subject theory into a single window.
2. **Reuse is banked at the right layer.** Craft (①) is written once for all projects;
   subject expertise (②) once per field; only quadrant ④ is genuinely per-product. That is
   the maximum-reuse, minimum-duplication factoring — duplication is the root cause of both
   drift and wasted tokens.
3. **Right knowledge → less rework.** The classic expensive failure is an agent producing
   plausible-but-wrong output because it lacked a product constraint (④) or a domain fact
   (②). Stage-scoped infusion puts that fact in front of the agent *before* it acts, which
   is orders of magnitude cheaper than catching the mistake after.
4. **Presence is activation.** Because a plugin is auto-discovered by its mere presence,
   adding product context needs **no edit to any base asset** — no wiring, no registry, no
   re-plumbing that would itself burn review tokens.

---

## AgentForge's USP over generic agent tools

Beyond the three mechanisms above, these are the differentiators worth naming:

- **⭐ Engineering-discipline packs — build real AI/ML/firmware products, not just apps.**
  This is AgentForge's headline differentiator. On top of the generic SDLC sit
  **product-domain disciplines** under `skills/ENGINEERING/`, each a manifest-first pack of
  agents + commands + skills + hooks that a project activates by declaring one line
  (`active_disciplines`):
  - **`ai-ml`** (ADR-0014) — take an objective to a **training-ready model**: `/dataset-scout`
    (find + license-check a dataset), `/auto-label` (zero-shot Grounding-DINO/SAM), `/synth-data`
    (Replicator/BlenderProc when real data is missing), `/model-select` (pretrained backbone +
    transfer recipe), `/model-build` (**generate the PyTorch/TF model + training script** as a
    cloud-GPU handoff package). AgentForge builds the model; only the GPU training run happens
    outside.
  - **`ai-genai`** (ADR-0011) — build GenAI/agentic products: MCP-server patterns, autonomous
    loops, cost-aware model routing (`/model-route`), a GAN-style build/eval harness
    (`/gan-build`), plus `ai-app-reviewer` and `llm-security-reviewer`.
  - **`embedded`** (ADR-0010) — firmware: MISRA/CERT-C review, linker/startup/`.bss`/vector-table
    correctness, RTOS/ISR safety, and a host→SIL→HIL test ladder, via `embedded-c-reviewer` and
    `embedded-build-resolver`.
  A non-declaring project loads none of a pack (files ship but stay dormant), so the core stays
  lean while the disciplines make AgentForge span **software, AI/ML, GenAI, and embedded** from
  one toolkit — where generic agent tools stop at web-app scaffolding.
- **Two speeds: full pipeline and a fast lane.** Use full `/agentforge` for a new objective; use
  the PRP fast lane (`/prp-plan` → `/prp-implement` → `/prp-pr`) or `--stage` re-entry for
  incremental change, and **`/fix "<defect>"`** (or `/agentforge --fix`) for a one-call
  triage → failing-test → fix → review → PR loop. See `fast_lane_and_defect_fixing.md`.
- **Cost visibility everywhere.** Per-stage token/cost usage is recorded in `run.json` inside a
  run, and **standalone command usage** (commands run outside `/agentforge`) is recorded to
  per-command runlogs and rolled up by `/budget-report --commands` — so spend is visible whether
  or not the orchestrator drove the work.
- **Single source of truth, enforced.** Root `commands/`, `agents/`, `skills/` are
  canonical; the `.claude/` copies are generated and git-ignored. `install.py --verify`
  and `--check-coverage` are single-sourced with the installer, so **drift is detected
  mechanically** rather than discovered as a bug later (the audit that motivated this found
  13 of 20 installed commands had silently diverged while every prior check passed clean).
- **Product-independent core.** The toolkit carries no per-product scaffold; every consumer
  is just another install target receiving the same generic assets plus a neutral template.
  One codebase serves all products without forking.
- **A real SDLC state machine, not a chat loop.** `/agentforge` drives research → PRD →
  epics → tasks → build → review → test → deploy through role-specialized subagents, with
  **human-review gates** and durable run/gate state (`agentforge/src/state/`). You can
  `--resume` after a break instead of re-establishing context.
- **Traceability from requirement to test.** Test plans bind to acceptance criteria and
  TC-IDs (`/test-plan`, `/trace-matrix`, `/test-run`), so coverage is *provable*, not
  claimed — the anti-rework discipline at the QA layer.
- **Progressive disclosure by construction.** Skills are patched in as *references* and
  loaded on route, not pasted upfront — the framework's default posture is "load the
  minimum that the task needs."
- **Seed-once, project-owned artifacts.** `CLAUDE.md`, settings, the memory bank, and the
  product plugin are seeded once and then owned by the project — re-running setup to pick up
  an upstream update **never clobbers** filled-in context. Safe to re-run is a
  prerequisite for a tool you actually keep current.
- **Quality gates as first-class steps.** `/quality-gate`, language reviewers, and a
  holistic `code-reviewer` pass are wired into the flow, so defects are caught at the
  cheapest point on the cost curve.

---

## Further optimization opportunities (critical analysis)

The framework already does the big things right. The following are honest gaps and
higher-leverage refinements, roughly ordered by payoff:

1. **Measure AI token cost per stage.** Today the budget report models *delivery* cost
   (`$/story-point`) and explicitly ignores AI runtime cost. Without per-stage token
   telemetry you are optimizing blind — you cannot see which stage or agent burns the most
   tokens, so you cannot target the biggest win. **Add lightweight token accounting to the
   run state** (`agentforge/src/state/`) and surface a per-stage breakdown. This is the
   single highest-leverage addition to the *prime objective*.
2. **Lint `CLAUDE.md` health, not just presence.** The health check confirms `CLAUDE.md`
   *exists*; it does not flag the two things that quietly inflate cost: (a) unfilled `TODO`
   markers (context the agent will re-derive because it was never captured) and (b) size
   creep past the "keep it short" guidance. **Add a soft check**: warn on residual `TODO`s
   and on a root `CLAUDE.md` over ~N lines.
3. **Detect memory-bank staleness automatically.** `ACTIVE.md`/`PROGRESS.md` carry a
   last-updated date but nothing warns when they age out. A stale memory bank produces
   confidently-wrong work — the worst rework. **Flag context files not touched in N days**
   in the health check or a Stop hook, complementing the existing `/memory-audit`.
4. **Precompute a per-stage context manifest.** `discover_plugins.py` re-globs
   `stage_context` at each stage. For large plugins this is repeated filesystem work; a
   cached manifest (invalidated on plugin change) trims it.
5. **Make per-agent model routing explicit and auditable.** Agents already declare a
   `model:` (opus/haiku). A `model-route` skill exists, but there is no report that shows
   *which* work is going to an expensive model. Surface it, and default mechanical
   sub-tasks (build-error triage, doc updates, coverage bookkeeping) to a cheaper model —
   easy, large, recurring savings.
6. **Prefer retrieval over inclusion for external docs.** Where guidance is currently pasted
   into skills, lean harder on MCP retrieval (context7, memory) so large reference text is
   fetched on demand rather than resident in the prompt.
7. **Fix documentation drift as a gate.** Onboarding guides still show the removed `--type`
   flag; a doc that tells a new user to run a command that now errors is a rework generator
   at the worst moment (first contact). A tiny CI check that greps guides for removed flags
   would keep docs honest cheaply.

---

*Related: `how_to_build_your_project.md` (full workflow), `how_to_install_agentforge.md`
(install), `agentforge_assets.md` (asset inventory),
`agentforge_custom_plugin/README.md` (authoring product context).*
