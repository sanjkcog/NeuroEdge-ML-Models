"""Renders extracted PRD/objectives sections into a self-contained HTML page.

The `<style>` block (_STYLE) is copied verbatim from
docs/guides/how_to_run_agentforge.html so the generated document is visually
indistinguishable from the existing hand-authored guides (EP-09, US-09-01 AC:
"matching the existing docs/guides/*.html precedent"). Zero dependencies —
inline CSS only, no `<link>`, no remote `<script src="http...">`
(skills/SUPPORTING-TOOLS/design/frontend-slides.md's zero-dependency rule).

Markdown support is intentionally narrow: paragraphs, `### ` sub-headings,
pipe tables, `- `/`* ` bullet lists (with wrapped continuation lines), fenced
``` code blocks, inline `` `code` ``, `**bold**`, and `[text](url)` links —
exactly what the five source sections use, not a general-purpose converter.
"""

from __future__ import annotations

import html
import re

from .sources import REQUIRED_SECTIONS

# SOURCE: docs/guides/how_to_run_agentforge.html:3-126 (copied verbatim).
_STYLE = """
:root {
  --ink: #17212f;
  --muted: #607086;
  --line: #d8e1ec;
  --soft: #f4f7fb;
  --panel: #ffffff;
  --teal: #007c89;
  --green: #2d7d46;
  --amber: #a56300;
  --blue: #2a5d9f;
  --plum: #704a7f;
  --red: #a33b3b;
  --dark: #121e2d;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  color: var(--ink);
  background: #ffffff;
  font-family: "Segoe UI", Arial, sans-serif;
  line-height: 1.55;
  font-size: 16px;
}
a { color: var(--blue); text-decoration: none; font-weight: 750; }
a:hover { text-decoration: underline; }
code {
  padding: 0.12rem 0.34rem;
  color: #0f1b2a;
  background: #edf3f8;
  border: 1px solid #d7e2ec;
  font-family: Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 0.92em;
}
pre {
  overflow-x: auto;
  padding: 1rem 1.2rem;
  color: #eaf2fb;
  background: var(--dark);
  border-radius: 8px;
  font-family: Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 0.88rem;
  line-height: 1.5;
}
pre code { padding: 0; color: inherit; background: none; border: none; }
.hero {
  padding: 4rem 6vw 3rem;
  color: #ffffff;
  background: linear-gradient(120deg, #121e2d, #1c3049);
}
.hero-inner, .wrap { width: 100%; max-width: 1100px; margin: 0 auto; }
.eyebrow {
  display: inline-flex;
  align-items: center;
  padding: 0.35rem 0.62rem;
  color: #ffffff;
  border: 1px solid rgba(255, 255, 255, 0.42);
  background: rgba(255, 255, 255, 0.08);
  font-size: 0.78rem;
  font-weight: 850;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
h1 {
  max-width: 900px;
  margin: 1rem 0 0;
  font-size: clamp(2rem, 4.4vw, 3.2rem);
  line-height: 1.08;
  font-weight: 750;
}
.hero p { max-width: 780px; margin: 1.1rem 0 0; color: #dbe6f4; font-size: 1.08rem; }
main { padding: 3rem 6vw 5rem; }
section { max-width: 1100px; margin: 0 auto 3.4rem; }
h2 {
  margin: 0 0 1rem;
  padding-bottom: 0.6rem;
  border-bottom: 2px solid var(--line);
  font-size: clamp(1.5rem, 2.6vw, 2rem);
  font-weight: 740;
}
h3 { margin: 1.6rem 0 0.6rem; font-size: 1.15rem; font-weight: 740; }
p { max-width: 78ch; }
table { width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.94rem; }
th, td { padding: 0.55rem 0.8rem; text-align: left; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.03em; }
tr:last-child td { border-bottom: none; }
.callout {
  padding: 1rem 1.2rem;
  margin: 1.2rem 0;
  background: var(--soft);
  border-left: 4px solid var(--teal);
  border-radius: 0 6px 6px 0;
}
.callout.warn { border-left-color: var(--amber); }
.callout.gap { border-left-color: var(--red); }
.badge {
  display: inline-block;
  padding: 0.15rem 0.5rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 800;
  text-transform: uppercase;
}
.badge.hard { color: #fff; background: var(--red); }
.badge.soft { color: #fff; background: var(--amber); }
.badge.none { color: #fff; background: var(--muted); }
.checklist { list-style: none; margin: 0.6rem 0; padding: 0; }
.checklist li { margin: 0.4rem 0; padding-left: 1.6rem; position: relative; }
.checklist li::before {
  content: "☐";
  position: absolute; left: 0; color: var(--muted);
}
footer { padding: 2rem 6vw 3rem; color: var(--muted); font-size: 0.86rem; border-top: 1px solid var(--line); }
@media (prefers-color-scheme: dark) {
  body { color: #e7edf6; background: #0d1520; }
  code { color: #dce7f4; background: #16202e; border-color: #223046; }
  pre { background: #060b12; }
  h2 { border-bottom-color: #223046; }
  th, td { border-bottom-color: #223046; }
  .callout { background: #16202e; }
  table { color: #cfdaeb; }
  th { color: #93a3b8; }
  footer { border-top-color: #223046; color: #93a3b8; }
}
""".strip()

