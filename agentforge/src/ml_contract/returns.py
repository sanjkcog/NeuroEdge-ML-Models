"""M11 `return`: does the portal need a return package at all? (ADR-0033)

A return package is how a model trained OUTSIDE the portal enters it: the owner uploads it on the portal's
**Bring a trained model → Finished training return package** card. A model the portal trained itself --
the training-package runner, or the portal's own fine-tune -- is already registered there by the run that
produced it (NeuroEdge-Web `package_run_service.run_and_register`, read at Web `9eed61b`). Uploading it
back is not refused: it creates a second run of the same model, marked `portal-upload`, that becomes the
portal's "latest" model and has lost the link to the portal run and its held-out evaluation. So M11 first
decides where the model was trained:

* **portal** -- the package was recorded by `intake` from `from-neuroedge/` (a portal download) AND its
  own `model_artifact.json` does not contradict that: `extras.package_run.runner` is a portal runner, or
  absent while the M7 runner is a portal runner. The `return-upload` gate is then recorded automatically,
  no upload zip is built, and the owner is pointed at the portal's **Compare Runs → Promote** for the run.
* **offline** -- no portal evidence at all and the M7 runner is `offline`: build the upload zip, as before.
* **ask** -- anything else (no package, evidence that disagrees with M7, a hand-placed package on a portal
  runner). The orchestrator asks the owner "portal or offline?" and records their answer with
  ``portal`` or ``build`` with ``--identity <who>``. It never guesses.

    python -m agentforge.src.ml_contract.returns check  --dest <dest>              # exit 0 portal, 2 offline, 3 ask
    python -m agentforge.src.ml_contract.returns portal --dest <dest> [--identity <who> --reason "<words>"]
    python -m agentforge.src.ml_contract.returns build  --dest <dest> [--identity <who> --reason "<words>"]

Nothing here calls the portal (ADR-0025 D-1).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import zipfile
from datetime import datetime, timezone
from typing import Any

from . import gates
from .handoff import HANDOFF_JSON, SENT_DIR, TO_DIR, _latest_run, architecture_of, runner_of

GATE_ID = "return-upload"
STAGE = "return"
RETURN_JSON = "return.json"
AUTOMATIC_IDENTITY = "agentforge-ml return route (automatic)"
PORTAL_RUNNERS = ("portal-package", "portal-finetune")
PACKAGE_FILES = ("model.onnx", "meta.json", "model_artifact.json", "metrics.json")
PROMOTE_SCREEN = "Step 3 · Prepare Model → Compare Runs → Promote"
UPLOAD_SCREEN = "Step 3 · Prepare Model → Bring a trained model → Finished training return package"

EXIT = {"portal": 0, "offline": 2, "ask": 3}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def route(dest: str) -> dict[str, Any]:
    """Where the model M11 would return was trained: ``portal``, ``offline`` or ``ask``, with the evidence."""
    runner = runner_of(dest)
    arch = architecture_of(dest)
    run_id = _latest_run(dest, arch) if arch else None
    out: dict[str, Any] = {"route": "ask", "runner": runner, "arch": arch, "run_id": run_id, "evidence": []}
    ev: list[str] = out["evidence"]
    if not arch or not run_id:
        ev.append("no model package found under <arch>/runs/<run_id>/model-package/ (M9 not done, or the "
                  "architecture is ambiguous)")
        return out
    rel = f"{arch}/runs/{run_id}/model-package"
    package = os.path.join(dest, rel)
    if not os.path.isfile(os.path.join(package, "model_artifact.json")):
        ev.append(f"{rel}/model_artifact.json is missing")
        return out

    recorded = (_read_json(os.path.join(dest, "inputs", "inputs.json")).get("inputs") or {}).get("model_package") or {}
    from_portal = recorded.get("run_id") == run_id and recorded.get("arch") == arch
    extras = _read_json(os.path.join(package, "model_artifact.json")).get("extras") or {}
    package_run = extras.get("package_run") if isinstance(extras.get("package_run"), dict) else {}
    trained_by = package_run.get("runner")
    out["portal_run_id"] = package_run.get("run_id") or (run_id if from_portal else None)

    ev.append(f"M7 runner: {runner or 'not recorded'}")
    ev.append(f"package {rel}: " + ("recorded by intake from from-neuroedge/ (a portal download)" if from_portal
                                    else "not recorded by intake (placed in the folder, not downloaded from the portal)"))
    ev.append(f"model_artifact.json extras.package_run.runner: {trained_by or 'absent'}")

    if from_portal:
        if trained_by in PORTAL_RUNNERS or (trained_by is None and runner in PORTAL_RUNNERS):
            out["route"] = "portal"
        else:
            ev.append("contradiction: downloaded from the portal, but nothing says the portal trained it")
    elif trained_by in PORTAL_RUNNERS:
        ev.append("contradiction: the package says the portal trained it, but it was not recorded as a portal download")
    elif runner == "offline":
        out["route"] = "offline"
    else:
        ev.append(f"the M7 runner is {runner!r} but the package was not downloaded from the portal: it may be "
                  "the RUN_ON_GPU.md fallback, trained offline")
    return out


def _write_return(dest: str, arch: str, run_id: str, record: dict[str, Any]) -> str:
    path = os.path.join(dest, arch, "runs", run_id, RETURN_JSON)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    return os.path.relpath(path, dest).replace(os.sep, "/")


def _withdraw_staged_upload(dest: str) -> list[str]:
    """A portal-trained model needs no return upload: remove an unsent staged copy and an unsent build."""
    notes: list[str] = []
    record = _read_json(os.path.join(dest, HANDOFF_JSON))
    entry = (record.get("artifacts") or {}).get("04")
    if entry and not entry.get("sent_at"):
        staged = os.path.join(dest, TO_DIR, entry.get("staged_name", ""))
        if os.path.isfile(staged):
            os.remove(staged)
            notes.append(f"removed the unsent staged copy {TO_DIR}/{entry['staged_name']}")
        del record["artifacts"]["04"]
        record["updated_at"] = _now()
        with open(os.path.join(dest, HANDOFF_JSON), "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2)
    elif entry and entry.get("sent_at"):
        notes.append(f"04 was already uploaded ({entry.get('registration_id')}); left in {SENT_DIR}/ as the record")
    return notes


def portal(dest: str, *, identity: str | None = None, reason: str | None = None) -> tuple[int, list[str]]:
    """Record that the portal trained the model: the gate closes and nothing is uploaded.

    Without ``identity`` this is the automatic path and needs ``route`` to say ``portal``. With it, it is the
    owner's answer to the "portal or offline?" question, and is recorded as theirs.
    """
    r = route(dest)
    if identity is None and r["route"] != "portal":
        return 3, ["the evidence does not show the portal trained this model; ask the owner and pass --identity",
                   *(f"  {e}" for e in r["evidence"])]
    if not r["arch"] or not r["run_id"]:
        return 1, ["no model package to record a return for", *(f"  {e}" for e in r["evidence"])]
    arch, run_id = r["arch"], r["run_id"]
    portal_run = r.get("portal_run_id") or run_id
    lines = [f"route: portal — the portal trained this model (portal run {portal_run}); no return upload",
             *(f"  {e}" for e in r["evidence"])]
    upload = os.path.join(dest, arch, "runs", run_id, "return", "upload.zip")
    if os.path.isfile(upload):
        os.remove(upload)
        lines.append(f"  removed {arch}/runs/{run_id}/return/upload.zip: a second copy would register a duplicate run")
    lines += [f"  {n}" for n in _withdraw_staged_upload(dest)]
    package = os.path.join(dest, arch, "runs", run_id, "model-package")
    why = reason or "the portal trained this model and already holds it; a return upload would duplicate the run"
    _write_return(dest, arch, run_id, {
        "schema": "agentforge-ml-return/1", "route": "portal", "decided_at": _now(),
        "decided_by": identity or AUTOMATIC_IDENTITY, "reason": why, "evidence": r["evidence"],
        "arch": arch, "run_id": run_id, "portal_run_id": portal_run,
        "model_onnx_sha256": _sha256(os.path.join(package, "model.onnx"))
        if os.path.isfile(os.path.join(package, "model.onnx")) else None,
        "upload": None, "next": f"{PROMOTE_SCREEN}: promote run {portal_run} so every later step uses it",
    })
    gate_reason = f"route portal (portal run {portal_run}): {why}"
    if identity:
        gates.open_pending(dest, GATE_ID, stage=STAGE, opened_by="agentforge-ml return")
        state = gates.load(dest)
        state.record_decision(GATE_ID, "approved", identity=identity, reason=gate_reason)
        state.save(os.path.join(dest, gates.GATES_FILE))
        outcome = f"approved by {identity}"
    else:
        outcome = gates.record_automatic(dest, GATE_ID, stage=STAGE, passed=True, reason=gate_reason,
                                         identity=AUTOMATIC_IDENTITY)
    lines += [f"gate '{GATE_ID}': {outcome}",
              f"NEXT (in the portal, not a gate): {PROMOTE_SCREEN} — run {portal_run}, model "
              f"{(_sha256(os.path.join(package, 'model.onnx'))[:12] + '…') if os.path.isfile(os.path.join(package, 'model.onnx')) else '?'}"]
    return 0, lines


def _validate(upload: str) -> dict[str, Any]:
    try:
        from neuroedge_return import validate_package  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError:
        return {"status": "not_available", "reason": "neuroedge_return is not installed here; not fetched (ADR-0025 D-1)"}
    try:
        report = validate_package(upload)
    except Exception as exc:  # noqa: BLE001 - the validator's failure is the report
        return {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}
    return {"status": "ran", "report": report if isinstance(report, (dict, list, str, bool)) else repr(report)}


def build(dest: str, *, identity: str | None = None, reason: str | None = None) -> tuple[int, list[str]]:
    """The offline route: build ``return/upload.zip``, validate it when the validator is installed, open the gate."""
    r = route(dest)
    if identity is None and r["route"] != "offline":
        return 3, [f"route is {r['route']!r}, not offline; build only on the offline route or with the owner's "
                   "--identity", *(f"  {e}" for e in r["evidence"])]
    if not r["arch"] or not r["run_id"]:
        return 1, ["no model package to return", *(f"  {e}" for e in r["evidence"])]
    arch, run_id = r["arch"], r["run_id"]
    package = os.path.join(dest, arch, "runs", run_id, "model-package")
    missing = [f for f in PACKAGE_FILES if not os.path.isfile(os.path.join(package, f))]
    if missing:
        return 1, [f"the package is missing {missing}: fix M9/M10, do not pack around it"]
    out_dir = os.path.join(dest, arch, "runs", run_id, "return")
    os.makedirs(out_dir, exist_ok=True)
    upload = os.path.join(out_dir, "upload.zip")
    with zipfile.ZipFile(upload, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in PACKAGE_FILES:
            zf.write(os.path.join(package, name), name)
        calibration = os.path.join(package, "calibration")
        for dirpath, dirnames, filenames in os.walk(calibration):
            dirnames.sort()
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                zf.write(full, os.path.relpath(full, package).replace(os.sep, "/"))
    validation = _validate(upload)
    rel = _write_return(dest, arch, run_id, {
        "schema": "agentforge-ml-return/1", "route": "offline", "decided_at": _now(),
        "decided_by": identity or AUTOMATIC_IDENTITY, "reason": reason, "evidence": r["evidence"],
        "arch": arch, "run_id": run_id,
        "upload": {"path": f"{arch}/runs/{run_id}/return/upload.zip", "sha256": _sha256(upload),
                   "contents": {n: _sha256(os.path.join(package, n)) for n in PACKAGE_FILES},
                   "calibration": "present" if os.path.isdir(os.path.join(package, "calibration")) else "absent"},
        "validate_package": validation, "portal_screen": UPLOAD_SCREEN, "registration_id": None,
    })
    action = gates.open_pending(dest, GATE_ID, stage=STAGE, opened_by="agentforge-ml return")
    return 0, [f"route: offline — built {arch}/runs/{run_id}/return/upload.zip ({_sha256(upload)[:12]}…)",
               f"  validate_package: {validation['status']}", f"  recorded in {rel}",
               f"gate '{GATE_ID}': {action} — the owner uploads it on {UPLOAD_SCREEN}"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, helptext in (("check", "say where the model was trained, with the evidence"),
                           ("portal", "record that the portal trained it: close the gate, upload nothing"),
                           ("build", "offline: build and validate the upload zip, open the gate")):
        a = sub.add_parser(name, help=helptext)
        a.add_argument("--dest", required=True, help="the model folder")
        if name != "check":
            a.add_argument("--identity", help="the owner, when this is their answer rather than the evidence's")
            a.add_argument("--reason", help="the owner's words")
    args = p.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):   # a Windows console cannot print every arrow in the output
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    if args.cmd == "check":
        r = route(args.dest)
        print(f"route: {r['route']}  (arch {r['arch']}, run {r['run_id']})")
        for e in r["evidence"]:
            print(f"  {e}")
        if r["route"] == "ask":
            print("ASK the owner: was this model trained on the portal or offline? Then `returns portal` or "
                  "`returns build` with --identity.")
        return EXIT[r["route"]]
    if args.identity is None and args.reason:
        print("--reason needs --identity: a reason is the owner's words", file=sys.stderr)
        return 2
    code, lines = (portal if args.cmd == "portal" else build)(args.dest, identity=args.identity, reason=args.reason)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
