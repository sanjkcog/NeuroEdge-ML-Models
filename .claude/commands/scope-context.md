# Scope Context Command

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /scope-context · Skills: context-scoping, agentic-engineering`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/development/context-scoping.md`
> - `agentic-assets/skills/SDLC/development/agentic-engineering.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Usage

`/scope-context [path] [--modular|--monolith|--auto] [--max-depth N] [--router] [--force] [--dry-run]`

Examples:

```text
/scope-context src --dry-run
/scope-context src --modular --max-depth 1 --router
/scope-context services/billing --monolith
/scope-context .                        # auto-detect mode
```

## Purpose

Make Claude load only the **active subfolder's** context, and reach outside it
only on a need basis. Two modes:

- **Modular** — auto-generate a nested `CLAUDE.md` per package + a slim root router.
- **Monolith** — guide a TODO-driven segment-scoping process (no auto-generation;
  a boundary must be manufactured first).

Read-only by default in monolith mode until the user confirms writes.

## Execution

### Step 1 — ROUTE

State the command, the `context-scoping` skill, and (monolith only) the
`context-scoper` agent. Confirm the target `path` (default `src` if present,
else repo root).

### Step 2 — DETECT MODE (if `--auto` or unspecified)

Count package markers under the path (`__init__.py`, `package.json`, `go.mod`,
`pom.xml`, `*.csproj`).

- ≥2 markers → **modular**.
- 0–1 markers with many loose source files → **monolithic**.

Announce the detected mode and why.

### Step 3a — MODULAR

Run the walker, preferring `--dry-run` first so the user sees the plan:

```bash
python agentic-assets/scripts/scope/generate_subfolder_claude.py \
  --root <path> [--max-depth N] [--router] [--force] [--dry-run]
```

Then **enrich**: for each generated `CLAUDE.md`, fill the one-line file roles and
confirm the detected public surface is the intended API (edit *outside* the
`SCOPE:AUTO` markers). Finally, propose slimming the root `CLAUDE.md` into a
router (project-wide rules + module map) and moving module detail into the
nested files.

### Step 3b — MONOLITH

Delegate to the `context-scoper` agent and walk the 10-step TODO from the
`context-scoping` skill. Use `code-explorer` for boundary tracing and
`tdd-guide` for characterization tests. Do not write a scoped `CLAUDE.md` until
the segment map exists and the user confirms.

For full brownfield onboarding (memory bank, risk register, modernization plan),
hand off to `/legacy-audit --subfolder-claude`.

## Arguments

`$ARGUMENTS` may include:

- `path` — source root or subsystem to scope (default: `src`, else repo root)
- `--modular` / `--monolith` / `--auto` — force a mode or auto-detect (default)
- `--max-depth N` — modular: levels below root to scope (default 2; `1` = top-level only)
- `--router` — modular: also (re)write the root `CLAUDE.md` module map
- `--force` — modular: overwrite files lacking `SCOPE:AUTO` markers
- `--dry-run` — modular: print planned actions, write nothing

## Required Routing

| Trigger | Agent |
|---|---|
| Monolith segment scoping | `context-scoper` |
| Deep execution tracing | `code-explorer` |
| Characterization tests | `tdd-guide` |
| Full brownfield onboarding | `legacy-modernizer` (via `/legacy-audit`) |
| New architecture boundary | `architect` / `code-architect` |
