"""/model-fetch: acquire a pretrained base model the way /dataset-download acquires data (ADR-0028 D-2, D-3, D-4).

M7 runs this when ``model_proposed.md`` names a pretrained base. It never calls the portal (ADR-0025 D-1). It
downloads from the model's own hub, hashes what arrived, and writes ``<dest>/model/base/``:

* ``weights/``              : the downloaded files, git-ignored by ``model/base/.gitignore``;
* ``loader.json``           : the loader family, the entry file and every file's sha256;
* ``base-model-card.json``  : source, pinned revision, sha256, licence and its gate outcome, loader, and a
  ``selection_note`` when the choice differs from the portal's pick (the portal matches an upload against it);
* ``base-model-card.md``    : the same, for the human who answers the licence gate.

**A revision is always pinned.** ``latest``, a branch name, or no revision is refused. The two hubs whose
catalogue entries carry no revision are pinned at fetch: ``ultralytics`` by the release tag of
``ultralytics/assets``, ``torchvision`` by the weights file name, whose suffix is the first hex digits of its
sha256 and is checked after the download.

**The licence gate (D-3, as amended 2026-09-21).** The licence is an input with its evidence, never a guess:

* a permissive licence with evidence  -> ``approved``, no gate;
* AGPL-3.0 (every Ultralytics model)   -> ``approved_internal_only`` by the owner's MVP decision, no gate.
  ``distribution: internal_only`` is written as a flag that travels and is shown. Nothing refuses on it;
* non-commercial, unverifiable, missing, or any other terms -> the hard gate ``model/base-model-card.md`` opens
  at M7 and the run stops until a human decides. ``licence`` records that decision in the card afterwards.

No token value is ever written: a card names the environment variable a gated source needs, nothing more.

    python -m agentforge.src.ml_contract.model_fetch fetch --dest <model folder> --hub huggingface
        --ref <org/model> --revision <commit or tag> --loader transformers --model-id <id>
        --licence <SPDX> --licence-evidence <where it was read>
    python -m agentforge.src.ml_contract.model_fetch fetch --dest <model folder> --from-recommendation
        [--revision <tag or file>] [--licence-evidence <where it was read>]
    python -m agentforge.src.ml_contract.model_fetch licence --dest <model folder>
        --outcome approved|approved_internal_only|rejected
    python -m agentforge.src.ml_contract.model_fetch runner --loader <loader> [--path fine_tune|training_package|bring]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import gates as gt

CARD_SCHEMA = "base-model-card/1"
LOADER_SCHEMA = "base-model-loader/1"
BASE_DIR = "model/base"
WEIGHTS_DIR = "weights"
CARD_JSON = "base-model-card.json"
CARD_MD = "base-model-card.md"
LOADER_FILE = "loader.json"
LICENCE_GATE = "model/base-model-card.md"
GATE_STAGE = "model-select"
AUTOMATIC_IDENTITY = "model-fetch (automatic)"

LOADERS = ("ultralytics", "torchvision", "timm", "transformers", "tao", "custom", "none")
RUNNERS = ("portal-finetune", "portal-package", "offline")
PATHS = ("fine_tune", "training_package", "bring")
HUBS = ("huggingface", "ngc", "github", "ultralytics", "torchvision", "aihub")
# The portal's built-in trainers rebuild these three families only (NeuroEdge-Web ADR-0011 S-5).
_FINETUNE_LOADERS = ("ultralytics", "torchvision", "timm")
# The environment variable a gated source reads. The NAME is recorded, the value never is.
TOKEN_ENV = {"huggingface": "HF_TOKEN", "ngc": "NGC_API_KEY"}

_MOVING_REVISIONS = {"", "latest", "main", "master", "head", "trunk", "develop", "dev", "nightly"}
_SAFE_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TORCHVISION_FILE = re.compile(r"^[A-Za-z0-9_.]+-([0-9a-f]{8})\.pth$")
_TORCHVISION_BASE = "https://download.pytorch.org/models/"
_ULTRALYTICS_REPO = "ultralytics/assets"

OWNER_DECISION = "owner decision 2026-09-21 (ADR-0028 D-3 amendment): AGPL-3.0 is accepted for the MVP"
_PERMISSIVE = {"apache-2.0", "mit", "bsd-2-clause", "bsd-3-clause", "isc", "cc0-1.0", "cc-by-4.0"}
_INTERNAL_ONLY = {"agpl-3.0", "agpl-3.0-only", "agpl-3.0-or-later"}
_NO_LICENCE = {"", "unknown", "unverifiable", "other", "none", "to_verify", "noassertion"}
_NON_COMMERCIAL = re.compile(r"(^|[-_ ])nc([-_ ]|$)|non-?commercial|research[-_ ]only", re.I)

Downloader = Callable[["FetchRequest", Path], None]


class FetchError(ValueError):
    """The base model cannot be fetched or recorded as asked. Each problem is listed."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class FetchRequest:
    hub: str
    ref: str
    revision: str | None
    loader: str
    model_id: str
    licence_spdx: str | None = None
    licence_evidence: str | None = None
    catalogue_id: str | None = None
    selection_note: str | None = None
    via: str | None = None  # e.g. "aihub:<model>": the listing this upstream source was looked up through


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------- runner routing (D-4)


