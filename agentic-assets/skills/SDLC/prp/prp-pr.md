---
name: prp-pr
description: Pull-request creation procedure: mandatory security-review gate, PR-template discovery, push, and PR body assembly with security and coverage notes.
origin: NeuroEdge
---

# PRP — Pull Request

The full `prp-pr` procedure. It is single-sourced here so the exact same steps run whether a human invokes `/prp-pr` or a subagent reads this skill. The invoking command passes its `$ARGUMENTS` through as this procedure's input.

## Gate delegation

This procedure pauses at one or more points to ask the user a question and wait for the
answer (marked **GATE**, **STOP**, or **CHECKPOINT** below). Those questions can only be
asked from the main session: per decision D1 a subagent running this skill can neither
call `AskUserQuestion` nor spawn another agent. When this skill runs inside a subagent it
must surface each gate's question in its returned result and stop there; the main-session
orchestrator (`/agentforge`, or the human running the slash command) asks the user and
re-invokes the skill with the answer. Never silently skip a gate — dropping the question
would let a subagent bypass a control this procedure requires.

## Phase 0 — SECURITY GATE

**MANDATORY. Do not skip or bypass.** Runs before any git/push/PR action.

1. Compute the diff for review: `git diff origin/<base>...HEAD` (fall back to `git diff <base>...HEAD` if the branch
   isn't pushed yet).
2. Spawn the `security-reviewer` agent against that diff. It checks for secrets, SSRF, injection, unsafe crypto, and
   OWASP Top 10 issues.
   - **High/critical findings → STOP.** Report them to the user. Do not proceed to Phase 1 until fixed; re-run this
     gate after fixes.
   - Low/medium findings → carry them into the PR body's Security Notes section (Phase 4) and proceed.
3. Spawn the `pr-test-analyzer` agent against the same diff to assess test coverage **quality**, not just presence.
   This is advisory — report findings, do not block on them.
4. Keep both agents' summaries for Phase 4.

**CHECKPOINT**: No high/critical security findings (or the user has explicitly acknowledged and chosen to proceed
after seeing them).

---

## Phase 1 — VALIDATE

Check preconditions:

```bash
git branch --show-current
git status --short
git log origin/<base>..HEAD --oneline
```

| Check | Condition | Action if Failed |
|---|---|---|
| Not on base branch | Current branch ≠ base | Stop: "Switch to a feature branch first." |
| Clean working directory | No uncommitted changes | Warn: "You have uncommitted changes. Commit or stash first. Use `/prp-commit` to commit." |
| Has commits ahead | `git log origin/<base>..HEAD` not empty | Stop: "No commits ahead of `<base>`. Nothing to PR." |
| No existing PR | `gh pr list --head <branch> --json number` is empty | Stop: "PR already exists: #<number>. Use `gh pr view <number> --web` to open it." |

If all checks pass, proceed.

---

## Phase 2 — DISCOVER

### PR Template

Search for PR template in order:

1. `.github/PULL_REQUEST_TEMPLATE/` directory — if exists, list files and let user choose (or use `default.md`)
2. `.github/PULL_REQUEST_TEMPLATE.md`
3. `.github/pull_request_template.md`
4. `docs/pull_request_template.md`

If found, read it and use its structure for the PR body.

### Commit Analysis

```bash
git log origin/<base>..HEAD --format="%h %s" --reverse
```

Analyze commits to determine:
- **PR title**: Use conventional commit format with type prefix — `feat: ...`, `fix: ...`, etc.
  - If multiple types, use the dominant one
  - If single commit, use its message as-is
- **Change summary**: Group commits by type/area

### File Analysis

```bash
git diff origin/<base>..HEAD --stat
git diff origin/<base>..HEAD --name-only
```

Categorize changed files: source, tests, docs, config, migrations.

### PRP Artifacts

Check for related PRP artifacts:
- `neuroedge/docs/project_related/<objective-slug>/02-project-plan/reports/` — Implementation reports
- `neuroedge/docs/project_related/<objective-slug>/02-project-plan/` — Plans that were executed
- `neuroedge/docs/project_related/<objective-slug>/02-project-plan/` — Related PRDs

Reference these in the PR body if they exist.

---

## Phase 3 — PUSH

```bash
git push -u origin HEAD
```

If push fails due to divergence:
```bash
git fetch origin
git rebase origin/<base>
git push -u origin HEAD
```

If rebase conflicts occur, stop and inform the user.

---

## Phase 4 — CREATE

### With Template

If a PR template was found in Phase 2, fill in each section using the commit and file analysis. Preserve all template sections — leave sections as "N/A" if not applicable rather than removing them.

### Without Template

Use this default format:

```markdown
## Summary

<1-2 sentence description of what this PR does and why>

## Changes

<bulleted list of changes grouped by area>

## Files Changed

<table or list of changed files with change type: Added/Modified/Deleted>

## Testing

<description of how changes were tested, or "Needs testing">

## Security Notes

<low/medium findings from Phase 0's security-reviewer pass, or "None — security-reviewer found no issues">

## Test Coverage Notes

<pr-test-analyzer's assessment from Phase 0, or "N/A">

## Related Issues

<linked issues with Closes/Fixes/Relates to #N, or "None">
```

If a PR template was found in Phase 2 instead, still append **Security Notes** and **Test Coverage Notes** sections
even if the template doesn't define them — do not drop Phase 0's findings from the PR body.

### Create the PR

```bash
gh pr create \
  --title "<PR title>" \
  --base <base-branch> \
  --body "<PR body>"
  # Add --draft if the --draft flag was parsed from $ARGUMENTS
```

---

## Phase 5 — VERIFY

```bash
gh pr view --json number,url,title,state,baseRefName,headRefName,additions,deletions,changedFiles
gh pr checks --json name,status,conclusion 2>/dev/null || true
```

---

## Phase 6 — OUTPUT

Report to user:

```
PR #<number>: <title>
URL: <url>
Branch: <head> → <base>
Changes: +<additions> -<deletions> across <changedFiles> files

Security Gate (Phase 0): <PASS — no high/critical findings | PASS — user acknowledged N low/medium findings>
Test Coverage (pr-test-analyzer): <summary or "N/A">

CI Checks: <status summary or "pending" or "none configured">

Artifacts referenced:
  - <any PRP reports/plans linked in PR body>

Next steps:
  - gh pr view <number> --web   → open in browser
  - /code-review <number>       → review the PR
  - gh pr merge <number>        → merge when ready
```

---

## Edge Cases

- **No `gh` CLI**: Stop with: "GitHub CLI (`gh`) is required. Install: <https://cli.github.com/>"
- **Not authenticated**: Stop with: "Run `gh auth login` first."
- **Force push needed**: If remote has diverged and rebase was done, use `git push --force-with-lease` (never `--force`).
- **Multiple PR templates**: If `.github/PULL_REQUEST_TEMPLATE/` has multiple files, list them and ask user to choose.
- **Large PR (>20 files)**: Warn about PR size. Suggest splitting if changes are logically separable.
- **High/critical security finding in Phase 0**: Stop entirely. Do not proceed to Phase 1 even if the user is in a
  hurry — report the finding and require either a fix or an explicit, logged override decision from the user.
