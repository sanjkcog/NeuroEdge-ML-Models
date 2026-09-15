---
name: prp-prd
description: Problem-first, hypothesis-driven PRD generation procedure: interactive discovery, grounding research, and a full PRD template with stable FR-NN requirement numbering.
origin: NeuroEdge
---

# PRP — PRD Generation

The full `prp-prd` procedure. It is single-sourced here so the exact same steps run whether a human invokes `/prp-prd` or a subagent reads this skill. The invoking command passes its `$ARGUMENTS` through as this procedure's input.

## Gate delegation

This procedure pauses at one or more points to ask the user a question and wait for the
answer (marked **GATE**, **STOP**, or **CHECKPOINT** below). Those questions can only be
asked from the main session: per decision D1 a subagent running this skill can neither
call `AskUserQuestion` nor spawn another agent. When this skill runs inside a subagent it
must surface each gate's question in its returned result and stop there; the main-session
orchestrator (`/agentforge`, or the human running the slash command) asks the user and
re-invokes the skill with the answer. Never silently skip a gate — dropping the question
would let a subagent bypass a control this procedure requires.

## Phase 0 — DETECT

Determine input type from `$ARGUMENTS`:

| Input Pattern | Detection | Action |
|---|---|---|
| Path ending in `project_objectives.md` | Objectives file | Read it; seed Phases 1, 2, 4, 6 from its content instead of asking every question from scratch |
| Empty / blank | No input | Look for `project_objectives.md` at the repo root — if found, treat as above; otherwise proceed to Phase 1 with no seed (today's behavior) |
| Path to any other `.md` file | Reference file | Read for context, treat as free-form seed — not assumed to have structured objectives |
| Free-form text | Feature/product idea | Proceed directly to Phase 1 as today |

### Objectives File Parsing (when input is `project_objectives.md`)

Objectives docs vary in structure — extract by content and intent, not by requiring exact headings.

1. Read the file in full.
2. Extract whatever is present, mapping to where it seeds later phases:

   | Extracted | Seeds |
   |---|---|
   | Problem / mission / why statement | Phase 1 restated understanding; Phase 2 Q2 (What) / Q3 (Why can't they solve it today) |
   | Target users / personas / audience | Phase 4 Primary User |
   | Goals / success criteria / KPIs | Phase 2 Q5 (How will you know) + Phase 6 Key Hypothesis |
   | Constraints (timeline, budget, technical, regulatory) | Phase 2 Q3 + Phase 4 Constraints |
   | Non-goals / explicit exclusions | Phase 6 Out of Scope |
   | Stated priorities / must-haves | Phase 6 MVP Definition / Must Have vs Nice to Have |

3. Present the extraction back to the user before proceeding — do not silently assume it's complete or correct:

   > **Loaded `project_objectives.md`. Here's what I extracted:**
   > - Problem: {extracted or "not stated"}
   > - Users: {extracted or "not stated"}
   > - Goals/KPIs: {extracted or "not stated"}
   > - Constraints: {extracted or "not stated"}
   > - Out of scope: {extracted or "not stated"}
   >
   > I'll skip questions already answered above and only ask about what's missing. Confirm or correct anything before
   > I continue?

   **GATE**: Wait for confirmation/corrections before proceeding to Phase 1.

4. In Phases 1, 2, 4, and 6 below: for any individual question whose answer was already extracted with reasonable
   confidence, **show the extracted answer instead of asking** (still let the user correct it) and only ask the
   sub-questions that remain genuinely unanswered. Do not re-ask what the objectives file already answered.
5. Note the objectives file as the source in the generated PRD (Phase 7 template's Research Summary section).

If no `project_objectives.md` is found and none was provided, proceed exactly as today — no behavior change.

---

## Your Role

You are a sharp product manager who:
- Starts with PROBLEMS, not solutions
- Demands evidence before building
- Thinks in hypotheses, not specs
- Asks clarifying questions before assuming
- Acknowledges uncertainty honestly

**Anti-pattern**: Don't fill sections with fluff. If info is missing, write "TBD - needs research" rather than inventing plausible-sounding requirements.

---

## Process Overview

```
QUESTION SET 1 → GROUNDING → QUESTION SET 2 → RESEARCH → QUESTION SET 3 → GENERATE
```

Each question set builds on previous answers. Grounding phases validate assumptions.

---

## Phase 1: INITIATE - Core Problem

**If `project_objectives.md` was loaded in Phase 0**, use its extracted problem/mission statement as the restated
understanding directly — skip the open-ended "what do you want to build" question.

**If no input provided** (and no objectives file found), ask:

> **What do you want to build?**
> Describe the product, feature, or capability in a few sentences.

**If input provided**, confirm understanding by restating:

> I understand you want to build: {restated understanding}
> Is this correct, or should I adjust my understanding?

**GATE**: Wait for user response before proceeding.

---

## Phase 2: FOUNDATION - Problem Discovery

If Phase 0 already extracted answers to any of the questions below, show the extracted answer instead of asking and
only ask what's genuinely missing — see Phase 0's Objectives File Parsing.

Ask these questions (present all at once, user can answer together):

> **Foundation Questions:**
>
> 1. **Who** has this problem? Be specific - not just "users" but what type of person/role?
>
> 2. **What** problem are they facing? Describe the observable pain, not the assumed need.
>
> 3. **Why** can't they solve it today? What alternatives exist and why do they fail?
>
> 4. **Why now?** What changed that makes this worth building?
>
> 5. **How** will you know if you solved it? What would success look like?

**GATE**: Wait for user responses before proceeding.

---

## Phase 3: GROUNDING - Market & Context Research

After foundation answers, conduct research:

**Research market context:**

1. Find similar products/features in the market
2. Identify how competitors solve this problem
3. Note common patterns and anti-patterns
4. Check for recent trends or changes in this space

Compile findings with direct links, key insights, and any gaps in available information.

**If a codebase exists, explore it in parallel:**

1. Find existing functionality relevant to the product/feature idea
2. Identify patterns that could be leveraged
3. Note technical constraints or opportunities

Record file locations, code patterns, and conventions observed.

**Summarize findings to user:**

> **What I found:**
> - {Market insight 1}
> - {Competitor approach}
> - {Relevant pattern from codebase, if applicable}
>
> Does this change or refine your thinking?

**GATE**: Brief pause for user input (can be "continue" or adjustments).

---

## Phase 4: DEEP DIVE - Vision & Users

If Phase 0 already extracted Primary User or Constraints from `project_objectives.md`, show those instead of asking
and only ask what's missing.

Based on foundation + research, ask:

> **Vision & Users:**
>
> 1. **Vision**: In one sentence, what's the ideal end state if this succeeds wildly?
>
> 2. **Primary User**: Describe your most important user - their role, context, and what triggers their need.
>
> 3. **Job to Be Done**: Complete this: "When [situation], I want to [motivation], so I can [outcome]."
>
> 4. **Non-Users**: Who is explicitly NOT the target? Who should we ignore?
>
> 5. **Constraints**: What limitations exist? (time, budget, technical, regulatory)

**GATE**: Wait for user responses before proceeding.

---

## Phase 5: GROUNDING - Technical Feasibility

**If a codebase exists, perform two parallel investigations:**

Investigation 1 — Explore feasibility:
1. Identify existing infrastructure that can be leveraged
2. Find similar patterns already implemented
3. Map integration points and dependencies
4. Locate relevant configuration and type definitions

Record file locations, code patterns, and conventions observed.

Investigation 2 — Analyze constraints:
1. Trace how existing related features are implemented end-to-end
2. Map data flow through potential integration points
3. Identify architectural patterns and boundaries
4. Estimate complexity based on similar features

Document what exists with precise file:line references. No suggestions.

**If no codebase, research technical approaches:**

1. Find technical approaches others have used
2. Identify common implementation patterns
3. Note known technical challenges and pitfalls

Compile findings with citations and gap analysis.

**Summarize to user:**

> **Technical Context:**
> - Feasibility: {HIGH/MEDIUM/LOW} because {reason}
> - Can leverage: {existing patterns/infrastructure}
> - Key technical risk: {main concern}
>
> Any technical constraints I should know about?

**GATE**: Brief pause for user input.

---

## Phase 6: DECISIONS - Scope & Approach

If Phase 0 already extracted Goals/KPIs, non-goals, or stated priorities from `project_objectives.md`, show those as
the starting point for Key Hypothesis / Out of Scope / MVP Definition instead of asking from scratch.

Ask final clarifying questions:

> **Scope & Approach:**
>
> 1. **MVP Definition**: What's the absolute minimum to test if this works?
>
> 2. **Must Have vs Nice to Have**: What 2-3 things MUST be in v1? What can wait?
>
> 3. **Key Hypothesis**: Complete this: "We believe [capability] will [solve problem] for [users]. We'll know we're right when [measurable outcome]."
>
> 4. **Out of Scope**: What are you explicitly NOT building (even if users ask)?
>
> 5. **Open Questions**: What uncertainties could change the approach?

**GATE**: Wait for user responses before generating.

---

## Phase 7: GENERATE - Write PRD

**Output path**: `neuroedge/docs/project_related/<objective-slug>/02-project-plan/PRD.md`

Create directory if needed: `mkdir -p neuroedge/docs/project_related/prd`

### PRD Template

```markdown
# {Product/Feature Name}

## Problem Statement

{2-3 sentences: Who has what problem, and what's the cost of not solving it?}

## Evidence

- {User quote, data point, or observation that proves this problem exists}
- {Another piece of evidence}
- {If none: "Assumption - needs validation through [method]"}

## Proposed Solution

{One paragraph: What we're building and why this approach over alternatives}

## Key Hypothesis

We believe {capability} will {solve problem} for {users}.
We'll know we're right when {measurable outcome}.

## What We're NOT Building

- {Out of scope item 1} - {why}
- {Out of scope item 2} - {why}

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|--------------|
| {Primary metric} | {Specific number} | {Method} |
| {Secondary metric} | {Specific number} | {Method} |

## Open Questions

- [ ] {Unresolved question 1}
- [ ] {Unresolved question 2}

---

## Users & Context

**Primary User**
- **Who**: {Specific description}
- **Current behavior**: {What they do today}
- **Trigger**: {What moment triggers the need}
- **Success state**: {What "done" looks like}

**Job to Be Done**
When {situation}, I want to {motivation}, so I can {outcome}.

**Non-Users**
{Who this is NOT for and why}

---

## Solution Detail

### Core Capabilities (MoSCoW)

Assign each row a stable `FR-NN` code in table order (all Must rows first, then Should, then Could, then Won't) —
this is the PRD's functional-requirement numbering, the single source of truth `/prd-to-epics` traces stories back
to. Once assigned, an FR code is permanent: later edits append new rows at the end of their priority block rather
than renumbering existing ones.

| FR | Priority | Capability | Rationale |
|----|----------|------------|-----------|
| FR-01 | Must | {Feature} | {Why essential} |
| FR-02 | Must | {Feature} | {Why essential} |
| FR-03 | Should | {Feature} | {Why important but not blocking} |
| FR-04 | Could | {Feature} | {Nice to have} |
| FR-05 | Won't | {Feature} | {Explicitly deferred and why} |

### MVP Scope

{What's the minimum to validate the hypothesis}

### User Flow

{Critical path - shortest journey to value}

---

## Technical Approach

**Feasibility**: {HIGH/MEDIUM/LOW}

**Architecture Notes** — cite the `FR-NN` code where a component maps directly to a capability row
- {Key technical decision and why} (implements FR-NN, if applicable)
- {Dependency or integration point}

**Technical Risks**

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| {Risk} | {H/M/L} | {How to handle} |

---

## Implementation Phases

<!--
  STATUS: pending | in-progress | complete
  PARALLEL: phases that can run concurrently (e.g., "with 3" or "-")
  DEPENDS: phases that must complete first (e.g., "1, 2" or "-")
  PRP: link to generated plan file once created
-->

| # | Phase | Description | Status | Parallel | Depends | PRP Plan |
|---|-------|-------------|--------|----------|---------|----------|
| 1 | {Phase name} | {What this phase delivers} | pending | - | - | - |
| 2 | {Phase name} | {What this phase delivers} | pending | - | 1 | - |
| 3 | {Phase name} | {What this phase delivers} | pending | with 4 | 2 | - |
| 4 | {Phase name} | {What this phase delivers} | pending | with 3 | 2 | - |
| 5 | {Phase name} | {What this phase delivers} | pending | - | 3, 4 | - |

### Phase Details

**Phase 1: {Name}**
- **Goal**: {What we're trying to achieve}
- **Scope**: {Bounded deliverables}
- **Success signal**: {How we know it's done}

**Phase 2: {Name}**
- **Goal**: {What we're trying to achieve}
- **Scope**: {Bounded deliverables}
- **Success signal**: {How we know it's done}

{Continue for each phase...}

### Parallelism Notes

{Explain which phases can run in parallel and why}

---

## Decisions Log

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| {Decision} | {Choice} | {Options considered} | {Why this one} |

---

## Research Summary

**Source Objectives**
{Path to `project_objectives.md` if one seeded this PRD, or "None — started from free-form input/discovery questions"}

**Market Context**
{Key findings from market research}

**Technical Context**
{Key findings from technical exploration}

---

*Generated: {timestamp}*
*Status: DRAFT - needs validation*
```

---

## Phase 8: OUTPUT - Summary

After generating, report:

```markdown
## PRD Created

**File**: `neuroedge/docs/project_related/<objective-slug>/02-project-plan/PRD.md`
**Source Objectives**: {path to project_objectives.md, or "None — free-form/discovery"}

### Summary

**Problem**: {One line}
**Solution**: {One line}
**Key Metric**: {Primary success metric}

### Validation Status

| Section | Status |
|---------|--------|
| Problem Statement | {Validated/Assumption} |
| User Research | {Done/Needed} |
| Technical Feasibility | {Assessed/TBD} |
| Success Metrics | {Defined/Needs refinement} |
| Functional Requirements | {N} FR codes assigned (FR-01…FR-NN) |

### Open Questions ({count})

{List the open questions that need answers}

### Recommended Next Step

{One of: user research, technical spike, prototype, stakeholder review, etc.}

### Implementation Phases

| # | Phase | Status | Can Parallel |
|---|-------|--------|--------------|
{Table of phases from PRD}

### To Start Implementation

Run: `/prp-plan neuroedge/docs/project_related/<objective-slug>/02-project-plan/PRD.md`

This will automatically select the next pending phase and create an implementation plan.
```

---

## Question Flow Summary

```
┌─────────────────────────────────────────────────────────┐
│  INITIATE: "What do you want to build?"                 │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  FOUNDATION: Who, What, Why, Why now, How to measure    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  GROUNDING: Market research, competitor analysis        │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  DEEP DIVE: Vision, Primary user, JTBD, Constraints     │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  GROUNDING: Technical feasibility, codebase exploration │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  DECISIONS: MVP, Must-haves, Hypothesis, Out of scope   │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  GENERATE: Write PRD to neuroedge/docs/project_related/<objective-slug>/02-project-plan/              │
└─────────────────────────────────────────────────────────┘
```

---

## Integration with ECC

After PRD generation:
- Use `/prp-plan` to create implementation plans from PRD phases
- Use `/plan` for simpler planning without PRD structure
- Use `/save-session` to preserve PRD context across sessions

## Success Criteria

- **PROBLEM_VALIDATED**: Problem is specific and evidenced (or marked as assumption)
- **USER_DEFINED**: Primary user is concrete, not generic
- **HYPOTHESIS_CLEAR**: Testable hypothesis with measurable outcome
- **SCOPE_BOUNDED**: Clear must-haves and explicit out-of-scope
- **QUESTIONS_ACKNOWLEDGED**: Uncertainties are listed, not hidden
- **ACTIONABLE**: A skeptic could understand why this is worth building
- **REQUIREMENTS_TRACEABLE**: every Core Capabilities row carries a stable `FR-NN` code so `/prd-to-epics` and
  `/stories-to-tasks` can trace story → AC → FR without guessing
