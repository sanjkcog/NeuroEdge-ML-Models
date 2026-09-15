# `ai-genai` Engineering-Discipline Manifest

This is the discipline manifest for building AI/GenAI/agentic **products** —
the ADR-0010 taxonomy's first `ENGINEERING/` pack (ADR-0011). It is loaded
manifest-first: a project declares the `ai-genai` discipline and the
orchestrator reads this file to decide which reviewers, skills, and commands
to bring into context for the active stage. Non-declaring projects still
receive every file on disk (the installer copies whole-tree/flat regardless
of declaration), but never load them — see `load_scope` below.

The single fenced `yaml` block below is machine-parseable: every `path:`
entry under `reviewers`, `skills.owned`, `skills.references`, `commands`, and
`agents_extra` MUST resolve to an existing file in this repo (AC-01.4,
TC-01-01-04). `artifacts:` entries are all `status: backlog` and carry no
`path:` — they are declared scope, not yet-authored files, and are
deliberately excluded from the resolve check.

```yaml
discipline: ai-genai
adr: [ADR-0011, ADR-0010]
version: 0.1.0
status: phase-1
reviewers:
  - {name: ai-app-reviewer,      path: agents/ENGINEERING/ai-genai/ai-app-reviewer.md}
  - {name: llm-security-reviewer, path: agents/ENGINEERING/ai-genai/llm-security-reviewer.md}
skills:
  owned:
    - {path: skills/ENGINEERING/ai-genai/mcp-server-patterns.md}
    - {path: skills/ENGINEERING/ai-genai/autonomous-loops.md}
    - {path: skills/ENGINEERING/ai-genai/continuous-agent-loop.md}
    - {path: skills/ENGINEERING/ai-genai/cost-aware-llm-pipeline.md}
    - {path: skills/ENGINEERING/ai-genai/extraction-with-citation.md}
  references:
    - {path: skills/SDLC/development/agentic-engineering.md,
       reason: "OQ-2 REFERENCE: cross-cutting engineering practice (ADR-0012 meta-concern);
                21 load-bearing consumers incl. /agentforge banner; not discipline-owned"}
    - {path: skills/SDLC/testing/eval-harness.md,
       reason: "OQ-2 REFERENCE: generic Claude-Code-session EDD; consumed by /eval,/learn-eval"}
    - {path: skills/SDLC/testing/ai-regression-testing.md,
       reason: "borrowed; test-stage realization (FR-11 backlog) builds on it"}
    - {path: skills/ENGINEERING/_mechanism/ml-artifact-destination.md,
       reason: "REFERENCE: cross-pack rule for where ai-ml/ai-genai commands write artifacts (ADR-0021)"}
commands:
  - {name: gan-build,   path: commands/ENGINEERING/ai-genai/gan-build.md}
  - {name: model-route, path: commands/ENGINEERING/ai-genai/model-route.md}
agents_extra:
  - {path: agents/ENGINEERING/ai-genai/gan-planner.md}
  - {path: agents/ENGINEERING/ai-genai/gan-generator.md}
  - {path: agents/ENGINEERING/ai-genai/gan-evaluator.md}
stage_realizations:
  test:
    status: declared-phase3        # OQ-4 on-disk form deferred to Phase 3 (FR-11)
    builds_on: [eval-harness, ai-regression-testing]
    realization: "evals + guardrails + non-determinism regression"
artifacts:
  - {name: eval-suite,           status: backlog}   # FR-14
  - {name: guardrail-spec,       status: backlog}   # FR-13 (placement OQ-1)
  - {name: tool-scope-manifest,  status: backlog}   # FR-12
  - {name: model-routing-budget, status: backlog}   # FR-15
load_scope:
  declared_by: TBD-OQ5           # requires_subjects-style; validation pending
  note: "pack loads only when a project declares discipline ai-genai; non-declaring
         projects have files on disk (whole-tree install) but never load them"
```

## Reading this manifest

- **`reviewers`** — discipline reviewers that complement (never replace) the
  generic `security-reviewer`/`code-reviewer`. Installed flat via the FR-02
  `_AGENT_SUBDIRS` fix; declared here so a stage that names them can load them
  by path.
- **`skills.owned`** — consolidated under this pack (FR-05 MOVE-ATOMIC); a
  non-AI-product SDLC run would never need these, so they live here rather
  than in the cross-cutting `skills/SDLC/` tree.
- **`skills.references`** — deliberately NOT moved (OQ-2 REFERENCE-in-place):
  broadly consumed by non-AI SDLC assets, so moving them would strand those
  consumers or invert the "generic capability under an AI-product discipline"
  relationship. See ADR-0011 §"Consolidation strategy" for the ownership test.
- **`stage_realizations`** — how the ADR-0008 canonical SDLC's generic stages
  realize for an AI/agentic product. Only `test` is declared this run
  (`declared-phase3`, an explicit stub — not a live loader); it names the
  skills its eventual eval/guardrail realization builds on.
- **`artifacts`** — discipline-owned outputs this pack will eventually
  produce; all `status: backlog` this run (EP-04), listed here so they are
  visible and traceable rather than silently dropped.
- **`load_scope`** — the negative + positive context-scope contract
  (TC-01-01-05): a project that does not declare `ai-genai` loads none of
  this pack's assets; one that does loads only the assets its active stage
  names. The declaration surface itself is OQ-5, tracked as backlog.
