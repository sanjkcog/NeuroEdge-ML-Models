# Packaging review — what ships to a target, what is surplus, what is ignored

**Reviewed:** 2026-09-14 · **Scope:** ADR-0014 through ADR-0018, and the install pathway
(`install.py`, `patch_assets.py`, `update_agentforge_claude_project.py`, `setup_neuroedge_agentic_tools.py`).

Every number here was measured, not estimated: a clean `git init` directory was installed into and
then enumerated, and `--verify` / `--check-coverage` were run against the result.

> **Note on where this file lives.** `docs/guides/` is shipped, so this document installs into
> every target as `agentic-assets/docs/guides/review_surplus_files_to_target.md`. That is
> intentional — the "what gets copied" section answers a question a target operator actually has.
> Per the shipped-guide link rule, out-of-tree files are named as plain backticked paths rather
> than links, because a link out of `docs/guides/` dangles once the file is installed one level
> deeper.

---

## 1. What gets copied to a target

A fresh install writes **512 files**, of which **497 are content-managed** (recorded in
`agentic-assets/INSTALLED_MANIFEST.json` and therefore prunable on a later update). The remainder
are bootstrapped-once files the target then owns.

> That 497 includes this document, which ships as a guide like any other. The trim described in §2
> measured 505 → 489 immediately after it; each guide or package file added since has raised the managed
> count by one. Re-measure with `--check-coverage` rather than trusting this number if guides have changed.

### 1.1 Copied assets

| Source in Assets | Destination in target | Files | Notes |
|---|---|---|---|
| `commands/**` | `.claude/commands/**` | 44 | Tree shape preserved |
| `agents/**` + `packs/*/agents/` | `.claude/agents/` | 67 | **Flattened** — Claude Code discovers agents by flat scan |
| `scripts/hooks/*.js` | `scripts/hooks/` | 17 | Tests excluded (§2) |
| `scripts/scope/` | `agentic-assets/scripts/scope/` | 1 | `/scope-context` invokes it by literal path |
| `skills/**` + `packs/*/skills/` | `agentic-assets/skills/**` | 235 | Largest single payload |
| `docs/guides/*.md` | `agentic-assets/docs/guides/` | 12 | `.md` only — HTML excluded (§2) |
| `plugins/` | `agentic-assets/plugins/` | 3 | Plugin catalog |
| `agentforge/src/` | `agentforge/src/` | 54 | SDLC orchestrator + QA runners |
| `health_check/` | `health_check/` | 8 | |
| `simulator/` | `agentforge_simulator/` | 36 | **Renamed on install** |
| `src/*/` | `src/*/` | 17 | `neuroedge_marketing` (13), `neuroedge_productdoc` (4) |
| `projects/generic/` | `CLAUDE.md`, `.env.example` | 2 | Seeded once, then project-owned |
| `NOTICE.md`, `README.md` | root + `agentic-assets/` | 3 | Attribution |

The 235 skills break down as: `SOFTWARE` 105, `SDLC` 50, `DEPLOY-TARGETS` 21, `ENGINEERING` 21,
`SUPPORTING-TOOLS` 19, `DOMAIN` 12, `REGULATORY` 5, `SUBJECTS` 2.

### 1.2 Generated, not copied

These are created by the installer and then belong to the target. They are deliberately **not** in
the manifest, so an update will never overwrite or delete a team's own content.

| Path | What it is |
|---|---|
| `docs/context/` (5 files) | The target's own memory bank — `ACTIVE.md`, `PROGRESS.md`, `REPO_MAP.md`, `GLOSSARY.md`, `OPEN_QUESTIONS.md`. This is what the `session-start-memory-bank.js` hook reads |
| `docs/decisions/ADR-0000-template.md`, `TECH-DEBT.md` | ADR template and the target's own debt ledger (a write-target for `developer`) |
| `docs/decisions/archive/`, `docs/audit/` | `.gitkeep` placeholders |
| `AGENTS.md`, `CLAUDE.md` | Project instruction files, seeded from the generic template |
| `.claude/settings.json` | Merged from `hook-config.json` — 18 hook groups |
| `.claude/settings.local.json` | Blank API-key stub |
| `agentic-assets/docs/context/README.md` | Pointer to the real memory bank (see §2.4) |
| `.env.example` | Placeholder template |

