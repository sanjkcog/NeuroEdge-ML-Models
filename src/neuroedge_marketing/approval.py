"""Human review stamps: a video is not fetched or rendered before a person has approved it.

Two gates, matching the two human reviews in ``/marketing-video``:

========  =========================================================  ==========
Gate      A person has...                                            Gates
========  =========================================================  ==========
script    read the storyboard -- voice-over, captions, queries       ``fetch``
footage   watched the selected clips (``contact_sheet.html``)        ``render``
========  =========================================================  ==========

The stamp records a SHA-256 of what was approved, so editing ``storyboard.json`` after approving it
voids the approval instead of rendering words nobody read. ``pick`` is left out of the script
fingerprint on purpose: choosing a clip is a footage decision, and ``render`` honours a ``pick`` only
when it names one of the clips already fetched and shown on the contact sheet -- all of which the
footage approval covered. A pick therefore needs no re-approval; fetching again does, because it
rewrites ``_selection.json``.

🔴 **Enforced at the CLI boundary only.** ``cli.cmd_fetch`` and ``cli.cmd_render`` stay callable
without a stamp, because callers that run their own gate import them directly -- the Studio's
nine-stage pipeline stamps its own manifest, and ``recorded-demo`` checks ``--approved``. A gate
inside those functions would break both on their next update.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

STAMP_NAME = "approval.json"
SELECTION_NAME = "_selection.json"
GATES = ("script", "footage")
#: Which approvals each gated command needs, in the order they are checked.
REQUIRED = {"fetch": ("script",), "render": ("script", "footage")}


def stamp_path(storyboard_path: Path) -> Path:
    """The stamp lives beside the storyboard it approves."""
    return Path(storyboard_path).parent / STAMP_NAME


def script_fingerprint(storyboard_path: Path) -> str:
    """SHA-256 of the storyboard's content, key order and whitespace ignored, ``pick`` excluded."""
    data = json.loads(Path(storyboard_path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for scene in data.get("scenes") or []:
            if isinstance(scene, dict):
                scene.pop("pick", None)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def footage_fingerprint(footage_dir: Path) -> str:
    """SHA-256 of the fetch result the person watched."""
    return hashlib.sha256((Path(footage_dir) / SELECTION_NAME).read_bytes()).hexdigest()


def _fingerprint(gate: str, storyboard_path: Path, footage_dir: Path | None) -> str:
    if gate == "script":
        return script_fingerprint(storyboard_path)
    if footage_dir is None:
        raise ValueError("the footage gate needs the footage directory")
    return footage_fingerprint(footage_dir)


def read_stamps(storyboard_path: Path) -> dict[str, Any]:
    """Recorded approvals; an absent or unreadable stamp is no approval, never an error."""
    path = stamp_path(storyboard_path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def approve(gate: str, storyboard_path: Path, footage_dir: Path | None = None) -> dict[str, Any]:
    """Record that a person approved ``gate`` for exactly the current content."""
    if gate not in GATES:
        raise ValueError(f"unknown gate {gate!r}; expected one of {', '.join(GATES)}")
    entry: dict[str, Any] = {
        "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256": _fingerprint(gate, storyboard_path, footage_dir),
    }
    if gate == "footage":
        entry["selection"] = str(Path(footage_dir) / SELECTION_NAME)
    stamps = read_stamps(storyboard_path)
    stamps[gate] = entry
    path = stamp_path(storyboard_path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(stamps, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return entry


def check(command: str, storyboard_path: Path, footage_dir: Path | None = None) -> str | None:
    """Why ``command`` may not run yet, or ``None`` when every approval it needs is current."""
    stamps = read_stamps(storyboard_path)
    for gate in REQUIRED.get(command, ()):
        entry = stamps.get(gate)
        if not isinstance(entry, dict) or not entry.get("sha256"):
            return f"the {gate} review has not been approved. Review it, then run: approve --stage {gate}"
        try:
            current = _fingerprint(gate, storyboard_path, footage_dir)
        except (OSError, ValueError) as exc:
            return f"the {gate} approval cannot be verified: {exc}"
        if current != entry["sha256"]:
            changed = "storyboard.json" if gate == "script" else SELECTION_NAME
            return f"the {gate} approval is stale: {changed} changed after it was approved. Review it again, then re-approve."
    return None
