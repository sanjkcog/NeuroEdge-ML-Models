---
name: cognizant-ppt
description: Generate brand-compliant Cognizant PowerPoint decks from a structured content brief. Self-contained — uses python-pptx and builds slides from scratch using the brand palette extracted from a real Cognizant deck. No external template assets required. Use for one-pagers, sales decks, customer-facing presentations, internal briefings, and competitive analyses.
origin: NeuroEdge AgentForge
---

# Cognizant PPT

Produce a brand-compliant Cognizant PowerPoint deck (.pptx) from a structured content brief. The output uses the exact color palette, typography, and layout patterns extracted from the canonical Cognizant template (e.g. "Physical AI Competitive Landscape — Qualcomm vs. Nvidia", May 2026 — the brand reference for this skill). Self-contained: no template .pptx asset is required at runtime.

## When to Activate

- User asks to create a presentation, deck, slides, one-pager, or PPT
- User invokes `/cognizant-ppt`
- Any agent (e.g. `doc-updater`) needs to materialize a deck from a PRD, research report, or content brief
- Customer-facing or internal Cognizant slide deck is requested
- A markdown one-pager needs a slide-deck companion

## Hard Bans (Never Violate)

- **Never invent or guess Cognizant brand colors.** Use only the constants in the Brand Constants section below.
- **Never use non-Arial fonts.** Arial only; if unavailable on the runtime, fall back to "Helvetica" then "sans-serif" — do not introduce serifs.
- **Never use clip-art, emoji icons, or stock cartoon visuals.** Use solid shapes filled with brand colors only.
- **Never produce slides with > 5 bullets per column or > 3 columns per slide.** Split into multiple slides.
- **Never lead a sales slide with productivity %s, vendor logos, or generic "agentic AI" framing.** Lead with the outcome / category claim.
- **Never put placeholder text in the final deliverable** (no "Lorem ipsum", no "TODO", no "[INSERT TITLE]"). If a field is missing in the spec, ask the user — do not auto-fill.

## Brand Constants (Extracted From Canonical Cognizant Deck)

### Slide Canvas
- **Size:** 13.333" × 7.5" (16:9 widescreen, native PowerPoint default)
- **EMU:** 12,192,000 × 6,858,000

### Color Palette (use ONLY these)

| Token | Hex | RGB | Usage |
|-------|-----|-----|-------|
| `COG_NAVY` | `#000048` | (0, 0, 72) | Cover background, table header rows, slide titles on white bg |
| `COG_NAVY_DARK` | `#000033` | (0, 0, 51) | Cover bg accent dark band |
| `COG_BLUE_MID` | `#2D78C3` | (45, 120, 195) | Phase 2 banner, secondary headings, accent rectangles |
| `COG_TEAL` | `#03C6CB` | (3, 198, 203) | Phase 3 banner, accent lines, bullet dots, highlight callouts |
| `COG_BLUE_LIGHT` | `#92F6F9` | (146, 246, 249) | Cover descriptor text on dark bg, light highlight |
| `COG_BLUE_CYAN` | `#B3D9F2` | (179, 217, 242) | Cover subtitle accent text |
| `COG_WHITE` | `#FFFFFF` | (255, 255, 255) | Text on dark bg, icon fills |
| `COG_BODY` | `#404040` | (64, 64, 64) | Body text on white bg |
| `COG_GRAY_DARK` | `#52565A` | (82, 86, 90) | Captions, sub-headers, muted text |
| `COG_GRAY_MID` | `#96999B` | (150, 153, 155) | Borders, dividers |
| `COG_GRAY_LIGHT` | `#F5F7FB` | (245, 247, 251) | Zebra-stripe alternate row in tables |
| `COG_RED` | `#C72030` | (199, 32, 48) | "HIGH" risk callout text |
| `COG_AMBER` | `#D4891A` | (212, 137, 26) | "MEDIUM" risk callout text |
| `COG_GREEN` | `#1E8A4A` | (30, 138, 74) | Positive / on-track status |

### Typography

