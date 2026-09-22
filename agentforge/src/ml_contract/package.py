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
them. A **vision** run has no contract folder: its split files list each unit's image files, so a file travels
only when a train or val unit lists it, a file listed by a test unit is withheld and sealed, and a file listed on
both sides is a leak and refuses the build. ``vision_anomaly`` is not packaged yet. Only EXACT file overlap between
the splits is checked here. Near-duplicate images (burst frames, re-encodes, crops of one capture) are NOT: that
control belongs to the dataset verify stage (M4, ``vision-ml``: group by source image and capture session).
This guard covers ``data/contract/`` ONLY. ``data/synthetic/`` and ``model/base/`` ship whole, by
design: synthetic data is train-only and base weights are not split data. A generator that ever
keys synthetic files by real unit id must extend the allow-list to them first.

**The sealed test bundle (ADR-0028 D-12).** What is withheld from the trainer is not thrown away: ``build`` also
writes ``data/portal_test.zip``, holding ``data/splits/test.json`` and the files of the test-only units, with a
``test_bundle.json`` that names the lock and the hashes of the train and val split files the package carries. A
runner that holds both can prove they are two halves of one split, and then run the package's own ``eval.py``
on data its training never saw. ``package.json`` says how: ``evaluate`` is the one command, with two
placeholders the runner fills (``{model_package}``, ``{out}``). Every generated ``eval.py`` takes
``--package --split --config --out``. The bundle is never part of the training package, and is git-ignored.

Building refuses, rather than guesses: an edited lock, a missing entry script, a secret-looking file,
a link that leads out of the model folder, or a train/val unit whose files cannot be found.

    python -m agentforge.src.ml_contract.package build  --dest <model folder> --arch <Arch> [--baseline <Dir>]
                                                         [--data in-package|local|s3://bucket/prefix]
                                                         [--catalogue-id <portal catalogue entry>]
    python -m agentforge.src.ml_contract.package verify --zip <training-package.zip>
    python -m agentforge.src.ml_contract.package check-env --dest <model folder> --arch <Arch> [--baseline <Dir>]

A package has ONE environment: every step's ``requirements.txt`` is installed together, on the runner's
Linux and Python, from wheels only. ``build`` checks offline what it can (plain pinned lines, no package pinned
two ways). ``check-env`` is the one command here that uses the network, and only because the owner runs it:
it asks pip whether the pins can be installed together on the runner's platform, and installs nothing.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from .lock import LOCK_FILE, LockError, read_lock

PACKAGE_SCHEMA = "training-package/1"
DATA_MANIFEST_SCHEMA = "training-data-manifest/1"
PACKAGE_FILE = "package.json"
DATA_MANIFEST_FILE = "data_manifest.json"
ZIP_NAME = "training-package.zip"
TEST_BUNDLE_SCHEMA = "training-test-bundle/1"
TEST_BUNDLE_FILE = "test_bundle.json"
TEST_BUNDLE_ZIP = "data/portal_test.zip"
_TEST_SPLIT = "data/splits/test.json"
_TRAINER_SPLITS = ("data/splits/train.json", "data/splits/val.json")

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

# What the portal's package runner installs on (NeuroEdge-Web `package_launcher`: python:3.11-slim, wheels only).
RUNNER_PYTHON = "3.11"
RUNNER_PLATFORMS = ("manylinux_2_28_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64")
# The portal refuses any other line (NeuroEdge-Web `training_package_service.requirements_problems`): the install
# phase is the one moment a run has a network, so a requirements file may not redirect pip.
_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[A-Za-z0-9._,\s-]+\])?\s*==\s*([A-Za-z0-9.*+!_-]+)"
                  r"(\s*;\s*[A-Za-z0-9_.\s'\"<>=!()]+)?$")


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


def _split_files(dest: Path, split: str) -> list[str]:
    """Every file the units of one split list (the vision layout), as written in the split file."""
    path = dest / "data" / "splits" / f"{split}.json"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        return [str(name) for unit in json.load(fh).get("units", []) for name in unit.get("files") or []]


