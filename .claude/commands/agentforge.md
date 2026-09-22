---
description: Orchestrate the full SDLC — onboarding through backlog, QA traceability, sprint planning, build, review, ship, deploy, and sprint close (+ enablement) — sequencing existing role agents and standalone commands, persisting state to run.json after every transition.
argument-hint: "<objective>" [--stage <id>] | --stage bootstrap | --fix "<defect>" | --status | --resume | --dry-run (blank objective = you'll be asked for one)
---

## Arguments

$ARGUMENTS — one of:
- `"<objective>"` — the objective for a new or continuing run, e.g. `"PPE detection portal"`. If blank, ask the user for one before doing anything else.
- `--stage <id>` — join the pipeline at an already-wired stage instead of starting at S0
  (EP-07, ADR-0006). For a user who already has some artifacts outside the orchestrator
  — a hand-written `neuroedge/docs/project_related/<objective-slug>/02-project-plan/PRD.md`, epics from a prior `/prd-to-epics` run — this skips
  straight past the stages that already happened rather than redoing them. Valid values
  are every id in `run_state.STAGE_SEQUENCE` (see the stage table below), plus the
  special non-stage value `bootstrap` described next. Note `onboarding` is
  `STAGE_SEQUENCE[0]`, so `--stage onboarding` skips nothing and is equivalent to a plain
  run — if what you want is onboarding *without* an objective, you want `bootstrap`.
- `--stage bootstrap` — the **onboarding fast lane**, and the answer to "I want the legacy
  audit, the memory bank, and the `CLAUDE.md` hierarchy, but I don't have a project
  objective yet." Runs `/legacy-audit . --memory-bank --subfolder-claude --plan` (which
  spawns `legacy-modernizer` with writes authorized), and **requires no objective, inits
  no `run.json`, and advances no stage** — it is intercepted before the state machine,
  exactly like `--fix`. This is what makes AgentForge *ready* for a `project_objective`:
  once bootstrap has produced the memory bank, a later `/agentforge "<objective>"` sees a
  target classified `onboarded` and correctly skips S0 instead of re-scanning. See the
  `--stage bootstrap` procedure below.
- `--fix "<defect>"` — the **defect-fix fast lane**. Instead of the full S0–S17 pipeline, run the
  bounded triage → failing-test → code-fix → verify → review → PR flow for a single reported defect on
  an already-existing objective. Does not init or advance `run.json`. Identical to the standalone
  `/fix` command — both execute `skills/SDLC/development/defect-fix.md`. See the `--fix` procedure below.
- `--status` — print stage, blocker, and owner in one screen, then stop (no stage advances).
- `--resume` — restore stage and gate state after a session break, with no transcript replay, then continue the stage loop if nothing blocks it.
- `--dry-run` — print the remaining stage sequence (and which agent/command each stage
  would use) with zero side effects, then stop. Never writes `run.json`, never spawns
  anything — a preview, not a partial run.

## You run in the main session — never as a subagent

**Do not delegate this command to an agent.** Per decision D1 the orchestrator must run
in the main session: it spawns subagents (a subagent cannot spawn another) and it asks
the user through `AskUserQuestion` (only the main session can). A subagent-typed
`/agentforge` cannot do either, so this command declares no agent type and must be
invoked directly.

## What this does

Sequences the full stage graph — **existing** agents and standalone commands only, no
new ones invented — passing each stage's output forward, and records the run in
`run.json` so it resumes from that file alone if interrupted (FR-02):

The order and gating below follow the canonical SDLC in
[ADR-0008](../docs/decisions/ADR-0008-canonical-sdlc-stages.md). `run.json` advances a single
linear cursor through these ids; the **Dev lane** / **QA lane** labels are the role view.

| # | id | Agent / command | Produces | Gate |
|---|---|---|---|---|
| S0 | `onboarding` | `legacy-modernizer` | `docs/context/REPO_MAP.md`, memory bank | soft (brownfield only — skipped when already `onboarded` or truly `greenfield`, see below) |
| S1 | `research` | `researcher` | `neuroedge/docs/project_related/<objective-slug>/01-research/*.md` | none |
| S2 | `requirements` | `product-manager` | `neuroedge/docs/project_related/<objective-slug>/02-project-plan/PRD.md` | **hard** |
| S3 | `epics` | `epic-writer` | `neuroedge/docs/project_related/<objective-slug>/02-project-plan/epics-and-user-stories.md` | none |
| S4 | `tasks` | `task-writer` | `neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md` | none |
| S5 | `sprint-plan` | `project-manager` | `sprint-NN.json` | **hard** |
| S6 | `test-plan` *(QA lane — derived from the user stories)* | `qa-engineer` | `neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md` | **hard** |
| S7 | `architecture` *(Dev lane)* | `architect` | `neuroedge/docs/project_related/<objective-slug>/04-development/hld.md`, `neuroedge/docs/project_related/<objective-slug>/04-development/lld.md`, `neuroedge/docs/project_related/<objective-slug>/04-development/risk-assessment.md` | **hard ×2 — HLD + LLD, human architect (ADR-0013)** |
| S8 | `build` *(Dev lane)* | `developer` + `tdd-guide`, per task | code + unit tests | none |
| S9 | `test-automation` *(QA lane)* | `qa-automation-engineer` | automated tests bound to TC-IDs | none |
| S10 | `test-run` *(QA lane)* | *(no owning agent — EP-05)* `/test-run` | JUnit XML | none |
| S11 | `triage` *(QA lane)* | `test-triage` | classified failures, filed defects | none |
| S12 | `trace-matrix` *(convergence — release readiness)* | `qa-engineer` produces it; **PM** confirms it | `neuroedge/docs/project_related/<objective-slug>/05-quality/traceability.md` | fail-loud verdict — **not** a `gates.json` entry, see below |
| S13 | `review` *(the PR gate)* | `team-lead` (fans in `code-reviewer`, `security-reviewer`, `pr-test-analyzer`, and language reviewers) | adjudicated verdict | **hard — tied to `gh pr create`, no override** |
| S14 | `ship` | *(none — bookkeeping)* | PR created | unblocked the instant the S13 PR gate is approved; no second ask |
| S15 | `deploy` | `devops` | CI workflow, deploy plan | none — never an actual deploy trigger; runs after both lanes converge |
| S16 | `sprint-close` | `project-manager` | completion report, burndown chart, budget report | none — fires at the sprint boundary, not every run, see below |
| S17 | `enablement` | *(none)* `/product-doc`, `/marketing-video --technical-walkthrough` | product doc, walkthrough video | none — only runs when S16 actually closes the sprint |