| Role | Font | Size | Weight | Color |
|------|------|------|--------|-------|
| Cover title (line 1) | Arial | 40pt | Bold | White |
| Cover subtitle (line 2) | Arial | 24pt | Regular | White |
| Cover descriptor | Arial | 18pt | Regular | `#92F6F9` (cyan) |
| Cover date | Arial | 14pt | Regular | `#B3D9F2` (light blue) |
| Slide title (white bg) | Arial | 28pt | Bold | `#000048` (navy) |
| Sub-header (slide body) | Arial | 14pt | Bold | `#000048` (navy) |
| Body text (white bg) | Arial | 11pt | Regular | `#404040` (dark gray) |
| Table header row | Arial | 11pt | Bold | White on `#000048` bg |
| Table body row | Arial | 10pt | Regular | `#404040` on white / `#F5F7FB` (zebra) |
| Risk callout (HIGH/MEDIUM) | Arial | 10pt | Bold | `#C72030` / `#D4891A` |
| Footer left (page + © text) | Arial | 8pt | Regular | `#52565A` (gray) on white |
| Footer text on dark bg | Arial | 8pt | Regular | White |

### Layout Zones (inches, 13.333 × 7.5 canvas)

#### Cover slide
- Solid full-bleed fill `#000048` (navy)
- Cognizant white logo OR text wordmark: top-left at `(0.5, 0.4)` size `(1.8, 0.4)`
- Title block: x=0.6, y=2.4, w=8.5, h=1.0 (40pt Bold White)
- Subtitle: x=0.6, y=3.4, w=8.5, h=0.6 (24pt Regular White)
- Descriptor: x=0.6, y=4.3, w=8.5, h=1.0 (18pt Cyan)
- Date: x=0.6, y=5.8, w=4.0, h=0.4 (14pt Light Blue)
- Right 40% of slide may carry an accent shape — a single dark blue rotated rectangle (45° tilt) suggesting the prism artwork without requiring image assets
- Footer left: x=0.5, y=7.15, w=4.0, h=0.25 — "1 © 2025–2027 Cognizant | Private" 8pt White

#### Content slide (white bg)
- White full-slide background
- Slide title: x=0.5, y=0.35, w=12.3, h=0.6 — 28pt Bold Navy
- Content area: x=0.5, y=1.2, w=12.3, h=5.7 — varies by slide type
- Footer left: x=0.5, y=7.15, w=6.0, h=0.25 — "<page> © 2025–2027 Cognizant | Private" 8pt Gray
- Footer right: Cognizant logo OR text wordmark at x=11.8, y=7.1, w=1.5, h=0.3

#### Two-column slide
- Each column: w=6.0, gap=0.3 between, centered on canvas (left starts at 0.5)
- Optional vertical divider: thin gray rectangle at x=6.55, y=1.3, w=0.02, h=5.5
- Column heading: 16pt Bold Navy (or Mid-Blue for emphasis)
- Bullets: 11pt Body, max 5 per column

#### Three-column slide
- Each column: w=4.0, gap=0.15, centered
- Optional phase color band at top of each column: solid rectangle 0.5" tall, fill = `#000048` (col 1), `#2D78C3` (col 2), `#03C6CB` (col 3)
- Column content below band starts at y=1.85

#### Table slide
- Header row: fill `#000048`, white text, 11pt Bold
- Body rows: alternate fills white and `#F5F7FB`
- Row height: ~0.5" per row (auto-fit if content longer)
- Column widths: distribute evenly OR use ratios from spec (e.g. [3.5, 3.5, 3.5, 2.5])

## Slide Type Catalog

| Type | When to use | Layout |
|------|-------------|--------|
| `cover` | First slide, title block | Solid navy bg + title + subtitle + descriptor + date + footer |
| `closing` | Last slide, brand wrap-up | Solid navy bg, optional "Thank You" text, footer only |
| `content_text` | General single-column with bullets | White bg + title + bullet list |
| `two_column` | Comparison, before/after, side-by-side | White bg + title + 2 columns each with heading + bullets |
| `three_column` | Three KPIs, three phases, three pillars | White bg + title + 3 columns, optional phase color bands |
| `table` | Tabular comparison, capability matrix | White bg + title + table with navy header + zebra rows |
| `roadmap` | Three-phase timeline with colored headers | Like `three_column` but with explicit phase headers Phase 1 navy / Phase 2 blue / Phase 3 teal |
| `sub_sections` | Numbered sub-headers + body (per slides 4, 7, 8 of reference deck) | White bg + title + N (heading, body) pairs stacked vertically |

## Deck Spec Schema

Agents and commands invoke this skill by producing a JSON-like Python dict matching this schema:

