# Cognizant PPT

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /cognizant-ppt · Skills: cognizant-ppt`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SUPPORTING-TOOLS/content/cognizant-ppt.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Usage

`/cognizant-ppt [content-source | --spec <deck-spec.json> | --from-prd <path-to-prd.md>] [--out <output.pptx>]`

- `content-source` — free-form description of what to put in the deck (the skill will interpret and structure)
- `--spec <path>` — JSON file matching the deck_spec schema in the cognizant-ppt skill
- `--from-prd <path>` — derive deck from a PRD markdown file (skill extracts title, sections, messaging hierarchy)
- `--out <path>` — output path (default: `docs/marketing/<topic-slug>-<date>.pptx`)

## Pipeline

1. **PARSE** the input: spec file, PRD source, or free-form brief
2. **STRUCTURE** the content into slides — pick slide types from the cognizant-ppt skill catalog (cover, two_column, table, sub_sections, roadmap, closing)
3. **APPLY** the Cognizant brand constants from the skill (colors, fonts, layout zones — never invent values)
4. **GENERATE** a Python script using `python-pptx` per the skill's implementation pattern
5. **EXECUTE** the script (auto-installs `python-pptx` if missing)
6. **REPORT** the output file path and a one-line slide-type summary

## Notes

- The cognizant-ppt skill at `agentic-assets/skills/SUPPORTING-TOOLS/content/cognizant-ppt.md` is the source of truth for the brand palette, typography, layout zones, slide types, and the reference Python implementation. Read it before generating.
- This command does NOT productize a deck — it produces a draft for human review and brand-team sign-off before any external distribution.
- For external-facing decks, route the output through brand team approval before publishing.

## Arguments

`$ARGUMENTS`:
- positional: free-form brief or `--from-prd <path>` or `--spec <path>`
- `--out <path>` optional
- `--no-cover` optional (skip cover slide if embedding into existing deck)
- `--no-closing` optional (skip closing slide)
