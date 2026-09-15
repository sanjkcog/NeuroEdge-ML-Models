---
name: defect-fix
description: The canonical defect-fix fast lane — triage → failing test → code-fix → verify → review → ship, wiring existing agents (test-triage, tdd-guide, the build-resolvers/developer/silent-failure-hunter, code-reviewer/security-reviewer) into one bounded flow. Run by both /fix and /agentforge --fix so they behave identically. Use to fix a reported defect without the full S0–S17 pipeline.
origin: NeuroEdge AgentForge
---

# Defect-Fix Fast Lane

One disciplined flow for fixing a reported defect, assembled from **existing** agents — no new ones.
It is the shared procedure behind both `/fix <defect>` (standalone) and `/agentforge --fix <defect>`
(orchestrator mode); both read and execute this skill so the behavior is identical. It is a fast lane:
it does **not** enter the S0–S17 stage machine (`run.json`), it fixes one defect and ships it.

## When to Activate

- `/fix <defect>` or `/agentforge --fix <defect>` is invoked
- A defect/bug needs a fix on an objective that already exists — not a new feature

## Run in the main session

Like `/agentforge`, this flow spawns subagents and asks the user through `AskUserQuestion` at the PR
gate, so it must run in the **main session** — never delegated to a subagent (D1). A subagent cannot
spawn another agent or open a gate.

## The flow (do the phases in order — never skip triage or the failing test)

### 1 — Triage (classify before you touch code)

Spawn **`test-triage`** with the defect description (and any failing-test output / stack trace).
It classifies as one of: **product bug · test bug · environment · flake**, with attached evidence.

- **flake / environment** → **stop**. This is not a code change. Report the classification, quarantine
  the flaky test if appropriate, and do not "fix" product code. Only continue for a product/test bug.
- **product bug / test bug** → continue to phase 2.

Never start editing before triage — fixing the wrong class of failure (a flake, an env issue) is wasted
change and hides the real cause.

### 2 — Reproduce with a failing test (red first)

Spawn **`tdd-guide`** to write the **failing (red) test** that captures the defect **before** any
product code changes. This is the single most important step:

- The test must fail **for the defect's reason** (assert on the wrong behavior), not for an unrelated
  error — verify the red is the right red.
- It becomes the permanent regression guard once green.
- For a *test bug*, the "failing test" step is fixing the test to correctly express the intended
  behavior (which then fails against current code if the code is also wrong, or passes if only the test
  was wrong).

Do not proceed to the fix until a failing test exists and fails for the right reason.

### 3 — Code-fix (route by defect type, minimal diff)

Pick the narrowest specialist for the defect and make the **smallest change that turns the red green**:

| Defect type | Agent |
|---|---|
| Build / type / compile / dependency error | the matching **build-resolver** — `build-error-resolver`, `cpp-`/`csharp-`/`go-`/`java-`/`kotlin-`/`rust-`/`dart-build-resolver`, `embedded-build-resolver`, `pytorch-build-resolver` |
| Logic / behavior bug | **`developer`** (with `tdd-guide`) — minimal change to green |
| Silent / swallowed failure, bad fallback | **`silent-failure-hunter`** to find the root cause, then `developer` to fix it |

Resolvers do minimal-diff, get-it-green fixes — no architectural edits. If a fix wants an architectural
change, that is not a fast-lane defect fix: stop and route it to `/agentforge` proper.

**Prevent the defect class before spawning — the highest-leverage step here (TD-013).** Whatever agent
you spawn, hand it the *specific* prior findings for this file or module, verbatim, and name the existing
helper it must reuse rather than writing a variant. TD-013 measured this as the one change that stopped a
whole defect class from recurring at **zero extra token cost** — a review that finds nothing is far cheaper
than one that finds something. Sources for that context, in order: findings already reported earlier in
this session, recent entries in `docs/decisions/TECH-DEBT.md`, and `git log` on the file. If there are no
prior findings, say so in the spawn rather than silently omitting the step.

### 4 — Verify (green + no regressions)

Re-run the test suite. The red test from phase 2 must now **pass**, and **no other test may regress**.
If anything else breaks, the fix was too broad — narrow it. Do not proceed on a red suite.

### 5 — Review

Spawn **`code-reviewer`** on the diff. Add **`security-reviewer`** if the change touches user input,
authentication, secrets, or an API boundary — **one reviewer by default**: TD-013 measured two reviewers at
213K tokens against 96K for one, which still found 2 HIGH. Tell the reviewer to work from `git show <sha>`
and open whole files only where a finding requires it. Address blocking findings and re-verify. (The Stop
hook also nudges a holistic review of edited source — honor it.)

**Cap at two rounds, then escalate (TD-013).** If a second round still returns blocking findings, stop and
report rather than looping a third time — three rounds on one item is the signal that the work needs
re-scoping, not re-reviewing. Escalate to `/agentforge` proper.

⚠ **Do not read this as licence to review less.** TD-013 measured every round it ran finding *real* defects,
including HIGH issues introduced by the previous round's own fixes. The rules above reduce the **cost per
round**, never the number of gates. Do not weaken or bypass the Stop hook, and do not skip the review
because the diff looks small — the escaped defects it caught were in security-sensitive code written late
in a long session.

**A regression test for a security fix is not done when it passes — it is done when it has been observed
failing against the pre-fix code (TD-013).** Four tests written to prove a security fix shipped while
testing nothing: they asserted against the wrong branch, or split on a substring after the injection point,
and passed identically against the broken implementation. When the fix is a small predicate change,
reconstruct the old predicate in a scratch script and run the new assertion against it. That took under a
minute each time it was done, and it is the only step that reliably separated a real test from a decorative
one.

### 6 — Ship

Ship via the PRP tail: **`/prp-commit`** then **`/prp-pr`**. `/prp-pr` opens the PR behind the same
hard PR gate as the full pipeline — `AskUserQuestion` in the main session, no bypass. Show the
triage classification + the failing-test-now-green evidence + the reviewer verdict as part of the ask,
so the human approves with the full picture.

## Hard rules

- **Never skip triage** (phase 1) or **the failing test** (phase 2) — they are what make this a *fix*
  and not a guess.
- **Never mark done** until the red test is green and the whole suite passes (phase 4).
- **Minimal diff** — a defect fix changes as little as possible; architectural change escalates to
  `/agentforge`.
- **Main session only** — spawn agents and open the PR gate from the main session.

## Output

A one-screen fix summary: defect → triage class → the regression test added → the fix (files touched +
which agent) → suite result → reviewer verdict → PR URL.