### 1.3 The one rename

`simulator/` in Assets installs as `agentforge_simulator/` in a target. This trips people up, so it
is worth stating plainly: **`simulator/` is the only canonical source.** A directory named
`agentforge_simulator/` at the Assets repo root is self-install residue, is now gitignored, and
ships to nobody. Editing it is a silent no-op — see finding F-A below.

### 1.4 Integrity checks

Two commands verify the payload, both of which pass on a fresh install:

```bash
python install.py --project <path> --verify          # MISSING / DRIFT / UNVERIFIABLE / DANGLING
python install.py --project <path> --check-coverage  # every source asset has a counterpart
```

`DANGLING` is the ADR-0017 D-1 reference-resolution check (`install.py` `check_references`). It
extracts cited paths under exactly four prefixes — `agentic-assets/…`, `scripts/hooks/…`,
`scripts/scope/…`, and `agentforge/docs/…` — from `commands/**`, `agents/**`, and pack
`agents/`/`commands/`, and fails if a cited path is not shipped. Any `agentforge/docs/…` citation is
dangling by construction, since that tree never ships. Other `scripts/…` or `agentforge/…` paths
(for example `agentforge/src/…`) are not judged, and neither are target-side write paths. The check
reads the source tree, so a skill deleted without updating its citing command fails in Assets before
any install.

---

## 2. What is surplus — and what was removed

ADR-0017 finding F-4 identified four classes of over-copy. **Three were removed on 2026-09-14**
(ADR-0017 D-2); the fourth is a deliberate open decision.

### 2.1 Removed — 16 files, ~407 KB off every target

Managed-file count went **505 → 489** (it is 497 today; guides and package files added since account for the rest).

