# Test Plan

Produce a **tool-neutral test plan** traced to requirements: `neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md`, with a
`TC-NN-SS-TT` identifier for every generated test case, extending the existing
`FR → EPIC → Story → AC` chain by one more link (D9).

This is the same artifact the `qa-engineer` agent produces at the AgentForge S6 stage —
but this command lets you run it **standalone, outside `/agentforge`**, on any story set.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /test-plan · Skills: test-plan-generation, tdd-workflow, verification-loop`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/testing/test-plan-generation.md`
> - `agentic-assets/skills/SDLC/tdd/tdd-workflow.md`
> - `agentic-assets/skills/SDLC/testing/verification-loop.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Domain plugins (auto-discovered)

Product/client-specific context lives in custom plugins under
`agentforge_custom_plugin/<Name>/`. Before generating the plan, self-discover: run
`python agentforge_custom_plugin/discover_plugins.py --stage test-plan` (or find
`agentforge_custom_plugin/*/plugin.json` directly and read any plugin whose
`wiring.auto_load` is not `false`), and bind test cases to the **real data formats and
sample fixtures** it prints — honor any named safety constraint by testing
asymmetrically (a false pass may itself be a safety event), same posture `qa-engineer`
already applies when spawned at S6. Absence of plugins is normal — never a blocker.

## Usage

```
/test-plan <path/to/epics-and-user-stories.md | path/to/task-board.md>
/test-plan neuroedge/docs/project_related/<objective-slug>/02-project-plan/epics-and-user-stories.md
/test-plan --push
```

Flags:
- `--push` — after generating the plan, also attempt an upload via the configured
  test-management vendor (prompts once if none is configured, D16). Never required —
  the plan renders fully with no vendor at all (D12). If Zephyr Scale is chosen, set
  `ZEPHYR_BASE_URL` and `ZEPHYR_API_TOKEN` in the environment before pushing — a missing
  or malformed `ZEPHYR_BASE_URL` is reported as a failed upload, never a crash (D12).

## Phase 0 — DETECT

Resolve the input:

| Input | Action |
|---|---|
| Path to `epics-and-user-stories.md` | Trace against every story's ACs |
| Path to `task-board.md` | Cross-reference task IDs into generated test cases (optional context) |
| Empty | Look for `neuroedge/docs/project_related/<objective-slug>/02-project-plan/epics-and-user-stories.md`; if absent, ask |

## Phase 1 — GENERATE

Follow the `test-plan-generation` skill exactly. Parse every story's acceptance
criteria, assign `TC-NN-SS-TT` identifiers, and **list any unmapped AC explicitly** with
the reason — never drop one silently.

## Phase 2 — GATE

`neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md` enters the S6 hard gate. Report the summary and the gate status;
do not imply the plan is final before approval.

## Phase 3 — OPTIONAL PUSH

Only if `--push` was given: check `agentforge/src/qa/vendor_config.py`'s persisted
choice. If unset, prompt (`AskUserQuestion`, main session only, D1) among Zephyr Scale /
none (repo-local) / decide later, and persist the answer. Then attempt the upload via
the configured adapter — a failure here is reported, never silently swallowed, and never
blocks the plan artifact itself from existing (D12).

## Report

```
## Test Plan Created

- File: neuroedge/docs/project_related/<objective-slug>/05-quality/test-plan.md
- Test cases: N (M unmapped — see plan for reasons)
- Gate: S6 — <pending | approved>
- Vendor: <none | Zephyr Scale> <push result if --push>

> Next: /trace-matrix — render the full coverage chain once tests exist.
```

## Standalone vs. orchestrated

- **Standalone (this command):** you run it, you review the plan, you decide when to
  approve the gate.
- **Inside `/agentforge` (S6):** the same artifact is produced by `qa-engineer`, wired
  into the orchestrator's `STAGE_SEQUENCE` as the `test-plan` stage — the orchestrator
  spawns `qa-engineer` and runs the same S6 hard-gate check it already runs for S2/S3.

Either way, the artifact and the skill that produces it are identical — one source of
truth, whether a human drives it here or the orchestrator drives it at S6.
