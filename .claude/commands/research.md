---
description: Pre-project research — conducts market, competitive, and technology research before writing a PRD. Produces a cited report and decision brief saved to neuroedge/docs/project_related/<objective-slug>/01-research/. Run before /prp-prd on any new product, platform, or major feature.
argument-hint: <topic> [--type market|technology|competitive|combined] [--output path]
---

## Arguments

```
$ARGUMENTS:
  <topic>          What to research (e.g. "EMQX vs Mosquitto for edge AI", "OEM edge AI market")
  --type           Focus: market | technology | competitive | combined (default: combined)
  --output         Output file path (default: neuroedge/docs/project_related/<objective-slug>/01-research/<topic-slug>.md)
```

---

## Phase 0 — DETECT

Parse `$ARGUMENTS`:

| Pattern | Action |
|---|---|
| Topic text provided | Use as research subject |
| `--type market` | Focus on market sizing, competitive analysis, OEM/vendor landscape |
| `--type technology` | Focus on technology evaluation, framework comparison, SDK trade-offs |
| `--type competitive` | Focus on competitive product landscape and positioning gaps |
| `--type combined` (default) | Full pre-project research: market + technology + competitive |
| Empty / blank | Ask: "What topic or question do you want to research?" |

Print scope before proceeding:

```
Topic:      <topic>
Type:       <market | technology | competitive | combined>
Output:     <neuroedge/docs/project_related/<objective-slug>/01-research/...md>
Skills:     deep-research (technology), market-research (market/competitive)
```

---

## Phase 1 — SCOPE

Identify the decision this research must support. Ask ONE question if not clear:

> "What decision will this research inform — platform selection, build vs buy, go-to-market, or another choice?"

Then define 3–5 sub-questions covering:

| Research dimension | Sub-question type |
|---|---|
| **Technology** (if applicable) | Performance, footprint, integration complexity, support health |
| **Market** (if applicable) | TAM/SAM, existing players, customer pain points |
| **Competitive** (if applicable) | What has been built, lock-in risks, positioning gaps |
| **Vendor/partner** (if applicable) | SDK license, OEM certification, commercial model |

---

## Phase 2 — EXECUTE

Spawn the `researcher` agent with the topic, type, and sub-questions.

The `researcher` agent will:
1. Apply `deep-research` skill for technology sub-questions (web search + deep-read, cited)
2. Apply `market-research` skill for market/competitive sub-questions (decision-oriented)
3. Cross-reference findings across sources
4. Produce a structured report with comparison tables where applicable
5. Add a 3-bullet Decision Brief pointing to open questions for `/prp-prd`

---

## Phase 3 — GENERATE

Save the full report to `neuroedge/docs/project_related/<objective-slug>/01-research/<topic-slug>.md`.

Create `neuroedge/docs/project_related/<objective-slug>/01-research/` if it does not exist.

File naming: lowercase, hyphens, no special chars + ISO date:
`edge-ai-runtime-platform-2026-05-28.md`

Report structure:

```markdown
# Research: <Topic>

**Date:** <today>
**Type:** <market | technology | competitive | combined>
**Decision it supports:** <one sentence>
**Confidence:** High | Medium | Low

---

## Executive Summary
[3–5 sentences]

## Findings
[Themed sections with citations]

## Comparison Table (if technology or competitive)
[Option A vs B vs C]

## Risks & Gaps

## Recommendation

## Decision Brief
→ [Key decision + reason]
→ [Top constraint to carry into PRD]
→ [Open question for /prp-prd]

## Sources
```

---

## Phase 4 — OUTPUT

Report to the user:

```
✓ Research complete — neuroedge/docs/project_related/<objective-slug>/01-research/<file>.md

  Topic:        <topic>
  Sources:      <N> sources reviewed
  Confidence:   High | Medium | Low
  Key finding:  <one-sentence summary>

  Decision Brief:
  → <chosen option / approach>
  → <top constraint>
  → <open question>

  Next steps:
  → /prp-prd    — write the PRD using these findings as evidence
  → /research <related topic>  — go deeper on a specific dimension
```

---

## Integration with Build Workflow

```
/research    → Research report + Decision Brief    (neuroedge/docs/project_related/<objective-slug>/01-research/*.md)   ← you are here
/prp-prd     → PRD (uses research findings as §2 Evidence)
/prd-to-epics    → EPICs + User Stories
/stories-to-tasks → Task Board
/prp-plan        → Implementation Plan
/prp-implement   → Development
/prp-pr          → Pull Request
/quality-gate    → Gate
```

The Decision Brief produced by `/research` maps directly into:
- PRD §2 Evidence section (research findings as supporting data)
- PRD §4 Key Hypothesis (the recommended direction becomes the testable hypothesis)
- PRD §12 Risks (research gaps and caveats become PRD risks)

---

## Skill Selection Guide

| Research question type | Skill used | Why |
|---|---|---|
| "How does X work technically?" | `deep-research` | Multi-source web synthesis with citations |
| "Who else has built this?" | `deep-research` + `market-research` | Web depth + business framing |
| "What's the market size?" | `market-research` | TAM/SAM framework, not just web search |
| "Which vendor/SDK should we use?" | Both | Technical fit (deep) + commercial fit (market) |
| "What are OEM partners doing?" | `market-research` | Business intelligence, not just tech docs |
| "Current state of a protocol/tool?" | `deep-research` | Recent sources, cross-referenced |

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /research · Skills: deep-research, market-research`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/requirements/deep-research.md`
> - `agentic-assets/skills/SDLC/requirements/market-research.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->
