# Sprint Report

Render burn-down and velocity for the active sprint, or close a sprint into a
committed-vs-delivered completion report that returns carry-over to the backlog rather
than dropping it.

This is the same reporting `project-manager` produces from the PM lane and at sprint
close (S12) — but this command lets you run it **standalone, outside `/agentforge`**,
same posture `/trace-matrix` already established for `qa-engineer`.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /sprint-report · Skills: sprint-reporting, agentic-engineering`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/pm/sprint-reporting.md`
> - `agentic-assets/skills/SDLC/development/agentic-engineering.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Domain plugins (auto-discovered)

Product/client-specific context lives in custom plugins under
`agentforge_custom_plugin/<Name>/`. Before rendering, self-discover: run
`python agentforge_custom_plugin/discover_plugins.py --stage sprint-close` (or find
`agentforge_custom_plugin/*/plugin.json` directly and read any plugin whose
`wiring.auto_load` is not `false`), and use its glossary/workflow context so the
burn-down and completion report read in domain-accurate terms. Absence of plugins is
normal — never a blocker.

## Usage

```
/sprint-report --burndown
/sprint-report --close
```

Flags:
- `--burndown` — render remaining vs. committed points and velocity from closed
  sprints. Never blocks, never requires Jira (D12) — renders from `sprint-NN.json`
  alone, labelling the data's staleness against its own `updated` timestamp.
- `--close` — close the active sprint, returning any undelivered item to the backlog as
  carry-over (never dropped) and tracing every delivered item back through
  `US -> EP -> FR`.

## Phase 0 — DETECT

Resolve the active sprint via `sprint_state.resolve_sprint(path)`. No active sprint:
report that plainly, nothing to render.

## Phase 1 — RENDER

Follow the `sprint-reporting` skill exactly for the flag given. `--burndown` never
requires Jira or a live refresh — it reads whatever `sprint-NN.json` currently holds
and states its own staleness. `--close` requires the sprint be open; closing an
already-closed sprint is refused, naming the status.

## Report

```
## Sprint Burn-down: sprint-01
(or)
## Sprint Completion: sprint-01

<rendered table per sprint-reporting's Output Format>

> Next: /budget-report for the sprint's two-category cost figures.
```

## Standalone vs. orchestrated

- **Standalone (this command):** you run it whenever you want a read on the sprint.
- **Inside `/agentforge`:** the PM lane calls `refresh()` on every dev/QA stage
  transition to keep the data this command reads current; the orchestrator's
  `sprint-close` stage (S12) fires at the sprint boundary, not per run (D24) — it asks
  whether this run should close the sprint, and only then calls `--close` and
  `--burndown` (bundled with `/budget-report`) for real; otherwise both stages complete
  with a note that closure is deferred to whichever run actually closes it.

Either way, the artifact and the skill that produces it are identical — one source of
truth, whether a human drives it here or the orchestrator eventually drives it at S12.
