"""The training package: what M8 built, in the one form every runner executes (ADR-0028 D-5).

A runner is a laptop, a cloud VM, or the portal's package runner (NeuroEdge-Web ADR-0010 R-1). Each
runs the same zip and changes none of it. The zip is small: code, split files, the lock and
``package.json``. Heavy files (the contract dataset, synthetic data, base weights) travel either
inside it, or by reference with a manifest of their hashes:

* ``in-package`` : small data rides in the zip.
* ``local``      : the data stays in the model folder; ``data.location`` is its ``file://`` URI.
* ``s3://…``     : the owner uploads it once with the printed ``aws s3 sync`` command. Nothing
  here uploads or calls a network: the offline rule (ADR-0025 D-1) is kept.

The test split is withheld, by an allow-list: a contract data file travels only when it provably
belongs to a train or val unit (``data/contract/<unit>.<ext>`` or ``data/contract/<unit>/…``).
``data/splits/test.json``, test-only units and excluded units stay behind, and ``package.json`` lists
them. Only the time-series contract layout is understood so far; any other modality is refused.
This guard covers ``data/contract/`` ONLY. ``data/synthetic/`` and ``model/base/`` ship whole, by
design: synthetic data is train-only and base weights are not split data. A generator that ever
keys synthetic files by real unit id must extend the allow-list to them first.

Building refuses, rather than guesses: an edited lock, a missing entry script, a secret-looking file,
a link that leads out of the model folder, or a train/val unit whose files cannot be found.

    python -m agentforge.src.ml_contract.package build  --dest <model folder> --arch <Arch> [--baseline <Dir>]
                                                         [--data in-package|local|s3://bucket/prefix]
    python -m agentforge.src.ml_contract.package verify --zip <training-package.zip>
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

from .lock import LOCK_FILE, LockError, read_lock

PACKAGE_SCHEMA = "training-package/1"
DATA_MANIFEST_SCHEMA = "training-data-manifest/1"
PACKAGE_FILE = "package.json"
DATA_MANIFEST_FILE = "data_manifest.json"
ZIP_NAME = "training-package.zip"

# Small files every package carries, when the run has them.
_CODE_DIRS = ("common", "data/splits", "inputs/scaffold")
# Heavy files: inside the zip only for ``in-package``, else listed in the data manifest.
_DATA_DIRS = ("data/contract", "data/synthetic", "model/base")
_CONTRACT_DIR = "data/contract"
_CONTRACT_META = {"manifest.json", "readme.md"}  # named files beside the unit files: no rows, so they travel
_SKIP_DIRS = {"__pycache__", "runs", "mlruns", ".venv", "venv", ".git", ".pytest_cache"}
_SKIP_FILES = ("*.pyc", "*.joblib", "*.zip", "baseline_metrics.json")
_SECRET_FILES = (".env", ".env.*", "*.key", "*.pem", "*.pfx", "settings.local.json", "credentials*", "id_rsa*")
_ZIP_DATE = (2020, 1, 1, 0, 0, 0)  # fixed, so the same folder always builds the same zip


class PackageError(ValueError):
    """The package cannot be built from what the run has. Each problem is listed."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matches(name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(name.lower(), pattern) for pattern in patterns)


def _walk(root: Path, base: Path) -> tuple[list[str], list[str]]:
    """(files to carry, secret-looking files) under ``root``, as posix paths relative to ``base``."""
    keep: list[str] = []
    secrets: list[str] = []
    if not root.is_dir():
        return keep, secrets
    boundary = base.resolve()
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS)
        for name in sorted(files):
            # A symlink, or a Windows junction (which os.walk follows even with followlinks=False),
            # can point outside the model folder. What it reaches is not this run's to ship.
            if not (Path(current) / name).resolve().is_relative_to(boundary):
                raise PackageError([
                    f"{(Path(current) / name).relative_to(base).as_posix()} resolves outside the model folder "
                    f"({(Path(current) / name).resolve()}): a link or junction leads out of it. Copy the files "
                    "in, or remove the link."
                ])
            relative = (Path(current) / name).relative_to(base).as_posix()
            if _matches(name, _SECRET_FILES):
                secrets.append(relative)
            elif not _matches(name, _SKIP_FILES):
                keep.append(relative)
    return keep, secrets


def _split_units(dest: Path, split: str) -> set[str]:
    path = dest / "data" / "splits" / f"{split}.json"
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as fh:
        return {str(unit["unit_id"]) for unit in json.load(fh).get("units", [])}


def _unit_of(contract_file: str, units: set[str]) -> str | None:
    """The unit a contract file belongs to: ``data/contract/<unit>.<ext>`` or ``data/contract/<unit>/…``."""
    inside = Path(contract_file).relative_to(_CONTRACT_DIR).parts
    candidate = inside[0] if len(inside) > 1 else Path(inside[0]).stem
    return candidate if candidate in units else None