def allowed_runners(loader: str) -> tuple[str, ...]:
    """The runners a loader family may take. Running a package outside the portal stays possible for all."""
    if loader not in LOADERS:
        raise ValueError(f"unknown loader {loader!r}, expected one of {list(LOADERS)}")
    if loader == "tao":
        return ("offline",)
    if loader in _FINETUNE_LOADERS:
        return RUNNERS
    return ("portal-package", "offline")


def propose_runner(loader: str, catalogue_path: str | None = None) -> tuple[str, str]:
    """(runner, reason) M7 proposes from the loader and, when present, the catalogue ``path``. The human approves it."""
    allowed = allowed_runners(loader)
    if catalogue_path is not None and catalogue_path not in PATHS:
        raise ValueError(f"unknown catalogue path {catalogue_path!r}, expected one of {list(PATHS)}")
    wanted = {"fine_tune": "portal-finetune", "training_package": "portal-package", "bring": "offline"}.get(
        catalogue_path or "")
    if wanted in allowed:
        return wanted, f"the catalogue path is {catalogue_path!r} and loader {loader!r} allows it"
    if wanted:
        return allowed[0], (f"the catalogue path {catalogue_path!r} asks for {wanted!r}, which loader {loader!r} "
                            f"cannot take; {allowed[0]!r} is the first runner it can")
    if loader == "tao":
        return "offline", "TAO needs NVIDIA's toolchain: the user runs the driver on their own GPU machine"
    if loader in _FINETUNE_LOADERS:
        return "portal-finetune", f"the portal's built-in trainer can rebuild a {loader!r} model from local weights"
    return "portal-package", f"loader {loader!r} has no built-in portal trainer: the portal executes the package"


def runner_problems(loader: str, runner: str) -> list[str]:
    """Why ``runner`` cannot be proposed for ``loader``. Empty when it can."""
    if runner not in RUNNERS:
        return [f"runner {runner!r} is not one of {list(RUNNERS)}"]
    if runner not in allowed_runners(loader):
        return [f"runner {runner!r} is not allowed for loader {loader!r}: allowed {list(allowed_runners(loader))}"]
    return []


# --------------------------------------------------------------------------- the licence gate (D-3)


def is_internal_only(spdx: str | None) -> bool:
    """True for the AGPL-3.0 family, which the owner accepted for internal and demo use (D-3, 2026-09-21)."""
    return (spdx or "").strip().lower() in _INTERNAL_ONLY


