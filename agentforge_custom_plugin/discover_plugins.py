#!/usr/bin/env python3
"""discover_plugins.py — auto-discovery for AgentForge custom plugins.

The whole point of this file: a user drops (or edits) files under
`agentforge_custom_plugin/<Name>/` and the base SDLC picks them up automatically, with no
install step and no registry. **Presence is activation** — any directory here holding a
`plugin.json` with `wiring.auto_load != false` is an active plugin.

The base `/agentforge` orchestrator (and any role agent run standalone) calls this to learn,
for a given SDLC stage, exactly which context/skill files to read before producing its
artifact. Two sources feed that list: `wiring.stage_context` (per-stage context files) and
the plugin's `requires_domains` / `requires_subjects` skill trees (emitted at every stage). Everything is derived from each plugin's `plugin.json` — adding a new plugin needs
zero changes here or in the base SDLC.

Usage:
    python agentforge_custom_plugin/discover_plugins.py --list
    python agentforge_custom_plugin/discover_plugins.py --stage requirements
    python agentforge_custom_plugin/discover_plugins.py --agent product-manager --json

Output (default): newline-separated project-relative file paths an agent should read, one
per line, prefixed by the plugin name in a comment. `--json` emits a structured object for
programmatic callers. Exit code is always 0 (no active plugins is normal, not an error).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PLUGINS_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PLUGINS_ROOT.parent

# A subject or domain name from a manifest is a single bare path segment, never a path.
# This rejects `..`, slashes, and absolute/drive-letter injection before the value is used
# to build a path — the same guard patch_custom_plugin.py applies to its name inputs.
_SUBJECT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")

# Reusable skill families a plugin may declare it needs, mapped to the tree they live in.
# `requires_subjects` -> skills/SUBJECTS/ (cross-domain subject matter, e.g. Physics).
# `requires_domains`  -> skills/DOMAIN/   (vertical knowledge, e.g. process-automation).
# Both are emitted for EVERY stage the plugin is active for, because vertical and subject
# knowledge is not stage-scoped the way `wiring.stage_context` is: an agent needs the same
# IEC 61511 background whether it is writing requirements or a test plan. Before this map
# existed, only SUBJECTS resolved, so a plugin could ship a domain skill tree that no
# stage agent was ever told to read.
_SKILL_FAMILIES: dict[str, str] = {
    "requires_subjects": "SUBJECTS",
    "requires_domains": "DOMAIN",
}

# Which base SDLC role agent authors which stage — lets `--agent <name>` resolve a stage.
# Several agents author more than one stage (`qa-engineer`: test-plan + trace-matrix;
# `project-manager`: sprint-plan + sprint-close) but this map resolves each to only ONE
# representative stage — safe today only because nothing in this repo currently calls
# `--agent` (every commands/*.md file calls `--stage <id>` directly instead, confirmed
# by grep). If `--agent` becomes a real call site, a plugin's per-stage
# `wiring.stage_context` entries for the non-representative stage (trace-matrix,
# sprint-close) would be silently invisible via that path with no error — code-reviewer
# MEDIUM finding, not yet fixed since no caller is affected, but worth closing before
# `--agent` is wired into anything real.
AGENT_TO_STAGE: dict[str, str] = {
    "legacy-modernizer": "onboarding",
    "researcher": "research",
    "product-manager": "requirements",
    "architect": "architecture",
    "epic-writer": "epics",
    "task-writer": "tasks",
    "qa-engineer": "test-plan",
    "qa-automation-engineer": "test-automation",
    "project-manager": "sprint-plan",
    "developer": "build",
    "team-lead": "review",
    "devops": "deploy",
    "test-triage": "triage",
}

# Fallback stage->context map used when a plugin.json omits `wiring.stage_context`. Paths
# are relative to a plugin's own folder; only those that exist on disk are emitted.
DEFAULT_STAGE_CONTEXT: dict[str, list[str]] = {
    "onboarding":       ["context/integrations", "context/DOMAIN.md",
                         "context/constraints.md", "context/regulatory.md"],
    "research":         ["context/integrations", "context/DOMAIN.md"],
    "requirements":     ["context/personas.md", "context/regulatory.md",
                         "context/constraints.md", "context/workflows"],
    "architecture":     ["context/integrations", "context/constraints.md",
                         "context/regulatory.md"],
    "epics":            ["context/glossary.md", "context/workflows"],
    "tasks":            ["context/glossary.md", "context/workflows"],
    "test-plan":        ["context/integrations", "context/constraints.md"],
    "trace-matrix":     ["context/integrations", "context/constraints.md"],
    "sprint-plan":      ["context/glossary.md", "context/workflows"],
    "build":            ["context/integrations", "context/constraints.md",
                         "context/workflows"],
    "test-automation":  ["context/integrations", "context/constraints.md"],
    "test-run":         ["context/integrations", "context/constraints.md"],
    "triage":           ["context/constraints.md"],
    "review":           ["context/constraints.md", "context/regulatory.md"],
    "deploy":           ["context/integrations", "context/constraints.md",
                         "context/regulatory.md"],
    "sprint-close":     ["context/glossary.md", "context/workflows"],
    "enablement":       ["context/glossary.md", "context/DOMAIN.md"],
}


def _load_manifest(plugin_dir: Path) -> dict | None:
    """Return a plugin's manifest dict, or None if missing/invalid (never raises)."""
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _is_active(manifest: dict) -> bool:
    """Active unless the manifest explicitly opts out with wiring.auto_load == false."""
    wiring = manifest.get("wiring")
    if isinstance(wiring, dict) and wiring.get("auto_load") is False:
        return False
    return True