**Canonical order (ADR-0008).** The pipeline is linear through the **sprint plan** (S5), then
the **Dev lane** (S7 architecture → S8 build) and **QA lane** (S6 test-plan → S9 automation →
S10 run → S11 triage) — a role view serialized here as one cursor. **Architecture (S7) lives in
the Dev lane, and per ADR-0013 its HLD and LLD are each hard-gated (human-architect approval)**,
amending ADR-0008's original un-gated-architecture decision — a design a human architect signs off
before S8 build. The **QA test-plan (S6) is hard-gated and derives from the user stories**, not architecture.
The convergence **trace-matrix (S12)** is the PM's release-readiness check (requirements ↔ code
↔ tests ↔ results) and runs *before* the **S13 PR review gate**, so the human approving it sees
code, test, triage, and full traceability in one decision. **S14 "ship" carries no gate of its
own: approving S13 *is* shipping**; **deploy (S15) runs after both lanes converge.**

**S0 is conditional — on three states, not two.** Before entering `onboarding`, classify
the target:

```bash
python agentforge/src/state/run_state.py classify-target --project-root .
```

| Verdict | Meaning | S0 action |
|---|---|---|
| `brownfield` | existing source, **no** memory bank | spawn `legacy-modernizer` — this is the case S0 exists for |
| `onboarded` | memory bank present (`docs/context/REPO_MAP.md`) | skip — nothing left to reverse-engineer |
| `greenfield` | no memory bank **and** no meaningful source | skip — nothing to map yet |

This supersedes the original two-state check, which tested only "does `REPO_MAP.md`
exist" and treated its absence as greenfield. That inverted the intent (D26): an
un-onboarded legacy repo has no `REPO_MAP.md` *by definition*, so the repos most needing
the audit were exactly the ones skipped. The old rationale — "`install.py` already seeded
the memory bank" — only ever held for targets where `install.py` had in fact been run, and
that file is not present in every checkout; the classifier now decides from the target's
own contents instead of assuming it.

**S5 epics/tasks/test-plan note.** `tasks` and `test-plan` both only depend on `epics`,
not on each other — a subagent cannot spawn another (D1), so this orchestrator runs them
as fast interleaved sequential calls, not true concurrency, exactly like the PM lane
below. `STAGE_SEQUENCE` is a fixed linear list (`tasks` before `test-plan`) for
simplicity; nothing stops a human from running `/test-plan` earlier by hand if useful —
disclosed here as a deliberate simplification, not a silent scope cut.

State is owned by `agentforge/src/state/run_state.py`, whose CLI you call to record every
transition. It is the single source of truth — write it after every step, never batch.

## Artifact layout (TD-019, decided 2026-07-29 — supersedes TD-011)

> **One objective, one folder.** Every artifact a run produces lives under
> `neuroedge/docs/project_related/<objective-slug>/`, in the numbered stage folder matching what produced
> it. This **supersedes TD-011's track-scoped/PRD-group layout** (`prd/`, `<track>/`, `backlog/`,
> `research/`, `qa/`, `runs/`), which is now the superseded form.
>
> **Decisions are not artifacts.** ADRs and the tech-debt register are *target-level* and live at the
> target's repo-root `docs/decisions/` — never under `project_related/`. `neuroedge/` is the
> implementation surface: the target decides, and asks it to implement. The test for any document is
> *what/why* (→ decisions) versus *how* (→ objective folder).

**One objective folder, all of it:**

```
neuroedge/docs/project_related/<objective-slug>/
  00-objective.md                       the objective statement
  01-research/<topic-slug>.md           S1 research
  02-project-plan/PRD.md                S2 PRD
  02-project-plan/epics-and-user-stories.md   S3 epics
  02-project-plan/task-board.md         S4 tasks
  03-execution-plan/run.json · gates.json · sprint-NN.json   run state
  04-development/hld.md · lld.md        S7 architecture
  04-development/architecture.md        S7 architecture (standalone /architecture)
  04-development/risk-assessment.md     S7 risks
  05-quality/test-plan.md               S6 test plan
  05-quality/test-results.xml · tc-results.{md,json}         S10 results
  05-quality/traceability.md            S12 trace matrix
  06-delivery/                          S14–S15 delivery records
  runlog.md                             the per-stage run log
```

**`<objective-slug>` naming:** `adr-NNNN-<slug>` when the objective implements a recorded ADR (e.g.
`adr-0004-studio-as-configuration-tool`); a plain `<slug>` when it does not. The folder name is the link
back to the decision that authorised the work.

**Concurrent objectives duplicate, they do not share.** Two in-flight objectives touching the same
component each carry their **own** `04-development/hld.md`. A new objective that needs one **copies the
most recent version** — from the newest in-flight objective if there is one, else the newest archived —
and owns its copy from then on. There is deliberately no shared per-track document.