```python
deck_spec = {
    "meta": {
        "title": "Physical AI Competitive Landscape",       # required, cover line 1
        "subtitle": "Qualcomm vs. Nvidia",                  # optional, cover line 2
        "descriptor": "Strategic Gap Analysis & Cognizant Partnership Pathway",  # optional
        "date": "May 2026",                                 # optional
        "classification": "© 2025–2027 Cognizant | Private", # optional, footer
        "logo_path": None,                                  # optional .png path; falls back to text wordmark
    },
    "slides": [
        {
            "type": "cover",
            # cover slide reuses meta automatically
        },
        {
            "type": "two_column",
            "title": "Two Distinct Go-to-Market Models Define the Competitive Dynamic",
            "left":  {"heading": "Qualcomm — Silicon-First Platform",
                       "bullets": ["Core proposition: ...", "Model: ...", ...]},
            "right": {"heading": "Nvidia — Full-Stack AI Operating System",
                       "bullets": ["Core proposition: ...", "Model: ...", ...]},
        },
        {
            "type": "table",
            "title": "Physical AI Platform Capability Comparison: Qualcomm vs. Nvidia",
            "headers": ["Capability", "Qualcomm", "Nvidia", "Assessment"],
            "rows": [
                ["Edge AI Processor", "Dragonwing IQ10 — ...", "Jetson AGX Thor — ...", "Qualcomm leads on power-per-watt; ..."],
                # ...
            ],
            "col_widths": [2.8, 3.5, 3.5, 3.5],  # optional, defaults to even
        },
        {
            "type": "sub_sections",
            "title": "Nvidia Has Built Four Interlocking Moats That Qualcomm Must Strategically Address",
            "sections": [
                {"heading": "1. Software Gravity — CUDA / Isaac Ecosystem", "body": "CUDA holds a 17+ year moat..."},
                {"heading": "2. Foundation Model Leadership", "body": "GR00T N1.7..."},
                # ...
            ],
            "footnote": "Sources: Kavout Research (2025); Nvidia GTC/CES (2025–2026); SiliconAngle (2025)",  # optional
        },
        {
            "type": "roadmap",
            "title": "Recommended Roadmap: Three Phases to Competitive Parity",
            "phases": [
                {"name": "Phase 1", "duration": "0–6 Months", "color": "navy",
                  "sections": [
                      {"heading": "Establish Partnership Framework", "body": "Sign joint GTM agreement..."},
                      {"heading": "Build Reference Architectures", "body": "Develop 2–3 validated solution blueprints..."},
                  ]},
                {"name": "Phase 2", "duration": "6–18 Months", "color": "blue",
                  "sections": [ ... ]},
                {"name": "Phase 3", "duration": "18–36 Months", "color": "teal",
                  "sections": [ ... ]},
            ],
        },
        {
            "type": "closing",
            # closing slide auto-built from brand
        },
    ],
}
```

## Python Implementation Pattern

When this skill is activated, generate and run a Python script using `python-pptx` that:
1. Checks `python-pptx` is installed; if not, runs `pip install python-pptx` first
2. Creates a Presentation, sets canvas to 13.333"×7.5"
3. For each slide in `deck_spec["slides"]`, calls the matching layout function (cover, two_column, table, sub_sections, roadmap, closing)
4. Uses ONLY the Brand Constants colors above
5. Saves to the path specified by the caller, defaults to `docs/marketing/<topic-slug>-<date>.pptx` in the calling project

Reference implementation pattern (copy-adapt; do NOT invent new colors or fonts):