def active_plugins() -> list[tuple[Path, dict]]:
    """Every active plugin as (dir, manifest), sorted by folder name for stable output."""
    found: list[tuple[Path, dict]] = []
    if not PLUGINS_ROOT.is_dir():
        return found
    for child in sorted(PLUGINS_ROOT.iterdir()):
        if not child.is_dir():
            continue
        manifest = _load_manifest(child)
        if manifest is not None and _is_active(manifest):
            found.append((child, manifest))
    return found


def _stage_entries(manifest: dict, stage: str) -> list[str]:
    """The plugin-relative paths configured for `stage` (manifest map, else default)."""
    wiring = manifest.get("wiring")
    stage_map = wiring.get("stage_context") if isinstance(wiring, dict) else None
    if isinstance(stage_map, dict) and stage in stage_map:
        entries = stage_map[stage]
        if isinstance(entries, list) and all(isinstance(e, str) for e in entries):
            return entries
    return DEFAULT_STAGE_CONTEXT.get(stage, [])


def _expand(plugin_dir: Path, entries: list[str]) -> list[Path]:
    """Resolve configured entries to concrete existing files under the plugin folder.

    A directory entry expands to the Markdown files it contains (recursively); a file
    entry is included as-is if present. Anything that would escape the plugin folder, or
    that does not exist, is silently dropped — a stage map naming a not-yet-created file is
    normal for a seed plugin, not an error.
    """
    out: list[Path] = []
    for entry in entries:
        # An empty or "." entry resolves to the plugin folder itself and would rglob the
        # whole tree — skip it so a stray blank string can't balloon the stage's context.
        if not isinstance(entry, str) or not entry.strip() or entry.strip() == ".":
            continue
        target = (plugin_dir / entry).resolve()
        if not target.is_relative_to(plugin_dir.resolve()):
            continue  # never emit a path outside the plugin
        if target.is_dir():
            out.extend(sorted(p for p in target.rglob("*.md") if p.is_file()))
        elif target.is_file():
            out.append(target)
    # De-dup while preserving order.
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in out:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _rel(path: Path) -> str:
    """Project-relative POSIX path for an agent to read (falls back to absolute)."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_skill_dirs(manifest: dict, key: str) -> list[str]:
    """Project-relative paths for the skill directories `manifest[key]` names.

    Silently drops any entry that fails the single-segment name guard or that does not
    resolve to a real directory: a plugin naming a skill family this checkout does not
    ship is a normal condition (plugins are portable across targets), not an error.
    """
    family = _SKILL_FAMILIES[key]
    names = manifest.get(key, [])
    if not isinstance(names, list):
        return []
    root = REPO_ROOT / "skills" / family
    return [
        _rel(root / n)
        for n in names
        if isinstance(n, str) and _SUBJECT_RE.fullmatch(n) and (root / n).is_dir()
    ]


def enforce_regulated_admission(path: Path, gate_state, artifact: str) -> str | None:
    """ADR-0012 Direction-2 enforcement seam (FR-05, EP-06, OQ-3): refuse `artifact`
    from a regulated stage unless its FR-04 review gate has been recorded
    `approved`. Returns a named (human-readable) refusal reason, or None when the
    artifact is admitted.

    Consults `ingestion.draft_marker.marker_for(gate_state, artifact)` — the gate
    itself is the single source of truth (OQ-1), not `path`'s own stamped marker
    line, so a stale on-disk marker can never admit what the gate has not actually
    approved. `path` is accepted (and named in the refusal) for a clear diagnostic,
    not consulted for the decision itself.

    Fail-closed by construction: any failure to reach the ingestion package (e.g. a
    consumer project's older install predating this feature) refuses rather than
    silently admitting — the same posture as every other fail-closed check in this
    codebase (ExchangeConfig, authz).
    """
    try:
        # Both agentforge/src (for `ingestion`) AND agentforge/src/state must be on the
        # path: ingestion.draft_marker does a bare `from gate_state import GateState`,
        # which lives under src/state. Inserting only src made the import fail outside
        # the test harness (conftest pre-seeds both), so the seam refused every artifact
        # — approved included. Insert both so approved-binding context can actually pass.
        assets_src = REPO_ROOT / "agentforge" / "src"
        for _p in (assets_src, assets_src / "state"):
            if _p.is_dir() and str(_p) not in sys.path:
                sys.path.insert(0, str(_p))
        from ingestion.draft_marker import BINDING, marker_for  # type: ignore
        marker = marker_for(gate_state, artifact)
    except Exception:
        # fail-closed: any failure to reach the ingestion package / gate refuses rather
        # than silently admitting (e.g. a consumer install predating this feature).
        return (
            f"refused: {path.name!r} ({artifact!r}) could not be verified against an "
            "approved review gate — fail-closed (ADR-0012 FR-05, M2 never-silently-bind)"
        )

    if marker != BINDING:
        return (
            f"refused: {path.name!r} ({artifact!r}) is {marker} — an ingestion-authored "
            "context file with no distinct-human-approved review gate cannot enter a "
            "regulated stage (ADR-0012 FR-05, M2 never-silently-bind)"
        )
    return None


def collect_for_stage(
    stage: str,
    *,
    gate_state=None,
    regulated_stages: frozenset[str] | None = None,
) -> list[dict]:
    """Per active plugin: its name, subject deps, and the files to read for `stage`.

    `gate_state` + `regulated_stages` are optional and additive (ADR-0012 Direction
    2, FR-05, OQ-3): when both are supplied AND `stage` is one of
    `regulated_stages`, every collected file is checked via
    `enforce_regulated_admission` — a draft-marked (unapproved) file is refused
    (moved to the returned `refused` list with a named reason, never returned in
    `read`); an approved-binding file passes through exactly as before. Calling with
    neither (the pre-existing shape every caller in this repo still uses) leaves
    behaviour completely unchanged — `refused` is simply always empty.
    """
    enforcing = gate_state is not None and regulated_stages is not None and stage in regulated_stages

    result: list[dict] = []
    for plugin_dir, manifest in active_plugins():
        candidates = _expand(plugin_dir, _stage_entries(manifest, stage))
        files: list[str] = []
        refused: list[dict] = []
        for p in candidates:
            rel = _rel(p)
            if enforcing:
                reason = enforce_regulated_admission(p, gate_state, rel)
                if reason is not None:
                    refused.append({"file": rel, "reason": reason})
                    continue
            files.append(rel)
        result.append({
            "plugin": manifest.get("name", plugin_dir.name),
            "stage": stage,
            "requires_subjects": _resolve_skill_dirs(manifest, "requires_subjects"),
            "requires_domains": _resolve_skill_dirs(manifest, "requires_domains"),
            "read": files,
            "refused": refused,
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover active AgentForge custom plugins and the files a stage reads.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List active plugins")
    group.add_argument("--stage", metavar="ID", help="SDLC stage id (e.g. requirements)")
    group.add_argument("--agent", metavar="NAME", help="Role agent name (resolves to a stage)")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON")
    args = parser.parse_args()

    if args.list:
        plugins = active_plugins()
        if args.json:
            print(json.dumps(
                [{"plugin": m.get("name", d.name), "dir": _rel(d)} for d, m in plugins],
                indent=2,
            ))
        elif not plugins:
            print("No active custom plugins.")
        else:
            print("Active custom plugins:")
            for d, m in plugins:
                print(f"  - {m.get('name', d.name)}  ({_rel(d)})")
        return

    stage = args.stage
    if args.agent:
        stage = AGENT_TO_STAGE.get(args.agent)
        if stage is None:
            print(f"Agent '{args.agent}' authors no auto-wired SDLC stage; nothing to read.",
                  file=sys.stderr)
            return

    collected = collect_for_stage(stage)
    if args.json:
        print(json.dumps(collected, indent=2))
        return

    any_files = False
    for item in collected:
        skills = item["requires_domains"] + item["requires_subjects"]
        if not item["read"] and not skills:
            continue
        any_files = True
        print(f"# plugin: {item['plugin']} (stage: {stage})")
        for s in skills:
            print(s)
        for f in item["read"]:
            print(f)
    if not any_files:
        print(f"# no active-plugin context for stage '{stage}'")


if __name__ == "__main__":
    main()
