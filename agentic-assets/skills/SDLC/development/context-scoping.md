---
name: context-scoping
description: Keep only the active subfolder's code in Claude's context. Auto-generate nested CLAUDE.md files for modular codebases; guide a TODO-driven segment-scoping process for legacy monolithic code. Soft enforcement via conventions and subagent delegation.
origin: AgentForge
---

# Context Scoping

Use this skill when a codebase is large enough that loading "everything" wastes
the context window, and the user works on **one area at a time**. The goal:
when someone works in a subfolder, Claude loads **only that subfolder's**
guidance, and reaches outside it **only on a need basis** — via a subagent, not
by dragging unrelated files into the main window.

## First principle — what actually fills context

Claude Code never bulk-loads a source tree. Context fills from exactly two places:

1. **Always-on memory** — every `CLAUDE.md` from the working directory up to the
   repo root is injected each session. A fat root `CLAUDE.md` is a constant tax.
2. **Exploration** — files the agent chooses to Read/Grep/Glob during a task,
   which then persist in the window.

So scoping is three moves: **(a)** slim the always-on root, **(b)** push detail
into nested `CLAUDE.md` that load only when their folder is touched, and
**(c)** stop exploration from pulling in unrelated modules (delegate to `Explore`).

## Two modes

| Codebase | Seams exist? | Approach |
|---|---|---|
| **Modular** (packages / services) | Yes | **Automated** — walk the tree, generate a nested `CLAUDE.md` per package + a slim root router. |
| **Legacy monolithic** | No | **Guided** — a TODO-driven process manufactures a boundary (segment map) before any scoped file is written. |

Detect the mode first: if the source root has ≥2 package markers
(`__init__.py`, `package.json`, `go.mod`, `pom.xml`, `*.csproj`) → modular.
If it has 0–1 and lots of loose files → monolithic.

---

## Mode A — Modular (automated)

Run the walker (stdlib-only, no deps, safe on any repo — it never imports code):

```bash
# preview
python agentic-assets/scripts/scope/generate_subfolder_claude.py --root src --dry-run

# top-level packages only
python agentic-assets/scripts/scope/generate_subfolder_claude.py --root src --max-depth 1

# packages + one level of sub-packages (default), plus a root router
python agentic-assets/scripts/scope/generate_subfolder_claude.py --root src --router
```

What it does per package: extracts the docstring purpose, the **public surface**
(`__all__`, re-exports, top-level classes/functions), entry points, and a file
inventory; writes a nested `CLAUDE.md` between `SCOPE:AUTO` markers.

- **Idempotent.** Re-running updates only the marked block; prose you add
  outside the markers is preserved.
- **Test trees and generated dirs are skipped** (`tests/`, `__pycache__`,
  `node_modules`, `*.egg-info`, `dist`, `.venv`, …).

**After generation — enrich (agent step).** The script fills structure; a short
agent pass should fill each module's one-line role for its files and confirm the
"public surface" is the real intended API. Then **slim the root** `CLAUDE.md` to a
router (project-wide rules + the module map) and move module-specific detail down.

**The scope rule each nested file carries:**

> When working in this module, treat it as your working set. Depend on other
> modules only through their public surface. To learn how another module works,
> dispatch an `Explore` subagent — it returns a summary, not the files.

---

## Mode B — Legacy monolithic (guided, TODO-driven)

You cannot scope to a module that does not exist. First **manufacture a
boundary** around the segment the user will work on, then scope to it. Drive the
user through this checklist (also emitted by the `/scope-context --monolith`
command and owned by the `context-scoper` agent):

```text
[ ] 1. Name the segment  — the feature/subsystem/dir the user will actually change.
[ ] 2. Find entry points — routes, handlers, CLI commands, jobs, consumers into it.
[ ] 3. Trace outward     — (Explore/code-explorer) what it calls, reads, writes:
                           DB, queues, files, other subsystems.
[ ] 4. Trace inward      — who calls into it. Callers define the boundary contract.
[ ] 5. Record the seam   — list the functions/classes at the boundary + their I/O.
[ ] 6. Write the map     — docs/context/segment-map-<segment>.md from the trace.
[ ] 7. Characterize      — add tests that pin current behavior at the boundary
                           (tdd-guide) BEFORE any change.
[ ] 8. Drop scoped file  — a CLAUDE.md at the segment folder: "you own this;
                           everything else is a black box behind these seams;
                           cross-boundary lookups go to an Explore subagent."
[ ] 9. Mute noise        — add ignore entries for generated/vendor dirs.
[ ] 10. Validate         — make one small change using ONLY the map + scoped file.
```

Reuse existing AgentForge assets rather than duplicating them:

- `legacy-modernizer` agent + `legacy-modernization` skill — brownfield
  onboarding, memory bank, risk register, modernization lanes.
- `/legacy-audit --subfolder-claude` — inventory + baseline + CLAUDE hierarchy.
- `code-explorer` — execution-path tracing for steps 3–5.
- `tdd-guide` — characterization tests for step 7.

---

## Version-control gotcha (check `.gitignore` first)

Many AgentForge projects ignore `CLAUDE.md` wholesale (the root file is
*generated* by the setup script, not committed). A bare `CLAUDE.md` pattern also
ignores every **nested** file the walker creates — so team members won't get the
scoping on a fresh clone. Decide the policy per repo:

- **Regenerate on setup (default, matches AgentForge):** treat nested files as
  reproducible artifacts; run the walker as a setup step so a fresh clone gets
  them. Keep them git-ignored.
- **Commit them (team-shared, hand-enriched):** make the ignore precise so nested
  files are tracked — either scope the root ignore (`/CLAUDE.md`) or add a
  negation:

  ```gitignore
  CLAUDE.md
  !src/**/CLAUDE.md
  ```

Prefer "commit them" when developers hand-write file roles/purposes worth
sharing; prefer "regenerate" when the content is purely mechanical.

## Enforcement is soft — and that is deliberate

Claude Code has no native "sandbox reads to a folder," and hard `deny` globs are
brittle across arbitrary repos and block legitimately-needed reads. So scoping
relies on: nested `CLAUDE.md` conventions + the subagent-delegation habit. This
ports cleanly into any codebase. If a project wants a visible nudge, add a
non-blocking `PreToolUse` hook that warns when a Read targets a path outside the
active segment — but keep it a warning, not a block.

## Best-practice checklist

- Root `CLAUDE.md` stays a lean router; module detail lives in nested files.
- Every scoped file names its **public surface** and the **cross-boundary rule**.
- Cross-module facts come from an `Explore` subagent, not inline reads.
- Monolith work never edits before a segment map + characterization tests exist.
- Regenerate nested files after structural changes; never hand-edit inside the
  `SCOPE:AUTO` markers.
