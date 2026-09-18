"""Offline inputs from the portal: record, hash and check them, then gate them (ADR-0025 D-1, D-2, D-5).

The model project never calls the portal. What it needs from the portal arrives as a file a human
downloaded: the use case, the device's capability manifest, and the training scaffold. This module
copies such a file into ``<dest>/inputs/``, records its hash in ``<dest>/inputs/inputs.json``,
checks it against the use-case lock where one exists, and opens the hard gate the human answers.
It never edits the file, and it never decides the gate.

    python -m agentforge.src.ml_contract.intake record --dest <dest> --kind use_case --file <yaml>
    python -m agentforge.src.ml_contract.intake record --dest <dest> --kind capability_manifest --file <json>
    python -m agentforge.src.ml_contract.intake record --dest <dest> --kind scaffold --file <py|ipynb>
    python -m agentforge.src.ml_contract.intake show   --dest <dest>

The drop folder (ADR-0025 D-1a). ``init`` creates ``<dest>/inputs/incoming/`` with a README saying
what to put there and where each file comes from. ``check`` picks up what was dropped, records it
(opening its gate), and exits ``3`` naming every file still missing, so the orchestrator stops until
the human has put it there:

    python -m agentforge.src.ml_contract.intake init  --dest <dest>
    python -m agentforge.src.ml_contract.intake check --dest <dest> --need use_case,capability_manifest
    python -m agentforge.src.ml_contract.intake check --dest <dest> --need scaffold
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from typing import Any

from ..state.lock_digest import source_digest
from . import gates as gt
from .lock import LOCK_FILE, LockError, read_lock

INPUTS_DIR = "inputs"
INPUTS_FILE = "inputs.json"
INPUTS_SCHEMA = "ml-inputs/1"

# kind -> (stored path under <dest>, gate id, stage whose completion needs it)
KINDS: dict[str, tuple[str, str, str]] = {
    "use_case": ("inputs/use_case.yaml", "inputs/use_case.yaml", "destination"),
    "capability_manifest": ("inputs/capability_manifest.json", "inputs/capability_manifest.json", "destination"),
    "scaffold": ("inputs/scaffold/{name}", "inputs/scaffold", "model-build"),
}

# The audit gates whose checks read an input of each kind. A changed input re-arms them, so an
# approval computed against the previous file cannot keep a stage satisfied (ADR-0025 D-4).
DEPENDENT_AUDITS: dict[str, tuple[str, ...]] = {
    "use_case": ("audit/M0", "audit/M4", "audit/M8", "audit/M11"),
    "capability_manifest": ("audit/M0", "audit/M4", "audit/M8", "audit/M11"),
    "scaffold": ("audit/M8", "audit/M11"),
}

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
_CONTEXT_RE = re.compile(r"NEUROEDGE_CONTEXT\s*=\s*json\.loads\(\s*r?(?:'''|\"\"\")(.*?)(?:'''|\"\"\")\s*\)", re.S)
# A manifest older than this is reported: the device may have been re-flashed since it was measured.
MANIFEST_MAX_AGE_DAYS = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finding(level: str, check: str, detail: str) -> dict[str, str]:
    return {"level": level, "check": check, "detail": detail}


def _lock_or_none(dest: str) -> tuple[dict[str, Any] | None, str | None]:
    if not os.path.exists(os.path.join(dest, LOCK_FILE)):
        return None, None
    try:
        return read_lock(dest), None
    except LockError as exc:
        return None, str(exc)


# --------------------------------------------------------------------------- scaffold


def scaffold_text(raw: bytes, name: str) -> str:
    """The scaffold's code as one string; a notebook contributes its code cells, in order."""
    text = raw.decode("utf-8")
    if name.lower().endswith(".ipynb"):
        nb = json.loads(text)
        cells = [c for c in nb.get("cells", []) if c.get("cell_type") == "code"]
        return "\n".join("".join(c.get("source", [])) for c in cells)
    return text


def scaffold_context(text: str) -> dict[str, Any]:
    """``NEUROEDGE_CONTEXT`` from a portal scaffold. Raises ValueError when it is absent or unreadable."""
    match = _CONTEXT_RE.search(text)
    if not match:
        raise ValueError("no NEUROEDGE_CONTEXT block found; this is not a portal training scaffold")
    try:
        return json.loads(match.group(1))
    except ValueError as exc:
        raise ValueError(f"NEUROEDGE_CONTEXT is not valid JSON: {exc}") from exc


