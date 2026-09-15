# Fast lane, `--stage` re-entry, and defect fixing with AgentForge

The full `/agentforge` pipeline runs **S0→S17** with human hard gates at S2 requirements (PRD),
S5 sprint-plan, S6 test-plan and S7 architecture — two gates there, the HLD and the LLD, each approved
by a human architect (ADR-0013) — plus the **S13 PR review gate**, which is also hard: it is tied to
`gh pr create` and has no override. That rigor is right for a
**new objective**. It is heavy for the *2nd..Nth* change on an objective you have already taken
through a full run. This guide documents the lighter paths and when to use each.

## When to use which

| Situation | Use | Why |
|---|---|---|
| Brand-new objective / first feature / new sprint | **`/agentforge "<objective>"`** | Full gated S0→S17 — you want the PRD, sprint-plan, test-plan, HLD/LLD and PR gates |
| Legacy repo, no objective yet — just onboard it | **`/agentforge --stage bootstrap`** | Onboarding fast lane: no objective, no `run.json` |
| Incremental change on an already-run objective | **PRP fast lane** (below) | Reuses the same skills, skips the gated stage machine |
| You already have some artifacts (hand-written PRD, prior epics) | **`/agentforge --stage <id>`** | Rejoin the pipeline at a wired stage instead of redoing S0 |
| Fixing a defect | **`/fix "<defect>"`** or **`/agentforge --fix "<defect>"`** | Triage → failing test → fix → verify → review → PR, as one call |

## The PRP fast lane — four **separate** commands

```
/prp-plan  "<feature | path/to/prd.md | task-board.md>"   →  a plan file
/prp-implement  <path/to/plan.md>                          →  code + validation loops
/prp-commit  [target description]                          →  commits the work (blank = all changes)
/prp-pr  [base-branch]                                     →  pushes branch + opens the PR
```

**Important — `/prp-pr` does NOT run plan or implement.** It is *only* the last step: it
discovers a PR template, analyzes the already-committed changes, pushes the branch, and opens the
GitHub PR. If you run `/prp-pr` on a branch with no plan/implement work behind it, it just PRs
whatever commits already exist. Run the four in order; each is a deliberate checkpoint.

- `/prp-plan` — analyzes the codebase, extracts patterns, and writes a plan (interactive gates are
  asked by the main session, not a subagent).
- `/prp-implement` — executes that plan with rigorous validation loops (tests, typecheck).
- `/prp-commit` — commits.
- `/prp-pr` — push + PR (its procedure includes a mandatory security-review gate).

The fast lane deliberately has **none of the pipeline's stage gates** (PRD, sprint-plan, test-plan,
HLD/LLD). Use it only when the
objective's shape is already settled from the full run.

## `/agentforge --stage <id>` — rejoin mid-pipeline

Every id in `run_state.STAGE_SEQUENCE` is a valid `--stage` argument (`requirements`,
`architecture`, `epics`, `tasks`, `test-plan`, `build`, `review`, `deploy`, `sprint-close`, …).
`--stage <id>` on a fresh `init` marks every stage *before* `<id>` complete (noting they were
supplied outside the run — never fabricated as if `/agentforge` produced them) and starts the
stage loop at `<id>`. The orchestrator confirms with you which artifacts already exist for the
skipped stages, so the record is accurate. On an **existing** run, `--stage` is not meaningful — use
`--resume`, or start over then pass `--stage` on the fresh `init`.

`--stage bootstrap` is the one id that is **not** in `STAGE_SEQUENCE`: it is the onboarding fast
lane — it onboards a legacy repo with no objective and no `run.json`, like `--fix`. Don't reach for
`--stage onboarding` to get an audit without an objective; use `--stage bootstrap`.

Related re-entry flags: `--status` (one-screen re-orientation, no advance), `--resume` (restore
state after a break), `--dry-run` (preview remaining sequence, zero side effects).

## Defect fixing — recommended workflow (how AgentForge helps)

AgentForge packages a disciplined fix loop as one entry point, **`/fix`** (see
[below](#the-one-call-entry-points-fix-and-agentforge---fix)). This is the sequence it runs, and the
agents behind each step if you ever need to drive one by hand:

1. **Triage first — `test-triage` agent.** Classifies a failure as *product bug / test bug /
   environment / flake* with attached evidence, and files or quarantines. Don't fix before you
   know which of the four it is — a flake or env issue is not a code change.
2. **Reproduce with a failing test — `tdd-guide` agent.** Write the red test that captures the
   defect *before* touching product code. This is the single most important step: it proves the
   bug exists and proves the fix works, and it becomes a permanent regression guard.
3. **Make the fix:**
   - **Build/type/compile error** → the matching build-resolver (`build-error-resolver`,
     `cpp-build-resolver`, the `go`/`rust`/`java`/`kotlin`/`dart`/`csharp` resolvers,
     `embedded-build-resolver`, `pytorch-build-resolver`). These do minimal-diff, get-it-green fixes.
   - **Logic/behavior bug** → `developer` (with `tdd-guide`) for the smallest change that turns the
     red test green.
   - **Silent/swallowed failure** → `silent-failure-hunter` to find the root, not just the symptom.
4. **Verify + review** — re-run the suite; `code-reviewer` (and `security-reviewer` if the change
   touches input/auth/secrets) on the diff. The `stop:code-review-reminder` Stop hook already forces a
   holistic `code-reviewer` pass whenever source files were edited.
5. **Ship** — `/prp-commit` → `/prp-pr`.

### The one-call entry points: `/fix` and `/agentforge --fix`

You don't have to assemble the sequence by hand — it is wired as one call, two front doors that run the
**identical** flow (`skills/SDLC/development/defect-fix.md`):

```
/fix "<defect, ideally with a repro or failing-test output>"
# or, from inside the orchestrator:
/agentforge --fix "<defect>"
```

Either one runs: triage (`test-triage`) → **stop if flake/env** → failing test (`tdd-guide`) →
code-fix (build-resolver / `developer` / `silent-failure-hunter`, minimal diff) → verify (red→green,
no regressions) → review (`code-reviewer`, +`security-reviewer` if input/auth/secrets) → ship
(`/prp-commit` → `/prp-pr`, hard PR gate). Both run in the main session and neither enters the full
S0–S17 pipeline / `run.json`. Use `/fix` standalone; use `/agentforge --fix` if you're already in the
orchestrator mindset. Pass `--no-pr` to `/fix` to stop after review: the fix is committed, but no
PR is opened.

If the fix turns out to need an **architectural** change, it isn't a fast-lane defect fix — escalate to
`/agentforge "<objective>"` for the full gated pipeline.

Under the hood this is still the PRP fast lane (`/prp-commit` → `/prp-pr` do the shipping); `/fix` just
adds the triage + failing-test + routing discipline on top so defect-fixing has a first-class entry
point.