_SECTION_TITLES: dict[str, str] = {
    "problem_statement": "The Problem",
    "stage_graph": "The Stage Graph",
    "gate_model": "The Gate Model",
    "traceability": "Traceability",
    "pm_surface": "The PM Surface",
}

# One alternation, matched left-to-right in a single pass — each match consumes
# its span so a later alternative (e.g. bold) never re-scans text a code span
# already claimed (previously `` `**x**` `` -> <code><strong>x</strong></code>,
# a nested-markup bug a sequential chain of independent .sub() calls can't avoid).
_INLINE_RE = re.compile(
    r"`(?P<code>[^`]+)`"
    r"|\*\*(?P<bold>[^*]+)\*\*"
    r"|\[(?P<link_text>[^\]]+)\]\((?P<link_url>[^)]+)\)"
)

# Only http(s) and scheme-less (relative/anchor) URLs are linkified. Blocks
# javascript:/data:/vbscript: etc. from PRD/objectives prose becoming a live
# click-to-execute link — html.escape() alone neutralizes markup but not a
# dangerous *scheme*.
_URL_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):")
# Mirrors the WHATWG URL Standard's own two-step trim, since that's what a
# real browser applies before determining a URL's scheme — a naive check
# against the raw string is bypassable by exactly this kind of obfuscation
# (confirmed: " javascript:...", "java\tscript:...", and "\x01javascript:..."
# each previously slipped an earlier, narrower version of this check while a
# browser still executed them as javascript:).
# 1. ASCII tab (0x09) and newline (0x0A, 0x0D) are removed from anywhere.
_URL_TAB_NEWLINE_RE = re.compile(r"[\t\n\r]")
# 2. Leading/trailing C0 controls (0x00-0x1F) *and* space (0x20) are trimmed.
_URL_LEADING_TRAILING_C0_OR_SPACE_RE = re.compile(r"^[\x00-\x20]+|[\x00-\x20]+$")


def _safe_href(url: str) -> str:
    normalized = _URL_TAB_NEWLINE_RE.sub("", url)
    normalized = _URL_LEADING_TRAILING_C0_OR_SPACE_RE.sub("", normalized)
    match = _URL_SCHEME_RE.match(normalized)
    if match and match.group(1).lower() not in ("http", "https"):
        return "#"
    return url


def _inline_sub(match: re.Match[str]) -> str:
    if match.group("code") is not None:
        return f"<code>{match.group('code')}</code>"
    if match.group("bold") is not None:
        return f"<strong>{match.group('bold')}</strong>"
    href = _safe_href(match.group("link_url"))
    return f'<a href="{href}">{match.group("link_text")}</a>'


def _inline_markdown_to_html(text: str) -> str:
    """`code`, **bold**, [text](url) -> HTML, applied to already-escaped text
    so PRD/objectives prose can never inject markup of its own."""
    return _INLINE_RE.sub(_inline_sub, html.escape(text))


