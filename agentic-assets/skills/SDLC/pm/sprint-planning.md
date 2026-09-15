---
name: sprint-planning
description: Open or enrol into a cross-run sprint container, commit a capacity-bound backlog with the one-story-one-sprint split rule, and open the S5 sprint-plan hard gate — the procedure /sprint-plan and the project-manager agent both follow.
origin: NeuroEdge
---

# Sprint Planning

Produces or updates `sprint-NN.json`: the cross-run sprint container (D23) that many
`/agentforge` runs enrol into. Commits a capacity-bound backlog built from
`task-board.md`, splits any story that cannot finish inside the sprint rather than
letting it straddle a boundary (US-08-04), and opens the S5 sprint-plan hard gate before any
dev/QA stage may proceed.

## When to Activate

- `/sprint-plan` is invoked directly
- The orchestrator spawns `project-manager` at stage S5 — the `sprint-plan` stage in
  `run_state.STAGE_SEQUENCE`, after `tasks` (S4) and before `test-plan` (S6); see
  `commands/agentforge.md`. The same procedure also runs standalone via `/sprint-plan`.
- A human needs a sprint committed before build work starts

## Inputs

Resolve the active sprint with `sprint_state.resolve_sprint(path)`. Read
`neuroedge/docs/project_related/<objective-slug>/02-project-plan/task-board.md` for the candidate backlog (fall back to
`neuroedge/docs/project_related/<objective-slug>/02-project-plan/epics-and-user-stories.md` if no task board exists for
the target EPIC — the same fallback this EPIC itself needed, since EP-08 has no
`TS-08-*` board yet). Read `.claude/pm/jira-config.json` via `jira_config.load()` to
know whether a Jira push should be attempted after commitment.

## Procedure

1. **Resolve the active sprint.** Call `sprint_state.resolve_sprint(path)`. If `None`
   (no sprint file exists), **do not silently open one** — prompt the human to open a
   sprint with a declared capacity (US-08-02 boundary case: "with no active sprint at
   S5, the orchestrator prompts to open one rather than silently creating a
   single-feature sprint"). If the sprint exists but is `closed`, this is a hard
   failure — `resolve_sprint(path, require_open=True)` raises `SprintNotOpen` naming
   the actual status; do not reopen it silently.

2. **Build the candidate backlog.** Pull items from `task-board.md` (or
   `epics-and-user-stories.md`'s stories if no board exists), each with a story-point
   estimate. **Points are elicited here, not sourced upstream** — neither
   `task-board.md` nor `epics-and-user-stories.md` carries points today (only hour
   estimates and MoSCoW priority), so this is the commitment-time elicitation point,
   mirroring D16's "elicited once, persisted" pattern already used for the `$/pt`
   budget rate.

3. **Check each item against remaining capacity.** Call
   `sprint_state.fits_within_capacity(remaining=sprint.remaining_capacity(), points=item_points)`.
   An item that fits whole is committed via `commit_item`. An item that does **not**
   fit is a split candidate — go to step 4. A story exactly filling remaining capacity
   is committed **whole**, never split (US-08-04 boundary AC — `fits_within_capacity`
   already returns `True` at the exact boundary, so this falls out of step 3 rather
   than needing a separate check).

4. **Propose a split at a real task seam.** Call
   `sprint.split_story(story_id, points=total_points, first_points=<capacity-filling amount>)`.
   If no task seam produces two positive halves, `split_story` raises `ValueError`
   naming the story as un-splittable (US-08-04 failure case) — report it and hold the
   story out of the sprint rather than committing it to straddle. **The split is
   proposed here and confirmed at the gate in step 6 — never applied silently.**

5. **Attempt a best-effort Jira push.** If `jira_config.is_configured()`, call
   `jira_sync.push_sprint_backlog(sprint, config, jira_tool=...)`. A failure is
   reported in the output and does **not** block local commitment — `sprint_state` was
   already saved before this step (US-08-03: "a Jira write that fails leaves local
   sprint state unchanged"). With no Jira configured, state this explicitly and
   continue — nothing here is blocked on procurement (D12, OQ-7/ADR-0005).

6. **Open the S5 sprint-plan hard gate.** `sprint-NN.json` is a gated artifact that lives in the
   objective folder, `neuroedge/docs/project_related/<objective-slug>/03-execution-plan/sprint-NN.json`, beside that
   objective's `gates.json` (`commands/agentforge.md` "Artifact layout"); the fail-closed fallback
   list in `pre-write-hitl-gate.js` covers `<objective-slug>/03-execution-plan/sprint-*.json`. Open
   the gate in that objective's ledger, keyed by the file's project-root-relative path:
   ```bash
   GATES="neuroedge/docs/project_related/<objective-slug>/03-execution-plan/gates.json"
   python agentforge/src/state/gate_state.py --path "$GATES" open \
     neuroedge/docs/project_related/<objective-slug>/03-execution-plan/sprint-01.json --stage S5 --type hard
   ```
   Never key it as a bare `sprint-01.json`: a bare key never matches the real file path, so the
   approval would not seal the file against edits.
   State the gate is pending; do not imply the commitment is final before approval.

## Output Format

```markdown
# Sprint Plan: <sprint-id>

## Capacity
| Metric | Value |
|---|---|
| Capacity (pts) | N |
| Committed (pts) | N |
| Remaining (pts) | N |

## Committed Items
| ID | Points | Source split? |
|---|---|---|
| US-05-01 | 10 | no |
| US-05-04a | 20 | split from US-05-04 |
| US-05-04b | 26 | split from US-05-04 |

## Held Out (un-splittable)
| Story | Points | Reason |
|---|---|---|

## Jira Sync
<not configured | pushed | failed: reason>

## Gate
neuroedge/docs/project_related/<objective-slug>/03-execution-plan/sprint-01.json @ S5 (hard) — pending
```

## Gate delegation

`sprint-NN.json` enters a hard gate (S5). This skill does not itself call
`AskUserQuestion` — approving the gate is the main session's job (D1), via
`gate_state.py`'s `open`/`decide` commands, the same mechanism `test-plan-generation`
uses for S6. A subagent running this skill must surface "ready for the S5 gate" in its
returned result and stop there.