**Full run versus standalone — the discriminator is intent at invocation, not outcome:**

- A **full `/agentforge` run (S0–S17)** gets an objective folder, and keeps it **even if the run does not
  finish** — a run abandoned at S3 still belongs to its objective, because a full run was the intent.
- **Standalone command execution** keeps its state under `neuroedge/docs/project_related/runs/`. A one-off
  command was never an objective and must not manufacture a folder for one.

Mechanical test: does this invocation drive the staged pipeline (is there a `run.json` with an objective)?
Yes → objective folder. No → `runs/`.

**You (the orchestrator) own placement — the role skills write to their default paths; you move each
stage's artifact to its home as part of the per-stage bookkeeping (the same step that appends the runlog
row).** At init, derive `<objective-slug>` from the objective, create
`neuroedge/docs/project_related/<objective-slug>/03-execution-plan/`, and initialise
`run.json`/`gates.json` there (pass `--path`/`--gates-path` for every `run_state`/`gate_state` call this
run). Keep `runlog.md` at the objective-folder root, one level above.

**Invariant: no artifact may remain at a repo-root or bare `neuroedge/docs/…` path once a stage
completes** — a stray `neuroedge/docs/PRD.md` or `neuroedge/docs/hld.md` is a bug, not cosmetic.

**Archive lifecycle:** the tracked archive root is **`neuroedge/docs/project_related/archive/`** (no leading
underscore — see its `README.md` and `CLAUDE.md`). Two uses, same root:
- **Archive at sprint close** — when a sprint closes (S16), move the **whole objective folder** of every
  objective that *completed in that sprint* to `neuroedge/docs/project_related/archive/<objective-slug>/`,
  intact. **Leave any objective with carryover in place** until the sprint in which it actually completes.
  The top level of `project_related/` therefore always shows only in-flight work.
- **Archive-before-overwrite** — a stage re-run that would overwrite a doc artifact first snapshots the
  current file to `neuroedge/docs/project_related/archive/<objective-slug>/<YYYY-MM-DD>/`.

> **Pre-existing content is not retroactively migrated** (TD-019, 2026-07-29). A target that already has
> artifacts in the superseded track-scoped layout leaves them where they are; only new objectives use this
> structure. Do not write a migration that reorganises a target's docs tree.

## Procedure