def _withheld_vision(root: Path) -> tuple[list[str], set[str], list[str], list[str]]:
    """(files a trainer gets, files withheld, secret-looking files, problems) for a vision run.

    The same allow-list idea as the contract layout: an image travels only when a train or val unit lists it.
    """
    listed = {name: _split_files(root, name) for name in ("train", "val", "test")}
    problems = [f"data/splits/{name}.json is missing or lists no files: a vision split lists each unit's image "
                "files, and M4 /dataset-verify writes it" for name in ("train", "val") if not listed[name]]
    boundary = root.resolve()
    for name in sorted({n for names in listed.values() for n in names}):
        if _unsafe_name(name) or not (root / name).resolve().is_relative_to(boundary):
            problems.append(f"{name!r} in a split file is not a path inside the model folder")
        elif not (root / name).is_file():
            problems.append(f"{name} is listed in a split file but is not in the model folder")
    trainer = set(listed["train"]) | set(listed["val"])
    leaked = sorted(trainer & set(listed["test"]))
    problems += [f"{name} is listed by a test unit and by a train or val unit: that is test data in training"
                 for name in leaked]
    withheld = set(listed["test"]) | ({_TEST_SPLIT} if (root / _TEST_SPLIT).exists() else set())
    secrets = sorted(name for name in trainer if _matches(Path(name).name, _SECRET_FILES))
    return sorted(trainer - set(secrets)), withheld, secrets, problems


def _evaluate_step(root: Path, arch: str) -> dict[str, Any] | None:
    """How a runner executes the package's own held-out evaluation, when the package has one."""
    if not (root / arch / "eval.py").is_file() or not (root / _TEST_SPLIT).is_file():
        return None
    up = "/".join([".."] * len(Path(arch).parts))
    return {"cwd": arch, "cmd": ["python", "eval.py", "--package", "{model_package}", "--split", f"{up}/{_TEST_SPLIT}",
                                 "--config", "config.yaml", "--out", "{out}"]}


