---
name: prp-prd-migration
description: Migration PRD generation for a breaking redesign of a working system. Produces a retirement inventory, a behaviour-preservation contract, a cutover sequence and a rollback plan — the four things a product PRD has no place for. Use when accepted ADRs change an existing system's shape, not when specifying new product.
origin: NeuroEdge
---

# PRP — Migration PRD Generation

Sibling of `prp-prd`. **Use this one when the decisions are already made and the work is changing a
system that already runs.** `prp-prd` asks *what should we build and why*; this asks *what must
change, what must not, and how do we know we did not break it.*

## When this, not `prp-prd`

| Use `prp-prd` | Use `prp-prd-migration` |
|---|---|
| new product, feature, or platform | accepted ADRs change an existing system's shape |
| the problem is under-explored | the problem is decided; the risk is regression |
| success = the right thing gets built | success = the right thing gets built **and nothing silently stops working** |

If the input is a set of ADRs rather than a problem statement, you are in the right place.

## Gate delegation

This procedure pauses at points marked **GATE**. A subagent running this skill can neither call
`AskUserQuestion` nor spawn an agent — surface each gate's question in the returned result and stop
there; the main session asks and re-invokes with the answer. Never silently skip a gate.

## Phase 0 — DETECT

`$ARGUMENTS` is one of:

| Input | Action |
|---|---|
| paths/globs to ADR files | read all; treat their **Decision** sections as the requirement source |
| a directory of decisions | read every `ADR-*.md` with status `Accepted` |
| free text | ask for the ADRs — a migration PRD without decisions is a product PRD |

🔴 **GATE 0 — ADR status.** List every source ADR with its status. If any is still `Proposed`, stop
and ask whether to proceed. A migration built on unaccepted decisions bakes in choices nobody signed
off, and the retirement is not reversible at the same cost as the build.

## Phase 1 — RETIREMENT INVENTORY

The section a product PRD does not have, and the reason this skill exists.

For every Decision in the source ADRs, grep the tree and record what it makes stale. **Grep-verify;
never inventory from memory or from the ADR's own prose.**

| Column | Meaning |
|---|---|
| Item | the construct, field, module, or endpoint |
| Path | verified path(s) |
| Retired by | the ADR + decision id — **an item with no ADR is a bug, not a retirement** |
| Disposition | `delete` · `rewrite` · `replace` · `wire-in` (exists, unused) · `migrate` (data/config) |
| Blast radius | files touched, verified by grep |

Then state the disposition policy explicitly:

- **Default to delete.** Version control is the archive. An "archive" folder is a worse copy of
  history: unlinted, untested, outside the gates, and re-importable — at which point it is
  load-bearing again, not archived.
- **Exception — reference artifacts that are also test fixtures.** These move to a fixtures path
  *before* anything changes, because they are the regression baseline.
- **Recommend a branch, not a folder**, when blast radius crosses more than one estate.
- Tag the pre-migration commit regardless.

## Phase 1b — ACTORS

A migration usually has no external users, which is why a product PRD's persona section reads as
empty here. **It still has actors, and downstream decomposition requires them** — write them rather
than omitting the section.

Derive one actor per estate the retirement inventory touches, plus any genuinely external role:

| Typical actor | Owns |
|---|---|
| **Platform engineer** | the core the ADRs reshape — models, engine, registries |
| **<surface> engineer** | each additional estate with its own toolchain (UI, mobile, service) |
| **Migration operator** | adjudicates diffs, approves the retirement ledger, re-pins the baseline |
| **<external role>** | only if some step changes what an end user experiences |

Name them from the inventory, never from a template. An actor with no story in decomposition means
the inventory missed an estate.

## Phase 2 — BEHAVIOUR-PRESERVATION CONTRACT

For each area the migration touches, state which of the three it is. **Ambiguity here is the
single largest source of migration regression.**

| Class | Meaning | Verified by |
|---|---|---|
| **PRESERVED** | behaviour must be identical after | a test that passed before and passes after, unmodified |
| **CHANGED** | behaviour deliberately differs | a test asserting the new behaviour + one proving the old is gone |
| **REMOVED** | capability withdrawn | a test asserting it is absent, written so it cannot pass vacuously |

🔴 **GATE 1.** Present the PRESERVED list for confirmation before writing requirements. Anything the
user expects preserved that is not on this list is a defect discovered now rather than in production.

**The PRESERVED list is also this PRD's success metrics.** A migration succeeds when nothing that
should have kept working stopped — so emit it under a `## Success Metrics` heading as well as here,
rather than leaving downstream decomposition to find no metrics at all.

