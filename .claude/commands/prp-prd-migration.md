---
description: Migration PRD generator - retirement inventory, behaviour-preservation contract, test triage, cutover and rollback for a breaking redesign of a working system
argument-hint: [paths/globs to accepted ADRs | path to a decisions directory] (a migration PRD needs decisions, not a problem statement)
---

## Arguments

$ARGUMENTS — paths or globs to the ADRs whose decisions drive the migration, or a directory of
decision records. If given free text instead, the procedure asks for the ADRs: a migration PRD
without decisions is a product PRD, and `/prp-prd` is the right command for that.

## Procedure

This command's full procedure lives in the `prp-prd-migration` skill so a subagent can run it
identically. **Read and execute `agentic-assets/skills/SDLC/prp/prp-prd-migration.md`**, treating
`$ARGUMENTS` as its input.

Interactive gates in that procedure (ADR status, the preserved-behaviour list, and PRD approval) are
asked by the main session running this command, not delegated to a subagent — see the skill's "Gate
delegation" section.

## When to use this instead of `/prp-prd`

Use `/prp-prd` for a new product, feature, or platform; use this command when accepted ADRs
reshape a **working** system — the skill's opening comparison table carries the full contrast
(migration success adds "and nothing silently stops working").

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /prp-prd-migration · Skills: prp-prd-migration, product-capability`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/prp/prp-prd-migration.md`
> - `agentic-assets/skills/SDLC/requirements/product-capability.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->
