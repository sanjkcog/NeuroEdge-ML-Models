---
name: documentation-patterns
description: Patterns for writing and maintaining project documentation — READMEs, API docs, architecture codemaps, runbooks, and inline comments. Use when generating, reviewing, or updating any documentation artifact.
origin: NeuroEdge
---

# Documentation Patterns

Good documentation is code-adjacent: it ages at the same rate as the code it describes, lives in the same repo, and fails the same way bad code does — silently, by lying.

## When to Use

- Writing or updating a `README.md`, `CLAUDE.md`, or `CONTRIBUTING.md`
- Generating API documentation from code
- Creating architecture codemaps (`docs/CODEMAPS/`)
- Writing runbooks, deployment guides, or operational docs
- Reviewing inline comments for accuracy and necessity
- After significant API or interface changes that affect consumers

---

## Core Rules

**Write for the reader who just joined the project.**
Every doc assumes the reader has: this repo, a terminal, and no Slack history.

**Docs live next to the code they describe.**
`src/neuroedge_model_profiler/` → `src/neuroedge_model_profiler/README.md`.
Don't create separate `docs/` files for things that belong next to source.

**One source of truth.**
If a fact appears in two places, both will go stale. Decide which is authoritative and link from the other.

**Comments explain WHY, not WHAT.**
Code already says what it does. A comment earns its place only when:
- The reason is non-obvious (a hardware quirk, a protocol constraint, a known bug workaround)
- Removing the comment would make a future developer reverse the decision

---

## README Structure

```markdown
# [Project Name]

One sentence: what it does and who it's for.

## Quick Start
Minimum commands to get from zero to working. Every command must be tested.

## Architecture
One diagram or ASCII art showing the main moving parts and their relationships.

## Key Concepts
3–5 bullet points. The mental model a new engineer needs before reading code.

## Configuration
All environment variables and config files. Mark which are required vs. optional.

## Development
How to run tests, lint, and build locally.

## Deployment
How to deploy. Reference the runbook if it's complex.

## Contributing
PR process, branch naming, commit style.
```

---

## API Documentation

- Document every public interface at the point of definition — not in a separate file
- Include: purpose, parameters (type + meaning + default), return value, exceptions raised, one usage example
- If a parameter has a non-obvious constraint (e.g. "must be > 0", "ignored when mode=auto"), document it explicitly
- Deprecation notice format: `@deprecated since v0.N — use X instead. Will be removed in v0.N+2.`

---

## Architecture Codemaps

Output to `docs/CODEMAPS/<module>.md`. Each codemap covers one module or subsystem:

```markdown
# Codemap: [Module Name]

**Last updated:** YYYY-MM-DD  
**Status:** accurate | needs-update | stale

## Purpose
What problem this module solves.

## Entry Points
Where execution enters this module (CLI, API endpoint, import path).

## Key Files
| File | Purpose |
|------|---------|
| `path/to/file.py` | What it does in one line |

## Data Flow
Inputs → [transformation steps] → Outputs

## Dependencies
Internal and external deps this module requires.

## Known Limitations
Things it explicitly does NOT do, or known edge cases.
```

---

## Runbook Structure

A runbook answers: "What do I do when X happens?"

```markdown
# Runbook: [Incident Type]

**Trigger:** [What symptom indicates this runbook is needed]
**Severity:** P0 / P1 / P2

## Diagnosis
Step-by-step commands to confirm the issue and gather context.

## Resolution
Step-by-step commands to fix it, in order. Include rollback steps.

## Verification
How to confirm the fix worked.

## Post-Incident
What to file, update, or change after resolution.
```

---

## Commit and PR Documentation

- PR titles: imperative mood, < 70 chars: `Add TensorRT backend for Jetson`, not `Added TRT`
- PR body: what changed + why + how to test
- Commit messages: same imperative mood; first line ≤ 72 chars; blank line before body
- Do not describe changes in comments within files — that's what git history is for

---

## What NOT to Document

- Code that already reads clearly — `def load_model(path)` needs no comment
- Decisions that are already obvious from the code or config
- Temporary state ("this is a stub") — remove stubs rather than documenting them
- How-tos that already exist in official tool docs — link instead of copying
