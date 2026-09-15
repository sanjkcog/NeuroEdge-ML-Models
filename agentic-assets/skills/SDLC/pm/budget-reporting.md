---
name: budget-reporting
description: Report delivery cost and AI runtime cost as two separate, never-blended figures for the active sprint, with a monthly rollup assuming two sprints per month — the procedure /budget-report and the project-manager agent both follow.
origin: NeuroEdge
---

# Budget Reporting

Produces a per-sprint budget report and an optional monthly rollup, always as **two
distinct figures** — delivery cost (completed story points × a configured `1 SP = $X`
rate) and AI runtime cost (agent token/API spend) — never summed into one number (D20).

## When to Activate

- `/budget-report` or `/budget-report --monthly` is invoked directly
- A human needs cost visibility without opening Jira or a billing dashboard

## Inputs

Resolve the active sprint with `sprint_state.resolve_sprint(path)`. Read
`.claude/pm/budget-config.json` via `budget.RateConfig.load()` for the persisted `$/pt`
rate. For `--monthly`, resolve every `sprint-*.json` container available and pass them
to `budget.monthly_rollup()`.

## Procedure — default (per-sprint)

1. **Resolve the sprint.** No active sprint: report that plainly.
2. **Load the rate config.** If unset (`RateConfig.rate_usd_per_point is None`), this is
   the commitment-time elicitation point (D16 pattern, mirroring the Jira/vendor
   choice) — prompt in the main session, persist the answer, then proceed. **Never
   default the rate to zero or a guess** (US-08-08 failure case) — if the human
   declines to set one now, report delivery cost as unavailable with the reason and
   still compute runtime cost.
3. **Call `budget.compute_budget_report(sprint, rate_config)`.** Report both figures.
   A sprint with zero completed points **and** a configured rate reports a real,
   computed `$0` delivery cost — distinct from "unavailable" (US-08-08 boundary case).
4. **Never sum the two figures.** State them side by side, each labelled — delivery
   cost is explicitly marked **modelled, not actual**, since it derives from points and
   a rate rather than logged time (D20).

## Procedure — `--monthly`

1. **Resolve every sprint container for the target month** (by each `sprint-NN.json`'s
   `opened_at`).
2. **Call `budget.monthly_rollup(sprints, month=...)`.** State the two-sprints-per-month
   assumption explicitly in the output, never as a silent constant. A month with 1 or 3
   sprints reports its **actual** count and names the deviation from the assumption.
3. **Name incomplete sprints, never treat them as zero spend.** A sprint whose container
   was never refreshed (`runs` empty) is listed as incomplete with the gap named — the
   total excludes it rather than silently under-reporting as though its spend were $0
   (US-08-09 failure case).
4. **Disclose the breakdown limitation.** `sprint-NN.json`'s `runs` accumulator stores
   each run's cumulative usage, not a per-stage or per-model split (that detail exists
   only in the currently-active `run.json`, which has no archival — ADR-0005). State
   this explicitly rather than fabricating a by-model/by-stage breakdown the data
   doesn't support.

## Procedure — `--commands` (standalone command usage, TD-002)

Commands run **outside** `/agentforge` have no `run.json`/sprint container, so their token/cost
usage is recorded in per-command runlogs under `neuroedge/docs/project_related/misc/` instead
(`runlog-<command>-<arg-slug>.md`, one file per command+args, one row per invocation). Roll them up:

```bash
python agentforge/src/state/usage_state.py report          # add --json for machine output
```

Print the per-command + total table it returns. Report it as a **third, separate** figure — never
summed with the sprint's AI runtime cost or delivery cost. **No double-counting:** the standalone
ledger holds only non-orchestrated invocations; usage generated inside `/agentforge` lives on the
stage in `run.json`/`sprint-NN.json`. The two never overlap.

**How a standalone command's usage gets recorded (the convention).** At the end of a command run
that was *not* driven by the orchestrator, record the invocation with the token counts the session
knows — the same caller-provided numbers `/agentforge` passes to `run_state complete` for a stage:

```bash
python agentforge/src/state/usage_state.py record \
  --command <name> --args "<the command's args>" \
  --tokens-in <n> --tokens-out <n> --api-calls <n> --cost-usd <c> --model <id>
```

This mirrors `run_state`'s cost model (cost is caller-provided; there is no invented price table).
Fully-automatic capture is not possible from a hook alone — Claude Code does not hand token counts
to hooks — so recording is this explicit call; adoption is per-command and incremental.

## Output Format — default

```markdown
# Budget Report: <sprint-id>

| Category | Value |
|---|---|
| Delivery cost (modelled, not actual) | $N (M pts × $X/pt) — or "unavailable: <reason>" |
| AI runtime cost | $N |

These two figures are never summed (D20).
```

## Output Format — `--monthly`

```markdown
# Monthly Budget Rollup: <YYYY-MM>

Assumed sprints/month: 2 — actual this month: N <(matches assumption) | (deviation noted)>

| Sprint | Runtime cost | Data |
|---|---|---|
| sprint-01 | $N | complete |
| sprint-02 | — | INCOMPLETE — never refreshed |

Total (complete sprints only): $N

Note: breakdown by model/stage is not available from the sprint container's current
data — only per-sprint totals are computed (see skill Notes).
```

## Gate delegation

Neither report opens a gate — this skill never calls `AskUserQuestion` except to
elicit the `$/pt` rate on first use, and even that elicitation is explicitly delegated
to the main session (D1), matching `sprint-planning`'s own gate-delegation posture.
