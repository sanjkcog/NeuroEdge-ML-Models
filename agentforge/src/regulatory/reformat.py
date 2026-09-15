"""reformat.py — the FR-04 reformatter use case; the single never-synthesize
enforcement point (ADR-0009, EP-01, US-01-04).

Fixed contract (this signature is stated verbatim in `agents/SOFTWARE/reformatter.md`
and string-matched against it by `test_reformatter_contract.py`):

    reformat(source_content, target_format_spec) -> {conformed_doc, gap_report, conformance_result}

`_emit_section` is the ONLY function in this module that appends to the rendered
document or the gap report — no other code path writes content. Its governing branch:

    if section['fillable'] is False or present is None:
        gaps.append(GAP_LINE...); conformed.append(_marked_slot(section)); return

always wins over the present-and-fillable branch. A `fillable:false` section is
gapped and its slot marked (never populated) regardless of whatever bytes happen to
sit in the source at that slot — this is what makes the adversarial case (present but
`fillable:false`, TC-01-04-04) still produce zero model-generated prose.

Reference-implementation note on `source_content`'s shape: this module treats
`source_content` as a mapping from a spec section's `id` to that section's raw content
— either a plain string, or a `{"text": ..., "trace_id": "<canonical-id>"}` dict
carrying an optional canonical FR/EP/US/TS/TC id for boundary id-map resolution
(FR-06). A production adapter parses a real customer document into this shape before
calling `reformat`; this function never invents content, it only looks up what it is
given. `target_format_spec` is expected to be an (already class-gated, if needed —
see `specval.required_sections_for_class`) mapping carrying at least `id` and
`required_sections` (a list of section dicts as described by the FR-02 meta-schema).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import id_map as _id_map

GAP_LINE = "REQUIRED by {spec} §{ref} — not present in source — human input needed"

# Reference default location for the per-project instance map (FR-06, OQ-5 TBD/
# non-blocking). This path will almost always be absent in practice — id_map.load
# degrades gracefully to a passthrough (canonical-id) resolution in that case, which
# is exactly the safe default for a reference implementation with no project wiring.
_DEFAULT_INSTANCE_MAP_PATH = Path("id-map.instance.json")


@dataclass(frozen=True)
class ReformatResult:
    """The three named outputs of the FR-04 contract."""

    conformed_doc: str
    gap_report: list[str]
    conformance_result: dict


def _find_in_source(section: Mapping[str, Any], source: Any) -> Any:
    """Look up a required section's content in the parsed source.

    Returns the section's raw entry (a string, or a `{"text", "trace_id"}` dict) if
    present, else None. Never fabricates a value — an absent key is genuinely absent.
    """
    if not isinstance(source, Mapping):
        return None
    return source.get(section["id"])


def _marked_slot(section: Mapping[str, Any]) -> str:
    """The ONLY content ever written for an absent-or-non-fillable section: a marker
    identifying what is missing, never generated prose describing what the content
    might have been.
    """
    title = section.get("title", section["id"])
    ref = section.get("spec_ref", "")
    return f"[[UNFILLED — {title} (§{ref})]]"


def _is_gap(section: Mapping[str, Any], source: Any) -> bool:
    """True iff this section must take the gap branch: non-fillable (regardless of
    source content) or genuinely absent from the source.
    """
    present = _find_in_source(section, source)
    return section["fillable"] is False or present is None


def _resolve_trace_id(trace_id: str) -> str:
    """Boundary-only id-map resolution (FR-06). Loads the conventional per-project
    instance map if one exists; degrades harmlessly to canonical passthrough
    otherwise. This is the ONLY place in this module `id_map` is consulted.
    """
    id_map_instance = _id_map.load(_DEFAULT_INSTANCE_MAP_PATH)
    return id_map_instance.resolve(trace_id)


def _structural_remap(section: Mapping[str, Any], present: Any) -> str:
    """Present-and-fillable path: wrap the source's OWN content with the target
    spec's label / numbering. Content is carried through verbatim — only
    presentation (label, section-number) is remapped, never invented.
    """
    if isinstance(present, Mapping):
        text = present.get("text", "")
        trace_id = present.get("trace_id")
    else:
        text = present
        trace_id = None

    title = section.get("title", section["id"])
    ref = section.get("spec_ref", "")
    label = f"§{ref} {title}".strip()
    if trace_id:
        resolved = _resolve_trace_id(trace_id)
        label = f"{label} [{resolved}]"
    return f"{label}\n{text}"


def _emit_section(
    section: Mapping[str, Any],
    source: Any,
    conformed: list[str],
    gaps: list[str],
    spec_id: str,
) -> None:
    """The single write path onto `conformed`/`gaps`. See module docstring."""
    present = _find_in_source(section, source)
    if section["fillable"] is False or present is None:
        gaps.append(GAP_LINE.format(spec=spec_id, ref=section.get("spec_ref", section["id"])))
        conformed.append(_marked_slot(section))  # slot marked, NEVER populated
        return
    conformed.append(_structural_remap(section, present))


def reformat(source_content: Any, target_format_spec: Mapping[str, Any]) -> ReformatResult:
    """FR-04 fixed contract. Pure orchestration: never mutates `source_content` or
    `target_format_spec`, never writes to disk, and returns a fresh `ReformatResult`
    every call.
    """
    spec_id = target_format_spec.get("id", "<unknown-spec>")
    sections = target_format_spec.get("required_sections", [])

    conformed: list[str] = []
    gaps: list[str] = []
    for section in sections:
        _emit_section(section, source_content, conformed, gaps, spec_id)

    gap_ids = [section["id"] for section in sections if _is_gap(section, source_content)]
    conformance_result = {
        "status": "gaps" if gap_ids else "present",
        "gaps": gap_ids,
    }

    return ReformatResult(
        conformed_doc="\n\n".join(conformed),
        gap_report=gaps,
        conformance_result=conformance_result,
    )
