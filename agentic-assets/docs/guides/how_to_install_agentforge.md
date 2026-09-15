# How to Install AgentForge

**Version:** 1.1 - 2026-09-15
**Audience:** Developers who want to clone AgentForge, install it into a greenfield or legacy project, and verify that agents, commands, skills, hooks, plugins, and memory-bank files are ready.

This guide gets AgentForge installed and validated. After the health check passes, continue with the full workflow guide: [how_to_build_your_project.md](how_to_build_your_project.md).

For a complete list of available agents, commands, skills, hooks, plugins, MCP servers, and project templates, see [agentforge_assets.md](agentforge_assets.md).

---

## What Ready Means

AgentForge is ready when the target project has:

- `.claude/commands/` with the AgentForge slash commands.
- `.claude/agents/` with specialist agents.
- `agentic-assets/skills/` with local runtime skill files.
- `agentic-assets/plugins/` with MCP/plugin guidance.
- `scripts/hooks/` plus `.claude/settings.json` hook wiring.
- `CLAUDE.md` and `AGENTS.md` at the project root.
- `docs/context/` and `docs/decisions/` memory-bank files.
- `health_check/cli.py --verbose` returns PASS for hooks, skills, agents, and memory.

Current expected generic install shape (measured on a fresh install into an empty git repo,
2026-09-15 — re-derive rather than hand-edit: `python install.py --project <target> --check-coverage`
is the authoritative check, and these counts drift with every asset added):

```text
44 commands
67 agents
17 hook scripts (18 hook groups wired in settings.json)
runtime skills/plugins/docs under agentic-assets/ (235 skill files, 12 guides, 3 plugin files)
memory bank bootstrapped
512 files written, 497 of them recorded in agentic-assets/INSTALLED_MANIFEST.json
health check: hooks, skills, agents, memory PASS
```

---

## 1. Install Prerequisites

Install these once per workstation.

| Tool                         | Minimum | Why                                                                                       |
| ---------------------------- | ------: | ----------------------------------------------------------------------------------------- |
| Python                       |    3.11 | Setup scripts and health checks                                                           |
| Node.js                      |  20 LTS | Claude hooks                                                                              |
| Git                          |    2.40 | Clone, submodules, commits                                                                |
| GitHub CLI`gh`             |    2.40 | PR workflow through`/prp-pr`                                                            |
| Claude Code                  |  latest | Agent/command runtime                                                                     |
| ffmpeg + ffprobe             |     any | Marketing video render only (`/marketing-video`). Or set `FFMPEG_BIN` to their folder |
| MQTT broker (e.g. Mosquitto) |     any | Simulator and ingress MQTT transport only. Can run on another machine                     |