def _withheld(dest: Path, data_files: list[str]) -> tuple[set[str], list[str], list[str]]:
    """(files that must not reach a trainer, units whose one file also holds test rows, problems).

    An ALLOW-list, not a deny-list: a contract data file travels only when it provably belongs to a
    train or val unit. A file of a test-only unit, of an excluded unit, or of no unit this can
    name, stays behind. When a train or val unit has no file this can find, the layout is not one
    this understands, and the build refuses: packing nothing, or packing everything, would both be
    silent failures.
    """
    splits = {name: _split_units(dest, name) for name in ("train", "val", "test")}
    trainer_units = splits["train"] | splits["val"]
    problems = [f"data/splits/{name}.json is missing or names no units: M4 /dataset-verify writes it"
                for name in ("train", "val") if not splits[name]]

    withheld = {"data/splits/test.json"} if (dest / "data" / "splits" / "test.json").exists() else set()
    found: set[str] = set()
    for name in data_files:
        if not name.startswith(_CONTRACT_DIR + "/"):
            continue
        unit = _unit_of(name, trainer_units)
        if unit is not None:
            found.add(unit)
        elif name.lower() not in {f"{_CONTRACT_DIR}/{meta}" for meta in _CONTRACT_META}:
            withheld.add(name)  # a test-only unit, an excluded unit, or a file of no known unit
    missing = sorted(trainer_units - found)
    if missing and not problems:
        problems.append(
            f"no file under {_CONTRACT_DIR}/ could be matched to these train/val units: {missing}. This builder "
            f"knows `{_CONTRACT_DIR}/<unit>.<ext>` and `{_CONTRACT_DIR}/<unit>/…`. It will not guess which files "
            "are test data."
        )
    return withheld, sorted(splits["test"] & trainer_units), problems


def _data_location(dest: Path, data: str) -> str:
    if data == "in-package":
        return "in_package"
    if data == "local":
        return dest.resolve().as_uri()
    if data.startswith("s3://") and len(data) > len("s3://"):
        return data.rstrip("/")
    raise PackageError([f"--data {data!r} is not supported: use in-package, local, or s3://bucket/prefix"])


def _sync_command(dest: Path, location: str, withheld: set[str]) -> str:
    """The upload the OWNER runs. Whole data folders in, the withheld files out."""
    parts = [f'aws s3 sync "{dest.resolve()}" {location}', '--exclude "*"']
    parts += [f'--include "{folder}/*"' for folder in _DATA_DIRS if (dest / folder).is_dir()]
    parts += [f'--exclude "{name}"' for name in sorted(withheld) if name.startswith(_DATA_DIRS)]
    return " ".join(parts)


def build_package(dest: str, *, arch: str, baseline: str | None = None, data: str = "in-package") -> dict[str, Any]:
    """Write ``<dest>/<arch>/training-package.zip``. Returns its path, sha256 and any sync command."""
    root = Path(dest)
    problems: list[str] = []
    try:
        lock = read_lock(str(root))
    except (OSError, LockError) as exc:
        raise PackageError([f"no valid use-case lock in {root}: {exc}"]) from exc
    location = _data_location(root, data)
    if lock.get("modality") != "timeseries":
        # Only the time-series contract layout (data/contract/<unit>.<ext>) is understood here. A
        # vision dataset lives elsewhere, so a package built now would carry code and no data.
        raise PackageError([
            f"packaging a {lock.get('modality')!r} run is not implemented yet: this builder knows the "
            f"time-series contract layout only, and would ship no dataset. Run it yourself per RUN_ON_GPU.md."
        ])

    steps = [folder for folder in (baseline, arch) if folder]
    for folder in steps:
        for needed in ("train.py", "requirements.txt"):
            if not (root / folder / needed).is_file():
                problems.append(f"{folder}/{needed} is missing: M8 /model-build writes it")

    code_files, secrets = [LOCK_FILE], []
    for folder in (*steps, *_CODE_DIRS):
        keep, found = _walk(root / folder, root)
        code_files += keep
        secrets += found
    data_files: list[str] = []
    for folder in _DATA_DIRS:
        keep, found = _walk(root / folder, root)
        data_files += keep
        secrets += found
    problems += [f"{name} looks like a secret and must not travel in a package: remove it" for name in secrets]
    withheld, spanning, split_problems = _withheld(root, data_files)
    problems += split_problems
    if problems:
        raise PackageError(problems)

    code_files = sorted(set(code_files) - withheld)
    data_files = sorted(set(data_files) - withheld)

    in_zip = code_files + (data_files if location == "in_package" else [])
    manifest_bytes = b""
    if location != "in_package":
        manifest = {
            "schema": DATA_MANIFEST_SCHEMA,
            "lock_sha256": lock["lock_sha256"],
            "files": {name: {"sha256": _sha256(root / name), "size": (root / name).stat().st_size}
                      for name in data_files},
        }
        manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    files = {name: _sha256(root / name) for name in in_zip}
    if manifest_bytes:
        files[DATA_MANIFEST_FILE] = hashlib.sha256(manifest_bytes).hexdigest()
    package = {
        "schema": PACKAGE_SCHEMA,
        "use_case_id": lock["use_case_id"],
        "lock_sha256": lock["lock_sha256"],
        "arch": arch,
        "runtime": {"kind": "pip", "requirements": [f"{folder}/requirements.txt" for folder in steps]},
        "entrypoint": [{"cwd": folder, "cmd": ["python", "train.py", "--config", "config.yaml"]} for folder in steps],
        "outputs": {"model_package": f"{arch}/runs/*/model-package"},
        "data": {
            "location": location,
            "manifest": DATA_MANIFEST_FILE if manifest_bytes else None,
            "manifest_sha256": files.get(DATA_MANIFEST_FILE),
        },
        "withheld": {"files": sorted(withheld), "units_spanning_test": spanning},
        "files": dict(sorted(files.items())),
    }

    zip_path = root / arch / ZIP_NAME
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as out:
        def entry(name: str) -> zipfile.ZipInfo:
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            return info

        out.writestr(entry(PACKAGE_FILE), json.dumps(package, indent=2).encode("utf-8"))
        if manifest_bytes:
            out.writestr(entry(DATA_MANIFEST_FILE), manifest_bytes)
        for name in in_zip:
            # Streamed, never read whole: an in-package weights file can be hundreds of MB.
            with (root / name).open("rb") as src, out.open(entry(name), "w", force_zip64=True) as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)

    return {
        "zip": str(zip_path),
        "zip_sha256": _sha256(zip_path),
        "package": package,
        "sync_command": _sync_command(root, location, withheld) if location.startswith("s3://") else None,
    }


