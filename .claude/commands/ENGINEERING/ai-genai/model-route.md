# Model Route Command

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /model-route · Skills: cost-aware-llm-pipeline`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-genai/cost-aware-llm-pipeline.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Usage

`/model-route [task-description] [--budget low|med|high]`

## Routing Heuristic

- `haiku`: deterministic, low-risk mechanical changes
- `sonnet`: default for implementation and refactors
- `opus`: architecture, deep review, ambiguous requirements

## Required Output

- recommended model
- confidence level
- why this model fits
- fallback model if first attempt fails

## Arguments

$ARGUMENTS:
- `[task-description]` optional free-text
- `--budget low|med|high` optional