| Removed | Files | Why it was surplus |
|---|---|---|
| `docs/guides/*.html` | 6 | The guides' rendered form. The `.md` beside them is the runtime asset and still ships |
| `scripts/hooks/__tests__/` | 5 | The hooks' Node tests run in Assets' CI, against Assets' checkout |
| `docs/context/` (Assets') | 5 | **Assets' own memory bank** |

The memory bank was the most confusing of the three: a target received a blank `docs/context/ACTIVE.md`
and, beside it under `agentic-assets/`, AgentForge's own in-flight ADR state — already stale on
arrival, and describing a different project. Nothing ever read it; the hook resolves `docs/context/`
at the target root. It is replaced by a short pointer README.

On the HTML: ADR-0017 D-2 justified the exclusion as *"the `.md` is the runtime asset"*, but
`what_is_agentforge.html` has **no `.md` twin**, so that reasoning did not cover it. It is excluded
on a better basis — it is `/product-doc`'s **output**, so a target generates its own from its own
PRD, making ours the same mistake as shipping the memory bank. `index.html` links exactly the four
files that do have twins, so the set had to go as a unit or ship with broken links. Nothing reads
any of it at runtime: the CSS shell `neuroedge_productdoc.render` reuses was copied into that
module verbatim, not read from disk.

### 2.2 Still shipped, by open decision

These remain surplus for *some* targets. ADR-0017 D-3 (install-time `--without` groups) is the
mechanism that would make them selectable and is not yet built, so today's install is all-or-nothing.

| Still ships | Files | Surplus when |
|---|---|---|
| `src/neuroedge_marketing`, `src/neuroedge_productdoc` | 17 | The project never runs `/marketing-video` or `/product-doc`. D-2 explicitly keeps the default at "ship" to avoid breaking existing flows |
| `agentforge_simulator/` (from `simulator/`) | 36 | The project has no data source to simulate |
| `agentforge/src/` | 54 | The project does not drive the SDLC orchestrator |
| `ENGINEERING/**` discipline packs | 21 skills + agents | The discipline is not in `active_disciplines` |

The last row is ADR-0017 finding **F-5** and is the sharpest of the four. Selectivity is
runtime-first by design — *"files on disk, never loaded unless declared"* — but discipline **agents**
are flattened into `.claude/agents/`, where Claude Code discovers them by a flat scan. So a
discipline's agents are unconditionally discoverable by the harness even when the discipline is
undeclared, which is not what "never loaded unless declared" implies.

### 2.3 Never shipped (correct — listed so the exclusions are auditable)

| Path | Tracked files | Why excluded |
|---|---|---|
| `projects/dcn-fleet-orchestration/` | 306 | A worked example project. Only `projects/generic/` (1 file) is a template |
| `docs/project_related/` | 159 | Assets' own PRDs, backlogs, runlogs |
| `agentforge_custom_plugin/` | 52 | Client packs (`SunCHECK`, `Process_Automation_Product_Dev`). Only the neutral `Project_Specific_Context` template is scaffolded, and by `setup_neuroedge_agentic_tools.py` step 3 — not by `install.py` |
| `agentforge/tests/` | 59 | Assets' own tests |
| `tests/` | 35 | Assets' own tests |
| `docs/decisions/` | 21 | ADRs are Assets history. **Consequence:** commands citing an ADR link to a file no target has — an accepted, documented exception |
| `docs/audit/`, `docs/prds/`, `docs/marketing/` | — | Assets' own artifacts |
| `.github/`, `.vscode/`, root `*.py` installers | 5 + | Repo tooling |

### 2.4 Related fix — a declined prune used to lose track of files

Removing 16 files at once surfaced a pre-existing defect in `update_agentforge_claude_project.py`.
`install()` rewrites the manifest to the new file set **before** the orphan prune is confirmed, and
orphans are diffed old-minus-new. So a **declined** prune left the files on disk and invisible to
every later run — while the decline path printed *"re-run to prune"*. Fixed by re-recording
surviving orphans; a missing stdin is now treated as a decline rather than crashing mid-update.

**When refreshing an existing target, prefer `--yes`** so the prune is not left half-done:

```bash
python update_agentforge_claude_project.py --project <path> --yes
```

---

## 3. What is git-ignored

Two different `.gitignore` files matter. Conflating them is a common source of confusion.

### 3.1 In the Assets repo

Beyond the usual Python/venv/OS/editor noise, four groups carry real meaning:

| Ignored | Why |
|---|---|
| `.claude/commands/`, `.claude/agents/`, `agentic-assets/` | **Self-install residue.** Assets dogfoods AgentForge on itself, which reproduces the target layout inside the source repo. The top-level `commands/`, `agents/`, `skills/` are canonical; committing the copies would put two of every asset in one repo — a drift generator by construction |
| `agentforge_simulator/` | Same class, added 2026-09-14. `install.py` copies `simulator/` into a target *as* this name, so a self-install recreates it at the Assets root as a silent duplicate. It was committed once and swallowed three weeks of work (finding F-A) |
| `agentforge/docs/` | Dev-only orchestrator planning artifacts. `agentforge/src/` still ships; only the docs are dev-local |
| `agentic-assets/RELEASE_VERSION.json`, `agentic-assets/INSTALLED_MANIFEST.json`, `.claude/settings.local.json`, `.claude/.ts-edited-files`, `.claude/.source-edited-files`, `.claude/.ml-edited-files`, `exchange*.json`, `docs/project_related/misc/runlog-*.md`, `backup/` | Local state, per-machine telemetry, and secrets |

Secrets are covered by `.env`, `.env.*` (with `!.env.example`), and `*.local.json` (with
`!settings.local.json.example`).

> A `.gitignore` rule does **not** untrack a file that is already tracked. Both the
> `.source-edited-files` and `agentforge_simulator/` cleanups needed `git rm --cached` before the
> rule had any effect.

### 3.2 In a target

The installer appends 9 rules to the target's `.gitignore`, all for local AgentForge state:

```gitignore
# AgentForge local state and secrets
.claude/settings.local.json
.claude/.ts-edited-files
.claude/.source-edited-files
.claude/.ml-edited-files
.env
.env.*
!.env.example
agentic-assets/RELEASE_VERSION.json
agentic-assets/INSTALLED_MANIFEST.json
```

Note what is **not** ignored in a target: the installed assets themselves. `.claude/commands/`,
`.claude/agents/`, and `agentic-assets/skills/` are committed by the consuming project, which is
what makes `--verify`'s drift detection meaningful there.

---

## 4. Findings from the ADR-0014 → 0018 review

| # | Severity | Finding | State |
|---|---|---|---|
| F-A | 🔴 | ADR-0015's `cyclic_multichannel` profile reached no target and no test | Fixed |
| F-B | 🟠 | ADR-0014 read "Proposed (draft)" while its pack had shipped for ~7 weeks | Fixed |
| F-C | 🟠 | ADR-0014's Phasing section contradicted its own Decision section | Fixed |
| F-D | 🟠 | 16 files of over-copy (ADR-0017 F-4) | Fixed |
| F-E | 🔴 | A declined orphan prune silently lost track of the files forever | Fixed |
| F-F | 🟠 | Discipline agents are discoverable even when the discipline is undeclared | Open (ADR-0017 F-5) |
| F-G | 🔴 | Live targets hold pre-manifest installs with every skill reference broken | Open (ADR-0017 F-6) |

### F-A — the duplicate simulator tree (the most serious)

`install.py` ships `simulator/` into a target **as** `agentforge_simulator/`. A directory of that
name also existed at the Assets root — committed on 2026-08-21, never gitignored alongside the other
self-install residue. The two diverged, and ADR-0015's `cyclic_multichannel` work went into the
**duplicate**:

| | `cyclic_multichannel` occurrences |
|---|---|
| `agentforge_simulator/gen_input.py` (duplicate) | 8 |
| `simulator/gen_input.py` (ships) | 0 |
| installed target | 0 |

It was also untested — `tests/test_simulator.py` points at `simulator/` — which is why a fully green
suite said nothing about it for three weeks. Ported, covered by 9 new tests, duplicate deleted and
gitignored.

The general lesson: a directory named after the *target's* layout, sitting in the *source* repo, is
a trap. Anyone reasoning "the simulator ships as `agentforge_simulator/`, so that's where I edit"
is wrong in a way nothing catches.

### F-B / F-C — ADR-0014 status and internal consistency

The `ai-ml` pack (3 agents, 5 commands, 3 hooks, 7 of 8 skills) has been shipping since roughly
July, and ADR-0015 was accepted on top of it as *"the pack this extends"* — while ADR-0014 itself
still read "Proposed (draft)". Separately, its Phasing section named a `/train-eval` command and a
`training-and-eval.md` skill; neither exists, and neither should, because Decision A settles that
**AgentForge does not run training** — the loop stops at the handoff package. What shipped is
`/model-build` + `model-codegen.md`, with the eval gate realized as the `ml-eval-reviewer` **agent**
reviewing metrics returned from the external run. Both reconciled.

`data-centric-ml.md` is the one absent skill and is **Phase 3 work, not an omission**; nothing
outside the ADRs cites it, so it raises no `DANGLING`.

### F-G — the live targets

`NeuroEdge-Web` and `NeuroEdge-Device` hold partial, pre-manifest installs whose patched skill-read
blocks all point at paths that do not exist there — every skill reference in both is broken today.
Neither has an `INSTALLED_MANIFEST.json`, so an update prunes nothing. They need a fresh full setup,
not an update.

---

## 5. Verified state at review close

- 259 pytest passed, 34 Node hook tests passed, `ruff` clean
- Fresh temp-target install: `Verify OK — zero drift; every installed asset matches source and
  every citation resolves` and `Coverage OK`
- Upgrade path exercised on a target installed with the pre-trim code: decline → 16 orphans
  reported; decline again → still 16; accept → all 16 deleted; re-run → clean. The target's own
  memory bank untouched throughout
