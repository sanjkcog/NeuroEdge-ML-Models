# Product Doc

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /product-doc · Skills: product-doc`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SUPPORTING-TOOLS/content/product-doc.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Usage

`/product-doc [--prd <path>] [--objectives <path>] [--out <path>]`

- `--prd <path>` — optional; defaults to
  `neuroedge/docs/project_related/<objective-slug>/02-project-plan/PRD.md` (the target-side
  tree `/agentforge` S2 writes — see `commands/agentforge.md`; `agentforge/docs/` is never
  installed into a target, ADR-0017 F-2)
- `--objectives <path>` — optional; defaults to
  `neuroedge/docs/project_related/objectives/project_objectives.md` (target-side; created by
  the target's own runs, not shipped by install)
- `--out <path>` — optional; defaults to `docs/guides/what_is_agentforge.html`

## Pipeline

1. **PARSE** the input: resolve `--prd`/`--objectives`/`--out`, falling back to the
   defaults above when omitted
2. **EXTRACT** the five required sections (problem, stage graph, gate model,
   traceability, PM surface) — the product-doc skill's table is the source of truth for
   which heading maps to which section
3. **GENERATE** by running the reference implementation:
   ```bash
   PYTHONPATH=src python -X utf8 -m neuroedge_productdoc.cli generate \
     --prd <prd-path> --objectives <objectives-path> --out <out-path>
   ```
4. **REPORT** the output file path and a one-line section summary; if the command
   exits non-zero, surface the missing-heading error verbatim rather than retrying with
   a different heading match

## Notes

- The product-doc skill at `agentic-assets/skills/SUPPORTING-TOOLS/content/product-doc.md`
  is the source of truth for the required-sections table and the zero-dependency /
  fail-loudly rules. Read it before regenerating.
- This command produces a fully self-contained HTML file — no external requests, no
  `<link>`/remote `<script>`. If a required heading is missing from the PRD or
  objectives file, the command fails loudly rather than emitting a stale document.
- Never hand-edit the output file — if the rendered document looks wrong, fix
  `agentforge.prd.md` / `project_objectives.md` or the generator, then regenerate.

## Arguments

`$ARGUMENTS`:
- `--prd <path>` optional
- `--objectives <path>` optional
- `--out <path>` optional
