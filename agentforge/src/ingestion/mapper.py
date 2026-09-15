#!/usr/bin/env python3
"""mapper.py — the context-mapper: cited-or-TBD, never fabricate (ADR-0012
Direction 2, FR-02, EP-03).

`extract_claims` is the single, delegated entry point implementing the FR-06
`extraction-with-citation` skill's contract (see
skills/ENGINEERING/ai-genai/extraction-with-citation.md): atomic-claim
decomposition, a source span per claim, and a per-claim confidence — a
DETERMINISTIC reference implementation over already-provided source spans, not a
live LLM call (per LLD: "the point is the never-fabricate contract, not a live LLM
call"). `map_docs` never re-implements this logic inline — it only routes and
writes based on `extract_claims`'s output (TC-03-01-05).

M1 (never-fabricate) holds by construction here, not merely by discipline:
`_write_field` is the ONLY function in this module that ever writes a non-TBD value,
and it is called from exactly one call site, itself gated on a `Claim` actually
existing for that field. There is no second branch anywhere that could write an
uncited or synthesized value — a gap always falls through to `"tbd"`
(TC-03-01-01/02/03/04).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from pathlib import Path

from exchange.adapter import IngestedDoc

# Conservative confidence thresholds (OQ-2). Two named constants, not per-field
# variability: >= CONFIDENCE_HIGH writes cleanly; [CONFIDENCE_LOW, CONFIDENCE_HIGH)
# writes AND flags for review; below CONFIDENCE_LOW is always TBD, never written —
# the conservative (fail-toward-TBD) choice the LLD's OQ-2 calls for.
CONFIDENCE_HIGH = 0.85
CONFIDENCE_LOW = 0.55

# Schema-only targeting (TC-03-02-04): these four base names, plus the
# "workflows:<name>" and "integrations:<product>:<name>" prefixes, are the ONLY
# fields map_docs will ever write to. Mirrors the LLD's documented schema set
# exactly: glossary/personas/regulatory/constraints/workflows/*/integrations/<product>/*.
_BASE_SCHEMA_FIELDS = frozenset({"glossary", "personas", "regulatory", "constraints"})

# A single path segment must be a plain name — no separators, no `..`, no traversal.
# `workflows:<name>` / `integrations:<product>:<name>` leaf segments are attacker-shaped
# input in principle (a `target_fields` entry), so each captured segment is validated
# against this before it is ever joined into a filesystem path (mirrors
# discover_plugins._SUBJECT_RE). Prefix-checking alone would let `workflows:../../x`
# escape `plugin_dir` and become an arbitrary directory-create + file-write.
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

# One atomic claim per matched line: "<field>: <value> :: <confidence>". This is
# the reference extractor's whole input contract — a line not matching this shape
# carries no claim at all (never guessed at), which is exactly what keeps this
# module's never-fabricate behaviour testable deterministically.
_CLAIM_LINE = re.compile(
    r"^(?P<field>[A-Za-z0-9_:\-]+):\s*(?P<value>.+?)\s*::\s*(?P<confidence>[0-9]*\.?[0-9]+)\s*$"
)


@dataclass
class Claim:
    """One atomic, source-cited claim — the FR-06 skill's unit of output."""

    field: str
    value: str
    source_id: str
    locator: str
    span: str
    confidence: float


@dataclass
class MappedField:
    """The mapper's decision for one target field. `state` is always exactly one of
    "written" / "flagged" / "tbd" / "refused" — no third/undefined state exists."""

    field: str
    value: str | None
    state: str
    span: str = ""
    source_id: str = ""
    locator: str = ""
    confidence: float = 0.0
    flagged: bool = False
    reason: str = ""


@dataclass
class MapResult:
    fields: list[MappedField] = dc_field(default_factory=list)

    @property
    def fields_by_name(self) -> dict[str, MappedField]:
        return {f.field: f for f in self.fields}