def check_scaffold(ctx: dict[str, Any], text: str, lock: dict[str, Any] | None) -> list[dict[str, str]]:
    """The scaffold's contract against the lock (ADR-0025 D-5). The lock always wins; a FAIL
    means the scaffold was generated from a different use case than the one locked."""
    out: list[dict[str, str]] = []
    if lock is None:
        return [_finding(FAIL, "lock", "no valid use_case.lock.json; M0 must lock the use case before M8")]
    task = ctx.get("task") or {}
    task_input = task.get("input") or {}

    def same(check: str, got: Any, want: Any) -> None:
        if got == want:
            out.append(_finding(PASS, check, f"{got!r}"))
        else:
            out.append(_finding(FAIL, check, f"scaffold has {got!r}, the lock has {want!r}"))

    same("use_case_id", ctx.get("use_case_id"), lock.get("use_case_id"))
    same("class_names (order included)", list(task.get("classes") or []), lock.get("class_names"))

    ts = lock.get("timeseries")
    if ts:
        same("channel order", list(task_input.get("channels") or []), [c["name"] for c in ts["channels"]])
        rate = task_input.get("sample_rate_hz")
        same("sample_rate_hz", float(rate) if rate is not None else None, float(ts["sample_rate_hz"]))
        same("window_samples", task_input.get("window_samples"), ts["window_samples"])
        if task_input.get("resolution"):
            out.append(_finding(WARN, "vision field on a time-series use case",
                                f"input.resolution {task_input['resolution']} is a vision default; ignored"))
        if "min_accuracy_map50" in (ctx.get("performance_targets") or {}):
            out.append(_finding(WARN, "vision metric on a time-series use case",
                                "performance_targets.min_accuracy_map50 is a vision metric; ignored"))
        if "stride_samples" not in task_input:
            out.append(_finding(WARN, "stride", f"context carries no stride; the lock's {ts['stride_samples']} is used"))
        out.append(_finding(WARN, "units / definitions / reduce",
                            "context carries none of them; meta.json takes them from the lock"))

    accuracy = (ctx.get("performance_targets") or {}).get("accuracy") or {}
    if "at_fpr" not in accuracy:
        where = " (only in free-text notes)" if "fpr" in str(accuracy.get("notes", "")).lower() else ""
        out.append(_finding(WARN, "at_fpr", f"not a structured field{where}; the lock's "
                                            f"{lock['target']['at_fpr']} is used"))
    if not (ctx.get("data") or {}).get("path"):
        out.append(_finding(WARN, "data.path", "empty; the build reads data/contract/, never the scaffold's path"))
    if (ctx.get("model_hint") or {}).get("framework") in (None, "", "auto"):
        out.append(_finding(WARN, "framework", "model_hint.framework is 'auto'; model_proposed.md decides"))
    if re.search(r"git\+https?://", text):
        out.append(_finding(WARN, "return writer install", "the install hint fetches neuroedge_return over the "
                            "network; install it from a local path or wheel instead"))
    if re.search(r"pip install (?![^\n]*==)[^\n]*torch", text):
        out.append(_finding(WARN, "dependencies", "the scaffold's pip install pins no versions"))
    if "write_return_package" in text:
        out.append(_finding(PASS, "return writer", "the scaffold writes the package through neuroedge_return"))
    else:
        out.append(_finding(FAIL, "return writer", "no write_return_package call; not the portal's return contract"))
    out.append(_finding(WARN, "training body", "the scaffold's data loading, split, model, loss, metric and export "
                        "are NOT used; M8 generates them from the lock and model_proposed.md (ADR-0025 D-5)"))
    return out


# --------------------------------------------------------------------------- other kinds


def check_use_case(raw: bytes, lock: dict[str, Any] | None) -> list[dict[str, str]]:
    import yaml  # pyyaml

    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - any parse failure is the finding
        return [_finding(FAIL, "parse", f"not readable YAML: {exc}")]
    if not isinstance(data, dict) or not data.get("id"):
        return [_finding(FAIL, "parse", "not a use-case mapping with an id")]
    out = [_finding(PASS, "parse", f"use case {data['id']!r}")]
    if lock is not None:
        if source_digest(raw) == lock.get("use_case_sha256"):
            out.append(_finding(PASS, "lock", "identical to the use case the lock was built from"))
        else:
            out.append(_finding(FAIL, "lock", "differs from the use case the lock was built from; "
                                              "re-lock (--force) and re-run every stage the change affects"))
    return out


