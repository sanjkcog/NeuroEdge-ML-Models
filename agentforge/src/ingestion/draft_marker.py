#!/usr/bin/env python3
"""draft_marker.py — the draft-vs-binding marker (ADR-0012 Direction 2, FR-05,
EP-06, highest-risk seam).

Single source of truth (OQ-1): the marker is ALWAYS derived from the FR-04 review
gate's status, never independently hand-set. `marker_for` takes only a `GateState` +
an artifact key — there is no parameter through which a caller could hand it a
desired value. `stamp_marker` (the only function that writes the marker into a file)
has the same property: no `marker=`/`value=`/`force=` parameter exists, so the
written value can only ever be what `marker_for` computed at that moment
(TC-06-01-02).

The marker is an explicit machine-readable HTML-comment line, not merely implied by
scanning file content for the word "TBD" (TC-06-01-01) — `discover_plugins.py`'s
enforcement seam (FR-05's other half) reads it with `read_marker`, never by
inspecting the file's prose.
"""

from __future__ import annotations

from pathlib import Path

from gate_state import GateState

_MARKER_PREFIX = "<!-- ingestion-marker: "
_MARKER_SUFFIX = " -->"

DRAFT = "draft"
BINDING = "binding"


def marker_for(state: GateState, artifact: str) -> str:
    """The marker value derived from `artifact`'s gate in `state` — "binding" iff
    the gate is recorded `approved`, "draft" for every other state (pending,
    rejected, changes_requested, or never gated at all). Fail-closed: an artifact
    this function cannot prove approved is always "draft", never "binding"."""
    gate = state.gates.get(artifact)
    if gate is not None and gate.status == "approved":
        return BINDING
    return DRAFT


def stamp_marker(path: str | Path, state: GateState, artifact: str) -> str:
    """Write the marker derived from `artifact`'s gate as the first line of `path`,
    replacing any prior marker line. Returns the marker written.

    No parameter here accepts an explicit marker value — the written value is
    ALWAYS `marker_for(state, artifact)`, so "hand-set the marker to binding while
    the gate is pending" has no call shape that could do it (TC-06-01-02)."""
    path = Path(path)
    marker = marker_for(state, artifact)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = existing.split("\n")
    if lines and lines[0].startswith(_MARKER_PREFIX):
        lines = lines[1:]
    body = "\n".join(lines)
    stamped = f"{_MARKER_PREFIX}{marker}{_MARKER_SUFFIX}\n{body}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stamped, encoding="utf-8")
    return marker


def read_marker(path: str | Path) -> str:
    """Read the marker back from `path`. Missing file, missing marker line, or any
    unrecognised value all report "draft" — fail-closed (never mistaking an
    unmarked or unreadable file for "binding")."""
    path = Path(path)
    if not path.is_file():
        return DRAFT
    try:
        first_line = path.read_text(encoding="utf-8").split("\n", 1)[0]
    except OSError:
        return DRAFT
    if first_line.startswith(_MARKER_PREFIX) and first_line.endswith(_MARKER_SUFFIX):
        value = first_line[len(_MARKER_PREFIX):-len(_MARKER_SUFFIX)]
        if value in (DRAFT, BINDING):
            return value
    return DRAFT