This table lists only software pip cannot install. **Python packages are not on it:** every package
AgentForge needs installs from one file after setup, `agentic-assets/requirements-agentforge.txt`
(see [Python dependencies](#python-dependencies)). After setup, `python health_check/cli.py --only tools`
reports which of these tools are missing. It warns rather than fails, because each serves an optional feature.

Quick check:

```bash
python --version
node --version
git --version
gh --version
claude --version
ffmpeg -version     # only if you will render marketing video
```

Install Claude Code if needed:

```bash
npm install -g @anthropic-ai/claude-code
claude --version
```

On Windows, run AgentForge setup commands with `python -X utf8`.

> **Windows note — PowerShell version:** Windows ships **Windows PowerShell 5.1** by default.
> The `.ps1` wrapper scripts in this guide (`setup_agentforge_claude_project.ps1` and friends)
> require **PowerShell 7+ (`pwsh`)** and will refuse to run on 5.1 with
> `ScriptRequiresUnmatchedPSVersion`. Either install PowerShell 7 first
> (`winget install --id Microsoft.PowerShell -e`, then invoke with `pwsh -File <script>.ps1 ...`),
> or skip the wrapper and run the canonical `.py` script instead — it works unmodified on
> whatever PowerShell version (or shell) you already have.

---

## 2. Clone AgentForge

Use one of these patterns.

### Option A - Standalone AgentForge Clone

Use this when you want one central AgentForge checkout that can install into many projects.

```bash
git clone https://github.com/sanjkcog/NeuroEdge-AgenticAI-Assets.git C:/Sanjeev_E/NeuroEdge_AgenticAI_Assets
cd C:/Sanjeev_E/NeuroEdge_AgenticAI_Assets
```

### Option B - Project Submodule

Use this when a team wants the target project to pin AgentForge as a submodule.

```bash
cd <target-project>
git submodule add https://github.com/sanjkcog/NeuroEdge-AgenticAI-Assets.git agentic-assets
git submodule update --init --recursive
```

> **Submodule limitation (ADR-0018).** When the Assets checkout *is* `<target>/agentic-assets`, the installer
> skips the runtime copy because source and destination are the same tree. Pack skills live at
> `agentic-assets/packs/<name>/skills/`, not at `agentic-assets/skills/ENGINEERING/<name>/` where agents cite
> them, so those citations do not resolve in a submodule install. A standalone clone (Option A) is unaffected.

---

## 3. One product-independent install for every project

AgentForge is **product-independent**. Every target — a greenfield app, a legacy monolith,
a web portal, an edge device — receives the **same** generic assets plus the neutral
`projects/generic/CLAUDE.md` template. Product- and client-specific context lives in an
auto-scaffolded `Project_Specific_Context` plugin instead — see the Assets guide.

The generic template is a starter `CLAUDE.md` with `<!-- CUSTOMIZE: ... -->` comments
marking the lines a project team fills in after install (seeded once, then owned by the
project — a re-install never clobbers your edits).

---

## 4. Install, Update, or Remove AgentForge

AgentForge has a three-script lifecycle, all sharing the same `--project` and `--dry-run`
conventions. Update and Clean also take `--yes`; Setup has no `--yes`, prompts for the project
path if `--project` is omitted, and takes an optional `--remote <url>` for the Assets repo. **Each comes two ways — a canonical Python script and a matching
PowerShell wrapper** — so you can run the lifecycle however your shell prefers:

| Operation        | Python (any OS)                         | PowerShell (**pwsh 7+ required**)  | Use when                                                                                                          | Safe to re-run?                                   |
| ---------------- | --------------------------------------- | ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------- |
| **Setup**  | `setup_agentforge_claude_project.py`  | `setup_agentforge_claude_project.ps1`  | **First install** into a project (env checks + patch + install + plugin scaffold + scope).                  | Yes — idempotent; owned files are seeded once.   |
| **Update** | `update_agentforge_claude_project.py` | `update_agentforge_claude_project.ps1` | An**existing install** needs the latest AgentForge — apply only the diff and drop assets removed upstream. | Yes — copies only changes, prunes only orphans.  |
| **Clean**  | `clean_agentforge_claude_project.py`  | `clean_agentforge_claude_project.ps1`  | **Retiring** AgentForge, or resetting a broken install before a fresh setup.                                | Yes — a second run finds nothing left to remove. |

**Which to use.** The **`.py` scripts are canonical** and do all the real work; they run on any OS
(`python -X utf8 <script>.py ...`, works from bash *or* PowerShell). The **`.ps1` wrappers** are a
convenience for Windows/PowerShell users — they check prerequisites (Python 3.11+, git), then forward
to the same Python script. Flags map one-to-one: PowerShell uses `-Project <path>`, `-DryRun`, `-Yes`
(`-Remote <url>` for setup) where Python uses `--project <path>`, `--dry-run`, `--yes` (`--remote <url>`).
Pick either; they produce the same result.

### 4.1 First install

#### From a Standalone AgentForge Clone

```bash
cd C:/path/to/AgentForge-Assets

# Python (any OS):
python -X utf8 setup_agentforge_claude_project.py --project "C:/path/to/target-project"
```

```powershell
# PowerShell (Windows) — same result, via the wrapper:
./setup_agentforge_claude_project.ps1 -Project "C:/path/to/target-project"
./setup_agentforge_claude_project.ps1 -Project . -DryRun     # preview only
```

#### From a Submodule Inside the Target Project

```bash
cd <target-project>

python -X utf8 agentic-assets/setup_agentforge_claude_project.py --project .
```

Preview first:

```bash
python -X utf8 agentic-assets/setup_agentforge_claude_project.py --project . --dry-run
```

### What the setup steps do

`setup_agentforge_claude_project.py` checks prerequisites (Python 3.11+, git), optionally sets the
Assets git remote, then runs `setup_neuroedge_agentic_tools.py --project <path>`, which does four steps:

| Step  | Name    | Action                                                                                                                                                                                                                                                                                                |
| ----- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 / 4 | Patch   | Inject skill references into Assets command/agent files                                                                                                                                                                                                                                               |
| 2 / 4 | Install | Copy commands, agents, hooks, skills, orchestrator, simulator, health checker, and`CLAUDE.md` into the project, and write the install manifest                                                                                                                                                      |
| 3 / 4 | Plugin  | Scaffold the neutral`Project_Specific_Context` custom-plugin template into `agentforge_custom_plugin/` (seeded once; left alone if already present)                                                                                                                                               |
| 4 / 4 | Scope   | If the project has a`src/` with packages, generate a nested `CLAUDE.md` per package so Claude loads only the active subfolder's context. If no packages are found, the tree is treated as monolithic — use `/scope-context --monolith` in Claude Code for the guided segment-scoping workflow. |

After those, setup copies `settings.local.json.example` to `.claude/settings.local.json` (only if absent)
and runs `health_check/cli.py --verbose` in the target. With `--dry-run`, those last two are skipped.

The `--skip-patch`, `--skip-install`, `--skip-plugin`, and `--skip-scope` flags belong to
`setup_neuroedge_agentic_tools.py`, not to the `setup_agentforge_claude_project` wrapper — run that script
directly when you need them:

```bash
python -X utf8 setup_neuroedge_agentic_tools.py --project "C:/path/to/target-project" --skip-scope
```

### Python dependencies

Every Python package AgentForge's shipped code needs can be installed from one file the installer puts in your
project: `agentic-assets/requirements-agentforge.txt`. It pulls in each tool's own requirements file with `-r`
lines: the SDLC orchestrator, marketing video (including the local Chatterbox voice), and the simulator. The
installer rewrites it on every update, so reference it and don't edit it.

The installer **never edits your own dependency files**. After the Install step it prints, under
**Dependencies**, the one change that fits your project:

| Your project has                    | Do this once                                                                                             |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `pyproject.toml`, managed with uv | `uv add --group agentforge -r agentic-assets/requirements-agentforge.txt`                              |
| `requirements-dev.txt`            | add`-r agentic-assets/requirements-agentforge.txt` to it, then `pip install -r requirements-dev.txt` |
| only`requirements.txt`            | add the same line to`requirements.txt`, then `pip install -r requirements.txt`                       |
| neither                             | `pip install -r agentic-assets/requirements-agentforge.txt`                                            |

#### With pip

Run these from your project root, inside the environment your project uses:

```bash
python -m venv .venv                     # only if you have no environment yet
source .venv/bin/activate                # PowerShell: .venv\Scripts\Activate.ps1

# If you added the -r line to requirements-dev.txt or requirements.txt, install that file,
# so your own pins and AgentForge's resolve together:
python -m pip install -r requirements-dev.txt

# Otherwise, install the entry point directly:
python -m pip install -r agentic-assets/requirements-agentforge.txt

python -m pip check                      # reports conflicting pins
```

After an AgentForge update, run the same `pip install -r` again. A `-r` line is a reference, so it picks up
any package the update added.

#### With uv

For a project with `pyproject.toml`:

```bash
uv add --group agentforge -r agentic-assets/requirements-agentforge.txt   # writes the group, updates uv.lock, installs
uv sync --group agentforge                                                # every later sync, and on other machines
uv run --group agentforge python -c "import jsonschema, pydantic, yaml"   # run anything with the group installed
```

🔴 **A plain `uv sync` removes the group's packages.** By default uv installs only the `dev` group. Either pass
`--group agentforge` every time, or add `agentforge` to the default groups in your `[tool.uv]` table (create
the table if you don't have one):

```toml
[tool.uv]
default-groups = ["dev", "agentforge"]
```

After an AgentForge update, run the same `uv add` again. uv copies the packages into the group rather than
keeping a reference to the file, so this is how new packages get added. The installer reminds you when it sees
the group.

For a project without `pyproject.toml`, use uv as a faster pip:

```bash
uv venv
uv pip install -r agentic-assets/requirements-agentforge.txt
```

- **A dev dependency, not a runtime one.** AgentForge is development tooling, so it goes in a dev group or dev
  requirements file, not in your product's `[project.dependencies]`.
- **uv adds to your `pyproject.toml`; it doesn't replace it.** `uv add --group agentforge` creates or updates
  only the `agentforge` group under `[dependency-groups]`. Your `[project]` table, other groups, `[tool.*]`
  tables and comments stay as they are. uv reads the requirements file and its `-r` lines directly, so no
  second TOML file is needed.
- **Pin conflicts.** torch is the largest and most pin-sensitive package here, and chatterbox-tts pins its own
  torch and numpy versions. If your resolver reports a conflict, reference the files
  `requirements-agentforge.txt` lists one by one, and leave out `src/neuroedge_marketing/requirements-voice.txt`
  (you lose only the local voice). On a GPU machine, install a CUDA build of torch first.
- **A host that only consumes the simulator's transports** can keep referencing just
  `-r agentforge_simulator/requirements-transports.txt` (`paho-mqtt`, `requests`).

The Scope step is idempotent (it rewrites only content between `SCOPE:AUTO` markers) and honors `--dry-run`. It writes only the nested files and does not touch the root `CLAUDE.md`. Nested `CLAUDE.md` files are meant to be committed and shared with the team. The installer adds no `.gitignore` rule for `CLAUDE.md`, so they are tracked by default. If your own `.gitignore` has a bare `CLAUDE.md` pattern, add `!src/**/CLAUDE.md` after it. See the `context-scoping` skill for details.

> **AgentForge's own `src/` packages are skipped.** AgentForge ships `src/neuroedge_marketing/` and
> `src/neuroedge_productdoc/`. The installer owns those files: `--verify` checks their content and an update
> rewrites them. So the Scope step skips any package whose files are recorded in the install manifest, and
> prints `skip (AgentForge-managed …)` for each one. It scopes only your project's own packages. A target whose
> `src/` holds nothing else reports `Scope : only AgentForge-managed packages in src/ — nothing to scope`.
> `/scope-context` gets the same skip, because the walker reads `agentic-assets/INSTALLED_MANIFEST.json`.

### 4.2 Update an existing install

When the AgentForge team ships improvements (new agents, skills, commands, fixes), pull them into an already-installed project with `update_agentforge_claude_project.py`. It copies only what changed, removes assets that were deleted or renamed upstream, verifies the result, and reports the version delta — without a full re-setup and without leaving stale files behind.

#### Before you update: check and protect your project

> 🔴 **Update overwrites every file at an AgentForge-managed path with the Assets version, even if your project
> changed it.** It has no skip list. A fix you made in `.claude/agents/…`, or a module you replaced under
> `src/…`, is lost unless you protect it. Do these checks before every update.

**1. Start from a clean tree, and back up what git can't restore.**

```bash
cd <target-project>
git status --short     # must print nothing: commit or stash first
git check-ignore -v .claude/commands/x.md .claude/agents/x.md scripts/hooks/x.js health_check/cli.py agentic-assets/skills/x.md
```

Every path the second command prints is git-ignored in your project, so git can't undo an update there. Copy
those folders somewhere outside the project before you update.

**2. Run the dry run and read it.** In its output, look for:

| Output line | What it means for you |
|---|---|
| `No prior install manifest found` | Nothing is pruned this time, so assets renamed upstream leave stale copies behind (check 6) |
| `N asset(s) were removed/renamed upstream and will be deleted` | These files will be deleted. Make sure you don't rely on any of them |
| `N hook group(s) merged, M already present` | Hooks are matched by `id`. If `M` is lower than you expect, see check 4 |
| `.env.example … not in it` | Your env files are never written. Add the named variables yourself ([§ 5](#5-configure-local-secrets)) |

**3. Find your own edits to AgentForge-managed files.** There are two kinds:

- **Files you replaced with your own implementation.** For example, the NeuroEdge Studio renders marketing video
  through its portal, with its own `src/neuroedge_marketing/`, `marketing-video` command, marketing agents and
  video skills.
- **Fixes made in your project that never reached the Assets repo.**

This check compares each managed file in your project with every past version of its source in the Assets repo.
A file that matches no version is one your project changed. Run it from your AgentForge clone:

```bash
TARGET="C:/path/to/target-project" python -X utf8 - <<'EOF'
import os, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, ".")
import install
target = Path(os.environ["TARGET"]).resolve()
stamp = re.compile(rb"<!-- neuroedge-assets-patched[^\n]*?-->")
norm = lambda b: stamp.sub(b"", b.replace(b"\r\n", b"\n")).strip()
for pair in install._coverage_pairs(target):
    if not pair.content_checked or not pair.dst.is_file():
        continue
    mine = norm(pair.dst.read_bytes())
    if mine == norm(pair.src.read_bytes()):
        continue
    rel = pair.src.resolve().relative_to(Path(".").resolve()).as_posix()
    shas = subprocess.run(["git", "log", "--all", "--format=%H", "--follow", "--", rel],
                          capture_output=True, text=True).stdout.split()
    if not any(norm(subprocess.run(["git", "show", f"{s}:{rel}"], capture_output=True).stdout) == mine
               for s in shas):
        print("YOUR EDIT:", pair.dst.relative_to(target).as_posix())
EOF
```

Each `YOUR EDIT:` line is a file the update would overwrite. For each, either protect it (see
[Protecting files during an update](#protecting-files-during-an-update)) or move the change into the Assets repo
so every project gets it. A file that was renamed in the Assets repo can be listed even if you never changed it,
so look at each one before deciding.

**4. Check that your hook groups have ids.** Update merges AgentForge's hooks by `id`. A group without one gets
added again, and that hook then runs twice. From your project root:

```bash
python -X utf8 -c "import json; g=[x for v in json.load(open('.claude/settings.json', encoding='utf-8')).get('hooks', {}).values() for x in v]; print(len(g), 'hook groups;', sum('id' not in x for x in g), 'without an id')"
```

If any group has no id, copy the `id` of the matching group (same event and command) from the Assets repo's
`hook-config.json` into your `.claude/settings.json` before you update.

**5. Check that your packaging won't pick up AgentForge's packages.** The installer adds
`src/neuroedge_marketing/` and `src/neuroedge_productdoc/`. If your `pyproject.toml` discovers packages under
`src/` automatically, exclude them:

```toml
[tool.setuptools.packages.find]
where = ["src"]
exclude = ["neuroedge_marketing*", "neuroedge_productdoc*"]
```

**6. If there was no manifest, list stale files after the update.** A project installed before manifests existed
gets no pruning on its first update. This lists files in AgentForge folders that the current release doesn't
ship. Run it from your AgentForge clone, delete the stale AgentForge copies (for example
`.claude/commands/gan-build.md`, which moved to `ENGINEERING/ai-genai/`), and keep files that are yours:

```bash
TARGET="C:/path/to/target-project" python -X utf8 - <<'EOF'
import os, sys
from pathlib import Path
sys.path.insert(0, ".")
import install
target = Path(os.environ["TARGET"]).resolve()
shipped = {pair.dst.resolve() for pair in install._coverage_pairs(target)}
for area in (".claude/agents", ".claude/commands", "scripts/hooks", "health_check"):
    for f in sorted((target / area).rglob("*")):
        if f.is_file() and "__pycache__" not in f.parts and f.resolve() not in shipped:
            print("NOT SHIPPED:", f.relative_to(target).as_posix())
EOF
```

#### Protecting files during an update

Update can't skip files, so protect them by restoring your versions from git right after it runs. Record the list
of protected paths in your project, for example in `CLAUDE.md` or `docs/context/`, because you repeat this on
every update.

```bash
cd <target-project>
PROTECT="src/neuroedge_marketing .claude/commands/marketing-video.md agentic-assets/skills/SUPPORTING-TOOLS/video"   # your paths

# run the update, then:
git restore -- $PROTECT          # put your versions back
git clean -n -- $PROTECT         # list the files the update ADDED inside those paths
git clean -f -- $PROTECT         # remove them
git status --short -- $PROTECT   # must print nothing
```

- **Run `git clean` only from the clean tree of check 1.** It removes every untracked file under those paths, and
  the `-n` line shows exactly what will go.
- **A git-ignored protected path can't be restored this way.** Copy it back from your check-1 backup.
- **A file the update adds outside your protected paths stays.** If you don't want it, delete it by hand.
- **`install.py --verify` now reports your protected files as `DRIFT` or `MISSING`.** That's expected: they are the
  files you kept.

Then run the tests that cover the areas you protected, run `python health_check/cli.py --verbose`, review
`git diff`, commit, and restart Claude Code. The update never writes `.env`, `.env.example` or your dependency
files, so add new variables and packages yourself: see [§ 5](#5-configure-local-secrets) and
[Python dependencies](#python-dependencies).

#### Running the update

```bash
# In your AgentForge clone, get the latest first
git pull

# Preview what would change (writes nothing)
python -X utf8 update_agentforge_claude_project.py --project "C:/path/to/target-project" --dry-run

# Apply the update
python -X utf8 update_agentforge_claude_project.py --project "C:/path/to/target-project"
```

```powershell
# PowerShell (Windows) — same result, via the wrapper:
./update_agentforge_claude_project.ps1 -Project "C:/path/to/target-project" -DryRun   # preview
./update_agentforge_claude_project.ps1 -Project "C:/path/to/target-project"           # apply
```

| Option               | Effect                                                                               |
| -------------------- | ------------------------------------------------------------------------------------ |
| `--project <path>` | Required. The target project to update.                                              |
| `--dry-run`        | Preview: lists changed files and orphaned assets, writes nothing.                    |
| `--yes`            | Skip the confirmation prompt before deleting orphaned assets (CI / non-interactive). |

**What it does, in four steps:** (1) **copy the diff** — only changed files are rewritten; (2) **prune orphans** — assets recorded in the previous install but no longer shipped are deleted; (3) **verify** — every installed asset is compared to source (0 findings = clean); (4) **report** — old → new version and counts.

**Scope.** Update reconciles the *assets* only. It does **not** re-run Patch, the custom-plugin scaffold, or the Scope walker — for those, re-run setup. It updates from your current clone (working tree); to move a target to a specific revision, use `python install.py --project <path> --ref <commit-sha>`. The repo has no release tags yet, so pass a commit SHA; `--ref <tag>` works the same way once tags are cut. `install.py` refuses to install an older version over a newer one unless you pass `--force`.

Update refuses to run on a project with no AgentForge install (no manifest, no `.claude/agents/`, no `agentic-assets/`) and tells you to run setup first.

**Never overwritten or pruned.** `CLAUDE.md`, `.claude/settings.local.json`, `.env.example`, the `docs/context/` memory bank, `docs/decisions/`, and `agentforge_custom_plugin/` are project-owned. Update never overwrites or deletes them. It does make **additive-only** changes on every run, because it calls the same installer: missing AgentForge rules are appended to `.gitignore`, hook groups whose `id` is not already in `.claude/settings.json` are merged in, and any missing bootstrap file (for example `docs/decisions/TECH-DEBT.md` on an older target) is created. Orphan pruning is driven by an install manifest (`agentic-assets/INSTALLED_MANIFEST.json`) that records only content-owned assets, so your own agents, commands, and `src/` are never in scope. A file of yours at the **same path** as an AgentForge asset is different: it counts as AgentForge's, and update overwrites it (see [Before you update](#before-you-update-check-and-protect-your-project)).

**Declining the prune.** Without `--yes`, update asks you to type `yes` before deleting orphans. If you decline, or stdin is not available (CI, piped input), the asset changes still land, the orphans stay on disk, and they **stay recorded in the manifest**, so the next update reports them again. To finish a refresh in one go, use `--yes`:

```bash
python -X utf8 update_agentforge_claude_project.py --project "C:/path/to/target-project" --yes
```

> **First update after adopting manifests:** a project installed before manifests existed has none yet, so the first update prunes nothing but writes one — pruning of removed assets begins from the next update.
>
> **Upgrading from a pre-2026-09-14 install:** the payload no longer ships `docs/guides/*.html`, `scripts/hooks/__tests__/`, or the Assets repo's own memory bank under `agentic-assets/docs/context/` (ADR-0017 D-2). If the target has a manifest, the first update after that change lists those files as orphans to prune. A new pointer `agentic-assets/docs/context/README.md` is created; your own `docs/context/` is not touched.

### 4.3 Remove AgentForge (uninstall)

To retire AgentForge from a project — or to clear a corrupt install before a clean re-setup — use `clean_agentforge_claude_project.py`. It deletes the installed AgentForge files, removes AgentForge's hook groups (matched by `id`) from `.claude/settings.json` so nothing dangles, and prunes the emptied directories.

The delete list is computed from **your current Assets clone**: every destination the installer would write today that exists in the target. It does not read `INSTALLED_MANIFEST.json`, so it never touches a path the current release does not ship. Run clean from the same Assets version you installed or last updated from. A file that an older release installed and a newer one dropped is only removed by an update's orphan prune, not by clean.

```bash
# Preview what would be removed (writes nothing)
python -X utf8 clean_agentforge_claude_project.py --project "C:/path/to/target-project" --dry-run

# Remove (prompts for a typed 'yes')
python -X utf8 clean_agentforge_claude_project.py --project "C:/path/to/target-project"
```

```powershell
# PowerShell (Windows) — same result, via the wrapper:
./clean_agentforge_claude_project.ps1 -Project "C:/path/to/target-project" -DryRun   # list only
./clean_agentforge_claude_project.ps1 -Project "C:/path/to/target-project"           # remove
```

| Option               | Effect                                                           |
| -------------------- | ---------------------------------------------------------------- |
| `--project <path>` | Required. The target project to clean.                           |
| `--dry-run`        | Preview: lists every file that would be deleted, writes nothing. |
| `--yes`            | Skip the typed-`yes` confirmation (CI / non-interactive).      |

**Preserved.** `CLAUDE.md`, `AGENTS.md`, the `docs/context/` memory bank, `docs/decisions/`, `.claude/settings.local.json`, and `.gitignore` are kept. So is `.claude/settings.json`: only the AgentForge hook groups are removed, and the AgentForge rules in `.gitignore` are left in place.

**Also left behind** (verified on a fresh install followed by `--yes`): `.env.example`, `docs/audit/.gitkeep`, `agentic-assets/INSTALLED_MANIFEST.json`, `agentic-assets/RELEASE_VERSION.json`, `agentic-assets/docs/context/README.md`, any `src/<package>/CLAUDE.md` the Scope step created, and any `__pycache__/` created by running the health check. Delete them by hand if you want a completely clean tree.

**You must delete this yourself.** `agentforge_custom_plugin/` is left in place — you edited it directly in the target and it holds your proprietary product/client context. The script warns and points at it; remove it manually only when you are sure you want it gone.

---

## 5. Configure Local Secrets

The installer creates `.claude/settings.local.json` from `settings.local.json.example` if it does not already exist. Keep this file local and uncommitted (the installer adds it to `.gitignore`). It starts with blank keys used by the ML dataset commands:

```json
{
  "env": {
    "ROBOFLOW_API_KEY": "",
    "HF_TOKEN": "",
    "KAGGLE_USERNAME": "",
    "KAGGLE_KEY": ""
  }
}
```

Fill in only the keys your enabled tools need, and add others the same way.

### Environment variables: `.env.example` and `.env`

AgentForge's variables form one block, from `# >>> AgentForge >>>` to `# <<< AgentForge <<<`. The block
covers:

- the external-tool integration: `GITHUB_TOKEN`, `AGENTFORGE_GITHUB_REPO`, `JIRA_*`, `CONFLUENCE_*`, `ZEPHYR_*`, `TESTRAIL_*`;
- marketing video: `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `OPENAI_API_KEY`, `ELEVENLABS_*`, `ANTHROPIC_API_KEY`,
  `NEUROEDGE_VISION_MODEL`, `FFMPEG_BIN`, `DEMO_FONT_FILE`;
- commented-out optional hook settings.

The installer handles two files:

- **`.env.example` at your project root is seeded only if you have none**, and is never overwritten. If you
  already have one, the installer leaves it alone and names the AgentForge variables it lacks.
- **`agentic-assets/agentforge.env.example` is always the current block**, rewritten on every install. Copy
  from it.

If your project had no `.env.example`, copy the seeded one to `.env` (git-ignored) and fill in only what you
use. If your project has its own, do this from the project root. Both steps are safe to re-run:

```bash
# 1. Once: append the AgentForge block to your .env.example (skipped when its marker is already there)
touch .env.example
grep -q '>>> AgentForge' .env.example || { [ -n "$(tail -c1 .env.example)" ] && echo; cat agentic-assets/agentforge.env.example; } >> .env.example

# 2. Add to .env only the names it lacks, as empty values, so no value you already set is touched
touch .env
[ -n "$(tail -c1 .env)" ] && echo >> .env
grep -E '^[A-Z][A-Z0-9_]*=' agentic-assets/agentforge.env.example | cut -d= -f1 | while read -r k; do
  grep -q "^$k=" .env || echo "$k=" >> .env
done
```

```powershell
$block = [IO.File]::ReadAllText("$PWD\agentic-assets\agentforge.env.example")
# 1. Once: append the AgentForge block to your .env.example
if (-not (Test-Path .env.example)) { [IO.File]::WriteAllText("$PWD\.env.example", "") }
if (-not (Select-String -Path .env.example -Pattern '>>> AgentForge' -Quiet)) { [IO.File]::AppendAllText("$PWD\.env.example", "`n" + $block) }
# 2. Add to .env only the names it lacks, as empty values
if (-not (Test-Path .env)) { [IO.File]::WriteAllText("$PWD\.env", "") }
$have = @(Get-Content .env | ForEach-Object { ($_ -split '=', 2)[0].Trim() })
$add = $block -split "`r?`n" | Where-Object { $_ -match '^[A-Z][A-Z0-9_]*=' } | ForEach-Object { ($_ -split '=', 2)[0] } | Where-Object { $have -notcontains $_ }
if ($add) { $text = [IO.File]::ReadAllText("$PWD\.env"); $sep = if ($text -and -not $text.EndsWith("`n")) { "`n" } else { "" }; [IO.File]::AppendAllText("$PWD\.env", $sep + (($add | ForEach-Object { "$_=" }) -join "`n") + "`n") }
```

Then fill in values in `.env` for only the tools you use. Notes:

- **Names you already use are shared.** If your project already sets `OPENAI_API_KEY`, AgentForge uses that
  same key, and its usage is billed to it. Step 2 never adds a second copy.
- **Nothing loads `.env` for you.** AgentForge's Python reads the process environment. Load `.env` into the
  shell before running a command: `set -a && . ./.env && set +a` in bash, or the PowerShell one-liner in the
  block's header.
- **Hooks read the environment Claude Code started with.** Set the optional hook settings in that shell, or
  under `env` in `.claude/settings.local.json`.
- **After an AgentForge update,** step 1 does nothing, because your block already has its marker. If the
  installer names variables your `.env.example` lacks, copy those lines from
  `agentic-assets/agentforge.env.example`, then re-run step 2.

MCP/plugin examples live in:

```text
agentic-assets/plugins/mcp-servers.json
agentic-assets/plugins/legacy-project-onboarding.json
```

Keep the active MCP set small. For legacy onboarding, start with `filesystem`, `github`, and `memory`; add `context7` for current library docs and `playwright` for UI verification.

---

## 6. Verify AgentForge Is Ready

From the target project root:

```bash
python health_check/cli.py --verbose
```

On Windows (Git Bash), run `PYTHONIOENCODING=utf-8 python health_check/cli.py --verbose`. The checker prints box-drawing characters and does not switch its own output to UTF-8.

Expected result (counts from a fresh install on 2026-09-15; the `skills` line counts the installed slash commands):

```text
  [PASS]    hooks       18 hook(s) configured, all local scripts present
  [PASS]    skills      44 skill(s) valid (...)
  [PASS]    agents      67 agent file(s) active in .claude/agents/
  [PASS]    memory      memory bank files and local ignore rules present
  [PASS]    overall     4 passed, 0 warned, 0 failed
```

### Verify the payload against source

The health check confirms the pieces are present. To confirm every installed file **matches** the Assets
source, run these from your AgentForge clone. Neither command installs anything:

```bash
python -X utf8 install.py --project "C:/path/to/target-project" --verify          # MISSING / DRIFT / UNVERIFIABLE / DANGLING
python -X utf8 install.py --project "C:/path/to/target-project" --check-coverage  # MISSING / DANGLING
```

A clean target prints:

```text
Verify OK — zero drift; every installed asset matches source and every citation resolves.
Coverage OK — every source asset has an installed counterpart, and every citation resolves.
```

Both exit `1` on any finding. `DRIFT` means an installed file's content differs from source (line endings
and the patch-marker stamp are ignored). `UNVERIFIABLE` means a patched source was installed without its
stamp. `DANGLING` means a command or agent in the Assets source cites an `agentic-assets/…`, `scripts/hooks/…`,
`scripts/scope/…`, or `agentforge/docs/…` path that no install ships (ADR-0017 D-1). The template `CLAUDE.md`
is only checked for presence, never content. `settings.json`, `settings.local.json`, the memory bank, and
`.gitignore` are not checked at all.

If it fails:

- Re-run setup (`--project <path>`); it is idempotent and safe to re-run.
- Confirm `.claude/settings.json` exists.
- Confirm `agentic-assets/skills/` exists.
- Confirm `.claude/commands/legacy-audit.md` exists for generic/legacy projects.
- Confirm `.claude/agents/legacy-modernizer.md` exists.
- Restart Claude Code after reinstalling.

---

## 7. First Claude Code Check

Restart Claude Code in the target project so it reloads agents, commands, hooks, and `CLAUDE.md`.

Run one safe command:

```text
/memory-audit --report-only
```

For a new product, next run:

```text
/research "<topic>" --type combined
```

For a legacy project, next run:

```text
/legacy-audit . --memory-bank --subfolder-claude --plan
```

Do not start refactoring legacy code until `/legacy-audit` records baseline commands, current failures, memory-bank status, and the first low-blast-radius modernization slice.

---

## 8. What the Installer Adds

| Asset                         | Installed location                                                                                                |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Commands                      | `.claude/commands/`                                                                                             |
| Agents                        | `.claude/agents/`                                                                                               |
| Hook scripts                  | `scripts/hooks/`                                                                                                |
| Hook config                   | `.claude/settings.json`                                                                                         |
| Runtime skills                | `agentic-assets/skills/`                                                                                        |
| Plugin/MCP catalog            | `agentic-assets/plugins/`                                                                                       |
| Runtime docs                  | `agentic-assets/docs/guides/` (`.md` guides only)                                                             |
| Memory-bank pointer           | `agentic-assets/docs/context/README.md` (seeded once; points at your root `docs/context/`)                    |
| Assets README + notice        | `agentic-assets/README.md`, `agentic-assets/NOTICE.md`                                                        |
| Install manifest              | `agentic-assets/INSTALLED_MANIFEST.json` (rewritten each install; git-ignored)                                  |
| Version stamp                 | `agentic-assets/RELEASE_VERSION.json` (rewritten each install; git-ignored)                                     |
| Scope generator               | `agentic-assets/scripts/scope/`                                                                                 |
| Health checker                | `health_check/`                                                                                                 |
| SDLC orchestrator             | `agentforge/src/` (invoked by `/agentforge`, `/test-run`, `/test-plan`)                                   |
| Data-source simulator         | `agentforge_simulator/` (from source `simulator/`)                                                            |
| Shared Python utilities       | `src/neuroedge_marketing/`, `src/neuroedge_productdoc/`                                                       |
| Attribution notice            | `NOTICE.md` (always overwritten — upstream is source of truth)                                                 |
| Python dependency entry point | `agentic-assets/requirements-agentforge.txt` (rewritten each install; reference it, don't edit it)              |
| Credential template           | `.env.example` (seeded once, never overwritten)                                                                 |
| Current AgentForge env block  | `agentic-assets/agentforge.env.example` (rewritten each install; copy from it)                                  |
| Project instructions          | `CLAUDE.md`                                                                                                     |
| Universal agent pointer       | `AGENTS.md`                                                                                                     |
| Nested module context         | `src/<package>/CLAUDE.md` (modular projects, Scope step)                                                        |
| Memory bank                   | `docs/context/`, `docs/decisions/`, `docs/audit/`                                                           |
| Local secret template         | `.claude/settings.local.json`                                                                                   |
| Git ignore rules              | 9 lines appended to`.gitignore` under `# AgentForge local state and secrets` (only lines not already present) |
| Custom-plugin template        | `agentforge_custom_plugin/Project_Specific_Context/` (setup's Plugin step, not `install.py`)                  |

**Capability packs (ADR-0018).** Some disciplines are stored in the Assets repo as `packs/<name>/` (today:
`packs/embedded/`). They install to the same places as everything else, so the target layout does not
change: pack agents go flat into `.claude/agents/`, pack commands into `.claude/commands/ENGINEERING/<name>/`,
and pack skills plus `manifest.md` into `agentic-assets/skills/ENGINEERING/<name>/`.

**Not shipped to a target.** These stay in the Assets repo: the rendered `docs/guides/*.html` files,
`scripts/hooks/__tests__/`, the Assets repo's own `docs/context/` memory bank, `docs/decisions/`,
`docs/project_related/`, `data/` (including marketing-video output and caches), `tests/`, `agentforge/docs/`,
and every `__pycache__/`. For file counts per folder and the reasoning behind each exclusion, see
[review_surplus_files_to_target.md](review_surplus_files_to_target.md).

---

## 9. Extend Hooks for Project-Specific Languages

The installer wires lint/typecheck hooks for **Python** (`ruff`) and **TypeScript** (`tsc --noEmit` + `console.log` scan) only. C++ and C# edits get a Stop-time hook that requires a `cpp-reviewer` / `csharp-reviewer` pass, but no formatter or build check. The other shipped hooks are language-neutral: HITL gate, `--no-verify` block, ML-artifact commit block, ML-leakage scan, code-review and memory-bank reminders. That is a starting baseline, not a language contract. C++, Rust, Go, Java, Kotlin, C#, and Dart/Flutter projects need additional hooks appended to `.claude/settings.json` to get the same instant feedback loop on every edit.

### Why the default hook set is Python + TypeScript

- **Cheap toolchain.** `ruff` and `tsc` install in seconds and need no compiler or SDK.
- **Fast per-file.** Neither produces binaries, so hooks stay under ~1s per edit.
- **Cross-platform.** Same command works on Windows, Linux, macOS without per-machine tuning.
- **Deterministic.** No project-specific paths, no SDK version drift.

C++/Rust/Go builds need per-project SDK layouts and can take minutes, so the installer deliberately does not guess a build hook. It ships **language-specific agents** instead (see the table below) — those run on demand and cost nothing on quiet edits.

### Which agents are already installed (no extra wiring needed)

Reviewer and build-error-resolver agents ship with every install. Routing to them is described in the "Hooks, MCP, And Maintenance" section of the project `CLAUDE.md` template. Add a line there for each language your project uses. Hooks are optional latency-reducers, not gatekeepers.

| Language                                   | Reviewer agent          | Build-error resolver agent  |
| ------------------------------------------ | ----------------------- | --------------------------- |
| C++ / CUDA                                 | `cpp-reviewer`        | `cpp-build-resolver`      |
| Rust                                       | `rust-reviewer`       | `rust-build-resolver`     |
| Go                                         | `go-reviewer`         | `go-build-resolver`       |
| Java / Spring Boot                         | `java-reviewer`       | `java-build-resolver`     |
| Kotlin / Android                           | `kotlin-reviewer`     | `kotlin-build-resolver`   |
| C# / .NET                                  | `csharp-reviewer`     | `csharp-build-resolver`   |
| Dart / Flutter                             | `flutter-reviewer`    | `dart-build-resolver`     |
| Embedded C / firmware (`packs/embedded`) | `embedded-c-reviewer` | `embedded-build-resolver` |
| PyTorch runtime                            | —                      | `pytorch-build-resolver`  |

### Which JSON to edit — and why it matters

Add language hooks to **`.claude/settings.json`** (the committed team file). Do **not** add them to `.claude/settings.local.json`.

| File                            | Scope                                            | Purpose                                                                                   |
| ------------------------------- | ------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| `.claude/settings.json`       | Committed — shared by every teammate            | Team rules and hooks. Language coverage is a project contract, so it belongs here         |
| `.claude/settings.local.json` | Local only — never committed (in`.gitignore`) | Personal secrets (`API_KEY`s) and per-machine env vars. Never put hook definitions here |

If a C++ hook lived in `settings.local.json`, teammates would get no enforcement and the hook would vanish on a fresh clone.

Each hook entry needs:

- `matcher` — which Claude tool triggers it (`Edit|Write`, `Bash`, `*` for all).
- `hooks[].command` — the Node.js script under `scripts/hooks/`.
- `id` — stable identifier (AgentForge merges by `id` on re-install, so a stable id prevents duplicates).
- `description` — one-line note for teammates reading the file.

### Recommended additions by language

Add only what your project actually uses. Fast checks belong in `PostToolUse`. Slow full builds should stay out of hooks — use the build-resolver agent on demand instead.

| Language       | Fast`PostToolUse` check                                             | Slower`Stop` check (opt-in)                         | Prerequisites in repo                                                                                                      |
| -------------- | --------------------------------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| C++            | `clang-format --dry-run --Werror` on edited `.cpp/.h/.hpp/.cu`    | `clang-tidy` on edited file only                    | `.clang-format` + `compile_commands.json` (add `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON` in top-level `CMakeLists.txt`) |
| Rust           | `cargo fmt --check` on edited `.rs`                               | `cargo clippy -- -D warnings`                       | `rustfmt.toml` (optional), `clippy.toml` (optional)                                                                    |
| Go             | `gofmt -l` + `go vet` on edited `.go`                           | `golangci-lint run` on changed package              | `.golangci.yml` (optional)                                                                                               |
| Java           | `google-java-format --dry-run` or `spotless:check` on `.java`   | `mvn -q -DskipTests compile` (or Gradle equivalent) | Formatter plugin in`pom.xml` / `build.gradle`                                                                          |
| Kotlin         | `ktlint` on edited `.kt`                                          | `gradle compileKotlin`                              | `.editorconfig`                                                                                                          |
| C#             | `dotnet format --verify-no-changes` on `.cs`                      | `dotnet build --no-restore`                         | `.editorconfig`                                                                                                          |
| Dart / Flutter | `dart format --set-exit-if-changed` + `dart analyze` on `.dart` | `flutter test`                                      | `analysis_options.yaml`                                                                                                  |

### Example — add a C++ format hook

Append this entry under `PostToolUse` in `.claude/settings.json`:

```json
{
  "matcher": "Edit|Write",
  "hooks": [
    {
      "type": "command",
      "command": "node scripts/hooks/post-edit-cpp-format.js"
    }
  ],
  "description": "clang-format --dry-run on edited .cpp/.h/.hpp/.cu files",
  "id": "post:edit:cpp-format"
}
```

Then create `scripts/hooks/post-edit-cpp-format.js` modelled on the shipped `scripts/hooks/post-edit-py-lint.js` (same contract: file path arrives via stdin JSON, exit code 0 = pass, non-zero = block).

### Extending the pre-commit hook

The default `pre:bash:commit-quality` hook (`scripts/hooks/pre-commit-quality.js`) only inspects staged `.py/.ts/.js` files. If your project has C++/Rust/Go, extend that same script to also run the language's formatter check on the corresponding staged extensions. One file, one diff — no new hook entry needed.

### Rule of thumb

- **Fast checks (formatter, single-file lint) → hook it.** Instant feedback is worth the wiring.
- **Full builds → do not hook it.** Rely on the language's build-resolver agent when a manual build breaks.
- **Repository conventions (`.clang-format`, `rustfmt.toml`, `.editorconfig`) belong in the repo, not in the hook.** The hook enforces; the config file defines.

---

## 10. Ready-to-Work Routes

Once health check passes:

| Situation                     | Start with                                                  |
| ----------------------------- | ----------------------------------------------------------- |
| Greenfield product            | `/research`, then `/prp-prd`                            |
| Legacy/brownfield repo        | `/legacy-audit . --memory-bank --subfolder-claude --plan` |
| Small feature in known code   | `/prp-plan "<feature>"`                                   |
| Execute an approved plan      | `/prp-implement <plan>`                                   |
| Validate install health later | `python health_check/cli.py --verbose`                    |
| Clean stale memory            | `/memory-audit --report-only`                             |
| Commit                        | `/prp-commit "<message>"`                                 |
| PR                            | `/prp-pr`                                                 |
| Quality gate                  | `/quality-gate .`                                         |

For the end-to-end SDLC workflow, use [how_to_build_your_project.md](how_to_build_your_project.md).

---

## 11. Troubleshooting

| Symptom                                                                               | Likely cause                                                                                                                             | Fix                                                                                                               |
| ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `claude` not found                                                                  | Claude Code not installed or shell not restarted                                                                                         | `npm install -g @anthropic-ai/claude-code`, restart shell                                                       |
| Health check`skills` line warns `.claude/commands/ not found`                     | Setup did not run or wrong target path (commands are counted under`skills`)                                                            | Re-run setup from AgentForge root                                                                                 |
| Health check says skills missing                                                      | Runtime assets not copied                                                                                                                | Re-run setup; confirm`agentic-assets/skills/`                                                                   |
| Health check says hooks missing                                                       | `.claude/settings.json` stale                                                                                                          | Re-run setup and restart Claude Code                                                                              |
| Claude does not see new commands                                                      | Claude Code was already open                                                                                                             | Restart Claude Code in the target repo                                                                            |
| Legacy work starts without audit                                                      | Routing not explicit enough                                                                                                              | Run`/legacy-audit . --memory-bank --subfolder-claude --plan`                                                    |
| Too many MCP tools in context                                                         | MCP config overloaded                                                                                                                    | Keep only task-relevant servers enabled                                                                           |
| `Plugin : Project_Specific_Context not scaffolded` with `[WinError 3]`            | Windows 260-character path limit — the template's deepest file adds ~110 characters to the target path                                  | Use a shorter target path, then re-run setup (the plugin step is seed-once and only runs if the plugin is absent) |
| `--verify` reports `DRIFT …src/neuroedge_marketing/CLAUDE.md` on an older target | An earlier Scope step wrote its`SCOPE:AUTO` block into that AgentForge-managed file; current setup skips managed packages (see § 4.1) | Run update once to restore the source copy. Delete a leftover`src/neuroedge_productdoc/CLAUDE.md` by hand       |
| Update keeps listing the same orphans                                                 | The prune was declined, or stdin was unavailable                                                                                         | Re-run update with`--yes`                                                                                       |
| `installed version X is newer than incoming Y`                                      | `install.py` refuses downgrades                                                                                                        | Update your Assets clone, or pass`--force` to downgrade on purpose                                              |
| `ModuleNotFoundError` from an AgentForge command                                    | Python dependencies not installed in the environment that runs it                                                                        | Do what the installer printed under**Dependencies** (see [Python dependencies](#python-dependencies))        |
| Health check`tools` warns `ffmpeg not found` (or `gh`, `node`)                | That software is not installed or not on`PATH`                                                                                         | Install it yourself. Only the feature named in the warning needs it; for ffmpeg you can set`FFMPEG_BIN` instead |
| Install prints`AgentForge variable(s) not in it`                                    | Your own`.env.example` predates those variables                                                                                        | Copy the named lines from`agentic-assets/agentforge.env.example` (see [§ 5](#5-configure-local-secrets))        |

---

## Completion Checklist

- [ ] AgentForge repo cloned or added as `agentic-assets` submodule.
- [ ] Setup command completed for the target `--project`.
- [ ] `.claude/commands/` exists.
- [ ] `.claude/agents/` exists.
- [ ] `agentic-assets/skills/` exists.
- [ ] `agentic-assets/plugins/` exists.
- [ ] `CLAUDE.md` exists.
- [ ] `AGENTS.md` exists.
- [ ] `docs/context/ACTIVE.md` exists.
- [ ] Python dependencies installed from `agentic-assets/requirements-agentforge.txt` (see [Python dependencies](#python-dependencies)).
- [ ] `.env` holds the AgentForge variable names you use (see [§ 5](#5-configure-local-secrets)).
- [ ] `python health_check/cli.py --verbose` reports no FAIL. A `tools` WARN names software you still need to install yourself.
- [ ] Claude Code restarted.
- [ ] First route selected: greenfield `/research`, legacy `/legacy-audit`, or known work `/prp-plan`.

AgentForge is ready after this checklist passes.
