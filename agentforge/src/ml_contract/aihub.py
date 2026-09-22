"""A Qualcomm AI Hub compile and profile job, offline, behind a hard human gate (ADR-0028 D-10).

The job runs under **the user's own Qualcomm account** and sends the trained model, and for INT8 the calibration
data, to **Qualcomm's cloud**. That is a third party, so nothing is sent before a human has approved a request
that names every file that leaves the machine. This does not touch the no-network seam to the portal
(ADR-0025 D-1): the ONNX was downloaded from the portal by a human, and the result is uploaded there by a human.

Three steps, each its own command:

1. ``request`` hashes the files that would leave, writes ``aihub/compile-request-<digest>.{md,json}`` and opens the
   hard gate of the same name. The digest is part of the gate id, so a request edited after the approval is a
   request with no approved gate.
2. A human answers the gate (``gate_state.py decide``).
3. ``run`` refuses unless that gate is approved and every file still has the hash the human saw. Then it runs the
   job and writes ``aihub/<device>/artifact.json``: SoC, SDK version, the artifact's sha256 and the profile
   report. The human uploads these in the portal's Optimize tab (NeuroEdge-Web ADR-0011 S-11, S-13).

The job runner is a callable. The default one imports ``qai_hub`` lazily, so this module imports without it.
**Unverified:** the default runner's ``qai_hub`` calls were written from the package's public documentation and
have never been executed here; no real job has been run. Treat its first real run as a test.

    python -m agentforge.src.ml_contract.aihub request --dest <model folder> --onnx <file> --device "<AI Hub device>"
                                                       [--precision fp16|int8 --calibration <folder>]
    python -m agentforge.src.ml_contract.aihub run     --dest <model folder> --request aihub/compile-request-<digest>.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import gates as gt
from .lock import LockError, read_lock
from .package import PACKAGE_FILE, ZIP_NAME

REQUEST_SCHEMA = "aihub-compile-request/1"
ARTIFACT_SCHEMA = "aihub-compile-artifact/1"
AIHUB_DIR = "aihub"
GATE_STAGE = "aihub-compile"  # not a stage of the ml sequence: an open request never blocks the model run
DESTINATION = "Qualcomm AI Hub: Qualcomm's cloud service, under your own Qualcomm account (QAI_HUB_API_TOKEN)"
TOKEN_ENV = "QAI_HUB_API_TOKEN"  # the NAME only; qai_hub reads the value from its own configuration
PRECISIONS = ("fp16", "int8")
TARGET_RUNTIME = "qnn_context_binary"

# (request, output folder) -> {"artifact": path, "soc": str, "sdk_version": str, "profile_report": path|None, "jobs": {}}
JobRunner = Callable[[dict[str, Any], Path], dict[str, Any]]


class AihubError(ValueError):
    """The request cannot be made, or the job may not run. Each problem is listed."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, path: Path) -> str:
    """``path`` relative to the model folder, as posix. Refuses a path, or a link, that leads out of it."""
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise AihubError([f"{path} is a link or is outside the model folder: copy the file into "
                          f"{root / AIHUB_DIR / 'input'} first, so that what is approved is what is sent"])
    return path.resolve().relative_to(root.resolve()).as_posix()


def _leaving(root: Path, onnx: Path, calibration: Path | None) -> dict[str, dict[str, Any]]:
    paths = [onnx]
    if calibration is not None:
        paths += sorted(p for p in calibration.rglob("*") if p.is_file())
    return {_inside(root, p): {"sha256": _sha256(p), "size": p.stat().st_size} for p in paths}


def _sealed_hashes(root: Path) -> set[str]:
    """The sha256 of every withheld test file that a training package in this folder sealed (ADR-0028 D-12)."""
    sealed: set[str] = set()
    for zip_path in sorted(root.glob(f"*/{ZIP_NAME}")):
        try:
            with zipfile.ZipFile(zip_path) as z:
                package = json.loads(z.read(PACKAGE_FILE))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            continue
        sealed |= set(((package.get("withheld") or {}).get("sealed") or {}).values())
    return sealed