## Phase 3 — 🔴 TEST TRIAGE

The step teams skip, and the one that decides whether the migration is verifiable.

Classify **every** test file touching a retired surface:

| Bucket | Fate |
|---|---|
| **A — tests *of* retired code** | delete with the code |
| **B — tests that *assert a decision*** | revise **deliberately**, never delete quietly. Some must survive *unchanged* because the migration strengthens what they protect |
| **C — incidental users of a retired surface** | update fixtures only |

🔴 **The vacuous-pass trap.** A test asserting *"X does not appear in Y"* passes **trivially** once
X cannot exist. It goes green and proves nothing. Every Bucket-B test must be re-checked that it
still fails for the reason it claims.

🔴 **Baseline inversion.** If the project gates on *failing test ids* rather than counts — the
correct discipline normally — retirement inverts it: deleting a failing test makes "0 new failures"
trivially true. Require a **deleted-test ledger**: every removed test id with the ADR that retired
it. Re-pin the baseline deliberately, never as a side effect.

## Phase 4 — CUTOVER SEQUENCE

Order by **dependency, not by estate**. Derive it, and state the gate that must hold at each step.

State explicitly:
- which step is the point of no return
- which steps can land independently vs must land together
- what proves each step before the next starts

**Number each step and give it a title.** The cutover sequence *is* this PRD's implementation-phase
list, and decomposition maps one EPIC per step. Emit it under a heading containing the word
**Phases** (e.g. `## Cutover Sequence (Implementation Phases)`) so a downstream reader matching on
section intent finds it. An unnumbered prose sequence cannot be decomposed.

## Phase 5 — ROLLBACK

For each step: what reverts it, what does not revert (data, generated artifacts, external state),
and how long the old path stays runnable. **"Revert the commit" is not a rollback plan when
generated artifacts or migrated config are involved.**

## Phase 6 — REQUIREMENTS

Standard `FR-NN` numbering, so downstream `/prd-to-epics` and `/stories-to-tasks` work unchanged.
Every FR carries:

- the ADR + decision id it implements
- its behaviour class from Phase 2
- its acceptance check — **for a REMOVED capability, a check that cannot pass vacuously**

🔴 **GATE 2 — the PRD is a gated artifact.** Present for approval before any implementation planning.

## Output

Write to `<objective-slug>/02-project-plan/<name>.migration-prd.md`, the per-objective layout
`/prp-prd` also writes to (TD-019 replaced the older track-scoped tree). If the repo already uses a
different convention, **follow the repo's**, since downstream commands resolve siblings relative to
this path.

### 🔴 Required section headings

A migration PRD is an input to `/prd-to-epics`, which matches sections **by intent**, and whose gate
stops on missing personas or phases. Emit all of these, in this order:

| Heading | Content | Why it is required |
|---|---|---|
| `## Retirement Inventory` | Phase 1 | the section a product PRD lacks |
| `## Users & Context` | Phase 1b actors | **decomposition gate** — omitting it stops the pipeline |
| `## Behaviour-Preservation Contract` | Phase 2 | PRESERVED / CHANGED / REMOVED |
| `## Success Metrics` | the PRESERVED list, restated | **decomposition gate** |
| `## Test Triage` | Phase 3 | buckets + the deleted-test ledger requirement |
| `## Cutover Sequence (Implementation Phases)` | Phase 4, numbered | **decomposition gate** — one EPIC per step |
| `## Rollback` | Phase 5 | |
| `## Requirements` | Phase 6, `FR-NN` | |
| `## Out of Scope` | | |
| `## Open Questions` | closed ones marked decided, with who and when | |

**There is no MoSCoW table, and that is correct** — a migration's requirements are not optional; a
half-migrated system is not a reduced-scope system. Say so explicitly under `## Requirements` so a
reader looking for one does not conclude the section is missing.

## Anti-patterns

| Do not | Because |
|---|---|
| write a product PRD with a "migration" heading | the four sections above are the whole point |
| inventory from the ADR's prose | ADRs describe intent; grep describes reality |
| defer test triage to implementation | it decides whether the migration is verifiable at all |
| accept "0 new failures" without a deleted-test ledger | see Phase 3 |
| create an archive folder by default | see Phase 1 |
| retire an item with no ADR reference | that is scope creep wearing a cleanup costume |
| omit personas because "a migration has no users" | it has actors, and the decomposition gate stops on their absence — see Phase 1b |
| leave the cutover sequence as unnumbered prose | it is the implementation-phase list; one EPIC maps to one step |
| emit a PRD your own pipeline cannot read | the first run of this skill produced exactly that, and a human had to bridge the gap by hand |
