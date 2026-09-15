# Project_Specific_Context — domain context pack (index)

This is the **fill-in template** for teaching AgentForge about *your* product/client.
Everything here ships with `TODO`/`TBD` markers and neutral placeholders — replace
them with real facts and the base `/agentforge` SDLC will feed this context to the
right role agent at every stage automatically (via `discover_plugins.py`).

**Status: SEED — nothing here is authoritative until you fill it in.** Until then,
agents will surface each field as `TBD — needs SME input` rather than invent it.

## How to fill this in

Work top-down; you do not need to complete every file before it becomes useful.

| File | What to put in it | Fed to SDLC stage(s) |
|---|---|---|
| `DOMAIN.md` (this file) | One-paragraph description of the product/client and its purpose | research |
| `glossary.md` | Domain terms and acronyms a newcomer would not know | epics, tasks |
| `personas.md` | Who the users are; their goals and constraints | requirements |
| `regulatory.md` | Binding standards, compliance, legal frame (if any) | requirements |
| `constraints.md` | Non-negotiables: performance, platform, security, deadlines | requirements, architecture |
| `workflows/` | As-is workflow narratives (one file per workflow) | epics, tasks |
| `integrations/<product>/` | Interfaces, data formats, product specifics | architecture, test-* |
| `sources.md` | Provenance table — where each fact came from, and confidence | (audit trail) |

## What belongs here vs. elsewhere

- **Here (`Project_Specific_Context/`):** facts true *because it is this product/client*.
  Proprietary. Not reusable across vendors.
- **`skills/SUBJECTS/`:** reusable subject expertise (e.g. "computer vision", "FDA 510k")
  that any product in that domain would share. Declare those in `plugin.json`
  (`requires_subjects`) so they install alongside this plugin.

## Activation

Presence is activation. As long as `plugin.json` exists with `auto_load: true`,
the base SDLC discovers and loads this context — no install step, no wiring edit.
To deactivate without deleting, set `auto_load: false` in `plugin.json`.

See `agentforge_custom_plugin/README.md` for the full authoring guide, and
`agentforge_custom_plugin/SunCHECK/` for a worked example.