def extract_claims(docs: list[IngestedDoc]) -> list[Claim]:
    """The FR-06 skill's deterministic reference extractor: decompose each doc into
    atomic Claims, one per recognised `<field>: <value> :: <confidence>` line, each
    citing its exact source doc and the literal line as its source span. A line that
    does not match the convention yields no claim — this reference implementation
    never guesses at unstructured prose, which is the whole point (the never-
    fabricate contract, not NLP sophistication)."""
    claims: list[Claim] = []
    for doc in docs:
        for line in doc.content.splitlines():
            match = _CLAIM_LINE.match(line.strip())
            if match is None:
                continue
            claims.append(Claim(
                field=match.group("field"),
                value=match.group("value"),
                source_id=doc.source_id,
                locator=doc.locator,
                span=line.strip(),
                confidence=float(match.group("confidence")),
            ))
    return claims


def _resolve_schema_path(field_name: str, plugin_dir: Path) -> Path | None:
    """Resolve a target field name to its schema file under `plugin_dir/context/`,
    or None if it is out-of-schema (refused, TC-03-02-04). The ONLY resolvable
    shapes are the four base fields and the workflows:/integrations: prefixes."""
    parts = field_name.split(":")
    if len(parts) == 1 and parts[0] in _BASE_SCHEMA_FIELDS:
        return plugin_dir / "context" / f"{parts[0]}.md"
    # Every dynamic leaf segment must be a safe single name — reject `..`/separators
    # so a `workflows:`/`integrations:` entry can never escape plugin_dir/context/.
    if len(parts) == 2 and parts[0] == "workflows" and _SAFE_SEGMENT.match(parts[1]):
        return plugin_dir / "context" / "workflows" / f"{parts[1]}.md"
    if (
        len(parts) == 3
        and parts[0] == "integrations"
        and _SAFE_SEGMENT.match(parts[1])
        and _SAFE_SEGMENT.match(parts[2])
    ):
        return plugin_dir / "context" / "integrations" / parts[1] / f"{parts[2]}.md"
    return None


def _write_field(path: Path, claim: Claim) -> None:
    """The single write path for a non-TBD field value (M1). Called from exactly
    one site in `map_docs`, always gated on a `Claim` that actually exists — there
    is no other function in this module that writes field content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{claim.field}: {claim.value}\n", encoding="utf-8")


def map_docs(docs: list[IngestedDoc], plugin_dir: str | Path, target_fields: list[str]) -> MapResult:
    """Map `docs` onto `target_fields` under `plugin_dir`'s context schema.

    Delegates all extraction to `extract_claims` (TC-03-01-05) — this function only
    routes each field's best-evidenced Claim (highest confidence) to one of four
    states: "refused" (out-of-schema, checked first, independent of citation),
    "written" (>= CONFIDENCE_HIGH), "flagged" (write + flag, [CONFIDENCE_LOW,
    CONFIDENCE_HIGH)), or "tbd" (no claim at all, or below CONFIDENCE_LOW — never a
    synthesized value, M1).
    """
    plugin_dir = Path(plugin_dir)
    claims_by_field: dict[str, list[Claim]] = {}
    for claim in extract_claims(docs):
        claims_by_field.setdefault(claim.field, []).append(claim)

    fields: list[MappedField] = []
    for name in target_fields:
        schema_path = _resolve_schema_path(name, plugin_dir)
        if schema_path is None:
            fields.append(MappedField(
                field=name, value=None, state="refused",
                reason=f"refused: {name!r} is not a recognised context schema field "
                       "(glossary/personas/regulatory/constraints/workflows/*/integrations/<product>/*)",
            ))
            continue

        candidates = claims_by_field.get(name, [])
        best = max(candidates, key=lambda c: c.confidence, default=None)
        if best is None:
            fields.append(MappedField(field=name, value=None, state="tbd"))
            continue

        if best.confidence >= CONFIDENCE_HIGH:
            _write_field(schema_path, best)
            fields.append(MappedField(
                field=name, value=best.value, state="written", span=best.span,
                source_id=best.source_id, locator=best.locator, confidence=best.confidence,
                flagged=False,
            ))
        elif best.confidence >= CONFIDENCE_LOW:
            _write_field(schema_path, best)
            fields.append(MappedField(
                field=name, value=best.value, state="flagged", span=best.span,
                source_id=best.source_id, locator=best.locator, confidence=best.confidence,
                flagged=True,
            ))
        else:
            fields.append(MappedField(field=name, value=None, state="tbd"))

    return MapResult(fields=fields)
