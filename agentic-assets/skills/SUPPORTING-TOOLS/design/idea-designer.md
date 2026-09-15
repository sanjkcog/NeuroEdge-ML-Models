---
name: idea-designer
description: Turn a paragraph describing a product idea, screen, or flow into a faithful visual — annotated wireframes of an app shell, a step pipeline, or a screen sequence, rendered as a single shareable page. Use when a design is written down but nobody can see it, and prose keeps producing different pictures in different heads.
origin: NeuroEdge
---

# Idea Designer

Converts **a paragraph into a picture people can disagree with.**

Prose describing a UI produces a different mental image in every reader. The purpose of this skill
is not to make something pretty — it is to make the description **falsifiable**: a stakeholder can
point at a box and say *"that is in the wrong place"*, which they cannot do with a sentence.

Uses `frontend-design` for visual craft and `artifact-page` for the hosting constraints. This skill
covers only the translation: **text → layout → annotated wireframe.**

## When to use

- a design is written down but nobody can see it
- a step-by-step flow needs agreeing before it is built
- an ADR or PRD describes screens in prose
- someone asks *"can you show me what that looks like"*

**Not** for production UI code — that is `frontend-design`. This produces a *reviewable picture*,
and it should be visibly a wireframe, not mistakable for a screenshot.

## Phase 1 — EXTRACT

From the description, pull out — and **name what is missing rather than inventing it**:

| Element | Question |
|---|---|
| **Shell** | what is constant on every screen? nav, rails, footers |
| **Steps** | is this one screen or a sequence? |
| **Regions** | what areas does each screen divide into? |
| **Working surface** | which region does the user act in? |
| **Inspector** | is there a properties/detail panel, and where does it sit? |
| **State** | what changes between steps — progress, status, badges |
| **Gates** | what blocks moving forward? |

🔴 If the description does not say where something sits, **say so on the wireframe** rather than
choosing silently. An invented placement gets approved by accident and then has to be un-agreed.

## Phase 2 — GROUND IT IN THE REAL SYSTEM

Before drawing, look for what already exists:

- an existing app shell, component library, or design tokens — **draw against those**, not a generic
  layout. Name the real components in the annotations.
- a sibling product with the same chrome — match it; consistency across a family beats novelty
- real content: real labels, real ids, real numbers from the actual system

**Never use lorem, "Item 1", or invented product names.** A wireframe with fake content gets
reviewed for its layout; a wireframe with real content gets reviewed for whether it is *right*.

## Phase 3 — DRAW

One page. Each screen is a bordered card containing the **full shell**, so the constant chrome is
visible in every step rather than described once.

Build the shell from plain CSS boxes — grid for the body, flex for rows. Do not reach for a diagram
library; a UI wireframe is a layout, and layout is what CSS does.

**Make it read as a wireframe:**

| Signal | How |
|---|---|
| structure over polish | visible 1px rules, restrained fill, no shadows-as-decoration |
| state legible at a glance | small pills for `PASS` / `WARN` / `FAIL` / `open` / `🔒 derived` |
| selection visible | one row or node clearly selected, its inspector populated |
| realistic density | show the real number of items, including the awkward long one |

Show at least one **imperfect** state — a failing check, an open question, a warning. A wireframe
where everything passes hides exactly the cases the design has not thought about.

## Phase 4 — ANNOTATE

Every screen gets one short paragraph beneath it answering: *what is this step for, what is the
non-obvious rule, and what did the source text not say?*

This is where the skill earns its keep. **The annotation carries the decisions; the picture carries
the layout.** Bold the rule that would otherwise be missed — a gate condition, a field that is
read-only and why, an ordering that is guidance rather than enforcement.

Close with a short "constant across all screens" section naming the shell components and any
cross-cutting rule.

## Phase 5 — HAND BACK THE OPEN QUESTIONS

State plainly what the source description did not determine and what you assumed. A visual makes
assumptions look decided; listing them keeps them open.

## Anti-patterns

| Do not | Because |
|---|---|
| render a hi-fi mock | it invites review of colour instead of structure |
| invent content to fill space | fake content gets reviewed as layout, not as design |
| draw only the happy path | the failure states are where the design is actually tested |
| silently place an unspecified element | it gets approved by accident |
| describe the chrome once and omit it | the constant frame is most of what people are agreeing to |
| use a diagram library for a UI layout | CSS boxes are the right tool and read more like the real thing |
