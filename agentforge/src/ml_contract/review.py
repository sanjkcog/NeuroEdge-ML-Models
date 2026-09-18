"""Review packs for the human gates at M5, M6 and M7 (ADR-0025 D-3).

Each subcommand writes the page the human reads, then opens the hard gate they answer. The page
is built from the run's own manifests. It never opens ``data/splits/test.json`` or any test data:
test is summarised from the counts ``ts_contract`` recorded at M4.

    python -m agentforge.src.ml_contract.review split --dest <dest>
    python -m agentforge.src.ml_contract.review synth --dest <dest> [--cap-fraction 0.5]
    python -m agentforge.src.ml_contract.review synth --dest <dest> --skip-reason "<why M6 is not run>"
    python -m agentforge.src.ml_contract.review model --dest <dest>
    python -m agentforge.src.ml_contract.review model --dest <dest> --archive "<reason>"   (before a re-run)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from typing import Any

from . import gates as gt
from .lock import LockError, read_lock

SPLIT_REVIEW = "data/split-review.md"
SYNTH_REVIEW = "data/synth-review.md"
MODEL_PROPOSED = "model_proposed.md"
MODEL_ARCHIVE_DIR = "model_proposed"
SPLITS = ("train", "val", "test")

# What a proposal must cover before a human is asked to approve it (ADR-0025 D-3).
MODEL_SECTIONS = (
    "architecture", "framing", "synthetic", "augmentation", "baseline",
    "evaluation", "export", "runner", "alternatives considered",
)


class ReviewError(ValueError):
    """The pack cannot be built from what the run has. Each problem is listed."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _windows(rows: int, window: int, stride: int) -> int:
    return max(0, (rows - window) // stride + 1)


def _write(dest: str, rel: str, text: str) -> str:
    path = os.path.join(dest, rel)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def _section(md: str, heading_word: str) -> str | None:
    """The body of the first ``##`` section whose heading contains ``heading_word``."""
    match = re.search(rf"^##\s+[^\n]*{re.escape(heading_word)}[^\n]*\n(.*?)(?=^##\s|\Z)", md, re.S | re.M | re.I)
    return match.group(1).strip() if match else None


def _contract(dest: str) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        lock = read_lock(dest)
    except (OSError, LockError) as exc:
        raise ReviewError([f"no valid use-case lock: {exc}"]) from exc
    path = os.path.join(dest, "data", "contract", "manifest.json")
    if not os.path.exists(path):
        raise ReviewError(["data/contract/manifest.json is missing; M4 builds the contract dataset first"])
    manifest = _json(path)
    problems = []
    if manifest.get("lock_sha256") != lock["lock_sha256"]:
        problems.append("the contract dataset was built on another lock; rebuild it (ts_contract)")
    if "unit_labels" not in manifest or "segment_rows" not in manifest:
        problems.append("the contract manifest has no unit_labels / segment_rows; run "
                        "`ts_contract --dest <dest> --labels-only`")
    if problems:
        raise ReviewError(problems)
    return lock, manifest


def split_table(lock: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """Per split × class and per unit: units, rows, windows, hours — from the contract manifest only."""
    ts = lock["timeseries"]
    window, stride, rate = int(ts["window_samples"]), int(ts["stride_samples"]), float(ts["sample_rate_hz"])
    labels = manifest["unit_labels"]
    segs = manifest["segment_rows"]
    agg: dict[tuple[str, str], dict[str, float]] = {}
    per_unit = []
    for unit, by_split in sorted(manifest["units"].items()):
        for split, rows in by_split.items():
            label = labels.get(unit, {}).get(split, "?")
            # Windows never cross a gap between two segments of one split: count them per run.
            runs = segs.get(unit, {}).get(split) or [int(rows)]
            w = sum(_windows(int(r), window, stride) for r in runs)
            a = agg.setdefault((split, label), {"units": 0, "rows": 0, "windows": 0})
            a["units"] += 1
            a["rows"] += int(rows)
            a["windows"] += w
            per_unit.append({"unit": unit, "split": split, "label": label, "rows": int(rows), "windows": w})
    for a in agg.values():
        a["hours"] = a["rows"] / rate / 3600
    return {"agg": agg, "per_unit": per_unit, "window": window, "stride": stride, "rate": rate}


def split_pack(dest: str) -> str:
    """Build ``data/split-review.md`` (M5)."""
    lock, manifest = _contract(dest)
    t = split_table(lock, manifest)
    train = _json(os.path.join(dest, "data", "splits", "train.json"))
    val_path = os.path.join(dest, "data", "splits", "val.json")
    val = _json(val_path) if os.path.exists(val_path) else {}
    classes = lock["class_names"]
    lm_path = os.path.join(dest, "data", "label-manifest.md")
    label_manifest = open(lm_path, encoding="utf-8").read() if os.path.exists(lm_path) else ""
    window_s = t["window"] / t["rate"]

    out = [
        "# Split review — M5 (human gate `data/split-review.md`)",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} by "
        "`ml_contract.review split` from `data/contract/manifest.json` and `data/splits/{train,val}.json`. "
        "Test is summarised from the counts recorded at M4; `splits/test.json` was not opened.",
        "",
        f"- **Lock** `{lock['lock_sha256'][:12]}` · **split_hash** `{str(manifest.get('split_hash'))[:12]}`",
        f"- **Window** {t['window']} samples at {t['rate']:g} Hz = {window_s:g} s · **stride** {t['stride']} "
        f"({t['stride'] / t['rate']:g} s; consecutive windows share {max(0, t['window'] - t['stride'])} of "
        f"{t['window']} samples)",
        f"- **Classes** {classes} · **target** {lock['target'].get('metric')} ≥ {lock['target'].get('min_value')} "
        f"at FPR {lock['target'].get('at_fpr')}",
        "",
        "## Split × class",
        "",
        "| Split | Class | Units | Rows | Hours | Windows | Share of split windows |",
        "|---|---|---|---|---|---|---|",
    ]
    for split in SPLITS:
        total = sum(v["windows"] for (s, _), v in t["agg"].items() if s == split) or 1
        for cls in classes:
            v = t["agg"].get((split, cls))
            if v:
                out.append(f"| {split} | {cls} | {v['units']} | {v['rows']:,} | {v['hours']:.2f} | "
                           f"{v['windows']:,} | {100 * v['windows'] / total:.0f}% |")
        for (s, cls), v in sorted(t["agg"].items()):
            if s == split and cls not in classes:
                out.append(f"| {split} | **{cls} (not a lock class)** | {v['units']} | {v['rows']:,} | "
                           f"{v['hours']:.2f} | {v['windows']:,} | — |")
    out += ["", "## Per unit", "", "| Unit | Split | Label | Rows | Windows |", "|---|---|---|---|---|"]
    for u in sorted(t["per_unit"], key=lambda r: (SPLITS.index(r["split"]) if r["split"] in SPLITS else 9, r["unit"])):
        out.append(f"| {u['unit']} | {u['split']} | {u['label']} | {u['rows']:,} | {u['windows']:,} |")

    out += ["", "## How the data was split, and why", ""]
    out.append(f"- **Grouping:** {train.get('group_key', 'not recorded')}")
    out.append(f"- **Taxonomy:** {train.get('taxonomy', 'not recorded')}")
    deviations = {d for d in (train.get("deviation"), val.get("deviation")) if d}
    for d in deviations:
        out.append(f"- **Recorded deviation:** {d}")
    excluded = train.get("excluded_units") or []
    if excluded:
        out.append(f"- **Excluded units ({len(excluded)}):** {', '.join(excluded)} — reasons in `data/label-manifest.md`")
    out.append(f"- **Leakage controls:** windows are cut inside each unit's split bounds only; the M4 contract "
               f"build refuses any time-split gap shorter than one window ({window_s:g} s). Overlapping windows "
               "of one unit are near-duplicates, so metrics are reported per unit, not per window.")
    for word in ("Window rule", "Known limits"):
        body = _section(label_manifest, word)
        if body:
            out += ["", f"### From `data/label-manifest.md` — {word}", "", body]

    out += [
        "", "## Decision",
        "",
        "- **approve** — the split, the classes and the window rule are right; M6 (synthetic data) is next.",
        "- **changes_requested** with the reason — back to M4 (`/dataset-verify`) to re-split, or M5 to re-label.",
        "",
        "Nothing downstream reads the test split until M10 `eval`.",
    ]
    _write(dest, SPLIT_REVIEW, "\n".join(out) + "\n")
    return SPLIT_REVIEW


def synth_pack(dest: str, *, cap_fraction: float = 0.5, skip_reason: str | None = None) -> str:
    """Build ``data/synth-review.md`` (M6): the synthetic set against real train, or a recorded skip."""
    lock, manifest = _contract(dest)
    t = split_table(lock, manifest)
    classes = lock["class_names"]
    syn_path = os.path.join(dest, "data", "synthetic", "manifest.json")
    recipe_path = os.path.join(dest, "data", "synthetic-recipe.md")
    header = [
        "# Synthetic data review — M6 (human gate `data/synth-review.md`)",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} by `ml_contract.review synth`.",
        "",
    ]
    if skip_reason is not None:
        if os.path.exists(syn_path):
            raise ReviewError(["a synthetic set exists (data/synthetic/manifest.json); review it or remove it, "
                               "do not record a skip over it"])
        body = header + [
            "## M6 not run",
            "",
            f"**Reason:** {skip_reason}",
            "",
            "Real train, which is all M8 will train on:",
            "",
            "| Class | Units | Windows |",
            "|---|---|---|",
        ] + [
            f"| {c} | {t['agg'].get(('train', c), {}).get('units', 0)} | "
            f"{t['agg'].get(('train', c), {}).get('windows', 0):,} |" for c in classes
        ] + ["", "## Decision", "", "- **approve** — skip M6; M7 is next.",
             "- **changes_requested** — run `/synth-data` instead."]
        _write(dest, SYNTH_REVIEW, "\n".join(body) + "\n")
        return SYNTH_REVIEW

    if not os.path.exists(syn_path):
        raise ReviewError(["no data/synthetic/manifest.json; run /synth-data, or pass --skip-reason"])
    syn = _json(syn_path)
    problems = []
    for key, want in (("lock_sha256", lock["lock_sha256"]), ("split_hash", manifest.get("split_hash"))):
        if syn.get(key) is None:
            problems.append(f"UNSTAMPED: the synthetic manifest has no {key}; it cannot be tied to this lock/split")
        elif syn[key] != want:
            problems.append(f"MISMATCH: the synthetic manifest's {key} {str(syn[key])[:12]} is not this run's "
                            f"{str(want)[:12]}")
    window, stride = t["window"], t["stride"]
    syn_agg: dict[str, dict[str, int]] = {}
    for u in syn.get("units", []):
        a = syn_agg.setdefault(u.get("label", "?"), {"units": 0, "rows": 0, "windows": 0})
        a["units"] += 1
        a["rows"] += int(u.get("rows", 0))
        a["windows"] += _windows(int(u.get("rows", 0)), window, stride)

    out = header + [
        f"- **Lock** `{lock['lock_sha256'][:12]}` · **split_hash** `{str(manifest.get('split_hash'))[:12]}` · "
        f"**seed** {syn.get('seed', 'not recorded')}",
        f"- **Recipe** `data/synthetic-recipe.md`{'' if os.path.exists(recipe_path) else ' (MISSING)'}",
        "",
    ]
    if problems:
        out += ["## Stamping problems", ""] + [f"- {p}" for p in problems] + [""]
    out += [
        f"## Real train + synthetic, per class (synthetic capped at {cap_fraction:.0%} of real windows per class)",
        "",
        "| Class | Real units | Real windows | Synthetic units | Synthetic windows | Real : synthetic | "
        "Synthetic windows used (cap) | Share synthetic after cap |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in classes:
        real = t["agg"].get(("train", c), {"units": 0, "windows": 0})
        s = syn_agg.get(c, {"units": 0, "windows": 0})
        used = min(s["windows"], int(cap_fraction * real["windows"]))
        ratio = f"1 : {s['windows'] / real['windows']:.2f}" if real["windows"] else "—"
        share = used / (used + real["windows"]) if (used + real["windows"]) else 0
        out.append(f"| {c} | {real['units']} | {real['windows']:,} | {s['units']} | {s['windows']:,} | {ratio} | "
                   f"{used:,} | {share:.0%} |")
    recipe = open(recipe_path, encoding="utf-8").read() if os.path.exists(recipe_path) else ""
    for word in ("Fidelity", "Known limits"):
        body = _section(recipe, word)
        if body:
            out += ["", f"### From `data/synthetic-recipe.md` — {word}", "", body]
    out += [
        "", "## How it is used",
        "",
        "| Split | Synthetic |",
        "|---|---|",
        "| train | Mixed in, capped as above; every synthetic row keeps `source=synthetic` |",
        "| val | **Never.** The threshold is calibrated here, on real data only |",
        "| test | **Never.** It measures the real result, including the synthetic-to-real gap |",
        "",
        "M8 must train a real-only model and a real + synthetic model and compare them on **real val**. The "
        "synthetic data is kept only if it improves real-val recall at the target FPR.",
        "", "## Decision", "",
        "- **approve** — use the synthetic set as above; M7 is next.",
        "- **changes_requested** with the reason — re-run `/synth-data` (other cap, recipe or seed) or skip M6.",
    ]
    _write(dest, SYNTH_REVIEW, "\n".join(out) + "\n")
    if problems:
        raise ReviewError(problems + [f"{SYNTH_REVIEW} written with the problems listed; fix them before the gate"])
    return SYNTH_REVIEW


def check_model_proposal(dest: str) -> list[str]:
    """What ``model_proposed.md`` is missing before it can be put to a human (ADR-0025 D-3)."""
    path = os.path.join(dest, MODEL_PROPOSED)
    if not os.path.exists(path):
        return [f"{MODEL_PROPOSED} is missing; /model-select writes it"]
    headings = " ".join(re.findall(r"^#{1,4}\s+(.*)$", open(path, encoding="utf-8").read(), re.M)).lower()
    return [f"{MODEL_PROPOSED} has no section on '{s}'" for s in MODEL_SECTIONS if s not in headings]


def archive_model_proposal(dest: str, reason: str) -> str:
    """Move the current proposal to ``model_proposed/v<N>.md`` before M7 is re-run with an alternative."""
    src = os.path.join(dest, MODEL_PROPOSED)
    if not os.path.exists(src):
        raise ReviewError([f"{MODEL_PROPOSED} is missing; nothing to archive"])
    folder = os.path.join(dest, MODEL_ARCHIVE_DIR)
    os.makedirs(folder, exist_ok=True)
    n = 1 + max([int(m.group(1)) for f in os.listdir(folder) if (m := re.match(r"v(\d+)\.md$", f))] or [0])
    rel = f"{MODEL_ARCHIVE_DIR}/v{n}.md"
    shutil.move(src, os.path.join(dest, rel))
    with open(os.path.join(folder, "INDEX.md"), "a", encoding="utf-8") as fh:
        fh.write(f"- `v{n}.md` — archived {datetime.now(timezone.utc).date()}: {reason}\n")
    return rel


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="review", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("split", help="M5: write data/split-review.md and open its gate")
    s.add_argument("--dest", required=True)
    y = sub.add_parser("synth", help="M6: write data/synth-review.md and open its gate")
    y.add_argument("--dest", required=True)
    y.add_argument("--cap-fraction", type=float, default=0.5,
                   help="synthetic windows allowed per class, as a fraction of real train windows")
    y.add_argument("--skip-reason", help="M6 is not run; record why, for approval")
    m = sub.add_parser("model", help="M7: check model_proposed.md and open its gate")
    m.add_argument("--dest", required=True)
    m.add_argument("--archive", metavar="REASON", help="archive the current proposal before a re-run of M7")
    for sp in (s, y, m):
        sp.add_argument("--no-gate", action="store_true", help="write the pack without opening the gate")
    a = p.parse_args(argv)

    try:
        if a.cmd == "split":
            rel, stage = split_pack(a.dest), "label"
        elif a.cmd == "synth":
            rel, stage = synth_pack(a.dest, cap_fraction=a.cap_fraction, skip_reason=a.skip_reason), "synth"
        else:
            if a.archive:
                print(f"archived as {archive_model_proposal(a.dest, a.archive)}; re-run /model-select")
                return 0
            missing = check_model_proposal(a.dest)
            if missing:
                raise ReviewError(missing)
            rel, stage = MODEL_PROPOSED, "model-select"
    except ReviewError as exc:
        print("review refused:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"wrote {rel}" if a.cmd != "model" else f"{rel} covers every required section")
    if not a.no_gate:
        action = gt.open_pending(a.dest, rel, stage=stage, opened_by=f"review {a.cmd}")
        print(f"gate {rel!r} {action} — present it to the human (AskUserQuestion) and record the decision")
    return 0


if __name__ == "__main__":
    sys.exit(main())