def licence_outcome(spdx: str | None, evidence: str | None) -> dict[str, Any]:
    """The gate outcome a licence gets without a human, or ``pending`` when a human must decide. Never a guess."""
    name = (spdx or "").strip()
    key = name.lower()

    def result(outcome: str, distribution: str, opens_gate: bool, reason: str) -> dict[str, Any]:
        return {"spdx": name or None, "evidence": (evidence or "").strip() or None, "gate_outcome": outcome,
                "distribution": distribution, "opens_gate": opens_gate, "reason": reason,
                "decided_by": None if opens_gate else ("automatic" if outcome == "approved" else OWNER_DECISION)}

    if key in _NO_LICENCE:
        return result("pending", "to_verify", True, "no licence was given: it is unverifiable until a human reads it")
    if not (evidence or "").strip():
        return result("pending", "to_verify", True, f"{name} was named with no evidence of where it was read")
    if _NON_COMMERCIAL.search(name):
        return result("pending", "to_verify", True, f"{name} is a non-commercial licence")
    if key in _INTERNAL_ONLY:
        return result("approved_internal_only", "internal_only", False,
                      f"{name} is copyleft. It is accepted for internal and demo use in the MVP. A customer who "
                      "uses the model commercially obtains their own commercial licence (for Ultralytics models, "
                      "from Ultralytics). The flag is shown downstream; nothing refuses on it")
    if key in _PERMISSIVE:
        return result("approved", "unrestricted", False, f"{name} is compatible with the product")
    return result("pending", "to_verify", True,
                  f"{name} is not a licence this tool can clear on its own (per-model or copyleft terms): a human "
                  "reads the terms and decides")


# --------------------------------------------------------------------------- the request


def _is_moving(revision: str | None) -> bool:
    return (revision or "").strip().lower() in _MOVING_REVISIONS


def _parts_problems(what: str, value: str, count: tuple[int, ...]) -> list[str]:
    parts = value.split("/")
    if len(parts) not in count or not all(_SAFE_PART.match(part) for part in parts):
        return [f"{what} {value!r} is not a plain name of {' or '.join(str(c) for c in count)} parts separated by '/'"]
    return []


