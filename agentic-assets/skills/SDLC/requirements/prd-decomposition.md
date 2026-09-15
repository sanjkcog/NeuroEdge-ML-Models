---
name: prd-decomposition
description: Decompose a PRD into implementation-ready EPICs and User Stories with traceable acceptance criteria, MoSCoW priority mapping, and persona-aligned story format. Use when converting a PRD into a sprint-ready backlog.
origin: NeuroEdge
---

# PRD Decomposition — EPICs & User Stories

Turn a PRD into a sprint-ready backlog. Every story must be traceable (references a PRD section), testable (every AC is falsifiable), and persona-honest (every "As a" maps to a named persona from the PRD).

## When to Use

- A PRD exists and the next step is a sprint-ready backlog
- A phase plan needs user stories before implementation can start
- Stakeholder review requires a story map alongside the PRD
- An existing story set needs gap analysis against updated PRD requirements

---

## EPIC Sizing Rules

One EPIC = one cohesive phase or capability cluster completable by a single engineer in **1–4 weeks**.

| Signal | Action |
|---|---|
| Phase maps to a single system boundary (one container, one layer) | One EPIC per phase |
| Phase spans ≥ 3 disjoint system boundaries | Split into ≥ 2 EPICs |
| Phase contains only infra/scaffolding tasks | One EPIC, type = infrastructure |
| Two phases are explicitly parallel in the PRD | Separate EPICs, note parallel relationship |
| Phase 0 bootstrap has no user-facing value | EPIC required — internal user is the Eng team |

**EPIC ID scheme:** `EP-NN` where NN is the zero-padded phase number (EP-01, EP-02 … EP-09).

---

## User Story Format

Every story uses this three-part structure — no shortcuts:

```
As a [named persona from PRD §7 or equivalent section],
I want [concrete capability in one sentence],
so that [business/user value in one sentence].
```

**Story ID scheme:** `US-NN-SS` (EPIC number, story sequence within EPIC).

**Anti-patterns to reject:**
- `As a user` — too vague; use the exact PRD persona name
- `I want the system to` — system stories are not user stories; reframe around the human outcome
- `so that it works` — value-free; must state the concrete workflow benefit
- Compound stories: `I want X and Y` — split into two stories

---

## Acceptance Criteria Rules

Use checklist-style ACs — they map directly to CI validation and code review steps.

```
- [ ] [Observable, testable outcome in present tense]
- [ ] [Negative or boundary case covered]
- [ ] [Performance or reliability bound from PRD success metrics, if this story exercises one]
- [ ] [Error or failure mode handled]
```

**Minimum per story:** 3 ACs.
**Maximum per story:** 8 ACs. More than 8 = split the story.

**AC quality rules:**
- Each AC is independently verifiable (CI script or human reviewer can confirm it)
- No AC restates the story title — it adds new, falsifiable information
- At least one AC covers a failure or boundary scenario
- Success metrics from the PRD appear verbatim as ACs on the story that exercises them
- Mark ACs that cannot be automated as `[manual]`

---

## PRD Section → Story Mapping

| PRD Section | What to extract |
|---|---|
| Users & Personas | Exact names for `As a [X]` — never invent personas |
| Core Capabilities (MoSCoW) | MUST/SHOULD = story-bearing; COULD = future stories; WON'T = exclusion note only |
| Functional Requirements (FRs) | Each FR code should appear in ≥ 1 story AC as a reference |
| Success Metrics | Quantitative targets → verbatim ACs on the story that exercises them |
| Non-Functional Requirements | NFR bounds → ACs on the first story that exercises that boundary |
| Phases / Implementation Plan | Each phase → one EPIC; parallelism notes → parallel EPIC relationships |
| Open Questions | Blocking questions → noted on the EPIC they block |

---

## MoSCoW → Story Priority

| PRD Priority | Story priority | Sprint guidance |
|---|---|---|
| MUST | P0 — required in the same phase | Cannot close EPIC without all P0 stories done |
| SHOULD | P1 — targeted in phase, can slip to next | EPIC done if ≥ 80% of P1 stories done |
| COULD | P2 — stretch goal | Only if P0+P1 complete and capacity allows |
| WON'T | out-of-scope | Explicit exclusion note in EPIC; no story written |

---

## Story Splitting Heuristics

When a story is too large (> 5 ACs or > 3 days of work), split along these seams:

| Seam | Example |
|---|---|
| Happy path vs. error path | "Load model" vs. "Handle corrupted model file" |
| Stub vs. real implementation | "Backend stub compiles" vs. "Backend runs real inference" |
| Single platform vs. multi-platform | "x86 CPU pass" vs. "ARM64 pass" |
| Read vs. write | "Display sensor status" vs. "Configure sensor parameters" |
| Fast path vs. slow path | "Cache hit" vs. "Cold engine build" |

---

## Coverage Validation

After writing all stories, verify this checklist before finalising output:

```
[ ] Every MUST capability has ≥ 1 story
[ ] Every FR code appears in ≥ 1 story AC
[ ] Every persona appears as "As a [X]" in ≥ 1 story
[ ] Every quantitative success metric is referenced in ≥ 1 AC
[ ] Every blocking Open Question is noted on the EPIC it blocks
[ ] No story has < 3 ACs
[ ] No story has > 8 ACs (split if so)
[ ] WON'T items have an explicit exclusion note in the relevant EPIC — no story
```

---

## Output File Structure

The output document must contain these sections in order:

1. **Header block** — source PRD path, author, date, status
2. **EPIC INDEX table** — `ID | Epic | Phase | MoSCoW | Status`
3. **Per-EPIC sections** — one H2 per EPIC, containing goal sentence, phase, plan link, per-story H3 blocks
4. **Story Map** — ASCII phase-flow diagram
5. **Open Questions** — blocking OQs with owner and blocked EPIC/story

---

## Non-Negotiable Rules

- Do not invent personas not present in the PRD.
- Do not write stories for WON'T items — add an exclusion note instead.
- Every AC must be derivable from the PRD — no aspirational ACs invented from general knowledge.
- If a PRD section is missing (no Personas, no FRs), note the gap explicitly — do not fill with assumptions.
- If PRD status is `DRAFT — needs validation`, note this prominently at the top of output.
