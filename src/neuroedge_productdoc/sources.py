"""Extracts the five sections the product document requires from
agentforge.prd.md and project_objectives.md.

Matched by heading substring, not exact text, so PRD/objectives renumbering
(e.g. "## 5. Locked decisions" -> "## 6. Locked decisions") doesn't silently
break extraction. A heading that genuinely disappears raises ValueError naming
it, rather than emitting a doc with a missing or stale section (EP-09,
US-09-01 failure-case AC: "a regeneration run against a changed PRD updates
the document rather than silently emitting the previous version").
"""

from __future__ import annotations

import re
from pathlib import Path

# Strips markdown authoring notes (e.g. agentforge.prd.md's Implementation
# Phases section opens with a `<!-- STATUS: ... -->` comment for editors) so
# they don't leak into the rendered document as visible text.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->\n?", re.DOTALL)

# key -> (source file, heading substring to match, case-insensitive)
_SECTION_SOURCES: dict[str, tuple[str, str]] = {
    "problem_statement": ("prd", "Problem Statement"),
    "stage_graph": ("prd", "Implementation Phases"),
    "gate_model": ("objectives", "Locked decisions"),
    "traceability": ("objectives", "Traceability model"),
    "pm_surface": ("objectives", "Roles"),
}

REQUIRED_SECTIONS: tuple[str, ...] = tuple(_SECTION_SOURCES)


def _slice_section(markdown: str, heading_substring: str) -> str | None:
    """Return the body text under the `## `-level heading containing
    `heading_substring` (case-insensitive), up to the next `## `-level heading
    or end of file. `None` if no such heading exists.

    Only exact `## ` (two hashes) headings bound a section — a `### `
    sub-heading inside it is content, not a boundary.

    Raises ValueError if more than one `## `-level heading matches — matching
    by substring (rather than exact text) is deliberate so PRD/objectives
    renumbering doesn't break extraction (see module docstring), but an
    ambiguous match must not silently pick the first one and ship the wrong
    section.
    """
    lines = markdown.splitlines()
    needle = heading_substring.lower()
    matches = [i for i, line in enumerate(lines) if line.startswith("## ") and needle in line.lower()]
    if not matches:
        return None
    if len(matches) > 1:
        raise ValueError(
            f"heading {heading_substring!r} matches {len(matches)} different '## ' "
            f"headings — ambiguous, refusing to guess which one"
        )

    start = matches[0] + 1
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break

    return "\n".join(lines[start:end]).strip()


def extract_sections(prd_path: Path, objectives_path: Path) -> dict[str, str]:
    """Pull the five required sections from the PRD and objectives files.

    Raises ValueError naming the first missing or empty heading — never
    returns a partial or default-filled result.
    """
    # HTML comments are stripped from the *whole* file before heading
    # boundaries are located — not after slicing a section out. A comment
    # containing its own `## `-prefixed line (e.g. a commented-out draft
    # heading) would otherwise be mistaken for a real section boundary,
    # truncating the section, leaking a bare "<!--" past the now-out-of-
    # reach closing "-->", or tripping the ambiguous-match guard on dead
    # content.
    text_by_source = {
        "prd": _HTML_COMMENT_RE.sub("", Path(prd_path).read_text(encoding="utf-8")),
        "objectives": _HTML_COMMENT_RE.sub("", Path(objectives_path).read_text(encoding="utf-8")),
    }

    sections: dict[str, str] = {}
    for key, (source, heading_substring) in _SECTION_SOURCES.items():
        body = _slice_section(text_by_source[source], heading_substring)
        if body is None:
            raise ValueError(
                f"required heading {heading_substring!r} not found in {source} "
                f"(needed for product-doc section {key!r})"
            )
        if not body:
            raise ValueError(
                f"heading {heading_substring!r} found in {source} but has no content "
                f"before the next heading (needed for product-doc section {key!r})"
            )
        sections[key] = body

    return sections
