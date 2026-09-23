"""Offline inputs from the portal: record, hash and check them (ADR-0025 D-1, D-2, D-5; ADR-0027).

The model project never calls the portal. What it takes from the portal arrives as a file a human
downloaded. This module copies such a file into ``<dest>/inputs/``, records its hash in
``<dest>/inputs/inputs.json`` and checks it against the use-case lock where one exists. It never
edits the file, and it never decides a gate.

Only the **use case** is required and gated (ADR-0027 D-1): it is the contract between the portal,
the device and the model. The **capability manifest** and the **training scaffold** are optional.
When one is provided it is recorded and checked, and its findings are advisory; when it is not,
the run goes on (no device checks; M8's default template). Neither opens a gate nor re-arms an audit.
The portal's **model recommendation** (``model_recommendation.json``, ADR-0028 D-9) is the fourth kind, optional
and advisory in the same way: every finding on it is a WARN at most, and ``/model-select`` runs without it.

    python -m agentforge.src.ml_contract.intake record --dest <dest> --kind use_case --file <yaml>
    python -m agentforge.src.ml_contract.intake record --dest <dest> --kind capability_manifest --file <json>
    python -m agentforge.src.ml_contract.intake record --dest <dest> --kind scaffold --file <py|ipynb>
    python -m agentforge.src.ml_contract.intake record --dest <dest> --kind model_recommendation --file <json>
    python -m agentforge.src.ml_contract.intake show   --dest <dest>

The drop folder (ADR-0025 D-1a; renamed ``from-neuroedge/`` by ADR-0031 D-1). ``init`` creates
``<dest>/from-neuroedge/`` with a README saying what to put there and where each file comes from.
The old ``inputs/incoming/`` is still read, for one release, so an in-flight project does not break. ``check`` picks up what was dropped and records
it. It exits ``3`` only when a **required** input (the use case) is still missing, so the
orchestrator stops until the human has put it there. A missing optional input is reported and the
run continues:

    python -m agentforge.src.ml_contract.intake init  --dest <dest>
    python -m agentforge.src.ml_contract.intake check --dest <dest> --need use_case,capability_manifest
    python -m agentforge.src.ml_contract.intake check --dest <dest> --need scaffold
    python -m agentforge.src.ml_contract.intake check --dest <dest> --need model_recommendation

What comes back after training (ADR-0031 D-2) is recognised in the same folder and unpacked by the
run itself: the portal's **model package** (M9) to ``<arch>/runs/<run_id>/model-package/`` and its
**held-out result** (M10) beside it as ``portal_held_out.json``. ``<run_id>`` is read from the
package, never chosen by the operator, and a package built under another lock is refused:

    python -m agentforge.src.ml_contract.intake check --dest <dest> --need model_package
    python -m agentforge.src.ml_contract.intake check --dest <dest> --need held_out_result
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from typing import Any

from . import gates as gt
from .lock import LOCK_FILE, LockError, compare_use_case, normalise_unit, read_lock

INPUTS_DIR = "inputs"
INPUTS_FILE = "inputs.json"
INPUTS_SCHEMA = "ml-inputs/1"

# kind -> (stored path under <dest>, gate id, stage whose completion needs it)
KINDS: dict[str, tuple[str, str, str]] = {
    "use_case": ("inputs/use_case.yaml", "inputs/use_case.yaml", "destination"),
    "capability_manifest": ("inputs/capability_manifest.json", "inputs/capability_manifest.json", "destination"),
    "scaffold": ("inputs/scaffold/{name}", "inputs/scaffold", "model-build"),
    "model_recommendation": ("inputs/model_recommendation.json", "inputs/model_recommendation.json", "model-select"),
}

# Only the use case is required, gated, and able to fail an audit (ADR-0027 D-1). The other kinds
# are optional: recorded and checked when provided, never a reason to stop.
REQUIRED = ("use_case",)
OPTIONAL = ("capability_manifest", "scaffold", "model_recommendation")

# The audit gates whose checks can FAIL on an input of each kind. A changed input re-arms them, so
# an approval computed against the previous file cannot keep a stage satisfied (ADR-0025 D-4). An
# optional input only ever produces WARNs in the audit, so changing it re-arms nothing: a model
# built for one device can be tried against another without re-answering a gate (ADR-0027 D-2).
DEPENDENT_AUDITS: dict[str, tuple[str, ...]] = {
    "use_case": ("audit/M0", "audit/M4", "audit/M8", "audit/M11"),
    "capability_manifest": (),
    "scaffold": (),
    "model_recommendation": (),
}

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
_CONTEXT_RE = re.compile(r"NEUROEDGE_CONTEXT\s*=\s*json\.loads\(\s*r?(?:'''|\"\"\")(.*?)(?:'''|\"\"\")\s*\)", re.S)
# A manifest older than this is reported: the device may have been re-flashed since it was measured.
MANIFEST_MAX_AGE_DAYS = 30
# The portal's exported pick (NeuroEdge-Web ADR-0011 S-3). Older than this, the catalogue may have moved on.
RECOMMENDATION_SCHEMA = "model-recommendation/1"
RECOMMENDATION_MAX_AGE_DAYS = 30
RECOMMENDATION_STATES = ("fits", "does_not_fit", "unverified")


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
        if "stride_samples" in task_input:
            same("stride_samples", task_input.get("stride_samples"), ts["stride_samples"])
        else:
            out.append(_finding(WARN, "stride", f"context carries no stride; the lock's {ts['stride_samples']} is used"))
        ctx_channels = (task.get("timeseries") or {}).get("channels")
        if ctx_channels:
            same("channels (name, unit, reduce)",
                 [(c.get("name"), normalise_unit(c.get("unit")), c.get("reduce")) for c in ctx_channels],
                 [(c["name"], normalise_unit(c.get("unit")), c.get("reduce")) for c in ts["channels"]])
            if [c.get("definition") for c in ctx_channels] != [c.get("definition") for c in ts["channels"]]:
                out.append(_finding(WARN, "channel definitions", "differ from the lock's; meta.json takes the lock's"))
        else:
            out.append(_finding(WARN, "units / definitions / reduce",
                                "context carries none of them; meta.json takes them from the lock"))

    accuracy = (ctx.get("performance_targets") or {}).get("accuracy") or {}
    # The success criterion the model is built and gated against (ML-eval review, HIGH: only at_fpr
    # was compared, so a scaffold from a use case with another metric or bar passed clean).
    for key in ("metric", "min_value"):
        if key in accuracy:
            same(f"target {key}", accuracy[key], lock["target"].get(key))
        else:
            out.append(_finding(WARN, f"target {key}", f"context carries none; the lock's "
                                                       f"{lock['target'].get(key)!r} is used"))
    if "at_fpr" in accuracy:
        same("at_fpr", float(accuracy["at_fpr"]), float(lock["target"]["at_fpr"]))
    else:
        where = " (only in free-text notes)" if "fpr" in str(accuracy.get("notes", "")).lower() else ""
        out.append(_finding(WARN, "at_fpr", f"not a structured field{where}; the lock's "
                                            f"{lock['target']['at_fpr']} is used"))
    if not (ctx.get("data") or {}).get("path"):
        out.append(_finding(WARN, "data.path", "empty; the build reads data/contract/, never the scaffold's path"))
    if (ctx.get("model_hint") or {}).get("framework") in (None, "", "auto"):
        out.append(_finding(WARN, "framework", "model_hint.framework is 'auto'; model_proposed.md decides"))
    local_install = re.search(r"pip install -e [^\n]*neuroedge_return", text)
    if re.search(r"git\+https?://", text) and not local_install:
        out.append(_finding(WARN, "return writer install", "the install hint fetches neuroedge_return over the "
                            "network; install it from a local path or wheel instead"))
    if re.search(r"pip install (?![^\n]*==)[^\n]*torch", text):
        out.append(_finding(WARN, "dependencies", "the scaffold's pip install pins no versions"))
    if "write_return_package" in text:
        out.append(_finding(PASS, "return writer", "the scaffold writes the package through neuroedge_return"))
    else:
        out.append(_finding(FAIL, "return writer", "no write_return_package call; not the portal's return contract"))
    if "mlflow" in text:
        out.append(_finding(PASS, "mlflow", "the scaffold logs to MLflow; M8 reuses its run naming and tags "
                                            "(ADR-0026 D-3)"))
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
        # ADR-0030: the dataset and model are not redone after the lock, so only a model-contract field
        # FAILs here; an edit outside the contract (device, egress, prose) is a WARN, the lock still holds.
        out += [_finding(level, check, detail) for level, check, detail in compare_use_case(lock, data, raw)]
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


def _age_finding(generated: Any, max_days: int) -> dict[str, str]:
    if not generated:
        return _finding(WARN, "age", "no generated_at")
    try:
        made = datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
    except ValueError:
        return _finding(WARN, "age", f"unreadable generated_at {generated!r}")
    if made.tzinfo is None:
        made = made.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - made).days
    detail = f"generated {generated} ({age} days ago)"
    if age > max_days:
        return _finding(WARN, "age", f"{detail}; older than {max_days} days, export it again")
    return _finding(PASS, "age", detail)


def check_model_recommendation(raw: bytes, lock: dict[str, Any] | None,
                               manifest_id: str | None) -> list[dict[str, str]]:
    """The portal's recommendation against this run (ADR-0028 D-9). Advisory: WARN at most, never a refusal."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        return [_finding(WARN, "parse", f"not readable JSON ({exc}); /model-select runs without it")]
    if not isinstance(data, dict) or data.get("schema") != RECOMMENDATION_SCHEMA:
        got = data.get("schema") if isinstance(data, dict) else None
        return [_finding(WARN, "schema", f"schema is {got!r}, expected {RECOMMENDATION_SCHEMA!r}; "
                                         "/model-select runs without it")]
    pick = data.get("pick") if isinstance(data.get("pick"), dict) else None
    candidates = [c for c in data.get("candidates") or [] if isinstance(c, dict)]
    out = [_finding(PASS, "schema", f"{RECOMMENDATION_SCHEMA}, catalogue {data.get('catalogue_version')!r}, "
                                    f"{len(candidates)} candidate(s)")]
    if pick:
        out.append(_finding(PASS, "pick", f"{pick.get('id')!r} ({pick.get('loader')}, {pick.get('path')})"))
    else:
        out.append(_finding(WARN, "pick", "the user exported without picking; only the ratings are used"))
    odd = sorted({str(c.get("state")) for c in candidates} - set(RECOMMENDATION_STATES))
    if odd:
        out.append(_finding(WARN, "candidate states", f"unknown state(s) {odd}; those candidates bind nothing"))
    if lock is None:
        out.append(_finding(WARN, "use_case_id", "no use-case lock yet; not compared"))
    elif data.get("use_case_id") != lock.get("use_case_id"):
        out.append(_finding(WARN, "use_case_id", f"the recommendation is for {data.get('use_case_id')!r}, the lock "
                                                 f"is for {lock.get('use_case_id')!r}: it was exported for another "
                                                 "use case"))
    else:
        out.append(_finding(PASS, "use_case_id", f"{data.get('use_case_id')!r}"))
    theirs = data.get("capability_manifest_id")
    if theirs == manifest_id:
        out.append(_finding(PASS, "capability_manifest_id", f"{theirs!r}"))
    else:
        out.append(_finding(WARN, "capability_manifest_id", f"the recommendation was rated against {theirs!r}, this "
                                                            f"run recorded {manifest_id!r}: 'does not fit' may be "
                                                            "about another device"))
    out.append(_age_finding(data.get("generated_at"), RECOMMENDATION_MAX_AGE_DAYS))
    return out


