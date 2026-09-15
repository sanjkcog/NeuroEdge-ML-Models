# Model Route Command

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /model-route · Skills: cost-aware-llm-pipeline, ml-artifact-destination`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/ai-genai/cost-aware-llm-pipeline.md`
> - `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`
<!-- neuroedge-assets-patched source-version=8acd6bf -->

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

## Saving

Prints to chat and writes nothing by default. If the user asks to save the recommendation, resolve the
destination first per `ml-artifact-destination` (`agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`) — `--dest`, or propose
`<ML_ROOT>/<intent>-<modality>` and ask — then write `<dest>/model-route.md`.

## Arguments

$ARGUMENTS:
- `[task-description]` optional free-text
- `--budget low|med|high` optional
- `--dest <folder>` optional — only used when saving
