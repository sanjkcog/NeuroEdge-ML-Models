---
name: product-doc
description: Generate the self-contained HTML product document explaining what AgentForge is — problem, stage graph, gate model, traceability, PM surface — derived from agentforge.prd.md and project_objectives.md. Use when the user wants to (re)generate the product overview doc, or when agentforge.prd.md / project_objectives.md have changed and the doc needs to catch up.
origin: NeuroEdge AgentForge
---

# Product Doc

Turn `agentforge.prd.md` + `project_objectives.md` into one self-contained HTML page a
person who has never seen AgentForge can read to understand the product — no author
walkthrough needed (EP-09, US-09-01).

## When to Activate

- "Regenerate the product doc" / "update what_is_agentforge.html"
- The PRD or objectives file changed and the HTML doc needs to catch up
- `/product-doc` (the command — see related)

## Non-Negotiables

1. **Generated, never hand-edited.** The whole point is that `agentforge.prd.md`,
   `project_objectives.md`, and the HTML document cannot drift apart (US-09-01 AC). If
   the HTML looks wrong, fix the extraction/render code or the source PRD/objectives —
   never hand-edit `docs/guides/what_is_agentforge.html` directly.
2. **Zero dependencies.** One self-contained HTML file, inline CSS, no `<link>`, no
   remote `<script src="http...">` — matches `frontend-slides.md`'s own zero-dependency
   rule and the existing `docs/guides/*.html` precedent.
3. **Fail loudly, never silently stale.** If a required section's heading can't be
   found in the PRD/objectives, the generator raises rather than emitting the previous
   document's content unchanged.

## Required Sections (source of truth)

The generated document covers exactly five topics, each sourced from one heading.
Change this table, not the code, if the PRD/objectives ever renumber or rename these
headings — `neuroedge_productdoc.sources._SECTION_SOURCES` mirrors it exactly.

| Doc section | Source file | Heading (matched by substring, case-insensitive) |
|---|---|---|
| The Problem | `agentforge.prd.md` | `## Problem Statement` |
| The Stage Graph | `agentforge.prd.md` | `## Implementation Phases` |
| The Gate Model | `project_objectives.md` | `## 5. Locked decisions` |
| Traceability | `project_objectives.md` | `## 8. Traceability model` |
| The PM Surface | `project_objectives.md` | `## 7. Roles` |

## The Pipeline

1. **PARSE** — resolve the PRD and objectives paths (default to
   `agentforge/docs/project_related/<objective-slug>/02-project-plan/PRD.md` and
   `agentforge/docs/project_related/objectives/project_objectives.md` unless the user
   supplies different paths)
2. **EXTRACT** — `neuroedge_productdoc.sources.extract_sections(prd, objectives)`
   pulls the five sections above, stripping any `<!-- -->` editor comments, raising
   `ValueError` naming the missing heading if one is gone
3. **RENDER** — `neuroedge_productdoc.render.render_html(sections)` converts each
   section's markdown (paragraphs, `### ` sub-headings, pipe tables, `` `code` ``,
   `**bold**`, `[text](url)` links) into HTML, wrapped in the CSS shell copied
   verbatim from `docs/guides/how_to_run_agentforge.html`
4. **WRITE** — output to `docs/guides/what_is_agentforge.html` (or a path the user
   supplies)
5. **REPORT** — the output path and a one-line section summary

## Implementation

`src/neuroedge_productdoc/` (`sources.py`, `render.py`, `cli.py`) is the reference
implementation — read it before regenerating by hand. Invoke via:

```bash
PYTHONPATH=src python -X utf8 -m neuroedge_productdoc.cli generate \
  --prd agentforge/docs/project_related/<objective-slug>/02-project-plan/PRD.md \
  --objectives agentforge/docs/project_related/objectives/project_objectives.md \
  --out docs/guides/what_is_agentforge.html
```

## Notes

- No network calls, no external services — this is pure markdown parsing + HTML
  templating, unlike `cognizant-ppt` (python-pptx) or `marketing-video`
  (Pexels/Pixabay/TTS/ffmpeg).
- Installed automatically: `commands/`, `skills/`, and every top-level `src/` package
  are copied wholesale by `install.py` — no installer change is needed when this skill,
  its command, or the `neuroedge_productdoc` package are added or edited.