def _recorded_manifest_id(dest: str) -> str | None:
    path = stored_path(dest, "capability_manifest")
    if path is None or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data.get("manifest_id") if isinstance(data, dict) else None


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
    """Absolute path of the recorded input of ``kind``, or None when none was provided."""
    entry = read_inputs(dest).get(kind)
    return os.path.join(dest, entry["path"]) if entry and entry.get("path") else None


def usable_scaffold(dest: str) -> str | None:
    """Absolute path of the recorded scaffold when M8 may use it, else None (ADR-0027 D-3).

    A scaffold with a FAIL finding was generated from another use case. It is never a reason to
    stop: M8 ignores it and builds from the default template.
    """
    entry = read_inputs(dest).get("scaffold")
    if not entry or not entry.get("path") or any(f["level"] == FAIL for f in entry.get("findings", [])):
        return None
    path = os.path.join(dest, entry["path"])
    return path if os.path.exists(path) else None


def record(dest: str, kind: str, src: str, *, open_gate: bool = True) -> dict[str, Any]:
    """Copy ``src`` into the model folder as the input of ``kind``, check it and record it. A
    required kind also gets its gate opened; an optional kind never does (ADR-0027 D-1)."""
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
    elif kind == "model_recommendation":
        findings = check_model_recommendation(raw, lock, _recorded_manifest_id(dest))
        try:
            generated_at = json.loads(raw.decode("utf-8")).get("generated_at")
        except (ValueError, AttributeError):
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
    if previous and previous.get("path") and previous["path"] != rel:
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
        "gate": gate_id if kind in REQUIRED else None,
        "findings": findings,
    }
    if previous and previous.get("sha256"):
        entry["replaces_sha256"] = previous["sha256"]
    inputs["inputs"][kind] = entry
    path = os.path.join(dest, INPUTS_DIR, INPUTS_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(inputs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    unchanged = previous is not None and previous.get("sha256") == entry["sha256"]
    entry["unchanged"] = unchanged
    if open_gate and not unchanged and kind in REQUIRED:
        entry["gate_action"] = gt.open_pending(dest, gate_id, stage=stage, opened_by="intake")
    if not unchanged:
        # Unconditional (not tied to open_gate): a stale audit approval is wrong whether or not
        # this input's own gate is being opened.
        entry["audits_reopened"] = gt.reopen_if_present(dest, DEPENDENT_AUDITS[kind])
    return entry


# --------------------------------------------------------------------------- the drop folder

#: ADR-0031 D-1: the folder is named for the product the operator carries files from. The old name
#: is still read (never created) for one release, so a project mid-run does not break.
INCOMING_DIR = "from-neuroedge"
RECORDED_DIR = "from-neuroedge/recorded"
LEGACY_INCOMING_DIR = "inputs/incoming"
MISSING_EXIT = 3  # "a human must drop a file": distinct from 1 (a check failed) and 0 (all present)

#: What comes back after training (ADR-0031 D-2). Not in KINDS: neither is copied to one stored
#: path. Each is unpacked into the run it belongs to, and that run is read from the file itself.
RETURN_KINDS = ("model_package", "held_out_result")
#: The four files the run reads from a portal model package. Anything else in the zip
#: (held_out_test.json, LICENCE-NOTICE.txt, package.json) is recorded and ignored, never refused.
PACKAGE_FILES = ("model.onnx", "meta.json", "model_artifact.json", "metrics.json")
PACKAGE_DIR = "model-package"
HELD_OUT_FILE = "portal_held_out.json"
HELD_OUT_SCHEMA = "portal-held-out-result/1"
#: A ceiling on what one package member may decompress to. The sizes in a zip are its author's
#: claim, so the read itself is bounded too.
MAX_MEMBER_BYTES = 2 * 1024 ** 3
WHERE = {
    "use_case": "portal Step 1 Edge Use Case Design -> Download use_case.yaml",
    "capability_manifest": "the device's `ne-device-agent assess` output (the file uploaded in portal Step 2 Target Device)",
    "scaffold": "portal Step 3 Model Strategy -> Build my own -> Script (.py)",
    "model_recommendation": "portal Step 3 Model Strategy: pick from the rated list, then export the recommendation",
    "model_package": "portal Step 3 Optimize -> Downloads -> Download all as .zip",
    "held_out_result": "portal Step 3 Train -> Held-out evaluation -> Download result",
}
# What the run does without each optional input (ADR-0027 D-2, D-3).
ABSENT_MEANS = {
    "capability_manifest": "no device-fit checks here; the device is assessed at deployment",
    "scaffold": "M8 builds from the default template",
    "model_recommendation": "/model-select proposes from the data and the task alone, exactly as before",
}

INCOMING_README = """# What NeuroEdge gives this run

`/agentforge-ml` never calls the portal. Download these files from the portal (or the device) and
drop them in this folder. The run records each one with its hash, then moves it to `recorded/`.
What this run gives back to the portal is staged in `../to-neuroedge/`.

Only the **use case** is required: the run stops at M0 until it is here, and asks you to confirm it
at a gate. The others are **optional**. Drop one and it is used. Leave it out and the run goes
on without it. They can be added or replaced at any time without re-answering a gate.

| File | Needed from | Where to get it | Recognised as |
|---|---|---|---|
| the use case (`<use-case-id>.yaml`), **required** | M0 | Portal **Step 1 · Edge Use Case Design** → validate the spec → **Download use_case.yaml** | any `*.yaml` / `*.yml` with a top-level `id:` and `task:` |
| the device capability manifest, *optional* (advisory device-fit warnings) | M0 | The target device's assessment: `ne-device-agent assess --local` writes `capability_manifest.json`, the same file uploaded to the portal in **Step 2 · Target Device** | any `*.json` with `manifest_id` or `device_profile_id` |
| the training scaffold (`neuroedge_train_<id>.py`), *optional* (without it M8 uses the default template) | M8 | Portal **Step 3 · Model Strategy** → *Build my own* → **Script (.py)** (a notebook also works) | any `*.py` / `*.ipynb` containing `NEUROEDGE_CONTEXT` |
| the portal's model recommendation (`model_recommendation.json`), *optional* (advisory; `/model-select` must answer it) | M7 | Portal **Step 3 · Model Strategy**: pick from the rated list, then export the recommendation | any `*.json` whose `schema` is `model-recommendation/1` |

Check what is here and what is missing:

    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need use_case,capability_manifest
    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need scaffold
    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need model_recommendation

One file per kind. If two files of the same kind are here, `check` stops and names both; remove the
one you do not want. A newer download of a file already recorded replaces it. For the use case, its
gate and every audit are then asked again, and the lock must be rebuilt.

## What comes back after training

| File | Needed by | Where to get it | Recognised as |
|---|---|---|---|
| the portal's model package (`<use-case-id>-model-package.zip`) | M9 | Portal **Step 3 · Optimize** → *Downloads* → **Download all as .zip** | a `*.zip` holding `model_artifact.json` (and `model.onnx`, `meta.json`, `metrics.json`) |
| the held-out result (`*.json`) | M10 | Portal **Step 3 · Train** → *Held-out evaluation* → **Download result** | a `*.json` whose `eval_split` is `held_out_test` |

Drop either here as it is: **never unzip the package yourself, and never pick a run id.** The run
reads the run id from the package's own `model_artifact.json` and unpacks it to
`<arch>/runs/<run_id>/model-package/`; the held-out result goes beside it as `portal_held_out.json`,
matched to its package by the model's hash. A package whose `lock_sha256` is not this project's lock
is refused, naming both hashes, and left here; nothing is written under `<arch>/runs/`.

    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need model_package
    python -m agentforge.src.ml_contract.intake check --dest <this model folder> --need held_out_result
"""


def init_incoming(dest: str) -> str:
    """Create ``<dest>/from-neuroedge/`` and its README. Idempotent; returns the folder path."""
    folder = os.path.join(dest, INCOMING_DIR)
    os.makedirs(folder, exist_ok=True)
    readme = os.path.join(folder, "README.md")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as fh:
            fh.write(INCOMING_README)
    return folder


def drop_folders(dest: str) -> list[str]:
    """Every folder a human may have dropped a file into: ``from-neuroedge/``, then the old name."""
    folders = [init_incoming(dest)]
    legacy = os.path.join(dest, LEGACY_INCOMING_DIR)
    if os.path.isdir(legacy):
        folders.append(legacy)
    return folders


def _held_out_evidence(data: Any) -> dict[str, Any] | None:
    """The evidence block of a portal held-out result, or None when ``data`` is not one.

    The portal's download nests it under ``evidence``; a bare evidence block is accepted too. The
    split is required whatever the schema says: a number measured on val, the split the threshold
    was chosen on, is never filed as held-out evidence (ml-eval review, HIGH).
    """
    if not isinstance(data, dict):
        return None
    evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else data
    return evidence if evidence.get("eval_split") == "held_out_test" else None


def classify(path: str) -> str | None:
    """Which input kind a dropped file is, from its content (never its name alone), or None."""
    name = os.path.basename(path).lower()
    if name.endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as zf:
                return "model_package" if "model_artifact.json" in zf.namelist() else None
        except (OSError, zipfile.BadZipFile):
            return None
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
        if isinstance(data, dict) and str(data.get("schema", "")).startswith("model-recommendation/"):
            return "model_recommendation"
        if _held_out_evidence(data) is not None:
            return "held_out_result"
        ok = isinstance(data, dict) and (data.get("manifest_id") or data.get("device_profile_id"))
        return "capability_manifest" if ok else None
    if name.endswith((".py", ".ipynb")):
        try:
            scaffold_context(scaffold_text(raw, name))
        except ValueError:
            return None
        return "scaffold"
    return None


# --------------------------------------------------------------------------- after training (ADR-0031 D-2)


class ReturnRefused(ValueError):
    """A model package or held-out result this run will not unpack. Nothing was written."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _run_folder_stamp(created_at: Any) -> str | None:
    """``2026-09-23T06:47:11.83+00:00`` -> ``20260923T064711Z``, the portal's run-folder form."""
    try:
        made = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if made.tzinfo is None:
        made = made.replace(tzinfo=timezone.utc)
    return made.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _extras(artifact: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    extras = artifact.get("extras") if isinstance(artifact.get("extras"), dict) else {}
    run = extras.get("package_run") if isinstance(extras.get("package_run"), dict) else {}
    return extras, run


def package_run_id(artifact: dict[str, Any]) -> str | None:
    """The run a portal package belongs to, read from its own ``model_artifact.json``.

    ``extras.package_run_id``, else the portal runner's ``extras.package_run.run_id``, else
    ``created_at`` in the portal's run-folder form. Never the operator's choice: an operator
    choosing a run id is an operator inventing provenance (ADR-0031 D-2). An id that is not a plain
    folder name is refused rather than sanitised -- it names a folder this run writes into.
    """
    extras, run = _extras(artifact)
    for value in (extras.get("package_run_id"), run.get("run_id")):
        if isinstance(value, str) and value:
            return value if _SAFE_ID.match(value) else None
    return _run_folder_stamp(artifact.get("created_at")) if artifact.get("created_at") else None


def _package_lock(artifact: dict[str, Any]) -> str | None:
    extras, run = _extras(artifact)
    value = extras.get("lock_sha256") or run.get("lock_sha256")
    return value if isinstance(value, str) and value else None


def _package_arch(dest: str, artifact: dict[str, Any]) -> str | None:
    """The architecture folder the package was trained from: as the portal recorded it, else the project's own."""
    from .handoff import architecture_of  # noqa: PLC0415 - handoff imports nothing from here

    extras, run = _extras(artifact)
    named = run.get("arch") or extras.get("arch")
    if isinstance(named, str) and _SAFE_ID.match(named) and os.path.isdir(os.path.join(dest, named)):
        return named
    return architecture_of(dest)


def _read_member(zf: zipfile.ZipFile, name: str) -> bytes:
    info = zf.getinfo(name)
    if info.file_size > MAX_MEMBER_BYTES:
        raise ReturnRefused([f"{name} declares {info.file_size} bytes, over the {MAX_MEMBER_BYTES}-byte ceiling"])
    with zf.open(info) as fh:
        data = fh.read(MAX_MEMBER_BYTES + 1)
    if len(data) > MAX_MEMBER_BYTES:
        raise ReturnRefused([f"{name} decompresses past the {MAX_MEMBER_BYTES}-byte ceiling"])
    return data


def sha256_path(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_entry(dest: str, kind: str, entry: dict[str, Any]) -> dict[str, Any]:
    inputs = _read_inputs(dest)
    previous = inputs["inputs"].get(kind)
    if previous and previous.get("sha256"):
        entry["replaces_sha256"] = previous["sha256"]
    inputs["inputs"][kind] = dict(entry)
    os.makedirs(os.path.join(dest, INPUTS_DIR), exist_ok=True)
    with open(os.path.join(dest, INPUTS_DIR, INPUTS_FILE), "w", encoding="utf-8") as fh:
        json.dump(inputs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    entry["unchanged"] = bool(previous) and previous.get("sha256") == entry["sha256"]
    return entry


def unpack_model_package(dest: str, src: str) -> dict[str, Any]:
    """Unpack the portal's model package into ``<arch>/runs/<run_id>/model-package/`` (ADR-0031 D-2).

    The zip is never trusted beyond its bytes: only the four named members are read (never
    ``extractall``), their hashes are recorded, and the unpack is refused -- with nothing written --
    when the package's ``lock_sha256`` is not this project's lock. Raises :class:`ReturnRefused`.
    """
    lock, lock_error = _lock_or_none(dest)
    if lock is None:
        raise ReturnRefused([lock_error or "no use_case.lock.json: a package cannot be checked against a lock "
                                           "that does not exist (M0 locks the use case)"])
    try:
        zf = zipfile.ZipFile(src)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReturnRefused([f"{os.path.basename(src)} is not a readable zip ({exc})"]) from exc
    with zf:
        names = zf.namelist()
        missing = [n for n in PACKAGE_FILES if n not in names]
        if missing:
            raise ReturnRefused([f"the package has no {', '.join(missing)}; a model package carries "
                                 f"{', '.join(PACKAGE_FILES)} at its top level"])
        blobs = {n: _read_member(zf, n) for n in PACKAGE_FILES}
        extra = sorted(n for n in names if n not in PACKAGE_FILES and not n.endswith("/"))
    try:
        artifact = json.loads(blobs["model_artifact.json"].decode("utf-8"))
    except ValueError as exc:
        raise ReturnRefused([f"model_artifact.json is not readable JSON ({exc})"]) from exc
    if not isinstance(artifact, dict):
        raise ReturnRefused(["model_artifact.json is not a JSON object"])

    problems = []
    theirs = _package_lock(artifact)
    if theirs is None:
        problems.append("the package's model_artifact.json carries no lock_sha256, so nothing says which "
                        "contract it was trained under")
    elif theirs != lock["lock_sha256"]:
        problems.append(f"the package was trained under lock {theirs}, this project's lock is "
                        f"{lock['lock_sha256']}: it is another use case's model, or one trained before a re-lock")
    if artifact.get("use_case_id") and artifact["use_case_id"] != lock.get("use_case_id"):
        problems.append(f"the package is for use case {artifact['use_case_id']!r}, the lock is for "
                        f"{lock.get('use_case_id')!r}")
    run_id = package_run_id(artifact)
    if run_id is None:
        problems.append("the package names no usable run (no extras.package_run_id, extras.package_run.run_id "
                        "or readable created_at); a run id is never chosen by hand")
    arch = _package_arch(dest, artifact)
    if arch is None:
        problems.append("cannot tell which architecture folder the package belongs to: the portal recorded none "
                        "that exists here, and the project holds more than one (see `handoff show`)")
    if problems:
        raise ReturnRefused(problems)

    rel = f"{arch}/runs/{run_id}/{PACKAGE_DIR}"
    target = os.path.join(dest, rel)
    os.makedirs(target, exist_ok=True)
    for name, data in blobs.items():
        with open(os.path.join(target, name), "wb") as fh:
            fh.write(data)
    findings = [_finding(PASS, "lock_sha256", f"{theirs[:12]} is this project's lock"),
                _finding(PASS, "run_id", f"{run_id!r}, read from the package's model_artifact.json")]
    if extra:
        findings.append(_finding(PASS, "extra files", f"recorded and not read: {extra}"))
    return _write_entry(dest, "model_package", {
        "kind": "model_package",
        "path": rel,
        "sha256": sha256_path(src),
        "source_name": os.path.basename(src),
        "generated_at": artifact.get("created_at"),
        "recorded_at": _now(),
        "gate": None,
        "run_id": run_id,
        "arch": arch,
        "lock_sha256": theirs,
        "files": {n: hashlib.sha256(d).hexdigest() for n, d in blobs.items()},
        "ignored": extra,
        "findings": findings,
    })


def record_held_out(dest: str, src: str) -> dict[str, Any]:
    """Place the portal's held-out result beside the model package it scored (ADR-0031 D-2).

    The result carries the evaluation's own run id, which is not the package's. It is matched to the
    recorded package by the hash of the ONNX model it evaluated, so no run id is chosen by hand.
    Raises :class:`ReturnRefused` with nothing written.
    """
    with open(src, "rb") as fh:
        raw = fh.read()
    try:
        evidence = _held_out_evidence(json.loads(raw.decode("utf-8")))
    except ValueError as exc:
        raise ReturnRefused([f"{os.path.basename(src)} is not readable JSON ({exc})"]) from exc
    if evidence is None:
        raise ReturnRefused(["not a held-out result: its eval_split is not held_out_test"])
    lock, lock_error = _lock_or_none(dest)
    problems = []
    if lock is None:
        problems.append(lock_error or "no use_case.lock.json to check the result against")
    elif evidence.get("lock_sha256") != lock["lock_sha256"]:
        problems.append(f"the result was measured under lock {evidence.get('lock_sha256')}, this project's lock "
                        f"is {lock['lock_sha256']}")
    package = read_inputs(dest).get("model_package")
    onnx = evidence.get("model_onnx_sha256")
    if not package:
        problems.append("no model package is recorded yet: drop the portal's model package first (M9), so the "
                        "result has a run to belong to")
    elif not onnx:
        problems.append("the result names no model_onnx_sha256, so it cannot be tied to a model package")
    elif (package.get("files") or {}).get("model.onnx") != onnx:
        problems.append(f"the result evaluated model.onnx {onnx[:12]}, the recorded package's model.onnx is "
                        f"{str((package.get('files') or {}).get('model.onnx'))[:12]} (run {package.get('run_id')}): "
                        "download the package that was evaluated, or the result for this package")
    if problems:
        raise ReturnRefused(problems)

    rel = f"{package['arch']}/runs/{package['run_id']}/{HELD_OUT_FILE}"
    target = os.path.join(dest, rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as fh:
        fh.write(raw)
    headline = evidence.get("headline") if isinstance(evidence.get("headline"), dict) else {}
    meets = headline.get("meets_target")
    return _write_entry(dest, "held_out_result", {
        "kind": "held_out_result",
        "path": rel,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "source_name": os.path.basename(src),
        "generated_at": evidence.get("evaluated_at"),
        "recorded_at": _now(),
        "gate": None,
        "run_id": package["run_id"],
        "arch": package["arch"],
        "evaluation_run_id": evidence.get("evaluation_run_id"),
        "findings": [_finding(PASS, "model", f"model.onnx {onnx[:12]} is run {package['run_id']}'s"),
                     _finding(PASS if meets else WARN, "meets_target",
                              f"{meets!r} -- a held-out number is reported at M10, never tuned against")],
    })


def _unpack(dest: str, kind: str, path: str) -> dict[str, Any]:
    return unpack_model_package(dest, path) if kind == "model_package" else record_held_out(dest, path)


def check(dest: str, need: list[str]) -> tuple[int, list[str]]:
    """Record every needed input that was dropped, and report what is still missing.

    Returns ``(exit_code, lines)``: 0 when every **required** kind asked for is recorded,
    ``MISSING_EXIT`` when a human still has to drop one, 1 when a drop is ambiguous (two files of
    one kind) or refused. A missing optional kind is reported as ``[ABSENT]`` and never stops the
    run. A return kind (model package, held-out result) is required whenever it is asked for: the
    milestone that asks for it cannot go on without it.
    """
    unknown = [k for k in need if k not in KINDS and k not in RETURN_KINDS]
    if unknown:
        raise ValueError(f"unknown kind(s) {unknown}, expected some of {sorted([*KINDS, *RETURN_KINDS])}")
    folders = drop_folders(dest)
    folder = folders[0]
    dropped: dict[str, list[str]] = {}
    for where in folders:
        for name in sorted(os.listdir(where)):
            path = os.path.join(where, name)
            if os.path.isfile(path) and name != "README.md":
                kind = classify(path)
                if kind:
                    dropped.setdefault(kind, []).append(path)
    lines: list[str] = []
    if len(folders) > 1:
        lines.append(f"[NOTE] {LEGACY_INCOMING_DIR}/ is the old name of {INCOMING_DIR}/ and is read for one "
                     f"more release; drop new files in {INCOMING_DIR}/")
    missing: list[str] = []
    ambiguous = refused = False
    recorded = read_inputs(dest)
    for kind in need:
        files = dropped.get(kind, [])
        if len(files) > 1:
            ambiguous = True
            lines.append(f"[AMBIGUOUS] {kind}: {', '.join(os.path.basename(f) for f in files)} — keep one")
            continue
        if files:
            if kind in RETURN_KINDS:
                try:
                    entry = _unpack(dest, kind, files[0])
                except (OSError, ReturnRefused) as exc:
                    refused = True
                    lines.append(f"[REFUSED] {kind}: {os.path.basename(files[0])} is left where it is; "
                                 "nothing was written")
                    lines += [f"  - {p}" for p in getattr(exc, "problems", [str(exc)])]
                    continue
            else:
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
                             "remove it from the drop folder by hand")
        elif kind in recorded and recorded[kind].get("path"):  # a pre-ADR-0027 waiver has no path: absent
            lines.append(f"[PRESENT] {kind}: {recorded[kind]['path']} (sha256 {recorded[kind]['sha256'][:12]})")
        else:
            missing.append(kind)
    for kind in missing:
        if kind in REQUIRED or kind in RETURN_KINDS:
            lines.append(f"[MISSING] {kind}: drop it into {folder} (from {WHERE[kind]})")
        else:
            lines.append(f"[ABSENT] {kind}: optional, not provided ({ABSENT_MEANS[kind]}). "
                         f"To use one, drop it into {folder} (from {WHERE[kind]})")
    if ambiguous or refused:
        return 1, lines
    required_missing = [k for k in missing if k in REQUIRED or k in RETURN_KINDS]
    if required_missing:
        lines.append(f"STOP: {len(required_missing)} required input(s) missing. Drop them into {folder}, "
                     "then run check again.")
        return MISSING_EXIT, lines
    return 0, lines


def format_entry(entry: dict[str, Any]) -> str:
    if not entry.get("path"):  # a waiver recorded before ADR-0027: the input is simply absent
        return f"{entry['kind']}: not provided"
    lines = [
        f"{entry['kind']}: {entry['path']}",
        f"  sha256        {entry['sha256']}",
        f"  source        {entry['source_name']}",
        f"  generated_at  {entry.get('generated_at') or '-'}",
    ]
    if entry.get("run_id"):
        where = f"{entry['arch']}/runs/" if entry.get("arch") else ""
        lines.append(f"  run           {where}{entry['run_id']} (read from the file, never chosen)")
    if entry.get("replaces_sha256"):
        change = "unchanged" if entry.get("unchanged") else "CHANGED"
        lines.append(f"  replaces      {entry['replaces_sha256']} ({change})")
    for f in entry["findings"]:
        lines.append(f"  [{f['level']}] {f['check']}: {f['detail']}")
    if entry.get("gate_action"):
        lines.append(f"  gate {entry['gate']!r} {entry['gate_action']} — answer it before the input is used")
    elif entry.get("kind") in RETURN_KINDS:
        lines.append("  returned by the portal: unpacked by the run, no gate of its own")
    elif not entry.get("gate"):
        lines.append("  optional input: no gate, and its findings are advisory")
    elif entry.get("unchanged"):
        lines.append(f"  gate {entry['gate']!r} unchanged (same file as before)")
    if entry.get("audits_reopened"):
        lines.append(f"  re-opened {entry['audits_reopened']}: re-run /usecase-audit at those checkpoints")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="intake", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record", help="copy, hash and check an offline portal input (the use case is also gated)")
    r.add_argument("--dest", required=True)
    r.add_argument("--kind", required=True, choices=sorted(KINDS))
    r.add_argument("--file", required=True, help="the downloaded file")
    r.add_argument("--no-gate", action="store_true", help="record without opening a gate (tests, re-hash only)")
    s = sub.add_parser("show", help="print every recorded input and its findings")
    s.add_argument("--dest", required=True)
    i = sub.add_parser("init", help="create from-neuroedge/ (the drop folder) and its README")
    i.add_argument("--dest", required=True)
    c = sub.add_parser("check", help="record dropped files; exit 3 naming each REQUIRED input still missing")
    c.add_argument("--dest", required=True)
    c.add_argument("--need", required=True, help="comma-separated kinds, e.g. use_case,capability_manifest "
                                                 "or model_package,held_out_result")
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
    # An optional input's FAIL is advisory (M8 ignores a mismatched scaffold), so it is not an error exit.
    return 1 if args.kind in REQUIRED and any(f["level"] == FAIL for f in entry["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