```python
import subprocess, sys, os, datetime
try:
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-pptx", "--quiet"])
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

# === Brand constants (DO NOT modify) ===
COG_NAVY       = RGBColor(0x00, 0x00, 0x48)
COG_NAVY_DARK  = RGBColor(0x00, 0x00, 0x33)
COG_BLUE_MID   = RGBColor(0x2D, 0x78, 0xC3)
COG_TEAL       = RGBColor(0x03, 0xC6, 0xCB)
COG_BLUE_LIGHT = RGBColor(0x92, 0xF6, 0xF9)
COG_BLUE_CYAN  = RGBColor(0xB3, 0xD9, 0xF2)
COG_WHITE      = RGBColor(0xFF, 0xFF, 0xFF)
COG_BODY       = RGBColor(0x40, 0x40, 0x40)
COG_GRAY_DARK  = RGBColor(0x52, 0x56, 0x5A)
COG_GRAY_MID   = RGBColor(0x96, 0x99, 0x9B)
COG_GRAY_LIGHT = RGBColor(0xF5, 0xF7, 0xFB)
COG_RED        = RGBColor(0xC7, 0x20, 0x30)
COG_AMBER      = RGBColor(0xD4, 0x89, 0x1A)
COG_GREEN      = RGBColor(0x1E, 0x8A, 0x4A)

FONT = "Arial"
CANVAS_W, CANVAS_H = Inches(13.333), Inches(7.5)

def new_presentation():
    prs = Presentation()
    prs.slide_width = CANVAS_W
    prs.slide_height = CANVAS_H
    return prs

def add_solid_bg(slide, color):
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, CANVAS_W, CANVAS_H)
    bg.fill.solid(); bg.fill.fore_color.rgb = color
    bg.line.fill.background()
    return bg

def add_text(slide, x, y, w, h, text, *, size=11, bold=False, color=COG_BODY,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font=FONT):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]; p.alignment = align
    r = p.add_run(); r.text = text
    r.font.name = font; r.font.size = Pt(size); r.font.bold = bold
    r.font.color.rgb = color
    return tb

def add_footer(slide, page_num, classification, on_dark=False):
    color = COG_WHITE if on_dark else COG_GRAY_DARK
    add_text(slide, 0.5, 7.15, 6.0, 0.25,
             f"{page_num}   {classification}", size=8, color=color)
    # Logo wordmark at bottom-right (text fallback)
    if not on_dark:
        add_text(slide, 11.5, 7.10, 1.8, 0.3, "cognizant",
                 size=11, bold=True, color=COG_NAVY, align=PP_ALIGN.RIGHT)

def add_cover_slide(prs, meta, page_num=1):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank
    add_solid_bg(slide, COG_NAVY)
    # Decorative tilted rectangle on right 40% (suggests prism artwork)
    deco = slide.shapes.add_shape(MSO_SHAPE.PARALLELOGRAM,
                                   Inches(7.5), Inches(-1.0),
                                   Inches(8.0), Inches(10.0))
    deco.fill.solid(); deco.fill.fore_color.rgb = COG_BLUE_MID
    deco.line.fill.background()
    deco.rotation = 15
    # Cognizant text wordmark top-left
    add_text(slide, 0.5, 0.4, 2.5, 0.5, "cognizant",
             size=18, bold=True, color=COG_WHITE)
    # Title block
    add_text(slide, 0.6, 2.4, 8.5, 1.0, meta["title"],
             size=40, bold=True, color=COG_WHITE)
    if meta.get("subtitle"):
        add_text(slide, 0.6, 3.4, 8.5, 0.6, meta["subtitle"],
                 size=24, color=COG_WHITE)
    if meta.get("descriptor"):
        add_text(slide, 0.6, 4.3, 8.5, 1.0, meta["descriptor"],
                 size=18, color=COG_BLUE_LIGHT)
    if meta.get("date"):
        add_text(slide, 0.6, 5.8, 4.0, 0.4, meta["date"],
                 size=14, color=COG_BLUE_CYAN)
    add_footer(slide, page_num,
               meta.get("classification", "© 2025–2027 Cognizant | Private"),
               on_dark=True)
    return slide

def add_content_title(slide, title):
    add_text(slide, 0.5, 0.35, 12.3, 0.7, title,
             size=28, bold=True, color=COG_NAVY)

def add_two_column_slide(prs, meta, spec, page_num):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_content_title(slide, spec["title"])
    for i, (key, x_off) in enumerate([("left", 0.5), ("right", 6.85)]):
        col = spec[key]
        add_text(slide, x_off, 1.3, 6.0, 0.5, col["heading"],
                 size=16, bold=True, color=COG_NAVY)
        body = "\n".join(f"•  {b}" for b in col["bullets"])
        add_text(slide, x_off, 1.95, 6.0, 5.0, body, size=11, color=COG_BODY)
    # Vertical divider
    div = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                  Inches(6.55), Inches(1.3),
                                  Emu(20000), Inches(5.5))
    div.fill.solid(); div.fill.fore_color.rgb = COG_GRAY_MID
    div.line.fill.background()
    add_footer(slide, page_num, meta.get("classification", "© 2025–2027 Cognizant | Private"))
    return slide

def add_table_slide(prs, meta, spec, page_num):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_content_title(slide, spec["title"])
    headers = spec["headers"]; rows = spec["rows"]
    n_cols = len(headers); n_rows = len(rows) + 1
    col_widths = spec.get("col_widths") or [12.3 / n_cols] * n_cols
    x_start, y_start = 0.5, 1.3
    row_h = min(0.5, 5.7 / n_rows)
    table = slide.shapes.add_table(n_rows, n_cols,
                                    Inches(x_start), Inches(y_start),
                                    Inches(sum(col_widths)), Inches(row_h * n_rows)).table
    for ci, w in enumerate(col_widths): table.columns[ci].width = Inches(w)
    # Header row
    for ci, h in enumerate(headers):
        cell = table.cell(0, ci)
        cell.fill.solid(); cell.fill.fore_color.rgb = COG_NAVY
        tf = cell.text_frame; tf.clear()
        p = tf.paragraphs[0]; r = p.add_run(); r.text = h
        r.font.name = FONT; r.font.size = Pt(11); r.font.bold = True
        r.font.color.rgb = COG_WHITE
    # Body rows with zebra
    for ri, row in enumerate(rows, start=1):
        zebra = COG_GRAY_LIGHT if ri % 2 == 0 else COG_WHITE
        for ci, val in enumerate(row):
            cell = table.cell(ri, ci)
            cell.fill.solid(); cell.fill.fore_color.rgb = zebra
            tf = cell.text_frame; tf.clear(); tf.word_wrap = True
            p = tf.paragraphs[0]; r = p.add_run(); r.text = str(val)
            r.font.name = FONT; r.font.size = Pt(10); r.font.color.rgb = COG_BODY
    add_footer(slide, page_num, meta.get("classification", "© 2025–2027 Cognizant | Private"))
    return slide

def add_sub_sections_slide(prs, meta, spec, page_num):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_content_title(slide, spec["title"])
    sections = spec["sections"]
    y_start = 1.3; section_h = min(1.4, 5.5 / max(1, len(sections)))
    for i, sec in enumerate(sections):
        y = y_start + i * section_h
        add_text(slide, 0.5, y, 12.3, 0.4, sec["heading"],
                 size=14, bold=True, color=COG_NAVY)
        add_text(slide, 0.5, y + 0.42, 12.3, section_h - 0.45,
                 f"•  {sec['body']}", size=11, color=COG_BODY)
    if spec.get("footnote"):
        add_text(slide, 0.5, 6.8, 12.3, 0.3, spec["footnote"],
                 size=8, color=COG_GRAY_DARK)
    add_footer(slide, page_num, meta.get("classification", "© 2025–2027 Cognizant | Private"))
    return slide

def add_roadmap_slide(prs, meta, spec, page_num):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_content_title(slide, spec["title"])
    phases = spec["phases"]
    color_map = {"navy": COG_NAVY, "blue": COG_BLUE_MID, "teal": COG_TEAL}
    col_w = (12.3 - 0.4) / len(phases)
    for i, phase in enumerate(phases):
        x = 0.5 + i * (col_w + 0.2)
        # Phase header band
        header = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                         Inches(x), Inches(1.3),
                                         Inches(col_w), Inches(0.7))
        header.fill.solid(); header.fill.fore_color.rgb = color_map.get(phase.get("color"), COG_NAVY)
        header.line.fill.background()
        # Header text
        tb = header.text_frame; tb.margin_top = tb.margin_bottom = 0
        p = tb.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = phase["name"]
        r.font.name = FONT; r.font.size = Pt(16); r.font.bold = True; r.font.color.rgb = COG_WHITE
        if phase.get("duration"):
            p2 = tb.add_paragraph(); p2.alignment = PP_ALIGN.CENTER
            r2 = p2.add_run(); r2.text = phase["duration"]
            r2.font.name = FONT; r2.font.size = Pt(10); r2.font.color.rgb = COG_WHITE
        # Sections
        y = 2.1
        for sec in phase.get("sections", []):
            add_text(slide, x + 0.1, y, col_w - 0.2, 0.35, sec["heading"],
                     size=11, bold=True, color=COG_NAVY)
            add_text(slide, x + 0.1, y + 0.38, col_w - 0.2, 0.8,
                     f"•  {sec['body']}", size=9, color=COG_BODY)
            y += 1.2
    add_footer(slide, page_num, meta.get("classification", "© 2025–2027 Cognizant | Private"))
    return slide

def add_closing_slide(prs, meta, page_num):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_solid_bg(slide, COG_NAVY)
    deco = slide.shapes.add_shape(MSO_SHAPE.PARALLELOGRAM,
                                   Inches(7.5), Inches(-1.0),
                                   Inches(8.0), Inches(10.0))
    deco.fill.solid(); deco.fill.fore_color.rgb = COG_BLUE_MID
    deco.line.fill.background()
    deco.rotation = 15
    add_text(slide, 0.5, 0.4, 2.5, 0.5, "cognizant",
             size=18, bold=True, color=COG_WHITE)
    add_footer(slide, page_num,
               meta.get("classification", "© 2025–2027 Cognizant | Private"),
               on_dark=True)
    return slide

def build_deck(deck_spec, output_path):
    prs = new_presentation()
    builders = {
        "cover":        lambda spec, pg: add_cover_slide(prs, deck_spec["meta"], pg),
        "two_column":   lambda spec, pg: add_two_column_slide(prs, deck_spec["meta"], spec, pg),
        "table":        lambda spec, pg: add_table_slide(prs, deck_spec["meta"], spec, pg),
        "sub_sections": lambda spec, pg: add_sub_sections_slide(prs, deck_spec["meta"], spec, pg),
        "roadmap":      lambda spec, pg: add_roadmap_slide(prs, deck_spec["meta"], spec, pg),
        "closing":      lambda spec, pg: add_closing_slide(prs, deck_spec["meta"], pg),
    }
    for i, slide_spec in enumerate(deck_spec["slides"], start=1):
        t = slide_spec["type"]
        if t not in builders:
            raise ValueError(f"Unknown slide type: {t}. Supported: {list(builders.keys())}")
        builders[t](slide_spec, i)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    prs.save(output_path)
    print(f"[ NeuroEdge Assets ]  cognizant-ppt → {output_path}")
    return output_path
```