def build_request(dest: str, onnx: str, *, device: str, precision: str = "fp16",
                  calibration: str | None = None) -> dict[str, Any]:
    """What would be sent, and where. Pure apart from reading and hashing the files; sends nothing."""
    root, model = Path(dest), Path(onnx)
    problems: list[str] = []
    if precision not in PRECISIONS:
        problems.append(f"precision {precision!r} is not one of {list(PRECISIONS)}")
    if not device.strip():
        problems.append("name the AI Hub device, exactly as AI Hub lists it")
    if not model.is_file() or model.suffix.lower() != ".onnx":
        problems.append(f"{onnx} is not an .onnx file: download the trained model from the portal's Ready tab")
    if precision == "int8" and (calibration is None or not Path(calibration).is_dir()):
        problems.append("INT8 needs --calibration <folder>: the calibration samples are sent with the model")
    if precision != "int8" and calibration is not None:
        problems.append("calibration data is only sent for INT8: drop --calibration, so nothing extra leaves")
    if problems:
        raise AihubError(problems)
    files = _leaving(root, model, Path(calibration) if calibration else None)
    test_files = sorted(name for name, meta in files.items() if meta["sha256"] in _sealed_hashes(root))
    if test_files:
        raise AihubError([f"{name} is withheld test data: calibration samples come from the train split only"
                          for name in test_files])
    try:
        lock = read_lock(str(root))
    except (OSError, LockError):
        lock = {}
    request = {
        "schema": REQUEST_SCHEMA,
        "use_case_id": lock.get("use_case_id"),
        "lock_sha256": lock.get("lock_sha256"),
        "destination": DESTINATION,
        "device": device.strip(),
        "precision": precision,
        "target_runtime": TARGET_RUNTIME,
        "onnx": _inside(root, model),
        "files_leaving": files,
    }
    request["digest"] = hashlib.sha256(json.dumps(request, sort_keys=True).encode("utf-8")).hexdigest()
    return request


def gate_id(request: dict[str, Any]) -> str:
    return f"{AIHUB_DIR}/compile-request-{request['digest'][:12]}.md"


def gate_text(request: dict[str, Any]) -> str:
    """The page the human approves. It names every file that leaves, and where it goes."""
    total = sum(meta["size"] for meta in request["files_leaving"].values())
    rows = [f"| `{name}` | {meta['size']:,} | `{meta['sha256']}` |" for name, meta in request["files_leaving"].items()]
    data = ("The calibration samples are **your training data**. They are sent with the model."
            if request["precision"] == "int8" else "No training or calibration data is sent: FP16 needs none.")
    return "\n".join([
        "# Approve sending these files to Qualcomm AI Hub",
        "",
        f"**Where they go:** {request['destination']}.",
        "This is a third party's cloud. It is not the NeuroEdge portal and not your device.",
        "",
        f"**What for:** compile for `{request['device']}` ({request['precision']}, `{request['target_runtime']}`), "
        "then profile the compiled model on that device in Qualcomm's device farm.",
        "",
        f"**Exactly {len(rows)} file(s) leave this machine, {total:,} bytes in total. Nothing else is sent.**",
        "",
        "| File (in the model folder) | Bytes | sha256 |",
        "|---|---|---|",
        *rows,
        "",
        data,
        "Qualcomm keeps uploaded models and job results in your account under its own terms. Read them first.",
        "",
        f"**Nothing is sent until this gate (`{gate_id(request)}`) is approved.** If a file changes after the "
        "approval, the job refuses to run and a new request is needed.",
        "",
    ])


def open_request(dest: str, request: dict[str, Any], *, open_gate: bool = True) -> dict[str, str]:
    """Write the request and its gate page, and open the hard gate."""
    folder = Path(dest) / AIHUB_DIR
    folder.mkdir(parents=True, exist_ok=True)
    page = Path(dest) / gate_id(request)
    page.write_text(gate_text(request), encoding="utf-8")
    page.with_suffix(".json").write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    action = gt.open_pending(dest, gate_id(request), stage=GATE_STAGE, opened_by="aihub-compile") if open_gate else ""
    return {"gate": gate_id(request), "gate_action": action, "request": page.with_suffix(".json").as_posix()}