def _split_table_row(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [cell.strip() for cell in inner.split("|")]


def _is_separator_row(cells: list[str]) -> bool:
    # A row of ALL-empty cells must not count as a separator: `all()` over an
    # empty iterable is vacuously True, which previously misidentified a
    # genuine blank data row (e.g. "|   |   |") as the header separator and
    # silently dropped it from the rendered table.
    non_empty = [cell for cell in cells if cell]
    return bool(non_empty) and all(re.fullmatch(r":?-{2,}:?", cell) for cell in non_empty)


def _render_table(table_lines: list[str]) -> str:
    rows = [_split_table_row(line) for line in table_lines]
    if len(rows) >= 2 and _is_separator_row(rows[1]):
        header, body_rows = rows[0], rows[2:]
    else:
        header, body_rows = rows[0], rows[1:]

    thead = "".join(f"<th>{_inline_markdown_to_html(c)}</th>" for c in header)
    tbody = "".join(
        "<tr>" + "".join(f"<td>{_inline_markdown_to_html(c)}</td>" for c in row) + "</tr>"
        for row in body_rows
    )
    return f"<table><tr>{thead}</tr>{tbody}</table>"


_LIST_ITEM_RE = re.compile(r"^[-*]\s+(.*)")
_BLOCK_START_RE = re.compile(r"^(```|### |\|)")
# A homogeneous run of the same character only (---, ***, or ___) — real
# markdown HR syntax, not any 3+-character mix drawn from the set.
_HR_RE = re.compile(r"-{3,}|\*{3,}|_{3,}")


def _consume_code_fence(lines: list[str], i: int) -> tuple[str, int]:
    """`lines[i]` is an opening ``` fence. Return the rendered <pre><code>
    block and the index to resume at."""
    stripped = lines[i].strip()
    after_open = stripped[3:]
    same_line_close = after_open.find("```")
    if same_line_close != -1:
        # Both fences on one line (e.g. "```echo hello```") — a single-line
        # code span, not a block. Handled as its own case rather than
        # falling into the multi-line scan below: that scan starts at the
        # *next* line, so it would both discard this line's own content and,
        # absent a later standalone closing fence, keep consuming every
        # subsequent line (including unrelated paragraphs) as bogus code
        # content until end-of-input.
        code_text = html.escape(after_open[:same_line_close])
        return f"<pre><code>{code_text}</code></pre>", i + 1

    code_lines: list[str] = []
    i += 1
    while i < len(lines) and not lines[i].strip().startswith("```"):
        code_lines.append(lines[i])
        i += 1
    # Advance past the closing fence if one was found; if not (an
    # unterminated fence), stop at end-of-lines rather than looping forever —
    # everything captured up to here still renders as a code block instead
    # of being silently dropped.
    if i < len(lines):
        i += 1
    code_text = html.escape("\n".join(code_lines))
    return f"<pre><code>{code_text}</code></pre>", i


def _consume_table(lines: list[str], i: int) -> tuple[str, int]:
    """`lines[i]` starts a pipe-table row. Return the rendered <table> and
    the index to resume at."""
    table_lines = []
    while i < len(lines) and lines[i].strip().startswith("|"):
        table_lines.append(lines[i].strip())
        i += 1
    return _render_table(table_lines), i


def _consume_list(lines: list[str], i: int) -> tuple[str, int]:
    """`lines[i]` starts a `- `/`* ` list item. Return the rendered <ul> and
    the index to resume at. A line that isn't a new item, a blank line, a
    horizontal rule, or the start of another block type is treated as a
    wrapped continuation of the current item."""
    items = [_LIST_ITEM_RE.match(lines[i].strip()).group(1)]
    i += 1
    while i < len(lines):
        next_stripped = lines[i].strip()
        if not next_stripped or _HR_RE.fullmatch(next_stripped):
            break
        next_list_match = _LIST_ITEM_RE.match(next_stripped)
        if next_list_match:
            items.append(next_list_match.group(1))
        elif not _BLOCK_START_RE.match(next_stripped):
            items[-1] = f"{items[-1]} {next_stripped}"
        else:
            break
        i += 1
    list_html = "".join(f"<li>{_inline_markdown_to_html(item)}</li>" for item in items)
    return f"<ul>{list_html}</ul>", i


def markdown_block_to_html(markdown_text: str) -> str:
    """Convert paragraphs, `### ` sub-headings, pipe tables, `- `/`* ` bullet
    lists, and fenced ``` code blocks to HTML. A bare `---`/`***`/`___`
    horizontal-rule line is dropped — meaningless as literal text once
    rendered."""
    lines = markdown_text.splitlines()
    blocks: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{_inline_markdown_to_html(' '.join(paragraph))}</p>")
            paragraph.clear()

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            flush_paragraph()
            i += 1
        elif _HR_RE.fullmatch(stripped):
            flush_paragraph()
            i += 1
        elif stripped.startswith("```"):
            flush_paragraph()
            block, i = _consume_code_fence(lines, i)
            blocks.append(block)
        elif stripped.startswith("### "):
            flush_paragraph()
            blocks.append(f"<h3>{_inline_markdown_to_html(stripped[4:])}</h3>")
            i += 1
        elif stripped.startswith("|"):
            flush_paragraph()
            block, i = _consume_table(lines, i)
            blocks.append(block)
        elif _LIST_ITEM_RE.match(stripped):
            flush_paragraph()
            block, i = _consume_list(lines, i)
            blocks.append(block)
        else:
            paragraph.append(stripped)
            i += 1

    flush_paragraph()
    return "\n".join(blocks)


def render_html(sections: dict[str, str]) -> str:
    """Render `sections` (keyed by REQUIRED_SECTIONS) into a self-contained
    HTML page. A pure function of `sections` — no caching, so regenerating
    against changed input always reflects the change (US-09-01 failure-case
    AC)."""
    body_sections = "\n".join(
        f'<section id="{key}"><h2>{html.escape(_SECTION_TITLES[key])}</h2>\n'
        f"{markdown_block_to_html(sections[key])}\n</section>"
        for key in REQUIRED_SECTIONS
    )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>What is AgentForge? | NeuroEdge AgentForge</title><style>
{_STYLE}
</style></head>
<body>

<div class="hero"><div class="hero-inner">
  <span class="eyebrow">AgentForge · Product Overview</span>
  <h1>What is AgentForge?</h1>
  <p>Generated from <code>agentforge.prd.md</code> and
  <code>project_objectives.md</code> by <code>/product-doc</code> — regenerate
  after either changes, do not hand-edit this file.</p>
</div></div>

<main>
{body_sections}
</main>

<footer>NeuroEdge AgentForge · Standalone reference document, no external requests. Generated by <code>/product-doc</code>.</footer>
</body></html>
"""