## Output Contract

- **File format:** `.pptx`, native PowerPoint 16:9 widescreen (13.333" × 7.5")
- **Default save path:** `docs/marketing/<topic-slug>-YYYY-MM-DD.pptx` in the calling project's root
- **Caller may override** the path; the skill creates the parent directory if missing
- **Return value:** absolute path to the generated `.pptx`
- **Console output:** one status line `[ NeuroEdge Assets ]  cognizant-ppt → <path>`
- **No interactive prompts** during generation — the spec is the contract

## How agents/commands invoke this skill

1. Construct a `deck_spec` dict matching the schema above
2. Pick an output path (default: `docs/marketing/<topic>-<date>.pptx`)
3. Generate a Python script using the implementation pattern above (or copy `build_deck()` directly)
4. Run the script (the script auto-installs `python-pptx` if missing)
5. Verify the file exists at the returned path
6. Report the path to the user with a one-line summary of slide count and slide types used

## Anti-patterns (forbidden in any generated deck)

| Anti-pattern | Why it fails | Use instead |
|---|---|---|
| Importing colors from anywhere except the constants block | Brand drift | Use only `COG_*` constants |
| Adding slide transitions or animations | Premium decks rely on content, not motion | None |
| Mixing fonts (Helvetica, Roboto, etc.) | Off-brand | Arial only |
| Inserting clip-art or stock emoji icons | Off-brand | Solid brand-color shapes |
| Cramming >5 bullets in one column or >3 columns on one slide | Violates 3×3 rule | Split into multiple slides |
| Using `prs.slide_layouts[0]` (Title Slide layout) | Layout chrome conflicts with the brand cover | Use `slide_layouts[6]` (Blank) and build manually |
| Auto-filling missing spec fields with "TBD" or placeholder text | Ships unfinished work | Ask the user to provide the field |

## Wiring (do not edit unless you know what you are doing)

This skill is wired via `patch_assets.py` at the repo root:
- **Commands:** `cognizant-ppt` (the slash command at `commands/cognizant-ppt.md`)
- **Agents:** `doc-updater` (presentations are documentation)

When new agents need PPT capability (e.g. a future `presentation-builder` agent), add them to `AGENT_SKILLS["<agent>"]` in `patch_assets.py` with this skill's path: `agentic-assets/skills/SUPPORTING-TOOLS/content/cognizant-ppt.md`. Then re-run `patch_assets.py` and `install.py`.