def request_problems(req: FetchRequest) -> list[str]:
    """Why this request is refused before anything is downloaded."""
    problems: list[str] = []
    if req.hub not in HUBS:
        return [f"hub {req.hub!r} is not one of {list(HUBS)}"]
    if req.loader not in LOADERS:
        problems.append(f"loader {req.loader!r} is not one of {list(LOADERS)}")
    if req.loader == "none":
        problems.append("loader 'none' means trained from scratch: there is no base model to fetch")
    if not _SAFE_PART.match(req.model_id or ""):
        problems.append(f"model id {req.model_id!r} is not a plain name")
    if req.hub == "aihub":
        return problems + [
            "a Qualcomm AI Hub download is a compiled inference artifact and cannot be fine-tuned. Look the model "
            "up in the open-source `qai_hub_models` package, read which upstream repo and weights it loads, and "
            "fetch THAT source (--hub huggingface|github ... --via aihub:<model>). A source that was not read "
            "there is written as `unverified` in the proposal"]
    if req.hub == "ngc":
        name, _, version = req.ref.partition(":")
        problems += _parts_problems("NGC model", name, (2, 3))
        if _is_moving(version) or (req.revision and req.revision != version):
            problems.append(f"an NGC ref names its version, as org/team/model:version; {req.ref!r} with revision "
                            f"{req.revision!r} does not pin one")
        return problems
    if _is_moving(req.revision):
        problems.append(f"revision {req.revision!r} is not pinned: name a commit or a release tag, never 'latest' "
                        "or a branch" + _pin_hint(req.hub))
    if req.hub == "huggingface":
        problems += _parts_problems("Hugging Face repo", req.ref, (1, 2))
    elif req.hub == "github":
        problems += _parts_problems("GitHub release asset (owner/repo/asset)", req.ref, (3,))
    elif req.hub == "ultralytics":
        problems += _parts_problems("Ultralytics asset", req.ref, (1,))
    elif req.hub == "torchvision" and not _is_moving(req.revision) and not _TORCHVISION_FILE.match(req.revision or ""):
        problems.append(f"revision {req.revision!r} is not a torchvision weights file name such as "
                        "'mobilenet_v3_small-047dcff4.pth'" + _pin_hint("torchvision"))
    if not _is_moving(req.revision) and not re.match(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$", req.revision or ""):
        problems.append(f"revision {req.revision!r} is not a plain tag, commit or file name")
    return problems


def _pin_hint(hub: str) -> str:
    return {
        "ultralytics": f". For Ultralytics it is the release tag of github.com/{_ULTRALYTICS_REPO} that holds the file",
        "torchvision": ". For torchvision it is the weights file name from the model's `Weights` enum URL; its "
                       "suffix is the start of the file's sha256, which is checked after the download",
    }.get(hub, "")


def release_url(req: FetchRequest) -> str:
    """The one https URL a release-asset source resolves to (github, ultralytics, torchvision)."""
    if req.hub == "torchvision":
        return _TORCHVISION_BASE + str(req.revision)
    if req.hub == "ultralytics":
        return f"https://github.com/{_ULTRALYTICS_REPO}/releases/download/{req.revision}/{req.ref}"
    owner, repo, asset = req.ref.split("/")
    return f"https://github.com/{owner}/{repo}/releases/download/{req.revision}/{asset}"


# --------------------------------------------------------------------------- default downloaders (network; never in tests)


def _download_huggingface(req: FetchRequest, target: Path) -> None:
    try:
        from huggingface_hub import snapshot_download  # lazy: this module imports without it
    except ImportError as exc:
        raise FetchError(["huggingface_hub is not installed: `pip install huggingface_hub`, then run again"]) from exc
    # The token is read here and handed to the library. It is never stored, logged or returned.
    snapshot_download(repo_id=req.ref, revision=req.revision, local_dir=str(target),
                      token=os.environ.get(TOKEN_ENV["huggingface"]) or None)


def _download_ngc(req: FetchRequest, target: Path) -> None:
    if not os.environ.get(TOKEN_ENV["ngc"]):
        raise FetchError([f"{TOKEN_ENV['ngc']} is not set in this shell: NGC refuses the download without it"])
    exe = shutil.which("ngc")
    if exe is None:
        raise FetchError(["the `ngc` command is not installed: install the NGC CLI, then run again"])
    done = subprocess.run([exe, "registry", "model", "download-version", req.ref, "--dest", str(target)],  # noqa: S603
                          capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise FetchError([f"ngc refused the download (exit {done.returncode}): {done.stderr.strip()[-400:]}"])


def _download_release_asset(req: FetchRequest, target: Path) -> None:
    import urllib.request  # lazy, like the other two: nothing here touches a network at import

    url = release_url(req)
    name = url.rsplit("/", 1)[1]
    with urllib.request.urlopen(url, timeout=60) as response, (target / name).open("wb") as out:  # noqa: S310 - https, built above
        shutil.copyfileobj(response, out, 1024 * 1024)


def default_downloader(hub: str) -> Downloader:
    if hub == "huggingface":
        return _download_huggingface
    if hub == "ngc":
        return _download_ngc
    return _download_release_asset


# --------------------------------------------------------------------------- what arrived


def _inventory(weights: Path, boundary: Path) -> dict[str, dict[str, Any]]:
    """Every downloaded file with its sha256 and size. Refuses a link that leads out of the model folder."""
    files: dict[str, dict[str, Any]] = {}
    for current, dirs, names in os.walk(weights):
        dirs[:] = sorted(d for d in dirs if d not in {".cache", "__pycache__"})  # huggingface_hub's bookkeeping
        for name in sorted(names):
            path = Path(current) / name
            if not path.resolve().is_relative_to(boundary):
                raise FetchError([f"{path} resolves outside the model folder: a link leads out of it. Remove it"])
            files[path.relative_to(weights).as_posix()] = {"sha256": _sha256(path), "size": path.stat().st_size}
    if not files:
        raise FetchError(["the download wrote no file: nothing to hash, so nothing is recorded"])
    return files


def _entry_file(files: dict[str, dict[str, Any]]) -> str | None:
    """The single weights file a loader opens, or None when the loader reads the whole folder (a snapshot)."""
    return next(iter(files)) if len(files) == 1 else None


def _weights_digest(files: dict[str, dict[str, Any]]) -> str:
    """One hash for the whole download: the file's own for one file, else a hash over the sorted listing."""
    if len(files) == 1:
        return next(iter(files.values()))["sha256"]
    listing = "".join(f"{meta['sha256']}  {name}\n" for name, meta in sorted(files.items()))
    return hashlib.sha256(listing.encode("utf-8")).hexdigest()


def _torchvision_problems(req: FetchRequest, files: dict[str, dict[str, Any]]) -> list[str]:
    match = _TORCHVISION_FILE.match(req.revision or "")
    got = files.get(str(req.revision), {}).get("sha256", "")
    if req.hub == "torchvision" and match and not got.startswith(match.group(1)):
        return [f"{req.revision} has sha256 {got[:8] or 'nothing'}…, but its name promises {match.group(1)}…: "
                "this is not the file torchvision published"]
    return []


# --------------------------------------------------------------------------- the three files


def _card(req: FetchRequest, files: dict[str, dict[str, Any]], licence: dict[str, Any]) -> dict[str, Any]:
    pinned_by = "commit" if re.fullmatch(r"[0-9a-f]{40}", req.revision or "") else "tag_or_file"
    return {
        "schema": CARD_SCHEMA,
        "model_id": req.model_id,
        "catalogue_id": req.catalogue_id,
        "source": {"hub": req.hub, "ref": req.ref, "revision": req.revision, "pinned_by": pinned_by, "via": req.via},
        "loader": req.loader,
        "sha256": _weights_digest(files),
        "entry": _entry_file(files),
        "files": files,
        "licence": {key: licence[key] for key in ("spdx", "evidence", "gate_outcome", "distribution", "reason",
                                                   "decided_by")},
        # Also at the top, where the portal looks for the flag that travels (Web ADR-0011 S-15). One value.
        "distribution": licence["distribution"],
        "allowed_runners": list(allowed_runners(req.loader)),
        "selection_note": req.selection_note,
        "token_env": TOKEN_ENV.get(req.hub),
        "fetched_at": _now(),
    }


def card_markdown(card: dict[str, Any]) -> str:
    licence, source = card["licence"], card["source"]
    pending = licence["gate_outcome"] == "pending"
    via = f" (looked up through `{source['via']}`)" if source["via"] else ""
    access = f"needs `{card['token_env']}` in the environment when the source is gated" if card["token_env"] else "public"
    lines = [
        f"# Base model: {card['model_id']}",
        "",
        "| | |",
        "|---|---|",
        f"| Source | `{source['hub']}` · `{source['ref']}`{via} |",
        f"| Pinned revision | `{source['revision']}` ({source['pinned_by']}) |",
        f"| Loader | `{card['loader']}` · runners allowed: {', '.join(card['allowed_runners'])} |",
        f"| Catalogue entry | {card['catalogue_id'] or 'unlisted'} |",
        f"| sha256 | `{card['sha256']}` ({len(card['files'])} file(s), listed in `{CARD_JSON}`) |",
        f"| Access | {access} |",
        "",
        "## Licence",
        "",
        f"- **Licence:** {licence['spdx'] or 'not given'}",
        f"- **Where it was read:** {licence['evidence'] or 'nowhere: it was not verified'}",
        f"- **Gate outcome:** `{licence['gate_outcome']}` · **distribution:** `{licence['distribution']}`",
        f"- **Why:** {licence['reason']}",
        f"- **Decided by:** {licence['decided_by'] or 'nobody yet'}",
    ]
    if pending:
        lines += ["", f"**The hard gate `{LICENCE_GATE}` is open and the run stops here.** A human reads the licence "
                      "terms and chooses one of three outcomes: **approved** (compatible with the product), "
                      "**approved, internal and demo use only** (the flag `distribution: internal_only` travels "
                      "with the model), or **rejected** (choose another model)."]
    if source["pinned_by"] != "commit":
        lines += ["", "The revision is a tag or a file name. A tag can be moved; the sha256 above is what proves "
                      "which file this is."]
    if licence["distribution"] == "internal_only":
        lines += ["", "`distribution: internal_only` is information that travels with the weights and is shown in "
                      "the portal. For the MVP nothing refuses a release on it."]
    if card["selection_note"]:
        lines += ["", "## Why this differs from the portal's pick", "", card["selection_note"]]
    return "\n".join(lines) + "\n"


def _write_base(base: Path, card: dict[str, Any]) -> None:
    loader = {"schema": LOADER_SCHEMA, "loader": card["loader"], "model_id": card["model_id"],
              "weights_dir": WEIGHTS_DIR, "entry": card["entry"], "weights_sha256": card["sha256"],
              "files": {name: meta["sha256"] for name, meta in card["files"].items()}}
    (base / LOADER_FILE).write_text(json.dumps(loader, indent=2) + "\n", encoding="utf-8")
    (base / CARD_JSON).write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
    (base / CARD_MD).write_text(card_markdown(card), encoding="utf-8")
    # The folder ignores its own weights, so no project .gitignore has to be edited (the project owns that file).
    (base / ".gitignore").write_text(f"# written by /model-fetch: weights never enter git\n{WEIGHTS_DIR}/\n",
                                     encoding="utf-8")


def _safe_base(dest: str) -> Path:
    root = Path(dest).resolve()
    base = Path(dest) / BASE_DIR
    if not root.is_dir():
        raise FetchError([f"{dest} is not a model folder"])
    for path in (base.parent, base, base / WEIGHTS_DIR):
        if path.is_symlink() or (path.exists() and not path.resolve().is_relative_to(root)):
            raise FetchError([f"{path} is a link or leads outside the model folder: remove it"])
    return base


def fetch(dest: str, req: FetchRequest, *, downloader: Downloader | None = None, force: bool = False,
          open_gate: bool = True) -> dict[str, Any]:
    """Download, hash and record a base model under ``<dest>/model/base/``. Opens the licence gate when one is owed."""
    problems = request_problems(req)
    if problems:
        raise FetchError(problems)
    base = _safe_base(dest)
    weights = base / WEIGHTS_DIR
    if weights.is_dir() and any(weights.iterdir()):
        if not force:
            raise FetchError([f"{weights} already holds a download: pass --force to replace it"])
        shutil.rmtree(weights)
        for stale in (CARD_JSON, CARD_MD, LOADER_FILE):  # they describe the download that was just removed
            (base / stale).unlink(missing_ok=True)
    weights.mkdir(parents=True, exist_ok=True)
    (downloader or default_downloader(req.hub))(req, weights)
    shutil.rmtree(weights / ".cache", ignore_errors=True)  # huggingface_hub's bookkeeping is not part of the model
    files = _inventory(weights, Path(dest).resolve())
    problems = _torchvision_problems(req, files)
    if problems:
        shutil.rmtree(weights)  # a file that is not what its name promises does not stay beside a card
        raise FetchError(problems)
    licence = licence_outcome(req.licence_spdx, req.licence_evidence)
    card = _card(req, files, licence)
    _write_base(base, card)
    gate_action = None
    if licence["opens_gate"] and open_gate:
        # Re-arms an existing gate: an approval given for the model that was here before is not one for this model.
        gate_action = gt.open_pending(dest, LICENCE_GATE, stage=GATE_STAGE, opened_by="model-fetch")
    elif open_gate:
        gate_action = _close_superseded_gate(dest, card)
    return {"card": card, "base": str(base), "gate": LICENCE_GATE if licence["opens_gate"] else None,
            "gate_action": gate_action}


def _close_superseded_gate(dest: str, card: dict[str, Any]) -> str | None:
    """A licence gate left pending by the model that was replaced is about weights that are gone.

    The model now in the folder needs no human (its outcome is in the card), so the gate is closed automatically,
    with that reason on the record. Left pending, it would block M7 for ever over a model nobody uses.
    """
    gate = gt.load(dest).gates.get(LICENCE_GATE)
    if gate is None or gate.status != "pending":
        return None
    reason = (f"superseded: the base model was replaced by {card['model_id']} (sha256 {card['sha256'][:12]}), whose "
              f"licence {card['licence']['spdx']} needs no human: {card['licence']['gate_outcome']}")
    return gt.record_automatic(dest, LICENCE_GATE, stage=GATE_STAGE, passed=True, reason=reason,
                               identity=AUTOMATIC_IDENTITY)


def _decided_for_this_card(decision_time: str, card: dict[str, Any]) -> bool:
    """True when the decision was made AFTER these weights were fetched: only then is it about this model."""
    try:
        return datetime.fromisoformat(decision_time) > datetime.fromisoformat(str(card.get("fetched_at")))
    except ValueError:
        return False


# --------------------------------------------------------------------------- after the human decided


def read_card(dest: str) -> dict[str, Any]:
    path = Path(dest) / BASE_DIR / CARD_JSON
    if not path.is_file():
        raise FetchError([f"{BASE_DIR}/{CARD_JSON} is missing: /model-fetch writes it"])
    return json.loads(path.read_text(encoding="utf-8"))


def record_licence_decision(dest: str, outcome: str) -> dict[str, Any]:
    """Write the human's gate decision into the card. Refuses an outcome the gate does not carry.

    The decision itself is made through ``gate_state.py decide``, by a human. This only copies it into the card,
    so that it travels with the weights: it never decides.
    """
    outcomes = {"approved": ("approved", "unrestricted"), "approved_internal_only": ("approved", "internal_only"),
                "rejected": ("rejected", "to_verify")}
    if outcome not in outcomes:
        raise FetchError([f"outcome {outcome!r} is not one of {sorted(outcomes)}"])
    needed, distribution = outcomes[outcome]
    gate = gt.load(dest).gates.get(LICENCE_GATE)
    if gate is None or gate.status != needed or not gate.decisions:
        raise FetchError([f"gate {LICENCE_GATE!r} is {gate.status if gate else 'not open'}, not {needed}: a human "
                          "decides it first (gate_state.py decide), and this records what they decided"])
    decision = gate.decisions[-1]
    card = read_card(dest)
    if decision.identity == AUTOMATIC_IDENTITY or not _decided_for_this_card(decision.timestamp, card):
        raise FetchError([f"the last decision on {LICENCE_GATE!r} ({decision.identity}, {decision.timestamp}) was not "
                          f"made by a human about THIS model: {card['model_id']} (sha256 {card['sha256'][:12]}) was "
                          f"fetched at {card.get('fetched_at')}. An approval given for another model is never copied "
                          "onto this card"])
    card["licence"].update({"gate_outcome": outcome, "distribution": distribution,
                            "decided_by": f"{decision.identity} at the M7 gate, {decision.timestamp}",
                            "reason": decision.reason or card["licence"]["reason"]})
    card["distribution"] = distribution
    _write_base(Path(dest) / BASE_DIR, card)
    return card


# --------------------------------------------------------------------------- CLI


def _request_from_args(a: argparse.Namespace) -> FetchRequest:
    if not a.from_recommendation:
        missing = [flag for flag in ("hub", "ref", "loader", "model_id") if not getattr(a, flag)]
        if missing:
            raise FetchError([f"--{flag.replace('_', '-')} is required without --from-recommendation" for flag in missing])
        return FetchRequest(hub=a.hub, ref=a.ref, revision=a.revision, loader=a.loader, model_id=a.model_id,
                            licence_spdx=a.licence, licence_evidence=a.licence_evidence,
                            catalogue_id=a.catalogue_id, selection_note=a.selection_note, via=a.via)
    from . import recommendation as rec  # here, not at the top: recommendation imports this module

    req = rec.fetch_request(a.dest)
    if a.revision and req.revision and a.revision != req.revision:
        raise FetchError([f"the recommendation pins revision {req.revision!r}: --revision {a.revision!r} is another "
                          "model. Fetch a free-form source instead, and say why in --selection-note"])
    if a.revision and not req.revision:
        note = f"the portal's pick named no revision; {a.revision!r} was pinned at fetch"
        req = replace(req, revision=a.revision, selection_note=note)
    if a.licence_evidence:
        req = replace(req, licence_evidence=a.licence_evidence)
    return req


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="model_fetch", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download, hash and record a base model (uses the network)")
    f.add_argument("--dest", required=True, help="the model folder")
    f.add_argument("--from-recommendation", action="store_true",
                   help="fetch exactly the source the recorded model_recommendation.json picks")
    f.add_argument("--hub", choices=HUBS)
    f.add_argument("--ref", help="huggingface: org/model · ngc: org/team/model:version · github: owner/repo/asset · "
                                 "ultralytics: the file, e.g. yolov8n.pt · torchvision: the model name")
    f.add_argument("--revision", help="a commit, a release tag, or (torchvision) the weights file name. Never 'latest'")
    f.add_argument("--loader", choices=LOADERS)
    f.add_argument("--model-id")
    f.add_argument("--catalogue-id")
    f.add_argument("--licence", help="the SPDX id, as read from the source. Omit it when it could not be read")
    f.add_argument("--licence-evidence", help="where the licence was read: a URL or a file in the download")
    f.add_argument("--selection-note", help="why this choice differs from the portal's pick")
    f.add_argument("--via", help="the listing the source was looked up through, e.g. aihub:<model>")
    f.add_argument("--force", action="store_true", help="replace an existing download")
    li = sub.add_parser("licence", help="copy the human's decision on the licence gate into the card")
    li.add_argument("--dest", required=True)
    li.add_argument("--outcome", required=True, choices=("approved", "approved_internal_only", "rejected"))
    r = sub.add_parser("runner", help="print the runner M7 proposes for a loader")
    r.add_argument("--loader", required=True, choices=LOADERS)
    r.add_argument("--path", choices=PATHS, help="the catalogue path from model_recommendation.json")
    a = p.parse_args(argv)

    try:
        if a.cmd == "runner":
            runner, reason = propose_runner(a.loader, a.path)
            print(f"runner: {runner}  ({reason}). Allowed for this loader: {', '.join(allowed_runners(a.loader))}")
            return 0
        if a.cmd == "licence":
            card = record_licence_decision(a.dest, a.outcome)
            print(f"{BASE_DIR}/{CARD_JSON}: licence {card['licence']['gate_outcome']}, "
                  f"distribution {card['distribution']}")
            return 0
        result = fetch(a.dest, _request_from_args(a), force=a.force)
    except FetchError as exc:
        print("refused:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    card = result["card"]
    print(f"{result['base']}: {len(card['files'])} file(s), sha256 {card['sha256']}")
    print(f"licence {card['licence']['spdx'] or 'not given'} -> {card['licence']['gate_outcome']} "
          f"(distribution {card['distribution']}): {card['licence']['reason']}")
    if result["gate"]:
        print(f"gate {result['gate']!r} {result['gate_action']}: STOP. Show {BASE_DIR}/{CARD_MD} to the human, ask "
              "for one of the three outcomes, record it with gate_state.py decide, then run `model_fetch licence`.")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
