#!/usr/bin/env python3
"""provenance.py — the SunCHECK `sources.md` provenance record (ADR-0012 Direction 2,
FR-03, EP-04).

Emits the exact table shape already hand-authored at
`agentforge_custom_plugin/SunCHECK/context/sources.md`:

    | Fact | Source | Type | Confidence | Date |

Enforces the Type/Confidence enums documented in that same file's legend — an
out-of-enum value RAISES rather than being silently accepted, because a corrupted
value here would be invisible to a human reviewer (TC-04-01-02/03). Every unknown
load-bearing fact gets an explicit **TBD** row (`emit_tbd_row`) — never omitted, never
invented (M1, TC-04-01-05). A non-TBD row's `Source` cell is a resolvable coordinate
(`source_id::locator`) built directly from an `IngestedDoc` the FR-01 driver pulled —
`resolve_source` is the exact inverse, so provenance never claims a source that was
never actually pulled (TC-04-01-06).
"""

from __future__ import annotations

from dataclasses import dataclass

from exchange.adapter import IngestedDoc

TYPE_ENUM = frozenset({"vendor-doc", "vendor-web", "sme", "inferred"})
CONFIDENCE_ENUM = frozenset({"confirmed", "medium", "TBD"})

# The placeholder cell value for an unknown fact's Source/Type/Date — matches the
# literal SunCHECK sources.md convention ("— | — | TBD | —") exactly, so a TBD row
# emitted here renders identically to the hand-authored example.
_TBD_PLACEHOLDER = "—"   # em dash, "—"

_HEADER = "| Fact | Source | Type | Confidence | Date |"
_DIVIDER = "|---|---|---|---|---|"

# Source coordinate convention: "source_id::locator" — resolvable back to the
# IngestedDoc it came from (TC-04-01-06), never an opaque free-text string.
_COORD_SEP = "::"


@dataclass
class SourceRow:
    """One row of `sources.md`. `type`/`confidence` are already-validated enum
    members by construction — the only way to build a SourceRow is through
    `emit_sources_row`/`emit_tbd_row`, both of which enforce the enums."""

    fact: str
    source: str
    type: str
    confidence: str
    date: str

    def to_markdown_row(self) -> str:
        return f"| {self.fact} | {self.source} | {self.type} | {self.confidence} | {self.date} |"


def build_source_coordinate(doc: IngestedDoc) -> str:
    """The resolvable `Source` cell value for a fact traced to `doc` — the FR-01
    pull coordinate, never a free-text description (TC-04-01-06)."""
    return f"{doc.source_id}{_COORD_SEP}{doc.locator}"


def resolve_source(source: str) -> tuple[str, str] | None:
    """Inverse of `build_source_coordinate`. Returns None for a TBD placeholder (or
    any value that isn't a real pull coordinate) — resolving a fabricated Source to
    "nothing pulled" is exactly the failure TC-04-01-06 checks for."""
    if _COORD_SEP not in source:
        return None
    source_id, _, locator = source.partition(_COORD_SEP)
    if not source_id or not locator:
        return None
    return source_id, locator


def emit_sources_row(fact: str, source: str, type_: str, confidence: str, date: str) -> SourceRow:
    """Build one validated `SourceRow`. Raises ValueError (never silently accepts)
    when `type_` or `confidence` is out-of-enum (TC-04-01-02/03) — a corrupted
    Type/Confidence value is a safety-relevant control, not a cosmetic one: both
    stop-hitl-gate-style enforcement AND a human reviewer read this column directly."""
    if confidence not in CONFIDENCE_ENUM:
        raise ValueError(
            f"invalid Confidence {confidence!r}; expected one of {sorted(CONFIDENCE_ENUM)}"
        )
    if type_ not in TYPE_ENUM:
        raise ValueError(f"invalid Type {type_!r}; expected one of {sorted(TYPE_ENUM)}")
    return SourceRow(fact=fact, source=source, type=type_, confidence=confidence, date=date)


def emit_tbd_row(fact: str) -> SourceRow:
    """One explicit TBD row for a load-bearing fact with no confirmed source — the
    ONLY alternative to `emit_sources_row` (M1: every field is cited or TBD, no
    third state). Never omits the fact, never fabricates a Source/Type for it —
    Source/Type are always the placeholder, Confidence is always "TBD"
    (TC-04-01-05)."""
    return SourceRow(
        fact=fact,
        source=_TBD_PLACEHOLDER,
        type=_TBD_PLACEHOLDER,
        confidence="TBD",
        date=_TBD_PLACEHOLDER,
    )


def render_sources_md(rows: list[SourceRow]) -> str:
    """Render the full `sources.md` table body — header, divider, exactly one line
    per row, in the order given (TC-04-01-01/04)."""
    lines = [_HEADER, _DIVIDER]
    lines.extend(row.to_markdown_row() for row in rows)
    return "\n".join(lines) + "\n"
