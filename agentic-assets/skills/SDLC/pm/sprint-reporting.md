---
name: sprint-reporting
description: Render burn-down and velocity for the active sprint, or close a sprint into a committed-vs-delivered completion report — the procedure /sprint-report and the project-manager agent both follow.
origin: NeuroEdge
---

# Sprint Reporting

Produces two views over `sprint-NN.json`: a live burn-down/velocity read (`--burndown`)
and a sprint-close completion report (`--close`) that returns carry-over to the backlog
rather than dropping it.

## When to Activate

- `/sprint-report --burndown` or `/sprint-report --close` is invoked directly
- The orchestrator's PM lane refreshes burn-down data on a stage transition (see
  `refresh.py` — this skill's `--burndown` view and the refresh function read the same
  `sprint-NN.json` state, refresh just keeps it current)
- A human needs sprint status or a retrospective starting point without opening Jira

## Inputs

Resolve the active sprint with `sprint_state.resolve_sprint(path)`. For velocity,
resolve every **closed** sprint container available (`sprint-*.json` with
`status == "closed"`) and read each one's `committed_points()` at close time.

## Procedure — `--burndown`

1. **Resolve the sprint.** `None` (no active sprint) is reported plainly — nothing to
   burn down — never a blank or crashed output.
2. **Render remaining vs. committed.** `sprint.remaining_capacity()` is capacity minus
   committed, not remaining-to-deliver — burn-down needs **undelivered** points:
   `committed_points() - sum(points for items where status == "done")`.
3. **Compute velocity from closed sprints.** Sum each closed sprint's delivered points
   (from its own closure report, or recomputed from `committed_items` where
   `status == "done"`). **Boundary case (US-08-06):** with zero closed sprints, state
   "no historical velocity — first sprint" explicitly; never display a zero or
   extrapolate from a single data point.
4. **State staleness explicitly.** Burn-down data is only as current as the last
   PM-lane `refresh()` call. Report the container's own `updated` timestamp next to the
   chart — **do not silently present stale data as live** (US-08-06 failure case: an
   unreachable Jira/refresh path renders from last-known local state, labelled stale
   with its age).
5. **Render the real chart (S16).** Beyond the markdown table above, call
   `burndown_chart.write_burndown_chart(sprint, out_path, velocity=...,
   velocity_sprint_count=...)` (`agentforge/src/pm/burndown_chart.py`) to produce a
   self-contained HTML page — inline SVG, no external requests, same zero-dependency
   posture `neuroedge_productdoc` already established for `docs/guides/*.html` — plotting
   `sprint.burndown_snapshots` (appended by the PM-lane `refresh()` on every dev/QA stage
   transition; this is real history, not a single instant). A sprint with no snapshots
   yet renders an explicit "no data yet" message, never a broken or empty chart. Default
   output path: `docs/reports/sprint-<id>-closure.html`.

## Procedure — `--close`

1. **Resolve the sprint**, requiring it be open (`require_open=True` — closing an
   already-closed sprint is refused, naming the status).
2. **Call `sprint.close()`.** This returns a `ClosureReport(delivered, carry_over)` —
   `delivered` is every item marked `done`; `carry_over` is every item that is not,
   **returned to the backlog, never dropped** (US-08-07 failure case: unresolved
   in-progress items are reported as carry-over and refused as delivered).
3. **Trace delivered items back through the chain.** For each delivered item, cite its
   `US -> EP -> FR` lineage from `epics-and-user-stories.md` so the completion report is
   attributable to requirements, not just a bare ID list.
4. **Save the sprint as closed.** `sprint.save(path)` persists `status: "closed"`, which
   `--burndown`'s velocity computation (step 3 above) then picks up for future sprints.

## Output Format — `--burndown`

```markdown
# Sprint Burn-down: <sprint-id>

Day N — last refreshed: <sprint.updated> (<age>)

| Metric | Value |
|---|---|
| Committed (pts) | N |
| Delivered (pts) | N |
| Remaining (pts) | N |

Velocity: <N pts/sprint (from M closed sprints) | "no historical velocity — first sprint">

Chart: docs/reports/sprint-<sprint-id>-closure.html
```

## Output Format — `--close`

```markdown
# Sprint Completion: <sprint-id>

## Delivered
| ID | Points | Traces to |
|---|---|---|
| US-05-01 | 10 | EP-05 / FR-07 |

## Carry-over (returned to backlog, not dropped)
| ID | Points | Reason still open |
|---|---|---|

Committed: N pts · Delivered: M pts · Carry-over: R pts
```

## Gate delegation

Neither view opens a gate — `sprint-NN.json` was already gated once at S5
(`sprint-planning`); reporting on it is read-only and does not require a fresh
approval. This skill never calls `AskUserQuestion`.
