"""CLI entry point for the product-document generator.

Subcommands:
    generate — parse the PRD + objectives, render, write the HTML output
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .render import render_html
from .sources import extract_sections

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def cmd_generate(args: argparse.Namespace) -> int:
    prd_path = Path(args.prd)
    objectives_path = Path(args.objectives)
    out_path = Path(args.out)

    if not prd_path.is_file():
        logger.error("PRD file not found: %s", prd_path)
        return 1
    if not objectives_path.is_file():
        logger.error("Objectives file not found: %s", objectives_path)
        return 1

    try:
        sections = extract_sections(prd_path, objectives_path)
    except (OSError, UnicodeDecodeError) as e:
        # UnicodeDecodeError subclasses ValueError, so this must be checked
        # before the ValueError clause below — otherwise an encoding problem
        # gets misreported as a missing-heading "section extraction failed"
        # error instead of a file-read error.
        logger.error("Could not read %s or %s: %s", prd_path, objectives_path, e)
        return 1
    except ValueError as e:
        logger.error("Section extraction failed: %s", e)
        return 1

    html_doc = render_html(sections)

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html_doc, encoding="utf-8", newline="\n")
    except OSError as e:
        logger.error("Could not write %s: %s", out_path, e)
        return 1

    print(f"OK: wrote {out_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="neuroedge_productdoc")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_generate = sub.add_parser("generate", help="Generate the HTML product document")
    p_generate.add_argument("--prd", required=True, help="Path to agentforge.prd.md")
    p_generate.add_argument("--objectives", required=True, help="Path to project_objectives.md")
    p_generate.add_argument("--out", required=True, help="Output HTML file path")
    p_generate.set_defaults(func=cmd_generate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