def check_capability_manifest(raw: bytes) -> list[dict[str, str]]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        return [_finding(FAIL, "parse", f"not readable JSON: {exc}")]
    if not isinstance(data, dict) or not (data.get("manifest_id") or data.get("device_profile_id")):
        return [_finding(FAIL, "parse", "not a capability manifest (no manifest_id / device_profile_id)")]
    out = [_finding(PASS, "parse", f"{data.get('manifest_id')} ({data.get('device_profile_id')}, "
                                   f"{data.get('platform')})")]
    status = data.get("status")
    out.append(_finding(PASS if status == "success" else FAIL, "status", f"{status!r}"))
    generated = data.get("generated_at")
    if generated:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(generated.replace("Z", "+00:00"))).days
            level = WARN if age > MANIFEST_MAX_AGE_DAYS else PASS
            out.append(_finding(level, "age", f"generated {generated} ({age} days ago)"))
        except ValueError:
            out.append(_finding(WARN, "age", f"unreadable generated_at {generated!r}"))
    else:
        out.append(_finding(WARN, "age", "no generated_at"))
    out.append(_finding(PASS, "alignment", "compared with the use case by /usecase-audit at M0"))
    return out


# --------------------------------------------------------------------------- record


def _read_inputs(dest: str) -> dict[str, Any]:
    path = os.path.join(dest, INPUTS_DIR, INPUTS_FILE)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {"schema": INPUTS_SCHEMA, "inputs": {}}


def read_inputs(dest: str) -> dict[str, Any]:
    """``<dest>/inputs/inputs.json``'s entries by kind ({} when nothing was recorded)."""
    return _read_inputs(dest)["inputs"]


def stored_path(dest: str, kind: str) -> str | None:
    """Absolute path of the recorded input of ``kind``, or None."""
    entry = read_inputs(dest).get(kind)
    return os.path.join(dest, entry["path"]) if entry else None


def record(dest: str, kind: str, src: str, *, open_gate: bool = True) -> dict[str, Any]:
    """Copy ``src`` into the model folder as the input of ``kind``, check it, record it, gate it."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}, expected one of {sorted(KINDS)}")
    with open(src, "rb") as fh:
        raw = fh.read()
    name = os.path.basename(src)
    rel_tmpl, gate_id, stage = KINDS[kind]
    rel = rel_tmpl.format(name=name)
    lock, lock_error = _lock_or_none(dest)

    generated_at = None
    if kind == "use_case":
        findings = check_use_case(raw, lock)
    elif kind == "capability_manifest":
        findings = check_capability_manifest(raw)
        try:
            generated_at = json.loads(raw.decode("utf-8")).get("generated_at")
        except ValueError:
            pass
    else:
        text = scaffold_text(raw, name)
        try:
            ctx = scaffold_context(text)
            generated_at = ctx.get("generated_at")
            findings = check_scaffold(ctx, text, lock)
        except ValueError as exc:
            findings = [_finding(FAIL, "context", str(exc))]
    if lock_error:
        findings.insert(0, _finding(FAIL, "lock", lock_error))

    inputs = _read_inputs(dest)
    previous = inputs["inputs"].get(kind)
    target = os.path.join(dest, rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if previous and previous["path"] != rel:
        old = os.path.join(dest, previous["path"])
        if os.path.exists(old):
            os.remove(old)  # one input per kind: a scaffold of another name replaces the old one
    if os.path.abspath(src) != os.path.abspath(target):
        shutil.copyfile(src, target)

    entry = {
        "kind": kind,
        "path": rel.replace(os.sep, "/"),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "source_name": name,
        "generated_at": generated_at,
        "recorded_at": _now(),
        "gate": gate_id,
        "findings": findings,
    }
    if previous:
        entry["replaces_sha256"] = previous["sha256"]
    inputs["inputs"][kind] = entry
    path = os.path.join(dest, INPUTS_DIR, INPUTS_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(inputs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    unchanged = previous is not None and previous["sha256"] == entry["sha256"]
    entry["unchanged"] = unchanged
    if open_gate and not unchanged:
        entry["gate_action"] = gt.open_pending(dest, gate_id, stage=stage, opened_by="intake")
    if not unchanged:
        # Unconditional (not tied to open_gate): a stale audit approval is wrong whether or not
        # this input's own gate is being opened.
        entry["audits_reopened"] = gt.reopen_if_present(dest, DEPENDENT_AUDITS[kind])
    return entry


# --------------------------------------------------------------------------- the drop folder

INCOMING_DIR = "inputs/incoming"
RECORDED_DIR = "inputs/incoming/recorded"
MISSING_EXIT = 3  # "a human must drop a file": distinct from 1 (a check failed) and 0 (all present)

INCOMING_README = """# Drop portal files here

