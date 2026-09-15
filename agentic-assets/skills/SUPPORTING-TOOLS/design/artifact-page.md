---
name: artifact-page
description: Constraints and mechanics for a self-contained, shareable HTML page — CSP limits, dual-theme tokens, native mermaid, favicon and publish rules. Craft guidance lives in frontend-design; this covers only what is specific to a hosted single-file page. Use when producing a page that will be published rather than built into an app.
origin: NeuroEdge
---

# Artifact Page

**Deliberately narrow.** For visual craft — typography, palette, layout, avoiding generic
AI-looking output — read `frontend-design` first; it is the design skill and this does not repeat
it. What follows is only what is *different* about a single self-contained page that gets hosted
and shared.

> Written as a separate file rather than as edits to `frontend-design` because that skill is
> `origin: ECC` — external content is replaced on the next pull, so local additions belong beside
> it, not inside it.

## The page skeleton is supplied

Write the page **content only**. No `<!DOCTYPE>`, `<html>`, `<head>`, or `<body>` tags — the file
is wrapped at publish time, and a minimal CSS reset is already applied. Set a `<title>`; it names
the page in the browser tab and the gallery.

## 🔴 Strict CSP — everything must be inline

Requests to any external host are blocked. Not degraded — **blocked**.

| Blocked | Do instead |
|---|---|
| font CDN links | system font stacks, or `@font-face` with a data URI |
| external stylesheets | inline `<style>` |
| CDN scripts | inline `<script>` |
| remote images | data URIs, or draw with Canvas/SVG |
| `fetch` / XHR / WebSocket | none — the page is static unless runtime capabilities are declared |

A linked webfont does not error visibly; it **silently falls back**, and the page ships in a
typeface nobody chose. Pick system stacks deliberately, or inline the face.

## Dual theme is not optional

The page renders in the viewer's theme. Two signals, and the second must win in both directions:

1. `@media (prefers-color-scheme: dark)` — the OS preference
2. `:root[data-theme="dark"]` / `:root[data-theme="light"]` — stamped by the viewer's toggle

**The robust pattern is token-level:** define the palette as custom properties on `:root`, redefine
*only the tokens* in each of the three blocks, and style every component through the tokens. Never
style a component inside a media query — that is what makes the toggle fail one way.

A page may commit to a single visual world (a terminal, a letterpress invitation) — but make that
a stated choice, not an omission.

## Mermaid renders natively

` ```mermaid ` fences in Markdown, `<pre class="mermaid">` in HTML. No library, no import.

Diagrams inherit mermaid's own theme, which does not follow the page tokens. Two workable answers:
theme it with an `%%{init:{"theme":"base","themeVariables":{…}}}%%` directive, **or** give the
diagram its own fixed "paper" panel that reads correctly on both grounds. The second is more robust
and often reads better — a schematic is a printed thing.

## Layout rules that bite on a hosted page

- Wide content — tables, diagrams, code — gets `overflow-x: auto` **on its own container**. The page
  body must never scroll sideways.
- Lay out sibling groups with flex/grid `gap`, not per-element margins that collapse or double.
- `font-variant-numeric: tabular-nums` wherever digits align in columns.
- Watch selector specificity: type-based and element-based selectors fighting over the same padding
  is the most common way a generated page's spacing silently cancels out.

## Publish mechanics

| Field | Rule |
|---|---|
| `file_path` | same path on redeploy **keeps the URL**; a new path mints a new one |
| `favicon` | required; one or two emoji. **Keep it stable** — users find the tab by its icon. Change only on a hard topic pivot |
| `description` | one sentence; it is the gallery card's subtitle |
| `<title>` | stable across redeploys |
| `url` | required to update an artifact this conversation did not publish — otherwise a new URL is minted |

## Never publish

Pages impersonating a real person or organisation; fabricated records or receipts presented as
genuine; anything collecting credentials under false pretences; content targeting a private
individual. This holds regardless of who wrote the markup or what the stated purpose is.

Read any file you did not write, in full, before publishing it. Publishing distributes content — a
request not to look at it first is a reason to look, not an exemption.
