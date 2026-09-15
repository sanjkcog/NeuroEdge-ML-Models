#!/usr/bin/env python3
"""usage_state.py — per-command token/cost telemetry for STANDALONE command runs (TD-002).

The problem this closes: `run_state.py` records token/cost usage only for stages inside an
orchestrated `/agentforge` run. A command run on its own (e.g. `/model-route`, `/test-plan`,
`/prp-prd` invoked directly) has no per-stage `run.json` to write to, so its cost is invisible
to `/budget-report`. This module is the standalone counterpart: a lightweight per-command
ledger that lives OUTSIDE any run/sprint container.

Storage — there is no `project_related/<objective>/` folder for a standalone command, so records
go under **`neuroedge/docs/project_related/misc/`** as one human-readable markdown runlog per
(command, args) pair:

    neuroedge/docs/project_related/misc/runlog-<command>-<arg-slug>.md

Same command + same args  → a new timestamped ROW appended to the SAME runlog (history).
Same command + different args → a DIFFERENT runlog file (the arg-slug disambiguates), so each
file stays something the user can recognise ("that's my classify-defects route runs").

Mirrors `run_state.py`'s cost model deliberately: cost_usd is **caller-provided** (no price
table is invented here), tokens/calls are integers. Aggregation (`report`) is the standalone
analogue of `run_state.usage_rollup`, and `/budget-report` reads it for the standalone view.

This module writes AND reads the runlog table format, so the round-trip is owned in one place
(and locked by tests) rather than being a fragile hand-edited artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

DEFAULT_LOGS_DIR = "neuroedge/docs/project_related/misc"

# A runlog filename slug is lower-kebab, starts alnum, and is capped so a very long arg
# string can't produce an unusable filename. Beyond the cap we append a short deterministic
# hash of the FULL args, so two distinct long args that share a 40-char prefix never collide
# onto the same file while short/common args keep a clean, human-relatable name.
_SLUG_MAXLEN = 40
_NON_SLUG = re.compile(r"[^a-z0-9]+")

# A data row in the runlog table: starts with an ISO-8601 UTC timestamp in column 1. The
# header and separator rows never match this, so parsing can't mistake them for data.
_ROW = re.compile(
    r"^\|\s*(?P<ts>\d{4}-\d{2}-\d{2}T[0-9:]+Z)\s*\|\s*(?P<model>[^|]*?)\s*\|"
    r"\s*(?P<tin>\d+)\s*\|\s*(?P<tout>\d+)\s*\|\s*(?P<calls>\d+)\s*\|\s*(?P<cost>[0-9.]+)\s*\|\s*$"
)
_COMMAND_LINE = re.compile(r"^\*\*Command:\*\*\s*`?(?P<command>[^`\n]+?)`?\s*$")
# Anything that could break the single-line markdown table row (pipes, newlines, tabs).
_CELL_UNSAFE = re.compile(r"[|\r\n\t]+")

_TABLE_HEADER = "| Timestamp (UTC) | Model | Tokens In | Tokens Out | API Calls | Cost (USD) |"
_TABLE_SEP = "|---|---|---|---|---|---|"


def slugify_args(args: str) -> str:
    """Turn a command's argument string into a filename-safe, human-relatable slug.

    Empty/whitespace args → 'no-args'. A path-looking arg keeps its stem so `neuroedge/docs/PRD.md`
    reads as 'prd' rather than 'docs-prd-md'. Long args get a stable hash suffix (see module
    docstring) so distinct long args never collide, while short args stay clean.
    """
    raw = (args or "").strip()
    if not raw:
        return "no-args"

    # A lone path argument: slug from its stem (the part a human recognises). Use
    # PurePosixPath and treat BOTH separators explicitly so the stem is identical on
    # Windows and POSIX (ambient pathlib.Path would differ across OSes, breaking the
    # "same inputs -> same path" guarantee on the backslash form).
    candidate = raw
    if (("/" in raw or "\\" in raw) and " " not in raw):
        candidate = PurePosixPath(raw.replace("\\", "/")).stem or raw

    slug = _NON_SLUG.sub("-", candidate.lower()).strip("-")
    if not slug:
        slug = "no-args"

    if len(slug) > _SLUG_MAXLEN:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]
        slug = slug[:_SLUG_MAXLEN].rstrip("-") + "-" + digest
    return slug


def runlog_path(command: str, args: str, logs_dir: str | Path = DEFAULT_LOGS_DIR) -> Path:
    """The runlog file for a (command, args) pair. Deterministic: same inputs → same path."""
    command_slug = _NON_SLUG.sub("-", command.strip().lstrip("/").lower()).strip("-")
    return Path(logs_dir) / f"runlog-{command_slug}-{slugify_args(args)}.md"


@dataclass
class CommandUsage:
    """One aggregated command's standalone usage across all its runlog rows."""

    command: str
    invocations: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    api_calls: int = 0
    cost_usd: float = 0.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def record(
    command: str,
    args: str,
    *,
    tokens_in: int,
    tokens_out: int,
    api_calls: int,
    cost_usd: float = 0.0,
    model: str = "",
    logs_dir: str | Path = DEFAULT_LOGS_DIR,
    ts: str | None = None,
) -> Path:
    """Append one invocation row to the (command, args) runlog, creating it with a header
    on first use. Returns the runlog path written. Never overwrites prior rows — append-only,
    so the file is the invocation history for that exact command+args.

    Validates the numeric telemetry up front (mirroring run_state's `complete` guard): a
    negative or non-finite value is rejected with ValueError rather than written and then
    silently dropped by `report()`'s stricter row regex.

    Note: runlogs are keyed by the *slug* of args (see `slugify_args`), so two args strings
    that slugify identically intentionally share one runlog file.
    """
    for label, value in (("tokens_in", tokens_in), ("tokens_out", tokens_out),
                         ("api_calls", api_calls)):
        # Compare the raw value (not int(value)) so a negative fraction in (-1, 0) can't
        # truncate to 0 and slip past the guard.
        if value < 0:
            raise ValueError(f"{label} must be >= 0, got {value!r}")
    if not math.isfinite(cost_usd) or cost_usd < 0:
        raise ValueError(f"cost_usd must be finite and >= 0, got {cost_usd!r}")

    path = runlog_path(command, args, logs_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    command_disp = command.strip().lstrip("/")
    timestamp = ts or _utc_now_iso()
    model_cell = _CELL_UNSAFE.sub(" ", (model or "-")).strip() or "-"
    row = (
        f"| {timestamp} | {model_cell} | {int(tokens_in)} | {int(tokens_out)} "
        f"| {int(api_calls)} | {float(cost_usd):.4f} |"
    )

    if not path.exists():
        header = (
            f"# Runlog — /{command_disp}\n\n"
            "Standalone command usage log (TD-002) — one row per invocation of this command\n"
            "with these exact args. Aggregated by `agentforge/src/state/usage_state.py report`\n"
            "and surfaced in `/budget-report --commands`. Do not hand-edit the table rows.\n\n"
            f"**Command:** `{command_disp}`\n"
            f"**Args:** `{(args or '').strip()}`\n\n"
            f"{_TABLE_HEADER}\n{_TABLE_SEP}\n"
        )
        path.write_text(header + row + "\n", encoding="utf-8")
    else:
        text = path.read_text(encoding="utf-8-sig")
        if not text.endswith("\n"):
            text += "\n"
        path.write_text(text + row + "\n", encoding="utf-8")
    return path


def _parse_runlog(path: Path) -> CommandUsage | None:
    """Parse one runlog file into an aggregated CommandUsage, or None if it has no data rows."""
    text = path.read_text(encoding="utf-8-sig")
    command = ""
    usage = CommandUsage(command="")
    for line in text.splitlines():
        if not command:
            m = _COMMAND_LINE.match(line)
            if m:
                command = m.group("command").strip()
                continue
        row = _ROW.match(line)
        if row:
            usage.invocations += 1
            usage.tokens_in += int(row.group("tin"))
            usage.tokens_out += int(row.group("tout"))
            usage.api_calls += int(row.group("calls"))
            usage.cost_usd += round(float(row.group("cost")), 4)
    if usage.invocations == 0:
        return None
    # Fall back to the filename's command slug if the header line was missing.
    usage.command = command or path.stem.replace("runlog-", "").split("-")[0]
    return usage


def report(logs_dir: str | Path = DEFAULT_LOGS_DIR, command: str | None = None) -> dict:
    """Aggregate every `runlog-*.md` under logs_dir into a reporting-ready summary.

    Groups rows by command (a command with several arg-runlogs is summed across them), and
    returns per-command totals plus the grand total and the top-consuming command by total
    tokens — the standalone analogue of run_state.usage_rollup. `command` filters to one.
    """
    directory = Path(logs_dir)
    by_command: dict[str, CommandUsage] = {}
    if directory.is_dir():
        for path in sorted(directory.glob("runlog-*.md")):
            parsed = _parse_runlog(path)
            if parsed is None:
                continue
            if command and parsed.command != command.strip().lstrip("/"):
                continue
            agg = by_command.setdefault(parsed.command, CommandUsage(command=parsed.command))
            agg.invocations += parsed.invocations
            agg.tokens_in += parsed.tokens_in
            agg.tokens_out += parsed.tokens_out
            agg.api_calls += parsed.api_calls
            agg.cost_usd = round(agg.cost_usd + parsed.cost_usd, 4)

    commands = sorted(by_command.values(), key=lambda c: -(c.tokens_in + c.tokens_out))
    total = CommandUsage(command="(all)")
    for c in commands:
        total.invocations += c.invocations
        total.tokens_in += c.tokens_in
        total.tokens_out += c.tokens_out
        total.api_calls += c.api_calls
        total.cost_usd = round(total.cost_usd + c.cost_usd, 4)

    top = commands[0].command if commands else None
    return {
        "commands": [c.__dict__ for c in commands],
        "total": total.__dict__,
        "top_command": top,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _render_report(summary: dict) -> str:
    lines = ["Standalone command usage (neuroedge/docs/project_related/misc/):", ""]
    if not summary["commands"]:
        lines.append("  (no standalone command runlogs recorded yet)")
        return "\n".join(lines)
    lines.append(
        f"  {'command':24} {'runs':>5} {'tok_in':>9} {'tok_out':>9} {'calls':>6} {'cost_usd':>10}"
    )
    for c in summary["commands"]:
        lines.append(
            f"  {c['command']:24} {c['invocations']:>5} {c['tokens_in']:>9} "
            f"{c['tokens_out']:>9} {c['api_calls']:>6} {c['cost_usd']:>10.4f}"
        )
    t = summary["total"]
    lines.append("  " + "-" * 66)
    lines.append(
        f"  {'TOTAL':24} {t['invocations']:>5} {t['tokens_in']:>9} "
        f"{t['tokens_out']:>9} {t['api_calls']:>6} {t['cost_usd']:>10.4f}"
    )
    if summary["top_command"]:
        lines.append(f"\n  top consumer (by tokens): {summary['top_command']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-dir", default=DEFAULT_LOGS_DIR,
                        help=f"where runlogs live (default: {DEFAULT_LOGS_DIR})")
    sub = parser.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="append one invocation row to a command's runlog")
    rec.add_argument("--command", required=True)
    rec.add_argument("--args", default="")
    rec.add_argument("--tokens-in", type=int, required=True)
    rec.add_argument("--tokens-out", type=int, required=True)
    rec.add_argument("--api-calls", type=int, required=True)
    rec.add_argument("--cost-usd", type=float, default=0.0)
    rec.add_argument("--model", default="")
    rec.add_argument("--ts", default=None, help="override timestamp (ISO-8601 UTC); tests use this")

    rep = sub.add_parser("report", help="aggregate all standalone command runlogs")
    rep.add_argument("--command", default=None, help="filter to one command")
    rep.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    args = parser.parse_args(argv)

    if args.cmd == "record":
        path = record(
            args.command, args.args,
            tokens_in=args.tokens_in, tokens_out=args.tokens_out,
            api_calls=args.api_calls, cost_usd=args.cost_usd,
            model=args.model, logs_dir=args.logs_dir, ts=args.ts,
        )
        print(f"recorded -> {path}")
        return 0

    if args.cmd == "report":
        summary = report(args.logs_dir, command=args.command)
        if args.json:
            import json
            print(json.dumps(summary, indent=2))
        else:
            print(_render_report(summary))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