> ### State-file paths — MANDATORY, never repo root
>
> `run.json` and `gates.json` live **inside the objective folder**, alongside `sprint-NN.json`:
> `neuroedge/docs/project_related/<objective-slug>/03-execution-plan/`. They must **never** be created at
> the repo root — a root `run.json` is a bug (it strands the run's state outside the objective
> folder, so a mid-run handoff can't find it). This holds from the very first `init`, not just at
> sprint close.
>
> **Every `run_state.py` / `gate_state.py` call in the snippets below uses `"$RUN"` / `"$GATES"`.
> These are shorthand for the two objective-folder paths — set them once at the start of each shell
> invocation that touches state** (a fresh shell doesn't remember them):
>
> ```bash
> RUN="neuroedge/docs/project_related/<objective-slug>/03-execution-plan/run.json"
> GATES="neuroedge/docs/project_related/<objective-slug>/03-execution-plan/gates.json"
> ```
>
> Substitute your run's real `<objective-slug>`. Do not fall back to bare `run.json`/`gates.json`;
> if a snippet ever shows a bare name, read it as `"$RUN"`/`"$GATES"`.

### `--status` — one-screen re-orientation, no stage advance

```bash
python agentforge/src/state/run_state.py --path "$RUN" --gates-path "$GATES" status
```

Report the printed output verbatim and stop. Does not touch `run.json` or `gates.json`.
`status` also prints a one-line token summary when telemetry has been recorded.

### `usage` — per-stage token/cost breakdown

```bash
python agentforge/src/state/run_state.py --path "$RUN" usage          # human table
python agentforge/src/state/run_state.py --path "$RUN" usage --json   # machine-readable
```

Prints per-stage input/output tokens, API calls, modelled USD, the totals, and the
top-consuming stage — the place to target cost optimization first. Read-only; never
advances a stage. See the completion step (§ main loop) for how telemetry is recorded.

### `--resume` — restore state after a session break

```bash
python agentforge/src/state/run_state.py --path "$RUN" --gates-path "$GATES" resume
```

Exit code `0` → nothing blocks continuing; proceed to step 2 below at the reported stage.
Exit code `3` → a gate survived the break and is still pending; go straight to the **Gate
check** step below for that artifact before doing anything else. Never skip straight past
a reported blocker.

### `--dry-run` — preview the remaining sequence, no side effects

```bash
python agentforge/src/state/run_state.py --path "$RUN" preview
```

Report the printed output verbatim and stop. Reads `run.json` if it exists (previewing
what's left of an in-progress run); if none exists yet, ask the user for the objective
first so the preview can show the full sequence, but still do not call `init` — `preview`
itself never writes `run.json` or spawns anything, by design (ADR-0006).

### `--stage bootstrap` — onboarding fast lane (no objective, no run.json)

**Intercept this before step 0 below.** `bootstrap` is not a member of `STAGE_SEQUENCE`
and must never be passed to `init --start-stage` (argparse would reject it). Like `--fix`,
it is handled entirely outside the state machine: **no objective is asked for, no
`run.json` or `gates.json` is created, no objective folder is made, and no stage
advances.** Its whole job is to get a target project *ready* to receive a
`project_objective` later.

1. **Classify the target first** — bootstrap is a no-op on two of the three states:
   ```bash
   python agentforge/src/state/run_state.py classify-target --project-root .
   ```
   - **`greenfield`** → stop and say so. There is no existing code to audit; the user
     wants `/agentforge "<objective>"` directly, since a greenfield project starts at S1.
   - **`onboarded`** → tell the user the memory bank already exists and ask with
     `AskUserQuestion` whether to **refresh** it (re-run the audit over the current tree)
     or **stop**. Never silently re-scan and overwrite a memory bank someone curated.
   - **`brownfield`** → proceed to step 2. This is the intended case.
2. **Run the audit with writes authorized**, which is what separates bootstrap from a
   read-only `/legacy-audit`:
   ```text
   /legacy-audit . --memory-bank --subfolder-claude --plan
   ```
   That command spawns `legacy-modernizer` (which holds `Write`/`Edit` for exactly this
   purpose) and produces: `docs/audit/legacy-audit-<date>.md`, `docs/context/REPO_MAP.md`,
   `ACTIVE.md`, `PROGRESS.md`, `OPEN_QUESTIONS.md`, the root `CLAUDE.md`, and subfolder
   `CLAUDE.md` files for areas with distinct commands or risk profiles.
   Pass it the stage's plugin context too — `bootstrap` reuses the `onboarding` stage key:
   ```bash
   python agentforge_custom_plugin/discover_plugins.py --stage onboarding
   ```
3. **Confirm the result is real.** Re-run the classifier; it must now report `onboarded`.
   If it still reports `brownfield`, the audit did not write the memory bank — report that
   plainly rather than claiming success.
4. **Hand off.** Report what was written, then state the next command:

   > ✅ Bootstrap complete — `<repo>` is onboarded and AgentForge-ready.
   > Memory bank: `docs/context/{REPO_MAP,ACTIVE,PROGRESS,OPEN_QUESTIONS}.md` · routing:
   > root + `<n>` subfolder `CLAUDE.md` · audit: `docs/audit/legacy-audit-<date>.md`.
   > Next: `/agentforge "<objective>"` — S0 will now correctly skip as `onboarded`.

Bootstrap is idempotent in effect but not free: re-running it re-audits the tree. Prefer
`/legacy-audit . --risk-only` for a cheap refresh of just the risk register.

### `--fix "<defect>"` — defect fast lane (no S0–S17, no run.json)

When `--fix` is set, **do not** touch `run.json`, do not init a run, and do not enter the stage loop.
Instead run the shared defect-fix procedure — the exact same flow as the standalone `/fix` command, so
the two are interchangeable:

1. **Read `agentic-assets/skills/SDLC/development/defect-fix.md`** and execute its six phases in order,
   in the **main session** (it spawns agents and opens the PR gate — D1):
   triage (`test-triage`) → **stop if flake/env** → failing test (`tdd-guide`) → code-fix (the matching
   build-resolver / `developer` / `silent-failure-hunter`, minimal diff) → verify (red→green, no
   regressions) → review (`code-reviewer`, +`security-reviewer` if input/auth/secrets) → ship
   (`/prp-commit` → `/prp-pr`, hard PR gate via `AskUserQuestion`).
2. If triage classes it **flake/environment**, report that and stop — a fast-lane fix does not change
   product code for a non-bug.
3. If the fix would need an **architectural** change, stop and tell the user to run `/agentforge`
   proper — the fast lane is minimal-diff only.
4. **Keep the audit run log** at `<project_related>/<fix-slug>/runlog.md`. `<fix-slug>` is the design
   document's file name when the argument is a DD or ADR, else `fix-<date>-<slug>`. Follow the skill's
   **Audit run log** section exactly: create it before triage and append after every phase, covering
   triage, failing test, fix, verify, review and ship. It records the base commit, the baseline failing
   ids, the agents, tokens and main-session corrections, and closes with a files-touched table and
   commit SHA(s) taken from git. It is committed with the fix, and re-runs append `## Run N` rather
   than overwriting. This is the one exception to "standalone state lives under `runs/`": a fix's audit
   record sits beside the decision it implements.

`--fix` is deliberately outside the stage machine (like the PRP fast lane): one defect in, one PR out,
no `run.json`. For a change that warrants the full gated pipeline, use `/agentforge "<objective>"`.

### 0 — Resolve the objective

Read `$ARGUMENTS`. **If it is `--stage bootstrap`, stop here and run the bootstrap fast
lane above instead** — that mode is defined as needing no objective, so asking for one is
a bug, not diligence. Otherwise, if the objective is empty, ask the user for it with
`AskUserQuestion` and wait. Do not invent one.

Every other path through this command inits `run.json`, and `init --objective` is
`required=True` in `run_state.py` — so there is no way to enter the stage loop without an
objective, `--stage <id>` included. If a user reaches for `--stage onboarding` to get an
audit without an objective, route them to `--stage bootstrap`.

### 1 — Guard an existing run (do not clobber)

```bash
test -f "$RUN" && echo EXISTS || echo NONE
```

(Check the file directly, not `status`'s exit code — `status` now exits 0 even when
`run.json` is missing, printing `No run in progress` rather than erroring, per
`TS-02-03-03`.)

- **NONE** → initialise:
  ```bash
  python agentforge/src/state/run_state.py --path "$RUN" init --objective "<objective>"
  ```
  **If `--stage <id>` was given**, add `--start-stage <id>` to the same command instead:
  ```bash
  python agentforge/src/state/run_state.py --path "$RUN" init --objective "<objective>" --start-stage <id>
  ```
  This marks every stage before `<id>` complete with a note that it was supplied outside
  this run (never fabricated as if `/agentforge` produced it), and sets the cursor to
  `<id>` — step 2 below then naturally starts there, since it already skips any stage
  already `complete`. Confirm with the user which artifacts already exist for the
  skipped stages before proceeding, so the record is accurate.
- **EXISTS** → **stop and ask with `AskUserQuestion`**: resume the existing run, or start
  over? Only on an explicit "start over" re-run `init` with `--force`. A silent overwrite
  would discard a partially-completed run — never do it without the user's answer.
  `--stage` on an existing run is not meaningful — resume or start over, then use
  `--stage` only on the fresh `init` that follows a "start over" answer.

### 2 — Drive the stages in order

For each stage in `run_state.STAGE_SEQUENCE`, in order, skipping any already `complete`
in `status`:

0. **`onboarding` only**: classify the target — never eyeball it:
   ```bash
   python agentforge/src/state/run_state.py classify-target --project-root .
   ```
   - **`brownfield`** → continue with steps 1–4 below as normal, spawning
     `legacy-modernizer`. Tell it explicitly that memory-bank writes are authorized for
     this stage (it is read-only by default), so S0 actually produces
     `docs/context/REPO_MAP.md` and the memory bank rather than only describing them.
   - **`onboarded`** → mark the stage complete without spawning anything:
     ```bash
     python agentforge/src/state/run_state.py --path "$RUN" complete onboarding \
       --artifact "(skipped — target already onboarded, memory bank present)"
     ```
   - **`greenfield`** → same, with the greenfield reason:
     ```bash
     python agentforge/src/state/run_state.py --path "$RUN" complete onboarding \
       --artifact "(skipped — greenfield target, no existing code to map)"
     ```
   Then move to the next stage. Record the classifier's actual verdict as the reason —
   the two skip notes are not interchangeable, and a run that skipped S0 should say which
   of the two reasons applied.
1. Mark it in progress **before** spawning (this is what lets an interrupted stage resume
   instead of being skipped):
   ```bash
   python agentforge/src/state/run_state.py --path "$RUN" start <stage>
   ```
   Then **emit that stage's NeuroEdge Assets banner** so the operator sees which role,
   agent, and skills are active this stage: echo the exact
   `[ NeuroEdge Assets ]  Role: … · Agent: … · Skills: …` line declared at the top of that
   stage's agent definition (for a command-only stage — `test-run`, `ship`, `enablement` —
   echo that command's own banner line instead). Do this in the main session: otherwise the
   banner exists only inside the spawned subagent's transcript, which is never surfaced, so
   the role/agent/skills visibility that direct slash-command use gives would be lost inside
   an orchestrated run.
2. **Auto-discover domain plugins for this stage** (see "Domain plugins" below — every
   stage id in `STAGE_SEQUENCE` is a valid `--stage` argument to `discover_plugins.py`,
   including the new S6–S12 ones), then act according to the stage's own kind:
   - **Agent-owned stages** (`onboarding`, `research`, `requirements`, `architecture`,
     `epics`, `tasks`, `test-plan`, `trace-matrix`, `sprint-plan`, `build`,
     `test-automation`, `triage`, `review`, `deploy`, `sprint-close` — see the table's
     Agent column): spawn that stage's agent with the objective, the prior stage's
     artifact path(s), and the discovered plugin context files as binding input. Run:
     ```bash
     python agentforge_custom_plugin/discover_plugins.py --stage <stage>
     ```
     Every path it prints (subject skills first, then plugin context) is passed to the
     agent with the instruction to read those files and treat their constraints as
     **binding domain context**. If it prints only a `# no active-plugin context`
     comment, there is nothing to add — spawn as normal.
   - **Command-only stages with no owning agent** (`test-run`, `ship`, `enablement`):
     invoke the standalone command's own procedure directly (`/test-run`, and for
     `enablement`, `/product-doc` + `/marketing-video --technical-walkthrough`) rather
     than spawning a subagent — there is nothing to spawn. `ship` has no command of its
     own at all; see step 3's review (S13) / ship (S14) handling below.
   - **You** issue every spawn/invocation — every one is attributed to the orchestrator,
     so manual invocations stay at 0.
3. On success, record it — with stage-specific handling for the few stages that are not
   a plain "spawn, get artifacts back" cycle:
   - **`build`**: loop per task from `neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md`
     (this run's own tasks, not the whole sprint's cross-run backlog), spawning
     `developer` with `tdd-guide` for each. Record the stage complete only once every
     task in this run's board is done or explicitly deferred.
   - **`trace-matrix` (S12 — convergence / release readiness)**: this is a **fail-loud
     verdict, not a `gates.json` gate**. `qa-engineer` renders the requirements ↔ code ↔
     tests ↔ results matrix and reports `PASS` or `FAILED`; the **Project Manager** confirms
     it as the release-readiness check. On `FAILED`, name every uncovered MUST-priority AC,
     **stop the run**, do not mark the stage complete, and send the operator back to
     `/test-plan` for the missing cases. Only a `PASS` verdict completes this stage — and it
     runs *before* the S13 PR review, so the reviewer sees full traceability.

     **`PARTIAL` is not a verdict, and this is now enforced (TD-014).** `run_state.py`
     refuses to complete `trace-matrix` unless an artifact carries the verdict
     parenthesised — `--artifact "neuroedge/docs/project_related/<objective-slug>/05-quality/traceability.md (PASS)"`
     — so recording "PARTIAL by design" fails with `REFUSED` and a non-zero exit instead
     of silently closing the stage. That exact string closed S12 early on the ADR-0003
     run, and the backlog then drifted from reality by 118 ACs with nothing contradicting
     it. (`--start-stage` still backfills earlier stages untouched: those artifacts record
     provenance, not a verdict.)

     **Re-run S12 whenever more scope lands after it passed.** Its verdict is only true
     as of the scope it saw, so if `task-board.md` or `epics-and-user-stories.md` gains
     completed work after S12 completed, refresh it **before** S13:
     ```bash
     python agentforge/src/state/run_state.py --path "$RUN" reopen trace-matrix
     ```
     `reopen` re-arms a completed stage (preserving its spawn history, like
     `gate_state`'s `reopen`) so the stage loop executes it again instead of skipping it
     as already-complete. Without this the first verdict stands forever, which is exactly
     how the stale one went unnoticed for five EPICs.
   - **`review` (S13 — the PR gate)**: spawn `team-lead`, which fans in `code-reviewer`,
     `security-reviewer`, `pr-test-analyzer`, and any language-specific reviewer for the
     changed files, and emits **one** verdict. If `team-lead` reports `blocked`, loop
     back to `build` (S8) to address the findings and re-spawn `team-lead` — do not open the
     gate on a blocked verdict. Once `team-lead` reports **pass**, see the dedicated PR gate
     procedure below before attempting `gh pr create`.
   - **`ship`**: no agent, no separate ask — this stage completes the instant `gh pr
     create` succeeds (which only happens once the S13 PR gate is approved; see below).
     Record it complete with the PR URL as the artifact.
   - **`sprint-close` / `enablement`**: see the dedicated procedure below — these two
     only run their real content when this run is the one that closes the sprint;
     otherwise both complete with a note that they're deferred, never fabricated.
   - **Every other stage**: on the agent/command returning success,
     ```bash
     python agentforge/src/state/run_state.py --path "$RUN" complete <stage> \
       --artifact <path1> [--artifact <path2> ...] \
       [--tokens-in <in> --tokens-out <out> --api-calls <n> --cost-usd <c>]
     ```
     **Record token telemetry, with its provenance (TD-018).** Each subagent spawn
     returns its usage; pass those numbers through so the run tracks token cost per
     stage. Read them from the spawned agent's result (input/output tokens; API calls
     and modelled USD if available) and supply the matching flags.

     `--source` states **where the figure came from**, and the ledger reports it:
     - **`measured`** (the default when any figure is supplied) — transcribed from a
       real reported usage figure, i.e. a spawn result.
     - **`estimated`** — derived rather than observed. **Use this for every stage you
       (the orchestrator) performed yourself**, because your own work has no completion
       event to read a figure from: a model cannot observe its own token consumption
       mid-turn. State the method you used in the runlog row.
     - **omit all figures** — records `unrecorded`, which is **not** a zero. The stage
       is listed explicitly in `usage`, excluded from the totals, and the run is flagged
       as reporting a LOWER BOUND rather than a total.

     **Do not fabricate figures.** If a spawn reports no usage, pass nothing — an
     honest `unrecorded` is worth more than an invented number, and a round guess
     presented as `measured` is the specific failure TD-018 records (`19,000` and
     `22,500` appear verbatim across two unrelated runs). An estimate is welcome when it
     is *labelled* `estimated` and its method is stated.

     **A failed stage cost real tokens too.** `fail` now takes the same flags — record
     what the failed attempt consumed rather than losing it:
     ```bash
     python agentforge/src/state/run_state.py --path "$RUN" fail <stage>        [--tokens-in <in> --tokens-out <out> --api-calls <n> --cost-usd <c> --source measured]
     ```
     Usage **accumulates** across passes: a stage that fails, is retried, and then
     completes sums all three, and each pass is preserved in `usage_history`.

     **Show the running SDLC total after every stage.** Immediately after recording a
     stage complete, surface to the operator both (a) that stage's tokens — the `complete`
     command prints `(N tokens)` — and (b) the **cumulative SDLC total so far**, by echoing
     the totals line from:
     ```bash
     python agentforge/src/state/run_state.py --path "$RUN" status
     ```
     Report it each step, e.g. `Stage research: 75,102 tok · SDLC total so far: 75,102 tok`,
     so token consumption is visible as the pipeline progresses, not only at the end. The
     cumulative figure is already computed by `usage_rollup` — this only surfaces it per step.

     **Refresh the PM lane after every stage (TD-017).** Immediately after recording the
     stage complete, fold this run's usage into the sprint container and refresh
     `PROGRESS.md`, so status and progress cannot drift apart:
     ```bash
     python agentforge/src/pm/refresh.py --run "$RUN" --sprint "$SPRINT"        --run-id "$RUN_ID" --progress docs/context/PROGRESS.md
     ```
     **This never fails your stage.** `refresh` always exits 0 and prints its reason —
     its defining contract is that the PM lane never blocks the dev/QA lane. If no sprint
     is open yet it simply reports that and moves on. Skipping it is what let the backlog
     silently become fiction while the code was fine.

     **Project outbound, if the target opted in (TD-021).** After recording the stage
     complete, and **only when `exchange_config.json` has `"auto_export": true` and a provider is
     configured**, project run-state to the external substrate:
     ```bash
     python agentforge/src/exchange/exchange_cli.py export --config-path "$EXCHANGE_CONFIG"
     ```
     **Do not run this on every one of the 18 transitions.** Push at **gate transitions and
     terminal stages** (S2/S5/S6/S7 gates, S13 review, S14 ship, S16 sprint-close) — every
     `push()` writes a commit, so exporting all 18 would put 18
     `chore(agentforge): publish exchange record` commits per run into the target's
     repository. Gate and terminal transitions carry the signal an external monitor needs;
     intermediate ones are noise.

     **This never fails your stage** — same contract as `refresh.py`. An unconfigured
     substrate reports "not projected" via `NoneExchangeAdapter` and is a non-event, not an
     error. If `auto_export` is false (the default), skip this step entirely.

     **Inbound is NOT automatic, and that asymmetry is deliberate.** `import-intents` /
     `apply` mutate local state from an outside source, so they stay explicit human acts —
     ADR-0012 Direction 2's review gate exists to force that decision. Never add an
     auto-import counterpart to this step.

     **Append a run-log row after every stage.** After recording a stage complete, update the
     run log at `neuroedge/docs/project_related/<objective-slug>/runlog.md` (the objective-folder location
     named in the layout above — **not** a shared file at `project_related/` root; create it on the
     first stage if absent) with a
     row capturing: step id + stage, owning agent, the **key output counts** that stage produced
     (e.g. FR count at `requirements`; EPIC/US/AC counts at `epics`; task count + est. hours at
     `tasks`; test-case counts at `test-plan`; files/LOC at `build`; pass/fail counts at
     `test-run`), **two separate token columns — `Tokens (stage)` and `Tokens (cumulative)`** —
     plus the stage's **usage source** (`measured` / `estimated` / `unrecorded`). Counts come
     from the stage's artifact; tokens from `run_state usage`.

     **State the column convention in the runlog header.** Existing runlogs disagree with
     each other — two record per-stage figures and two record a running cumulative, under the
     same unlabelled `Tokens` heading — which makes cross-run comparison invalid (TD-018
     Problem 5). Two labelled columns, or an explicit statement of which one is used. Also keep the run log's gate table current
     when a gate is opened/decided. `run.json` tracks artifacts + usage but not artifact-internal
     counts — this log is the single at-a-glance ledger of "how many FRs/EPICs/US/Tasks and how
     many tokens per step."
   On any stage's agent returning `failed`:
   ```bash
   python agentforge/src/state/run_state.py --path "$RUN" fail <stage>
   ```
   The `fail` command retries once; a **second consecutive** failure exits non-zero and
   escalates. When it escalates, **stop the run** and report to the user — do not force
   past a gate the state machine raised.
4. **File-artifact gate check, before advancing past a gated stage.** `requirements`
   (S2), `sprint-plan` (S5), `test-plan` (S6), and `architecture` (S7 — a **hard gate on each of
   `neuroedge/docs/project_related/<objective-slug>/04-development/hld.md` and `neuroedge/docs/project_related/<objective-slug>/04-development/lld.md`, approved by a human architect**, per ADR-0013 amending
   ADR-0008) are **hard-gated**. The producing agent has no gate CLI, so **you (the orchestrator)
   open the gate** on the artifact it produced, then a human decides before you may advance past it.
   Check before continuing:
   ```bash
   python agentforge/src/state/gate_state.py --path "$GATES" status
   ```
   If it reports anything other than `Blocked: nothing`, **stop** — do not spawn the next
   stage's agent. Ask the user with `AskUserQuestion` (Approve / Request changes /
   Reject; main session only, D1), then record the answer:
   ```bash
   python agentforge/src/state/gate_state.py --path "$GATES" decide <artifact> \
     <approved|changes_requested|rejected> --identity <who> [--reason <text>]
   ```
   Only `approved` clears the block; `changes_requested`/`rejected` leave the artifact
   unapproved and the run halted at that stage until it is re-armed and re-decided:
   ```bash
   python agentforge/src/state/gate_state.py --path "$GATES" reopen <artifact>
   ```
   `reopen` (not `open`) is the correct re-arm command — it resets the gate to `pending`
   while preserving its prior decision history, so a reject → re-arm → approve cycle
   still shows the earlier rejection in the audit trail rather than erasing it.

### The S13 PR gate is different: tied to `gh pr create`, hard, no override

Unlike every other gate, the S13 review gate is not opened on a file artifact — it protects
the actual `gh pr create` call, and D3's original warn-with-override escape hatch has been
reversed: there is no bypass path left at all (`pre-write-hitl-gate.js` blocks unconditionally
on anything but `approved`).

1. Only after `team-lead` (spawned in step 3 above) reports **pass**, open the gate:
   ```bash
   python agentforge/src/state/gate_state.py --path "$GATES" open pr:<branch> \
     --stage S13 --type hard
   ```
2. Attempt the PR: `gh pr create --title "<title>" --body "<body>"`. It will be blocked
   (exit non-zero) because the gate is `pending` — this is expected the first time.
3. Ask the human with `AskUserQuestion` (Approve / Request changes / Reject; main session
   only, D1). **Show `team-lead`'s verdict as part of the ask** — the human is approving
   with the agentforge review already in hand, not blind. Record the answer with that
   context in `--reason`:
   ```bash
   python agentforge/src/state/gate_state.py --path "$GATES" decide pr:<branch> \
     <approved|changes_requested|rejected> --identity <who> \
     --reason "team-lead verdict: <one-line summary>"
   ```
4. **Approved** → retry `gh pr create` — it now succeeds. Mark `review` complete with the
   verdict as its artifact, then `ship` complete with the PR URL.
   **Changes requested / rejected** → the run halts at `review`; address the findings,
   re-spawn `team-lead`, `reopen` the gate, and repeat from step 1 above.

### Sprint close (S16) + enablement (S17): only real when this run closes the sprint

`sprint-close` fires at the sprint boundary (D24), not per run — a single `/agentforge`
run is scoped to one feature, but a sprint spans many runs (D23). Ask the human with
`AskUserQuestion`: close the sprint now, or leave it open for more runs?

- **Close now**: bundle the closure package —
  ```bash
  /sprint-report --close
  /sprint-report --burndown
  /budget-report
  ```
  (`--close` produces the completion report; `--burndown` renders the burndown/velocity
  chart described in `skills/SDLC/pm/sprint-reporting.md`.) Mark `sprint-close` complete
  with all three artifact paths, then immediately run `enablement`:
  ```bash
  /product-doc
  /marketing-video --technical-walkthrough
  ```
  Mark `enablement` complete with those artifact paths.
- **Leave open**: mark both `sprint-close` and `enablement` complete with a note that
  they're deferred to whichever future run actually closes the sprint — never fabricated
  as having produced closure artifacts that don't yet exist.

**Sprint transition (soft nudge — not a gate).** After a **Close now**, emit a sprint-transition
message so the operator is led into the next sprint rather than left at a dead end. From the sprint
report + task board, print: what sprint N delivered, the **carryover backlog** (unfinished +
deferred stories/tasks with hours), velocity, and the **exact next command** to start sprint N+1 —

> ✅ Sprint N closed. Delivered: `<summary>`. Carryover → sprint N+1: `<Hh>` (`<top items>`).
> Start sprint N+1? → `/agentforge --stage sprint-plan` (or `/sprint-plan`) to plan it from the
> carryover backlog.

Starting sprint N+1 is a *scheduling* decision, so this is a message, **not** a hard gate — but the
sprint N+1 **plan still hits the existing S5 sprint-plan hard gate**, where a human approves the new
sprint's committed scope before any build. Do not invent a second gate for the transition itself.

### 3 — Report and verify

When every stage is `complete` (accounting for the `onboarding` skip and any deferred
`sprint-close`/`enablement`), show the run summary and prove the run left this repo's
installed assets undrifted **in the same session**:

```bash
python agentforge/src/state/run_state.py --path "$RUN" status
test -f install.py && python install.py --project . --verify || echo "install.py not present — drift check skipped"
```

The drift check is **conditional because `install.py` is not present in every checkout**
(this repo, for one, has no root `install.py` — only unrelated copies under `venv/`).
Where it exists, run it and report its real result. Where it does not, say the check was
skipped — never print a "zero drift" line for a command that never ran.

Report to the user, naming every stage that ran (or was skipped/deferred, with the
reason) in order, plus:

```
run.json written after every transition · manual invocations: 0
install.py --verify: zero drift   (omit this line entirely when install.py is absent)
```

## Token discipline (measured, not guessed — TD-013)

A full S2→S13 run on one 25h work item cost **1,030,905 tokens**, of which **review was 392,029 (~38%)** and
the pre-code planning stages (S2–S6) were **618,388 (60%)**. Apply these; each is measured, and the two marked
⚠ are things that were *tried and did not work*.

**1. Prevention beats detection — the single highest-leverage rule.** When spawning `developer` at S8, paste
the *specific* defects earlier reviews found in this codebase, and name the converged helper to reuse. On this
run that stopped a whole defect class from recurring at **zero extra token cost**. A review that finds nothing
is far cheaper than one that finds something.

**2. One reviewer by default.** Spawn `security-reviewer` alongside `code-reviewer` only when the diff touches
a trust boundary, authn, secrets, or untrusted input. Two reviewers cost 213K; one cost 96K and still found
2 HIGH.

**3. Review the diff, not the tree.** Give the reviewer `git show <sha>` and tell it to open whole files only
where a finding requires it.

**4. Skip a stage whose artifact already exists.** If an accepted ADR already *is* the architecture, complete
S7 against it and open the hard gate on the ADR rather than generating `hld.md`/`lld.md` that restate it. Same
human sign-off, ~0 tokens. Record the substitution as the stage's artifact so the run stays honest.

**5. Cap review at 2 rounds, then escalate.** If round 2 still returns HIGH, stop and report rather than
looping — three rounds on one item is the signal that the work needs re-scoping, not re-reviewing.

⚠ **Do not "optimize" by weakening the Stop hook or skipping review.** On this run, rounds 1 and 2 each found
real HIGH defects *in the previous round's fixes*, including a CWE-117 sanitiser gap and a `str(exc)` leak.
Reduce cost per round, never the number of gates.

⚠ **Delta re-review via `SendMessage` does not save tokens.** Resuming an agent replays its transcript, so the
prior context is paid for again (measured: 157K to re-verify vs 96K for the original fresh review). It is
still worth using for *quality* — it caught an incomplete fix and a partially-vacuous test that a fresh
reviewer with no memory of the intent would likely have missed — but budget it as a quality step, not a saving.

## Domain plugins (automatic)

Product- and client-specific context lives in **custom plugins** under
`agentforge_custom_plugin/<Name>/` — self-contained bundles of proprietary context (and
optional plugin-scoped agents/commands/skills), separate from these base SDLC assets.

**Discovery is automatic and needs no install step: presence is activation.** Any
`agentforge_custom_plugin/<Name>/plugin.json` with `wiring.auto_load` not set to `false` is
active. For each stage, `discover_plugins.py --stage <stage>` reads each active plugin's
`wiring.stage_context` map and prints the exact context files (plus any reusable
`skills/SUBJECTS/<Subject>` the plugin declares via `requires_subjects`) that stage's agent
must read. You pass those into the spawn (step 2 above). This applies uniformly across
every stage in `STAGE_SEQUENCE`, not only S0–S5 — `discover_plugins.py` returns an empty
result for a stage with no configured context (a plugin author simply hasn't customized
that stage yet), never an error.

The user's only job is to **fill or add files** inside the plugin folder — no base SDLC
asset changes, and adding a brand-new plugin requires no change here. A plugin also ships
its own command (e.g. `/suncheck`) for consulting it directly outside a run.

## Known remaining gap: device-in-the-loop (EP-06)

Phase 6 (`--target device`, deploy → assert → teardown on real hardware) has **no
implementation at all** — not a wiring gap like everything above was, a genuine "not
built yet." `/test-run --target <name>` already provisions non-device environments from
`test-env.json` (EP-05); a `device` target specifically is out of scope for this
extension. Nothing in this command's sequence depends on it.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /agentforge · Skills: agentic-engineering, autonomous-loops`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/development/agentic-engineering.md`
> - `agentic-assets/skills/ENGINEERING/ai-genai/autonomous-loops.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->
