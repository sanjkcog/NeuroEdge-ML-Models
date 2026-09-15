---
description: Interactive PRD generator - problem-first, hypothesis-driven product spec with back-and-forth questioning
argument-hint: [feature/product idea | path/to/project_objectives.md] (blank = look for project_objectives.md, else start with questions)
---

## Arguments

$ARGUMENTS — a feature/product idea, a path to a `project_objectives.md` file, or blank (blank looks for `project_objectives.md` at the repo root, else starts with discovery questions).

## Procedure

This command's full procedure lives in the `prp-prd` skill so a subagent can run it identically. **Read and execute `agentic-assets/skills/SDLC/prp/prp-prd.md`**, treating `$ARGUMENTS` as its input.

Interactive gates in that procedure (user-facing questions and checkpoints) are asked by the main session running this command, not delegated to a subagent — see the skill's "Gate delegation" section.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /prp-prd · Skills: prp-prd, product-capability`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/prp/prp-prd.md`
> - `agentic-assets/skills/SDLC/requirements/product-capability.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->
