---
description: Execute an implementation plan with rigorous validation loops
argument-hint: <path/to/plan.md>
---

## Arguments

$ARGUMENTS — path to a plan file (e.g. `neuroedge/docs/project_related/<objective-slug>/02-project-plan/<name>.plan.md`).

## Procedure

This command's full procedure lives in the `prp-implement` skill so a subagent can run it identically. **Read and execute `agentic-assets/skills/SDLC/prp/prp-implement.md`**, treating `$ARGUMENTS` as its input.

Interactive gates in that procedure (user-facing questions and checkpoints) are asked by the main session running this command, not delegated to a subagent — see the skill's "Gate delegation" section.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /prp-implement · Skills: prp-implement, agentic-engineering, coding-standards, tdd-workflow`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/prp/prp-implement.md`
> - `agentic-assets/skills/SDLC/development/agentic-engineering.md`
> - `agentic-assets/skills/SDLC/development/coding-standards.md`
> - `agentic-assets/skills/SDLC/tdd/tdd-workflow.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->
