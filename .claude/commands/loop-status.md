# Loop Status Command

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /loop-status · Skills: continuous-agent-loop`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-genai/continuous-agent-loop.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Usage

`/loop-status [--watch]`

## What to Report

- active loop pattern
- current phase and last successful checkpoint
- failing checks (if any)
- estimated time/cost drift
- recommended intervention (continue/pause/stop)

## Watch Mode

When `--watch` is present, refresh status periodically and surface state changes.

## Arguments

$ARGUMENTS:
- `--watch` optional
