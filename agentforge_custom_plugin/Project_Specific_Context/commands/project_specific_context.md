---
description: Consult the Project_Specific_Context custom plugin — inject its domain/product expertise into an SDLC artifact. Not auto-wired into /agentforge; invoked deliberately.
argument-hint: "<what you need>" | --context | --check
---

## Procedure
1. Resolve intent from $ARGUMENTS (ask if empty).
2. Read the subject skill(s) in `skills/SUBJECTS/`, then
   `agentforge_custom_plugin/Project_Specific_Context/skills/project_specific_context-integration.md` and
   `agentforge_custom_plugin/Project_Specific_Context/context/DOMAIN.md`.
3. Spawn `project_specific_context-domain-expert` with the intent + loaded paths.
4. Report; surface every `TBD` as "needs SME input".

## NeuroEdge Assets — custom plugin: Project_Specific_Context
> Output at start: `[ NeuroEdge Assets ]  /project_specific_context · Plugin: Project_Specific_Context`
