"""specval.py — spec validation + class-gating for regulatory format specs (FR-02).

A regime instance (e.g. `skills/REGULATORY/IEC-62304/spec.json`) declares its own
`required_sections` and a `conformance_checklist`; the class-parameterization is a
pure data-driven filter (`required_for_classes`), never a per-class schema fork
(AC-02.4). `fillable` on every section and `section` on every checklist entry are
enforced as schema-level `required` fields (C-3) — omitting either is rejected here,
never silently defaulted to a permissive value.

Prefers the real `jsonschema` package (Draft 2020-12) when it is importable. This repo
does not currently carry `jsonschema` as a declared dev dependency (checked against
`pyproject.toml`), so a minimal, dependency-free hand-validator covering exactly the
same required-field invariants is used as a fallback — this keeps the regulatory suite
runnable without adding a new dependency, while still enforcing every invariant this
module is responsible for (AC-02.1..04).
"""

from __future__ import annotations

import json
from pathlib import Path

try:  # pragma: no cover - exercised whichever branch is actually installed
    from jsonschema import Draft202012Validator

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    Draft202012Validator = None  # type: ignore[assignment]
    _HAS_JSONSCHEMA = False

REGULATORY_ROOT = Path(__file__).resolve().parents[3] / "skills" / "REGULATORY"
_DEFAULT_SCHEMA_PATH = REGULATORY_ROOT / "_schema" / "format-spec.schema.json"

_REGIME_REQUIRED = (
    "id",
    "edition",
    "authority",
    "classification_axis",
    "required_sections",
    "conformance_checklist",
)
_SECTION_REQUIRED = (
    "id",
    "title",
    "spec_ref",
    "required_for_classes",
    "field_constraints",
    "cross_references",
    "fillable",
)
_CHECKLIST_REQUIRED = ("rule", "section", "condition", "severity")


class SpecValidationError(Exception):
    """A spec (or the meta-schema itself) failed validation.

    The message always names the first offending field so a failure is
    diagnosable without re-deriving which key was the problem.
    """


def _resolve_schema_path(schema_path: str | Path | None) -> Path:
    return Path(schema_path) if schema_path is not None else _DEFAULT_SCHEMA_PATH


def _load_schema(schema_path: str | Path | None) -> dict:
    path = _resolve_schema_path(schema_path)
    return json.loads(path.read_text(encoding="utf-8"))


def check_schema(schema_path: str | Path | None = None) -> None:
    """Assert the format-spec meta-schema itself is self-consistent.

    Raises `SpecValidationError` if not; returns None (exit-0 semantics) otherwise.
    """
    schema = _load_schema(schema_path)

    if _HAS_JSONSCHEMA:
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # jsonschema.exceptions.SchemaError
            raise SpecValidationError(f"INVALID format-spec.schema.json: {exc}") from exc
        return

    # Minimal hand-validator fallback: structural sanity check for the exact
    # invariants this schema exists to guarantee (C-3), without a jsonschema
    # dependency.
    if schema.get("type") != "object":
        raise SpecValidationError(
            "INVALID format-spec.schema.json: field 'type' must be 'object' at the top level"
        )
    section_required = schema.get("$defs", {}).get("section", {}).get("required", [])
    if "fillable" not in section_required:
        raise SpecValidationError(
            "INVALID format-spec.schema.json: field 'fillable' missing from "
            "$defs.section.required"
        )
    checklist_required = schema.get("$defs", {}).get("checklist_entry", {}).get("required", [])
    if "section" not in checklist_required:
        raise SpecValidationError(
            "INVALID format-spec.schema.json: field 'section' missing from "
            "$defs.checklist_entry.required"
        )


def validate_spec(spec: dict, *, schema_path: str | Path | None = None) -> None:
    """Validate `spec` against the format-spec meta-schema.

    Raises `SpecValidationError` naming the first offending field on failure;
    returns None on success.
    """
    if not isinstance(spec, dict):
        raise SpecValidationError("INVALID spec: top-level value is not an object")

    schema = _load_schema(schema_path)

    if _HAS_JSONSCHEMA:
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(spec), key=lambda e: list(e.absolute_path))
        if errors:
            first = errors[0]
            field = ".".join(str(p) for p in first.absolute_path) or "<top-level>"
            raise SpecValidationError(f"INVALID spec: field {field!r}: {first.message}")
        return

    # Minimal hand-validator fallback — same required-field invariants.
    for key in _REGIME_REQUIRED:
        if key not in spec:
            raise SpecValidationError(f"INVALID spec: missing required field {key!r}")

    sections = spec["required_sections"]
    if not isinstance(sections, list):
        raise SpecValidationError("INVALID spec: field 'required_sections' must be an array")
    for i, section in enumerate(sections):
        if not isinstance(section, dict):
            raise SpecValidationError(f"INVALID spec: required_sections[{i}] must be an object")
        for key in _SECTION_REQUIRED:
            if key not in section:
                raise SpecValidationError(
                    f"INVALID spec: required_sections[{i}] missing required field {key!r}"
                )
        if not isinstance(section["fillable"], bool):
            raise SpecValidationError(
                f"INVALID spec: required_sections[{i}] field 'fillable' must be a boolean"
            )

    checklist = spec["conformance_checklist"]
    if not isinstance(checklist, list):
        raise SpecValidationError("INVALID spec: field 'conformance_checklist' must be an array")
    for i, entry in enumerate(checklist):
        if not isinstance(entry, dict):
            raise SpecValidationError(f"INVALID spec: conformance_checklist[{i}] must be an object")
        for key in _CHECKLIST_REQUIRED:
            if key not in entry:
                raise SpecValidationError(
                    f"INVALID spec: conformance_checklist[{i}] missing required field {key!r}"
                )


def load_spec(regime: str, *, root: str | Path = REGULATORY_ROOT) -> dict:
    """Read+validate `skills/REGULATORY/<regime>/spec.json`.

    An unknown regime (no `spec.json` under `root/<regime>/`) raises
    `SpecValidationError` enumerating the regime directories that ARE available under
    `root`, so a typo is diagnosable without re-reading this module's source.
    """
    root = Path(root)
    spec_path = root / regime / "spec.json"
    if not spec_path.is_file():
        available = (
            sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith("_"))
            if root.is_dir()
            else []
        )
        raise SpecValidationError(
            f"UNKNOWN regime {regime!r}: no spec.json found under {root}; "
            f"available regimes: {available}"
        )
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    validate_spec(spec)
    return spec


def required_sections_for_class(spec: dict, active_class: str) -> list[dict]:
    """Pure filter: a section is required iff `active_class` is in its
    `required_for_classes` list. Never mutates `spec`.
    """
    return [
        section
        for section in spec.get("required_sections", [])
        if active_class in section.get("required_for_classes", [])
    ]