def _unsafe_name(name: str) -> bool:
    """True for a zip entry that could land outside the folder it is extracted into."""
    if not name or "\\" in name or name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        return True
    return any(part in ("", ".", "..") for part in name.rstrip("/").split("/"))


def verify_package(zip_path: str) -> list[str]:
    """Problems with a built zip: an unsafe or repeated entry name, a file whose hash changed, a
    missing file, an unlisted file. A consumer extracts only a zip this returns no problems for."""
    problems: list[str] = []
    with zipfile.ZipFile(zip_path) as z:
        entries = z.namelist()
        names = set(entries)
        problems += [f"{name!r} is not a safe relative path: it must stay inside the package"
                     for name in sorted(names) if _unsafe_name(name)]
        repeated = sorted({name for name in entries if entries.count(name) > 1})
        problems += [f"{name} appears more than once in the zip: only one copy can be the one that was hashed"
                     for name in repeated]
        if problems:
            return problems  # nothing below is worth reading from a zip shaped like this
        if PACKAGE_FILE not in names:
            return [f"{PACKAGE_FILE} is missing: this is not a training package"]
        package = json.loads(z.read(PACKAGE_FILE))
        if package.get("schema") != PACKAGE_SCHEMA:
            problems.append(f"schema is {package.get('schema')!r}, expected {PACKAGE_SCHEMA!r}")
        listed = package.get("files", {})
        for name, expected in listed.items():
            if name not in names:
                problems.append(f"{name} is listed in {PACKAGE_FILE} but missing from the zip")
            elif hashlib.sha256(z.read(name)).hexdigest() != expected:
                problems.append(f"{name} does not match its sha256 in {PACKAGE_FILE}")
        problems += [f"{name} is in the zip but not listed in {PACKAGE_FILE}"
                     for name in sorted(names - set(listed) - {PACKAGE_FILE})]
    return problems


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="zip what M8 built into a training package")
    b.add_argument("--dest", required=True, help="the model folder")
    b.add_argument("--arch", required=True, help="the architecture folder /model-build wrote, e.g. 1DCNN")
    b.add_argument("--baseline", help="the baseline folder, run first, e.g. MiniRocket")
    b.add_argument("--data", default="in-package", help="in-package | local | s3://bucket/prefix")
    v = sub.add_parser("verify", help="check a built zip against its own package.json")
    v.add_argument("--zip", required=True)
    a = p.parse_args(argv)

    if a.cmd == "verify":
        problems = verify_package(a.zip)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print("package intact" if not problems else "package does NOT verify", file=sys.stderr if problems else sys.stdout)
        return 1 if problems else 0

    try:
        result = build_package(a.dest, arch=a.arch, baseline=a.baseline, data=a.data)
    except PackageError as exc:
        print("refused:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    package = result["package"]
    print(f"{result['zip']}  sha256 {result['zip_sha256']}")
    print(f"lock {package['lock_sha256'][:12]} · {len(package['files'])} files · data: {package['data']['location']}")
    if package["withheld"]["files"]:
        print(f"withheld from the trainer: {', '.join(package['withheld']['files'])}")
    if package["withheld"]["units_spanning_test"]:
        print("these units' files also hold test rows (train.py reads only their train/val rows): "
              + ", ".join(package["withheld"]["units_spanning_test"]))
    if result["sync_command"]:
        print("upload the data yourself, once:\n  " + result["sync_command"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
