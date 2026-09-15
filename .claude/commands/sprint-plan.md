# Sprint Plan

Commit a capacity-bound sprint backlog into `sprint-NN.json`, the cross-run container
(D23) many `/agentforge` runs enrol into, splitting any story that cannot finish inside
the sprint rather than letting it straddle a boundary (US-08-04), and opening the S5
sprint-plan hard gate before any dev/QA stage may proceed.

This is the same artifact the `project-manager` agent produces at the AgentForge S5
`sprint-plan` stage — but this command lets you run it **standalone, outside `/agentforge`**, same
posture `/test-plan` already established for `qa-engineer`.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /sprint-plan · Skills: sprint-planning, agentic-engineering`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/pm/sprint-planning.md`
> - `agentic-assets/skills/SDLC/development/agentic-engineering.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Domain plugins (auto-discovered)

Product/client-specific context lives in custom plugins under
`agentforge_custom_plugin/<Name>/`. Before committing the plan, self-discover: run
`python agentforge_custom_plugin/discover_plugins.py --stage sprint-plan` (or find
`agentforge_custom_plugin/*/plugin.json` directly and read any plugin whose
`wiring.auto_load` is not `false`), and use its glossary/workflow context so the sprint
backlog reads in domain-accurate terms. Absence of plugins is normal — never a blocker.

## Usage

```
/sprint-plan --open --capacity 40
/sprint-plan
```

Flags:
- `--open` — open a new `sprint-NN.json` container with `--capacity <points>` before
  committing. Without an active sprint, committing is refused (US-08-02) rather than
  silently opening a single-feature sprint.
- `--capacity <points>` — declared capacity in story points, required with `--open`.

## Phase 0 — DETECT

Resolve the active sprint via `sprint_state.resolve_sprint(path)`. No active sprint and
no `--open` flag: prompt the human rather than guessing (US-08-02 boundary case).

## Phase 1 — COMMIT

Follow the `sprint-planning` skill exactly. Build the candidate backlog from
`task-board.md` (or `epics-and-user-stories.md` if no board exists), check each item
against remaining capacity with `fits_within_capacity`, and propose a split at any item
that doesn't fit — confirmed at the gate, never applied silently.

## Phase 2 — SYNC

Attempt a best-effort Jira push per `jira_config`'s persisted choice (D16 pattern). A
failure is reported, never silently swallowed, and never blocks local commitment (D12,
OQ-7/ADR-0005).

## Phase 3 — GATE

`neuroedge/docs/project_related/<objective-slug>/03-execution-plan/sprint-NN.json` enters the S5 hard gate,
opened in that objective's `gates.json` (the `sprint-planning` skill, step 6). Report the summary and the gate status; do
not imply the commitment is final before approval.

## Report

```
## Sprint Plan Committed

- File: neuroedge/docs/project_related/<objective-slug>/03-execution-plan/sprint-01.json
- Capacity: N pts / Committed: M pts / Remaining: R pts
- Split stories: N (see plan for seams)
- Jira: <not configured | pushed | failed: reason>
- Gate: S5 — <pending | approved>

> Next: /sprint-report --burndown once the sprint is underway.
```

## Standalone vs. orchestrated

- **Standalone (this command):** you run it, you review the commitment, you decide when
  to approve the gate.
- **Inside `/agentforge` (S5):** the same artifact is produced by `project-manager`,
  wired into the orchestrator's `STAGE_SEQUENCE` as the `sprint-plan` stage, after
  `tasks` (S4) and before `test-plan` (S6) — the S5 hard gate is checked the same way as
  S2/S6/S7, and the PM lane's non-blocking refresh() starts here.

Either way, the artifact and the skill that produces it are identical — one source of
truth, whether a human drives it here or the orchestrator drives it at S5.
