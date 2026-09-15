---
description: Turn a written design description into annotated wireframes - app shell, step pipeline or screen sequence, rendered as one shareable page
argument-hint: [a paragraph describing the screens/flow | path to an ADR or PRD section describing UI]
---

## Arguments

$ARGUMENTS — prose describing a product idea, screen, or flow; or a path to a document whose UI
description should be drawn. Blank asks what to draw.

## Procedure

This command's full procedure lives in the `idea-designer` skill so a subagent can run it
identically. **Read and execute `agentic-assets/skills/SUPPORTING-TOOLS/design/idea-designer.md`**,
treating `$ARGUMENTS` as its input.

The output is a **wireframe for review**, not production UI. It should be visibly a wireframe and
never mistakable for a screenshot. Anything the source text did not determine is named on the page
rather than silently chosen — that is the point of the skill.

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /idea-designer · Skills: idea-designer, frontend-design, artifact-page`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SUPPORTING-TOOLS/design/idea-designer.md`
> - `agentic-assets/skills/SUPPORTING-TOOLS/design/frontend-design.md`
> - `agentic-assets/skills/SUPPORTING-TOOLS/design/artifact-page.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->
