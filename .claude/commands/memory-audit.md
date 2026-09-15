# Memory Audit Command

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /memory-audit · Skills: continuous-learning-v2`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/development/continuous-learning-v2.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Usage

`/memory-audit [--instincts-only | --adrs-only | --report-only | --apply]`

- default: interactive — inventory, assess, propose, confirm, execute, report
- `--instincts-only`: review only continuous-learning instincts
- `--adrs-only`: review only `docs/decisions/`
- `--report-only`: inventory + assess; propose nothing (read-only)
- `--apply`: skip the confirm step (use only inside `/loop` automation)

## Bootstrap

If this is the first run on a fresh project, create the directories first:

```bash
mkdir -p docs/context docs/decisions docs/decisions/archive docs/audit
```

The audit will exit cleanly if these directories do not exist; the manual checklist (§ "Manual checklist" below) is the fallback.

## Pipeline

| Phase | Action |
|---|---|
| 1. INVENTORY | Lists every memory artifact: ACTIVE.md, PROGRESS.md, all ADRs in `docs/decisions/`, MEMORY.md entries, `continuous-learning` instincts |
| 2. ASSESS | Flags oversized files (>600 tokens for always-read), low-confidence instincts (<0.4), resolved ADRs >90 days old, PROGRESS sections with no updates in 30+ days, ACTIVE.md with stale "Next 3 actions" |
| 3. PROPOSE | Prints a prioritized prune/archive proposal |
| 4. CONFIRM | Asks user for explicit approval before any deletion or archival; no destructive action without confirmation |
| 5. EXECUTE | Archives resolved ADRs to `docs/decisions/archive/<year>/`, compresses PROGRESS sections, prunes low-confidence instincts, refreshes the MEMORY.md index |
| 6. REPORT | Writes a one-line summary to `docs/context/ACTIVE.md` "Recently changed" + a full audit report to `docs/audit/memory-audit-<date>.md` |

## What gets checked

| Artifact | Health signals |
|---|---|
| `CLAUDE.md` (root) | Size; references to removed files; mentions of deprecated commands/agents |
| `AGENTS.md` (root) | Build/test commands still accurate; not drifting from Makefile |
| `docs/context/ACTIVE.md` | Last-updated timestamp; "Next 3 actions" plausibility; size cap |
| `docs/context/PROGRESS.md` | Sections with no updates >30 days; orphaned workstreams |
| `docs/decisions/ADR-*.md` | Status field present; "decided" entries >90 days old → candidate to archive |
| `docs/context/REPO_MAP.md` | Last-refreshed timestamp; module mentions vs actual filesystem |
| Auto-memory (`~/.claude/projects/<hash>/memory/`) | Duplicates; entries pointing to deleted files; size of MEMORY.md index |
| `continuous-learning` instincts | Confidence score; usage count |
| MCP server config | Servers enabled but never called in last 30 days |

## Decision rules

| Signal | Default action | User override |
|---|---|---|
| ADR marked "decided" >90 days ago | Archive to `docs/decisions/archive/<year>/` | Keep in active if still load-bearing |
| Instinct confidence <0.4 AND usage <3 in 90 days | Suggest delete | Keep if user judges it durable |
| PROGRESS.md section with no updates >60 days | Compress to one summary line | Keep if workstream is dormant-but-alive |
| ACTIVE.md "Next 3 actions" unchanged for >14 days | Flag — likely not actually next | User must refresh |
| Always-read file >600 tokens | Suggest splitting or moving content | User judgment |
| MCP server unused 30+ days | Suggest disabling | Keep if it's a backup |

## Example output

```
[ NeuroEdge Assets ]  /memory-audit · Skills: continuous-learning-v2

INVENTORY  — 1 CLAUDE.md (28 KB), 1 ACTIVE.md (412 tokens), 1 PROGRESS.md (1.1 KB),
             4 ADRs in docs/decisions/, 12 entries in MEMORY.md index,
             37 instincts (5 with confidence <0.4)

ASSESS     — Flagged 5 items:
  ⚠ ADR-0001-onnx-as-cpu-default.md      status: decided, age 127 days
  ⚠ ADR-0002-aws-us-west-2-region.md     status: decided, age 104 days
  ⚠ PROGRESS.md §Web Portal              last updated 47 days ago
  ⚠ ACTIVE.md "Next 3 actions"           unchanged 18 days
  ⚠ instinct[a1b2c3] "prefer-pydantic"   confidence 0.31, used 1 time in 90d

PROPOSE    — Archive: ADR-0001, ADR-0002 → docs/decisions/archive/2026/
             Compress: PROGRESS.md §Web Portal (12 lines → 2 lines summary)
             Refresh:  ACTIVE.md (user action required)
             Delete:   instinct[a1b2c3] (low confidence + low usage)

CONFIRM    — Apply changes? [y/N]: y

EXECUTE    — ✓ Archived 2 ADRs
             ✓ Compressed 1 PROGRESS section
             ✓ Pruned 1 instinct
             ⏳ ACTIVE.md flagged — user must refresh manually

REPORT     — Full report: docs/audit/memory-audit-2026-06-04.md
             Summary appended to ACTIVE.md "Recently changed"
```

## Integration with /loop

```bash
/loop 30d /memory-audit
```

The `loop-operator` runs the audit on schedule, proposes changes, and pauses for your approval before applying. Dismiss with:

```bash
/loop-status                       # see queued loops
/loop-status --cancel memory-audit
```

## Manual checklist (when the skill isn't available)

Walk these monthly. Each item is 1–3 minutes.

- [ ] `docs/context/ACTIVE.md` — is "Focus" still accurate? Are the 3 next actions still the actual next actions? If not, rewrite.
- [ ] `docs/context/PROGRESS.md` — are any "In progress" items actually shipped? Move to "Done." Dormant workstreams? Compress.
- [ ] List `docs/decisions/` — any ADRs older than 90 days that no longer drive current behavior? Move to `docs/decisions/archive/<year>/`.
- [ ] Open `CLAUDE.md` — references to removed files, retired commands, deleted agents? Trim.
- [ ] Run `make health-check` — any FAIL signals stale config.
- [ ] `~/.claude/projects/<hash>/memory/MEMORY.md` — over 200 lines? Archive old entries.
- [ ] Instincts with confidence <0.4 AND no usage in 90 days → deletion candidate.
- [ ] Your enabled MCP servers (8–10) — all still used? Disable unused.

## Notes

- This command is a stub today — the inventory and assessment phases work, the EXECUTE phase is on the toolkit's future skills roadmap.
- For now, use the manual checklist above and apply changes by hand.

## Arguments

`$ARGUMENTS`:
- `--instincts-only` optional
- `--adrs-only` optional
- `--report-only` optional
- `--apply` optional (for use within `/loop` automation only)
