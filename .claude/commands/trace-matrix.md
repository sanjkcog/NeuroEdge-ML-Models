# Trace Matrix

Render the full **`FR → EPIC → Story → AC → TC → test → result → defect`** chain and
**fail loudly** on any uncovered MUST-priority acceptance criterion — coverage
enforced, not decorative.

This is the same artifact `qa-engineer` produces at the AgentForge S6b stage — but this
command lets you run it **standalone, outside `/agentforge`**, any time after
`/test-plan` has generated TC-IDs.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /trace-matrix · Skills: trace-matrix`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/testing/trace-matrix.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Domain plugins (auto-discovered)

Product/client-specific context lives in custom plugins under
`agentforge_custom_plugin/<Name>/`. Before rendering, self-discover: run
`python agentforge_custom_plugin/discover_plugins.py --stage trace-matrix` (or find
`agentforge_custom_plugin/*/plugin.json` directly and read any plugin whose
`wiring.auto_load` is not `false`) so a plugin's own priority/constraint context informs
which uncovered ACs are the most consequential to name first. Absence of plugins is
normal — never a blocker.

## Usage

```
/trace-matrix
/trace-matrix neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md
```

No flags — the matrix always renders from `neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md` and the current
backlog/story set; there is nothing to configure.

## Phase 0 — LOAD

Read `neuroedge/docs/project_related/<objective-slug>/02-project-plan/epics-and-user-stories.md` and `neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md`.
If either is missing, stop and name which one — do not guess at a partial matrix.

## Phase 1 — RENDER

Follow the `trace-matrix` skill exactly. Walk every FR → EPIC → Story → AC, attach the
TC-ID and any available execution result, and render the full chain.

## Phase 2 — VERDICT

If any MUST-priority AC has no TC-ID at all, **fail loudly**: name every such AC and
why, and report the render as `FAILED`, not as a warning. This must never render with
no vendor configured as an excuse to skip — the matrix is repo-local by design (D12).

## Report

```
## Trace Matrix Rendered

- File: neuroedge/docs/project_related/<objective-slug>/05-quality/traceability.md
- MUST coverage: N/M (100% required)
- Verdict: PASS | FAILED — <N> uncovered MUST AC(s) named in the matrix

> Next: address any FAILED ACs by generating their missing test cases via /test-plan,
> then re-run /trace-matrix.
```

## Standalone vs. orchestrated

- **Standalone (this command):** you run it any time after `/test-plan`, on demand.
- **Inside `/agentforge` (S6b):** the same artifact is produced by `qa-engineer`, wired
  into the orchestrator's `STAGE_SEQUENCE` as the `trace-matrix` stage — a `FAILED`
  verdict here stops the run (this is a fail-loud check, not a `gates.json` entry).

Either way, the artifact and the skill that produces it are identical.
