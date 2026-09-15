# Budget Report

Report delivery cost and AI runtime cost for the active sprint as two separate,
never-blended figures (D20), or roll up AI runtime cost across a calendar month
assuming two sprints per month.

This is the same reporting `project-manager` produces in the PM lane — but this command
lets you run it **standalone, outside `/agentforge`**.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /budget-report · Skills: budget-reporting, agentic-engineering`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/pm/budget-reporting.md`
> - `agentic-assets/skills/SDLC/development/agentic-engineering.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Domain plugins (auto-discovered)

Product/client-specific context lives in custom plugins under
`agentforge_custom_plugin/<Name>/`. Before computing, self-discover: run
`python agentforge_custom_plugin/discover_plugins.py --stage sprint-close` (or find
`agentforge_custom_plugin/*/plugin.json` directly and read any plugin whose
`wiring.auto_load` is not `false`), and use its glossary/workflow context so the report
reads in domain-accurate terms. Absence of plugins is normal — never a blocker.

## Usage

```
/budget-report
/budget-report --monthly
/budget-report --commands
```

Flags:
- `--monthly` — aggregate AI runtime cost across every sprint container falling in the
  current calendar month, stating the two-sprints-per-month assumption explicitly and
  naming any sprint with incomplete (never-refreshed) usage data rather than treating
  it as zero spend.
- `--commands` — report **standalone command** token/cost usage (TD-002): commands run
  **outside** `/agentforge` (e.g. `/model-route`, `/test-plan` invoked directly) record
  their usage under `neuroedge/docs/project_related/misc/runlog-<command>-<arg-slug>.md`, not in any
  `run.json`. This flag rolls those up:
  ```bash
  python agentforge/src/state/usage_state.py report
  ```
  Print its per-command + total table. This is a **separate** figure from the sprint's
  orchestrated AI runtime cost — never sum the two: the standalone ledger holds only
  non-orchestrated invocations, and usage generated inside `/agentforge` stays on the
  stage in `run.json`/`sprint-NN.json`, so they never overlap (no double-counting).

## Phase 0 — DETECT

Resolve the active sprint via `sprint_state.resolve_sprint(path)`. For `--monthly`,
resolve every `sprint-*.json` container whose `opened_at` falls in the target month.

## Phase 1 — COMPUTE

Follow the `budget-reporting` skill exactly. If no `$/pt` rate is configured, this is
the elicitation point (D16 pattern) — prompt in the main session, persist, then
proceed; declining still computes AI runtime cost with delivery cost marked
unavailable, never defaulted to zero.

## Report

```
## Budget Report: sprint-01

<rendered table per budget-reporting's Output Format — two figures, never summed>

> Next: /sprint-report --close once the sprint is done, for the full completion report.
```

## Standalone vs. orchestrated

- **Standalone (this command):** you run it whenever you want a cost read.
- **Inside `/agentforge`:** the PM lane's `refresh()` keeps the underlying
  `sprint-NN.json` usage data current on every dev/QA stage transition; the
  orchestrator's `sprint-close` stage (S12) calls this command as part of its closure
  bundle (alongside `/sprint-report --close`/`--burndown`) only when this run is the one
  that actually closes the sprint.

Either way, the artifact and the skill that produces it are identical — one source of
truth, whether a human drives it here or the orchestrator drives it.
