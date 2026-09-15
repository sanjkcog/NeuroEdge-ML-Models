---
description: Create comprehensive feature implementation plan with codebase analysis and pattern extraction
argument-hint: <feature description | path/to/prd.md | path/to/task-board.md>
---

## Arguments

$ARGUMENTS — a feature description, or a path to a `.prd.md` or `task-board.md` file.

## Procedure

This command's full procedure lives in the `prp-plan` skill so a subagent can run it identically. **Read and execute `agentic-assets/skills/SDLC/prp/prp-plan.md`**, treating `$ARGUMENTS` as its input.

Interactive gates in that procedure (user-facing questions and checkpoints) are asked by the main session running this command, not delegated to a subagent — see the skill's "Gate delegation" section.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /prp-plan · Skills: prp-plan, agentic-engineering, product-capability`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/prp/prp-plan.md`
> - `agentic-assets/skills/SDLC/development/agentic-engineering.md`
> - `agentic-assets/skills/SDLC/requirements/product-capability.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->