`/agentforge-ml` never calls the portal. Download these files from the portal (or the device) and
drop them in this folder. The run records each one with its hash, asks you to confirm it at a gate,
then moves it to `recorded/`. Nothing proceeds until the files a stage needs are here.

| File | Needed from | Where to get it | Recognised as |
|---|---|---|---|
| the use case (`<use-case-id>.yaml`) | M0 | Portal **Step 1 · Edge Use Case Design** → validate the spec → **Download use_case.yaml** | any `*.yaml` / `*.yml` with a top-level `id:` and `task:` |
| the device capability manifest | M0 | The target device's assessment: `ne-device-agent assess --local` writes `capability_manifest.json`, the same file uploaded to the portal in **Step 2 · Target Device** | any `*.json` with `manifest_id` or `device_profile_id` |
| the training scaffold (`neuroedge_train_<id>.py`) | M8 | Portal **Step 3 · Model Strategy** → *Build my own* → **Script (.py)** (a notebook also works) | any `*.py` / `*.ipynb` containing `NEUROEDGE_CONTEXT` |

Check what is here and what is missing:

    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need use_case,capability_manifest
    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need scaffold

One file per kind. If two files of the same kind are here, `check` stops and names both; remove the
one you do not want. A newer download of a file already recorded replaces it, and its gate and every
audit that compared it are asked again.
"""


def init_incoming(dest: str) -> str:
    """Create ``<dest>/inputs/incoming/`` and its README. Idempotent; returns the folder path."""
    folder = os.path.join(dest, INCOMING_DIR)
    os.makedirs(folder, exist_ok=True)
    readme = os.path.join(folder, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as fh:
            fh.write(INCOMING_README)
    return folder


def classify(path: str) -> str | None:
    """Which input kind a dropped file is, from its content (never its name alone), or None."""
    name = os.path.basename(path).lower()
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    if name.endswith((".yaml", ".yml")):
        import yaml  # pyyaml

        try:
            data = yaml.safe_load(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001 - an unreadable file is simply not a use case
            return None
        return "use_case" if isinstance(data, dict) and data.get("id") and data.get("task") else None
    if name.endswith(".json"):
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            return None
        ok = isinstance(data, dict) and (data.get("manifest_id") or data.get("device_profile_id"))
        return "capability_manifest" if ok else None
    if name.endswith((".py", ".ipynb")):
        try:
            scaffold_context(scaffold_text(raw, name))
        except ValueError:
            return None
        return "scaffold"
    return None


def check(dest: str, need: list[str]) -> tuple[int, list[str]]:
    """Record every needed input that was dropped, and report what is still missing.

    Returns ``(exit_code, lines)``: 0 when every needed kind is recorded, ``MISSING_EXIT`` when a
    human still has to drop a file, 1 when a drop is ambiguous (two files of one kind).
    """
    unknown = [k for k in need if k not in KINDS]
    if unknown:
        raise ValueError(f"unknown kind(s) {unknown}, expected some of {sorted(KINDS)}")
    folder = init_incoming(dest)
    dropped: dict[str, list[str]] = {}
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if os.path.isfile(path) and name != "README.md":
            kind = classify(path)
            if kind:
                dropped.setdefault(kind, []).append(path)
    lines: list[str] = []
    missing: list[str] = []
    ambiguous = False
    recorded = read_inputs(dest)
    for kind in need:
        files = dropped.get(kind, [])
        if len(files) > 1:
            ambiguous = True
            lines.append(f"[AMBIGUOUS] {kind}: {', '.join(os.path.basename(f) for f in files)} — keep one")
            continue
        if files:
            entry = record(dest, kind, files[0])
            lines.append(format_entry(entry))
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            try:
                os.makedirs(os.path.join(dest, RECORDED_DIR), exist_ok=True)
                os.replace(files[0], os.path.join(dest, RECORDED_DIR, f"{stamp}_{os.path.basename(files[0])}"))
            except OSError as exc:
                # Recorded already (inputs.json, gate): say so, instead of letting a file lock
                # (Defender, OneDrive, an open editor) abort the check and hide that it happened.
                lines.append(f"  recorded, but could not move {os.path.basename(files[0])} to recorded/ ({exc}); "
                             "remove it from incoming/ by hand")
        elif kind in recorded:
            lines.append(f"[PRESENT] {kind}: {recorded[kind]['path']} (sha256 {recorded[kind]['sha256'][:12]})")
        else:
            missing.append(kind)
    for kind in missing:
        where = {
            "use_case": "portal Step 1 Edge Use Case Design -> Download use_case.yaml",
            "capability_manifest": "the device's `ne-device-agent assess` output (the file uploaded in portal Step 2 Target Device)",
            "scaffold": "portal Step 3 Model Strategy -> Build my own -> Script (.py)",
        }[kind]
        lines.append(f"[MISSING] {kind}: drop it into {folder} (from {where})")
    if ambiguous:
        return 1, lines
    if missing:
        lines.append(f"STOP: {len(missing)} input(s) missing. Drop them into {folder}, then run check again.")
        return MISSING_EXIT, lines
    return 0, lines


def format_entry(entry: dict[str, Any]) -> str:
    lines = [
        f"{entry['kind']}: {entry['path']}",
        f"  sha256        {entry['sha256']}",
        f"  source        {entry['source_name']}",
        f"  generated_at  {entry.get('generated_at') or '-'}",
    ]
    if entry.get("replaces_sha256"):
        change = "unchanged" if entry.get("unchanged") else "CHANGED"
        lines.append(f"  replaces      {entry['replaces_sha256']} ({change})")
    for f in entry["findings"]:
        lines.append(f"  [{f['level']}] {f['check']}: {f['detail']}")
    if entry.get("gate_action"):
        lines.append(f"  gate {entry['gate']!r} {entry['gate_action']} — answer it before the input is used")
    elif entry.get("unchanged"):
        lines.append(f"  gate {entry['gate']!r} unchanged (same file as before)")
    if entry.get("audits_reopened"):
        lines.append(f"  re-opened {entry['audits_reopened']}: re-run /usecase-audit at those checkpoints")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="intake", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record", help="copy, hash, check and gate an offline portal input")
    r.add_argument("--dest", required=True)
    r.add_argument("--kind", required=True, choices=sorted(KINDS))
    r.add_argument("--file", required=True, help="the downloaded file")
    r.add_argument("--no-gate", action="store_true", help="record without opening a gate (tests, re-hash only)")
    s = sub.add_parser("show", help="print every recorded input and its findings")
    s.add_argument("--dest", required=True)
    i = sub.add_parser("init", help="create inputs/incoming/ (the drop folder) and its README")
    i.add_argument("--dest", required=True)
    c = sub.add_parser("check", help="record dropped files; exit 3 naming each input still missing")
    c.add_argument("--dest", required=True)
    c.add_argument("--need", required=True, help="comma-separated kinds, e.g. use_case,capability_manifest")
    args = p.parse_args(argv)

    if args.cmd == "init":
        print(f"drop folder ready: {init_incoming(args.dest)} (see its README.md)")
        return 0
    if args.cmd == "check":
        try:
            code, lines = check(args.dest, [k.strip() for k in args.need.split(",") if k.strip()])
        except (OSError, ValueError) as exc:
            print(f"check refused: {exc}", file=sys.stderr)
            return 1
        print("\n".join(lines))
        return code
    if args.cmd == "show":
        entries = read_inputs(args.dest)
        if not entries:
            print("no inputs recorded")
        for entry in entries.values():
            print(format_entry(entry))
        return 0
    try:
        entry = record(args.dest, args.kind, args.file, open_gate=not args.no_gate)
    except (OSError, ValueError) as exc:
        print(f"intake refused: {exc}", file=sys.stderr)
        return 1
    print(format_entry(entry))
    return 1 if any(f["level"] == FAIL for f in entry["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
