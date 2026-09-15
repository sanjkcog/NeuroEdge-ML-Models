# Quality Gate Command

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /quality-gate · Skills: coding-standards, plankton-code-quality`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/development/coding-standards.md`
> - `agentic-assets/skills/SDLC/development/plankton-code-quality.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Usage

`/quality-gate [path|.] [--fix] [--strict]`

- default target: current directory (`.`)
- `--fix`: allow auto-format/fix where configured
- `--strict`: fail on warnings where supported

## Pipeline

1. Detect language/tooling for target.
2. Run formatter checks.
3. Run lint/type checks when available.
4. Produce a concise remediation list.

## Notes

This command mirrors hook behavior but is operator-invoked.

## Arguments

$ARGUMENTS:
- `[path|.]` optional target path
- `--fix` optional
- `--strict` optional