def _write_zip(zip_path: Path, root: Path, names: list[str], generated: dict[str, bytes]) -> None:
    """A deterministic zip: fixed dates, generated entries first, files streamed."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as out:
        def entry(name: str) -> zipfile.ZipInfo:
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            return info

        for name, body in generated.items():
            out.writestr(entry(name), body)
        for name in names:
            # Streamed, never read whole: an in-package weights file can be hundreds of MB.
            with (root / name).open("rb") as src, out.open(entry(name), "w", force_zip64=True) as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)


def _sealed_files(root: Path, withheld: set[str], *, vision: bool = False) -> dict[str, str]:
    """What goes into the test bundle, with its hash: the test split and the files of its test-only units.

    The training package states these hashes (`withheld.sealed`), and the package is what a person approves. So a
    runner can tell the bundle it is handed from one whose `test.json` was edited afterwards: a bundle's own
    manifest only proves the bundle agrees with itself.
    """
    if _TEST_SPLIT not in withheld:
        return {}
    if vision:  # every withheld file is one a test unit lists
        return {name: _sha256(root / name) for name in sorted(withheld)}
    test_units = _split_units(root, "test")
    return {name: _sha256(root / name) for name in sorted(withheld)
            if name == _TEST_SPLIT or _unit_of(name, test_units) is not None}


def _build_test_bundle(root: Path, lock: dict[str, Any], arch: str, sealed: dict[str, str]) -> dict[str, Any] | None:
    """Write ``data/portal_test.zip``: the test split and the files of its test-only units (D-12).

    Only what the evaluation needs. An excluded unit's file is withheld from the trainer too, but it is in no
    split, so it stays behind here as well.
    """
    if not sealed:
        return None
    names = sorted(sealed)
    manifest = {
        "schema": TEST_BUNDLE_SCHEMA,
        "use_case_id": lock["use_case_id"],
        "lock_sha256": lock["lock_sha256"],
        "arch": arch,
        # The other half of the split: a runner compares these with the package's own `files` hashes.
        "trainer_splits": {name: _sha256(root / name) for name in _TRAINER_SPLITS if (root / name).is_file()},
        "files": dict(sealed),
    }
    zip_path = root / TEST_BUNDLE_ZIP
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    _write_zip(zip_path, root, names, {TEST_BUNDLE_FILE: json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")})
    return {"zip": str(zip_path), "zip_sha256": _sha256(zip_path), "files": names}


def _data_location(dest: Path, data: str) -> str:
    if data == "in-package":
        return "in_package"
    if data == "local":
        return dest.resolve().as_uri()
    if data.startswith("s3://") and len(data) > len("s3://"):
        return data.rstrip("/")
    raise PackageError([f"--data {data!r} is not supported: use in-package, local, or s3://bucket/prefix"])


def _sync_command(dest: Path, location: str, withheld: set[str], images: list[str] | None = None) -> str:
    """The upload the OWNER runs. Whole data folders in, the withheld files out. A vision run names each image."""
    parts = [f'aws s3 sync "{dest.resolve()}" {location}', '--exclude "*"']
    parts += [f'--include "{folder}/*"' for folder in _DATA_DIRS if (dest / folder).is_dir()]
    parts += [f'--include "{name}"' for name in images or []]
    parts += [f'--exclude "{name}"' for name in sorted(withheld) if name.startswith(_DATA_DIRS)]
    return " ".join(parts)


def _requirement_lines(path: Path) -> list[tuple[int, str]]:
    lines = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        # pip's own rule: a comment starts at a `#` that begins the line or follows white space
        line = "" if raw.lstrip().startswith("#") else re.split(r"\s+#", raw, maxsplit=1)[0].strip()
        if line:
            lines.append((number, line))
    return lines


def requirements_problems(root: Path, steps: list[str]) -> list[str]:
    """What can be known offline: every line is `name==version`, and no package is pinned two ways.

    The runner installs every step's file into one environment, so `scikit-learn==1.9.1` in one folder and
    `scikit-learn==1.7.2` in another is a package that cannot be installed.
    """
    problems: list[str] = []
    pinned: dict[str, tuple[str, str]] = {}
    for folder in steps:
        path = root / folder / "requirements.txt"
        if not path.is_file():
            continue  # reported by the caller
        for number, line in _requirement_lines(path):
            match = _PIN.match(line)
            if not match:
                problems.append(f"{folder}/requirements.txt line {number}: {line[:80]!r} is not a plain "
                                f"'package==version' line; the runner refuses pip options, URLs, paths and open ranges")
                continue
            name, version = re.sub(r"[-_.]+", "-", match.group(1)).lower(), match.group(3)
            first = pinned.setdefault(name, (version, folder))
            if first[0] != version:
                problems.append(f"{name} is pinned to {first[0]} in {first[1]} and to {version} in {folder}: a package "
                                f"has one environment, so every step must pin the same version")
    return problems


def check_environment(dest: str, *, arch: str, baseline: str | None = None, timeout_s: int = 900) -> list[str]:
    """Ask pip whether every step's pins install TOGETHER on the runner's platform. Installs nothing.

    Uses the network (the package index), which is why it is its own command and never part of `build`.
    """
    root = Path(dest)
    steps = [folder for folder in (baseline, arch) if folder]
    files = [root / folder / "requirements.txt" for folder in steps]
    problems = [f"{folder}/requirements.txt is missing" for folder, path in zip(steps, files) if not path.is_file()]
    problems += requirements_problems(root, steps)
    if problems:
        return problems
    with tempfile.TemporaryDirectory() as scratch:
        cmd = [sys.executable, "-m", "pip", "install", "--dry-run", "--ignore-installed", "--isolated", "--no-input",
               "--disable-pip-version-check", "--only-binary=:all:", "--implementation", "cp",
               "--python-version", RUNNER_PYTHON, "--target", scratch]
        for platform in RUNNER_PLATFORMS:
            cmd += ["--platform", platform]
        for path in files:
            cmd += ["-r", str(path)]
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, check=False)  # noqa: S603
        except (OSError, subprocess.TimeoutExpired) as exc:
            return [f"pip could not be run to check the environment: {exc}"]
    if done.returncode == 0:
        return []
    if "No module named pip" in done.stderr:
        return [f"{sys.executable} has no pip (a uv environment): run this command with a Python that has pip"]
    wanted = [line.strip() for line in (done.stdout + "\n" + done.stderr).splitlines()
              if line.startswith("ERROR") or " depends on " in line or "requested" in line]
    return ["the pins cannot be installed together on the runner "
            f"(Linux x86_64, Python {RUNNER_PYTHON}, wheels only)",
            *(dict.fromkeys(wanted) or [done.stderr.strip()[-600:]])]


def build_package(dest: str, *, arch: str, baseline: str | None = None, data: str = "in-package",
                  catalogue_id: str | None = None) -> dict[str, Any]:
    """Write ``<dest>/<arch>/training-package.zip``. Returns its path, sha256 and any sync command.

    ``catalogue_id`` is the portal catalogue entry this package implements, when the proposal adopted one
    (ADR-0028 D-5, D-9). ``baseline`` is declared in ``package.json`` too: M10 requires ``beats_baseline`` only of
    a package that declares one (D-11).
    """
    root = Path(dest)
    problems: list[str] = []
    try:
        lock = read_lock(str(root))
    except (OSError, LockError) as exc:
        raise PackageError([f"no valid use-case lock in {root}: {exc}"]) from exc
    location = _data_location(root, data)
    vision = lock.get("modality") == "vision"
    if lock.get("modality") not in ("timeseries", "vision"):
        # Two layouts are understood: the time-series contract folder, and vision split files that list each
        # unit's images. Anything else would ship code and no data, or data this cannot prove is not test data.
        raise PackageError([
            f"packaging a {lock.get('modality')!r} run is not implemented yet: this builder knows the "
            f"time-series contract layout and the vision split-file layout only. Run it yourself per RUN_ON_GPU.md."
        ])

    if not vision and not baseline:
        # D-11: a time-series package ALWAYS declares a baseline. Without one M10 would record
        # "not_applicable" and the beats_baseline gate could never open.
        problems.append("a time-series package always declares a baseline (ADR-0028 D-11): pass --baseline <Dir>, "
                        "the folder of the cheap reference trained on the same split (MiniRocket)")
    steps = [folder for folder in (baseline, arch) if folder]
    for folder in steps:
        for needed in ("train.py", "requirements.txt"):
            if not (root / folder / needed).is_file():
                problems.append(f"{folder}/{needed} is missing: M8 /model-build writes it")
    problems += requirements_problems(root, steps)

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
    images: list[str] = []
    if vision:
        images, withheld, found, split_problems = _withheld_vision(root)
        spanning: list[str] = []
        secrets += found
        data_files += images
    else:
        withheld, spanning, split_problems = _withheld(root, data_files)
    problems += [f"{name} looks like a secret and must not travel in a package: remove it" for name in secrets]
    problems += split_problems
    if problems:
        raise PackageError(problems)

    sealed = _sealed_files(root, withheld, vision=vision)
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
        **({"catalogue_id": catalogue_id} if catalogue_id else {}),
        "baseline": {"declared": bool(baseline), "folder": baseline},
        "runtime": {"kind": "pip", "requirements": [f"{folder}/requirements.txt" for folder in steps]},
        "entrypoint": [{"cwd": folder, "cmd": ["python", "train.py", "--config", "config.yaml"]} for folder in steps],
        "outputs": {"model_package": f"{arch}/runs/*/model-package"},
        **({"evaluate": evaluate} if (evaluate := _evaluate_step(root, arch)) else {}),
        "data": {
            "location": location,
            "manifest": DATA_MANIFEST_FILE if manifest_bytes else None,
            "manifest_sha256": files.get(DATA_MANIFEST_FILE),
        },
        "withheld": {"files": sorted(withheld), "units_spanning_test": spanning, "sealed": sealed},
        "files": dict(sorted(files.items())),
    }

    zip_path = root / arch / ZIP_NAME
    generated = {PACKAGE_FILE: json.dumps(package, indent=2).encode("utf-8")}
    if manifest_bytes:
        generated[DATA_MANIFEST_FILE] = manifest_bytes
    _write_zip(zip_path, root, in_zip, generated)

    return {
        "test_bundle": _build_test_bundle(root, lock, arch, sealed),
        "zip": str(zip_path),
        "zip_sha256": _sha256(zip_path),
        "package": package,
        "sync_command": _sync_command(root, location, withheld, images) if location.startswith("s3://") else None,
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
    b.add_argument("--catalogue-id", help="the portal catalogue entry this package implements, when one was adopted")
    v = sub.add_parser("verify", help="check a built zip against its own package.json")
    v.add_argument("--zip", required=True)
    c = sub.add_parser("check-env", help="ask pip whether the pins install together on the runner (uses the network)")
    c.add_argument("--dest", required=True)
    c.add_argument("--arch", required=True)
    c.add_argument("--baseline")
    a = p.parse_args(argv)

    if a.cmd == "check-env":
        problems = check_environment(a.dest, arch=a.arch, baseline=a.baseline)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print("the environment installs on the runner" if not problems else "the environment does NOT install",
              file=sys.stderr if problems else sys.stdout)
        return 1 if problems else 0

    if a.cmd == "verify":
        problems = verify_package(a.zip)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print("package intact" if not problems else "package does NOT verify", file=sys.stderr if problems else sys.stdout)
        return 1 if problems else 0

    try:
        result = build_package(a.dest, arch=a.arch, baseline=a.baseline, data=a.data, catalogue_id=a.catalogue_id)
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
    if result["test_bundle"]:
        bundle = result["test_bundle"]
        print(f"sealed test bundle: {bundle['zip']}  sha256 {bundle['zip_sha256']}  ({len(bundle['files'])} files). "
              "Upload it to the portal's Evaluate step only; it never goes to a trainer.")
    if result["sync_command"]:
        print("upload the data yourself, once:\n  " + result["sync_command"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
