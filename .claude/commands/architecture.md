# Architecture

Produce a feature's **design contract and risk register** before implementation:
`neuroedge/docs/project_related/<objective-slug>/04-development/architecture.md` (component and sequence diagrams,
interfaces, data flow, finalized patterns) and
`neuroedge/docs/project_related/<objective-slug>/04-development/risk-assessment.md` (implementation, regression, and
security risks with IDs and mitigations).

This is the same artifact set the `architect` agent produces at the AgentForge S3 stage — but
this command lets you run it **standalone, outside `/agentforge`**, on any feature or codebase.
Run it before `/prp-plan` so the plan and build inherit a finalized design instead of improvising
one.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /architecture · Skills: architecture-design, risk-assessment`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/development/architecture-design.md`
> - `agentic-assets/skills/SDLC/development/risk-assessment.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Domain plugins (auto-discovered)

Product/client-specific context lives in custom plugins under
`agentforge_custom_plugin/<Name>/`. Before designing, self-discover: run
`python agentforge_custom_plugin/discover_plugins.py --stage architecture` (or find
`agentforge_custom_plugin/*/plugin.json` directly and read any plugin whose
`wiring.auto_load` is not `false`), and treat what it prints — `context/DOMAIN.md`,
integration interfaces/data-formats, `context/constraints.md`, `context/regulatory.md`,
and any named `skills/SUBJECTS/<Subject>` — as **binding design drivers**, feeding
`RK-NN` risks the same way `architect` already does when spawned at S3. Absence of
plugins is normal — never a blocker.

## Usage

```
/architecture <feature description | path/to/prd.md | path/to/prd-phase>
/architecture "add OAuth login to the portal"
/architecture neuroedge/docs/project_related/<objective-slug>/02-project-plan/PRD.md
/architecture neuroedge/docs/project_related/<objective-slug>/02-project-plan/PRD.md --phase 3
```

Flags:
- `--phase N` — when the input is a PRD, design only that Implementation Phase.
- `--risks-only` — regenerate `neuroedge/docs/project_related/<objective-slug>/04-development/risk-assessment.md` alone against an existing architecture.
- `--track <name>` — output location group; inferred from a PRD path if omitted.

## Phase 0 — DETECT

Resolve the input:

| Input | Action |
|---|---|
| Path ending in `.prd.md` | Parse it; design the next pending phase, or the `--phase N` given |
| Path to any other `.md` | Read as context; treat as free-form |
| Free-form text | The feature to design |
| Empty | Ask what to design — do not guess |

Determine `<track>` from the PRD/plan path if present — it is the PRD group (`backend`,
`portal`, `industries`, …), matching the existing `plan/<group>/` names. If it cannot be
determined and matters, ask rather than guess; never fall back to a bare `docs/` path, which
the TD-011 artifact-layout invariant forbids.

## Phase 1 — CURRENT STATE

Read the real codebase before designing against it — modules, interfaces, conventions,
existing patterns. If a brownfield onboarding pass has run, read `docs/context/REPO_MAP.md`
and the memory bank as your baseline. Mirror what exists; do not design an idealised system
that ignores current conventions.

## Phase 2 — DESIGN

Follow the `architecture-design` skill exactly. Produce
`neuroedge/docs/project_related/<objective-slug>/04-development/architecture.md` with:
component and sequence diagrams (Mermaid, never images), interface contracts, data flow, state
transitions, the finalized patterns the build must follow (cited by skill path), alternatives
considered, ADRs to record, and any open questions.

## Phase 3 — RISK

Follow the `risk-assessment` skill exactly. Produce
`neuroedge/docs/project_related/<objective-slug>/04-development/risk-assessment.md` with the
three risk classes — implementation, regression, security — each risk carrying an `RK-NN` id,
likelihood, impact, and a mitigation. Every regression and security risk names a `TC-NN` test
case so the risk flows into the test plan. A lightweight STRIDE pass over the sequence diagrams
covers security-by-design here, before any code.

If a risk is severe enough to change the design, loop back to Phase 2 rather than recording a
risk against a design you already know is wrong.

## Phase 4 — REPORT

Print a summary and an explicit verdict:

```
## Architecture Ready

- Design:  neuroedge/docs/project_related/<objective-slug>/04-development/architecture.md   (N components, M sequence flows)
- Risks:   neuroedge/docs/project_related/<objective-slug>/04-development/risk-assessment.md (X implementation, Y regression, Z security)
- Finalized patterns: <skill paths the build will inherit>
- Open questions: <count, or "none">
- Highest risk: <RK-NN — one line>

Verdict: ready for implementation | needs another design pass | blocked on <open question>

> Next: /prp-plan <same input>  — the plan inherits this design and its risks.
```

## Standalone vs. orchestrated

- **Standalone (this command):** you run it, you review the output, you decide when to proceed.
  There is no automated gate — the review is yours.
- **Inside `/agentforge` (S3):** the same artifacts are produced by the `architect` agent and
  held at a hard gate; the orchestrator will not advance to plan or build until they are
  approved, and an unmitigated High-impact risk blocks that gate.

Either way the artifacts and the skills that produce them are identical — one source of truth,
whether a human drives it here or the orchestrator drives it at S3.
