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
so the human approves with the full picture. Then complete the audit run log's ship section and
files-touched table (see **Audit run log** below). That happens whatever the answer is.

## Audit run log — every phase, every run

Every fast-lane run leaves a **committed audit record**: what was asked, what each phase found, which
agent did it, which files changed, and which commit shipped it. It is written **as the run goes**, one
update per phase, never reconstructed at the end — the same rule `run.json` follows in the full pipeline.

### Where it lives

`<project_related>/<fix-slug>/runlog.md`, where:

- **`<project_related>`** is the first that exists of `neuroedge/docs/project_related/` and
  `docs/project_related/`; if neither exists, create `docs/project_related/`. Never a repo-root path.
- **`<fix-slug>`** names what authorised the fix:
  - the argument is a design document (a design decision, ADR, or any `.md` under `docs/`) → its file
    name without `.md`, lower-cased — e.g. `2026-09-21-capability-manifest-2.0-device-facts-only`,
    `adr-0029-simulator-opcua-egress-face`;
  - otherwise → `fix-<YYYY-MM-DD>-<defect-slug>` (kebab-case, at most 60 characters).

This is the one standalone output that **does** get a `project_related/` folder: the audit record belongs
beside the decision it implements, not in a shared `runs/` pile. No `run.json` or `gates.json` is created.

**Re-runs append, never overwrite.** A second fix against the same document adds `## Run 2` (then
`## Run 3` …) to the same `runlog.md`; earlier runs stay intact as history.

### When to write

| Moment | Write |
|---|---|
| Before phase 1 | Create the file (or append the next `## Run N`) with the **run header** |
| After each phase 1–5 | Append that phase's row to the phase table **and** its detail section |
| Stopped early (flake/env at triage, architectural escalation, round-2 blocking review, gate rejected) | Record the stop: phase, reason, evidence. A stopped run is still an audited run |
| After the ship gate | Record the gate decision, commit SHA(s), push state, PR URL or why there is none, and the files-touched table |

### Run header

```markdown
## Run <N> — <YYYY-MM-DD HH:MM UTC>

| Field | Value |
|---|---|
| Command | `/agentforge --fix <argument>` or `/fix <argument>` — exactly as invoked |
| Authorised by | `<path to design doc>` @ `<git log -1 --format=%h -- <path>>`, or "defect report" |
| Repository · branch | `<repo folder>` · `<git branch --show-current>` |
| Base commit | `<git rev-parse --short HEAD>` at the start of the run |
| Operator | `<git config user.name>` |
| Baseline suite | `<command>` → `<N passed, M failed>`; failing ids: `<list, or none>` |
```

Record the **baseline failing test ids** before any change — phase 4 compares ids against them, never
counts (a pre-existing failure is not a regression, and a count can hide a swap).

### Phase table (one row per phase, appended as it completes)

```markdown
| # | Phase | Agent | Outcome | Evidence | Tokens (source) |
|---|---|---|---|---|---|
| 1 | Triage | test-triage | product bug | <one line> | 27,236 (measured) |
```

Tokens come from the spawn's reported usage (`measured`); work the main session did itself is
`estimated` with the method stated, or `unrecorded`. Never invent a figure.

### Detail sections (one per phase)

1. **Triage** — the class, the evidence, anything triage flagged about the test itself.
2. **Failing test** — the test ids added or changed, the red count, and **why each is the right red**
   (the assertion that fails, not an import or fixture error). Tests that already passed, and why.
3. **Fix** — the agent, the prior findings handed to it (or "none recorded"), and the change in one line
   per file.
4. **Verify** — suite before → after, the red tests now green, and the failing ids after the change
   compared with the baseline ids. Name what could not be verified here (e.g. a C++ test not compiled).
5. **Review** — reviewer(s), rounds, verdict, and findings by severity; each finding fixed or deferred,
   with the reason.
6. **Ship** — the gate question as shown, the answer, who answered, and when.

**Main-session corrections.** When the main session edits anything itself, outside a spawned agent (for
example, fixing an agent's output after verifying it), list each edit under the phase it happened in,
with the reason. An audit record that credits the agents with the main session's changes is wrong.

### Files touched and commits

After the ship commit, append a table built from git, not from memory:

```bash
git show --name-status --format="%h %s" <sha>    # per commit: A/M/D/R + path
git show --stat --format= <sha>                   # lines changed per file
git status --short                                # anything left uncommitted
```

```markdown
| Commit | Status | File | +/- |
|---|---|---|---|
| 6d22f1d | M | ne-device-agent/ne_device_agent/assess.py | +9 −118 |
```

State the push state plainly: `pushed to <remote>/<branch>`, `committed locally, not pushed`, or
`not committed (gate: <answer>)`, plus the PR URL, or why there is none (for example, a direct-to-main
workflow).

### Committing the log

The log is part of the fix: stage `runlog.md` into the fix commit with the phase 1–5 sections. The ship
section needs the commit's own SHA, so append it afterwards and commit it on its own as
`docs(fix-log): record <sha> for <fix-slug>`. **Never amend** the fix commit to fold it in. When the
gate is rejected, the log is still committed (alone), so the rejected run stays on record.

## Hard rules

- **Never skip triage** (phase 1) or **the failing test** (phase 2) — they are what make this a *fix*
  and not a guess.
- **Write the audit run log as you go** — created before phase 1, one update per phase, committed with
  the fix, and never overwritten by a later run.
- **Never mark done** until the red test is green and the whole suite passes (phase 4).
- **Minimal diff** — a defect fix changes as little as possible; architectural change escalates to
  `/agentforge`.
- **Main session only** — spawn agents and open the PR gate from the main session.

## Output

A one-screen fix summary: defect → triage class → the regression test added → the fix (files touched +
which agent) → suite result → reviewer verdict → commit SHA(s) and PR URL (or why none) → the path of
the audit run log.
