---
description: Create a GitHub PR from current branch with unpushed commits — discovers templates, analyzes changes, pushes
argument-hint: [base-branch] (default: main)
---

## Arguments

$ARGUMENTS — the base branch (default: `main`); optional `--draft` to open a draft PR.

## Procedure

This command's full procedure lives in the `prp-pr` skill so a subagent can run it identically. **Read and execute `agentic-assets/skills/SDLC/prp/prp-pr.md`**, treating `$ARGUMENTS` as its input.

Interactive gates in that procedure (user-facing questions and checkpoints) are asked by the main session running this command, not delegated to a subagent — see the skill's "Gate delegation" section.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /prp-pr · Skills: prp-pr, git-workflow, security-review`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/prp/prp-pr.md`
> - `agentic-assets/skills/SDLC/development/git-workflow.md`
> - `agentic-assets/skills/SDLC/testing/security-review.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->
