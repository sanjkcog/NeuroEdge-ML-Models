"""M10 may accept the portal's held-out result instead of running ``eval.py`` again (ADR-0028 D-12).

The portal runs the package's own ``eval.py`` on the sealed test bundle (NeuroEdge-Web ADR-0011 S-10) and lets the
owner download the result: one JSON file holding the portal's evidence block and the full metrics ``eval.py``
wrote. Nothing here calls the portal (ADR-0025 D-1): the owner downloads the file, this checks it.

A result is accepted only when it is provably about THIS run:

* ``eval_split`` is ``held_out_test``, in the evidence and in the metrics;
* the lock is this run's lock;
* the test files the portal evaluated on are this run's test files, by sha256 (``data/splits/test.json`` and the
  files of the test-only units, as the package builder sealed them);
* the training package is the one in this folder, when it is still here.

Anything else, and M10 runs ``eval.py`` locally, exactly as before. Either way the KPI gate is M10's (D-11): this
module never decides whether the numbers are good enough.

    python -m agentforge.src.ml_contract.heldout accept --dest <model folder> --arch <Arch> --evidence <file.json>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .lock import LockError, read_lock
from .package import ZIP_NAME

EVIDENCE_SCHEMA = "portal-held-out-result/1"
ACCEPTED_FILE = "portal_held_out.json"
_TEST_SPLIT = "data/splits/test.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def problems_with(dest: str, arch: str, export: dict[str, Any]) -> list[str]:
    """Why this exported result cannot stand in for a local M10 run. Empty when it can."""
    root = Path(dest)
    if export.get("schema") != EVIDENCE_SCHEMA:
        return [f"schema is {export.get('schema')!r}, expected {EVIDENCE_SCHEMA!r}: this is not a portal held-out result"]
    evidence = export.get("evidence") if isinstance(export.get("evidence"), dict) else {}
    metrics = export.get("metrics") if isinstance(export.get("metrics"), dict) else {}
    problems: list[str] = []

    for where, block in (("evidence", evidence), ("metrics", metrics)):
        if block.get("eval_split") != "held_out_test":
            problems.append(f"{where}.eval_split is {block.get('eval_split')!r}, not 'held_out_test'")

    try:
        lock = read_lock(str(root))
    except (OSError, LockError) as exc:
        return problems + [f"no valid use-case lock in {root}: {exc}"]
    if evidence.get("lock_sha256") != lock["lock_sha256"]:
        problems.append("the result was produced under another lock: it is about a different use-case contract")

    sealed = evidence.get("test_files_sha256") if isinstance(evidence.get("test_files_sha256"), dict) else {}
    if _TEST_SPLIT not in sealed:
        problems.append(f"the result does not name {_TEST_SPLIT} among the files it was measured on")
    for name, digest in sorted(sealed.items()):
        path = root / name
        if ".." in Path(name).parts or Path(name).is_absolute():
            problems.append(f"{name!r} is not a path inside the model folder")
        elif not path.is_file():
            problems.append(f"{name} is not in this model folder, so the result cannot be tied to this run's test data")
        elif _sha256(path) != digest:
            problems.append(f"{name} here is not the file the portal evaluated on: the test data differs")

    package_zip = root / arch / ZIP_NAME
    if package_zip.is_file() and evidence.get("package_zip_sha256") != _sha256(package_zip):
        problems.append(f"{arch}/{ZIP_NAME} here is not the package the portal trained: rebuild and retrain, or run "
                        "eval.py locally")
    return problems


def accept(dest: str, arch: str, evidence_path: str) -> dict[str, Any]:
    """Check an exported result and, when it holds, keep it as ``<arch>/portal_held_out.json``. Returns the metrics."""
    export = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    if not isinstance(export, dict):
        raise ValueError("the evidence file must contain a JSON object")
    problems = problems_with(dest, arch, export)
    if problems:
        raise ValueError("; ".join(problems))
    kept = Path(dest) / arch / ACCEPTED_FILE
    kept.write_text(json.dumps(export, indent=2), encoding="utf-8")
    return export["metrics"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("accept", help="check the portal's exported held-out result against this run")
    a.add_argument("--dest", required=True, help="the model folder")
    a.add_argument("--arch", required=True)
    a.add_argument("--evidence", required=True, help="the JSON file downloaded from the portal")
    args = p.parse_args(argv)
    try:
        metrics = accept(args.dest, args.arch, args.evidence)
    except (OSError, ValueError) as exc:
        print("not accepted: run eval.py locally instead (M10), for these reasons:", file=sys.stderr)
        for reason in str(exc).split("; "):
            print(f"  - {reason}", file=sys.stderr)
        return 1
    caveats = (json.loads((Path(args.dest) / args.arch / ACCEPTED_FILE).read_text(encoding="utf-8"))
               .get("evidence", {}).get("caveats") or [])
    print(f"accepted: the portal's held-out result is about this run. Kept as {args.arch}/{ACCEPTED_FILE}.")
    for caveat in caveats:
        print(f"  caveat: {caveat}")
    print("The KPI gate is still M10's: compare these numbers with the use case's targets.")
    print(json.dumps({k: v for k, v in metrics.items() if isinstance(v, (int, float, str, bool))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