def approved_request(dest: str, request_file: str) -> dict[str, Any]:
    """The request, only when a human approved exactly this one and no file has changed since."""
    request = json.loads(Path(request_file).read_text(encoding="utf-8"))
    body = {key: value for key, value in request.items() if key != "digest"}
    if request.get("schema") != REQUEST_SCHEMA or hashlib.sha256(
            json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest() != request.get("digest"):
        raise AihubError([f"{request_file} is not the request that was written: it was edited. Make a new request"])
    gate = gt.load(dest).gates.get(gate_id(request))
    if gate is None or gate.status != "approved":
        raise AihubError([f"gate {gate_id(request)!r} is {gate.status if gate else 'not open'}, not approved: "
                          "nothing is sent to Qualcomm before a human approves this request"])
    problems = []
    for name, meta in request["files_leaving"].items():
        path = Path(dest) / name
        if not path.is_file() or path.is_symlink() or _sha256(path) != meta["sha256"]:
            problems.append(f"{name} is not the file that was approved (missing, a link, or changed)")
    if problems:
        raise AihubError(problems + ["make a new request, so that what is approved is what is sent"])
    decision = gate.decisions[-1]
    return {**request, "approved_by": decision.identity, "approved_at": decision.timestamp}


def _qai_hub_runner(request: dict[str, Any], out: Path) -> dict[str, Any]:  # pragma: no cover - needs an account
    """The real job. Unverified: written from qai_hub's documentation, never executed here."""
    try:
        import qai_hub as hub  # lazy: this module imports without it
    except ImportError as exc:
        raise AihubError(["qai_hub is not installed: `pip install qai-hub`, run `qai-hub configure` with your own "
                          "API token, then run again"]) from exc
    root = Path(request["_dest"])
    device = hub.Device(request["device"])
    options = f"--target_runtime {request['target_runtime']}"
    calibration = None
    if request["precision"] == "int8":
        raise AihubError(["INT8 through this runner is not built yet: the calibration samples must be loaded into "
                          "the input dictionary AI Hub expects, and that depends on the model's inputs"])
    compile_job = hub.submit_compile_job(model=str(root / request["onnx"]), device=device, options=options,
                                         calibration_data=calibration)
    target = compile_job.get_target_model()
    artifact = Path(target.download(str(out / "model")))
    profile_job = hub.submit_profile_job(model=target, device=device)
    report = out / "profile.json"
    report.write_text(json.dumps(profile_job.download_profile(), indent=2, default=str), encoding="utf-8")
    attributes = getattr(device, "attributes", None) or []
    soc = next((a.split(":", 1)[1] for a in attributes if str(a).startswith("chipset:")), "unknown")
    return {"artifact": artifact, "soc": soc, "sdk_version": "unknown: read it from the profile report",
            "profile_report": report, "jobs": {"compile": compile_job.job_id, "profile": profile_job.job_id}}


def run_job(dest: str, request_file: str, *, runner: JobRunner | None = None) -> dict[str, Any]:
    """Run the approved job and write the artifact record. Refuses before the gate is approved."""
    request = approved_request(dest, request_file)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", request["device"]).strip("-").lower() or "device"
    out = Path(dest) / AIHUB_DIR / slug
    out.mkdir(parents=True, exist_ok=True)
    result = (runner or _qai_hub_runner)({**request, "_dest": str(Path(dest).resolve())}, out)
    artifact = Path(result["artifact"])
    if not artifact.is_file() or not artifact.resolve().is_relative_to(Path(dest).resolve()):
        raise AihubError([f"the job returned no artifact inside {out}"])
    report = Path(result["profile_report"]) if result.get("profile_report") else None
    record = {
        "schema": ARTIFACT_SCHEMA,
        "use_case_id": request["use_case_id"],
        "lock_sha256": request["lock_sha256"],
        "source_onnx": {"file": request["onnx"], "sha256": request["files_leaving"][request["onnx"]]["sha256"]},
        "device": request["device"],
        "soc": result["soc"],
        "sdk_version": result["sdk_version"],
        "precision": request["precision"],
        "target_runtime": request["target_runtime"],
        "artifact": {"file": artifact.resolve().relative_to(Path(dest).resolve()).as_posix(),
                     "sha256": _sha256(artifact), "size": artifact.stat().st_size},
        "profile_report": report.resolve().relative_to(Path(dest).resolve()).as_posix() if report else None,
        "profile_report_sha256": _sha256(report) if report else None,
        "jobs": result.get("jobs") or {},
        "gate": {"id": gate_id(request), "approved_by": request["approved_by"], "approved_at": request["approved_at"]},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (out / "artifact.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="aihub", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("request", help="name what would be sent, and open the hard gate. Sends nothing")
    q.add_argument("--dest", required=True, help="the model folder")
    q.add_argument("--onnx", required=True, help="the trained model.onnx, inside the model folder")
    q.add_argument("--device", required=True, help="the AI Hub device name, e.g. 'QCS6490 (Proxy)'")
    q.add_argument("--precision", default="fp16", choices=PRECISIONS)
    q.add_argument("--calibration", help="INT8 only: the folder of calibration samples, which is sent too")
    r = sub.add_parser("run", help="run the approved job (uses the network and your Qualcomm account)")
    r.add_argument("--dest", required=True)
    r.add_argument("--request", required=True, help="aihub/compile-request-<digest>.json")
    a = p.parse_args(argv)

    try:
        if a.cmd == "request":
            request = build_request(a.dest, a.onnx, device=a.device, precision=a.precision, calibration=a.calibration)
            opened = open_request(a.dest, request)
            print(gate_text(request))
            print(f"gate {opened['gate']!r} {opened['gate_action']}: STOP. Ask the human, record the decision with "
                  f"gate_state.py decide, then: aihub run --dest {a.dest} --request {opened['request']}")
            return 3
        record = run_job(a.dest, a.request)
    except AihubError as exc:
        print("refused:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    print(f"{record['artifact']['file']}  sha256 {record['artifact']['sha256']}")
    print(f"SoC {record['soc']} · SDK {record['sdk_version']} · profile {record['profile_report']}")
    print("Upload the artifact, artifact.json and the profile report in the portal's Optimize tab. You upload them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
