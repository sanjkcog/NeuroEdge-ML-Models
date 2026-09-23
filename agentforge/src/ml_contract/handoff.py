"""The two folders that name the portal boundary: `to-neuroedge/` and `from-neuroedge/` (ADR-0031).

`/agentforge-ml` never calls the portal (ADR-0025 D-1). Every exchange is a human carrying a file,
which is the right trust boundary and is not what this module changes. What it changes is that the
boundary had no shape: five artifacts went to the portal from five folders, each to a different
screen, and which of them applied depended on the runner approved at M7 — a routing table the
operator was expected to hold in their head.

**Outbound is a staging view, never a new home** (ADR-0031 D-3). Each artifact is COPIED here from a
canonical path that does not move, so nothing that reads it — generated training code,
`/usecase-audit`, the portal's validators — learns a new path. `handoff.json` records the source and
its sha256 at staging time, so a stale copy is a detectable fact: ``verify`` re-hashes the source.

**A staged artifact needs no gate.** It is a copy of something a gate already approved, and the only
new fact is where it went — which ``sent`` records, with the registration id the portal gave back.

    python -m agentforge.src.ml_contract.handoff stage  --dest <dest>
    python -m agentforge.src.ml_contract.handoff show   --dest <dest>
    python -m agentforge.src.ml_contract.handoff verify --dest <dest>
    python -m agentforge.src.ml_contract.handoff sent   --dest <dest> --artifact 03 --registration <id>
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

TO_DIR = "to-neuroedge"
FROM_DIR = "from-neuroedge"
SENT_DIR = "to-neuroedge/sent"
HANDOFF_JSON = "to-neuroedge/handoff.json"

#: The runner approved at M7 decides which artifacts apply (ADR-0028 D-1). Both routes are shown to
#: the operator either way -- someone handed a project needs to know which world they are in, and
#: that there is another one (ADR-0031 D-4).
RUNNERS = ("portal-package", "portal-finetune", "offline")

#: Ordered by UPLOAD order, not by milestone number: the order is what gets got wrong. The ordinal
#: is the artifact's stable id (`handoff sent --artifact 04`); the milestone is in the staged name so
#: the folder listing alone says what produced each file.
#: (ordinal, milestone, kind, source-path template, portal screen, which runners it applies to)
OUTBOUND: tuple[tuple[str, str, str, str, str, tuple[str, ...]], ...] = (
    ("01", "M8", "training-package", "{arch}/training-package.zip",
     "Step 3 · Model Strategy → Custom development → Training package",
     ("portal-package",)),
    ("02", "M9", "test-bundle", "data/portal_test.zip",
     "Step 3 · Train → Held-out evaluation → Upload test bundle",
     ("portal-package",)),
    ("03", "M9", "dataset-upload", "data/portal_upload.zip",
     "Step 3 · Model Strategy → Fine-tune a base model → Dataset",
     ("portal-finetune",)),
    ("04", "M11", "return-package", "{arch}/runs/{run_id}/return/upload.zip",
     "Step 3 · Model Strategy → Finished training return package",
     ("portal-package", "portal-finetune", "offline")),
    ("05", "M12", "simulator-data", "sim/",
     "Step 5 · Virtual Run → Upload test data",
     ("portal-package", "portal-finetune", "offline")),
    # ADR-0031 D-7/D-8: an addition to the unweighted export, never a replacement. Its own folder and
    # its own manifest, because the portal keeps one export per use case and replays its first file.
    ("06", "M12", "demo-simulator-data", "sim-demo/",
     "Step 5 · Virtual Run → Upload test data (replaces the export above while you demo)",
     ("portal-package", "portal-finetune", "offline")),
)

#: What comes back the other way, and which milestone is waiting for it. Recognition and unpacking
#: belong to `intake`; this is the operator-facing half -- what to fetch and from where. `after` is
#: the outbound ordinal it follows in the walk-through: the package comes back once training ran.
#: (kind, intake kind, milestone, portal screen, which runners, after)
INBOUND: tuple[tuple[str, str, str, str, tuple[str, ...], str], ...] = (
    ("model-package", "model_package", "M9",
     "Step 3 · Optimize → Downloads → Download all as .zip",
     ("portal-package", "portal-finetune"), "03"),
    ("held-out-result", "held_out_result", "M10",
     "Step 3 · Train → Held-out evaluation → Download result",
     ("portal-package", "portal-finetune"), "03"),
)

TO_README = """# Give these to NeuroEdge

Files this run produces for the portal. Each one is a **copy** — the original stays where the tools
read it, and `handoff.json` records the source and its hash, so a stale copy here is detectable
(`handoff verify`).

They are numbered in **upload order**, not by milestone. Upload one, paste the registration id or
the refusal back with `handoff sent`, and it moves to `sent/`.

Run `/agentforge-ml handoff` to see what is outstanding for this project's runner, and where each
file goes in the portal.

What comes back the other way goes in `../from-neuroedge/`.
"""

#: The originals are kept out of git by the project's own rules (training-package.zip can hold the
#: dataset; data/portal_test.zip IS the sealed test split). A copy under a new name would slip past
#: those rules, so the staging folder ignores its own copies -- without editing the project's
#: .gitignore, which the project owns. handoff.json and the README stay tracked.
TO_GITIGNORE = """# Copies of artifacts whose originals live elsewhere (ADR-0031 D-3). They can hold the dataset and the
# sealed test split, and `handoff stage` rebuilds them in seconds: never commit them.
*.zip
"""

FROM_README_TAIL = """
## What comes back after training

| File | Needed by | Where to get it |
|---|---|---|
| the portal's model package (`*-model-package.zip`) | M9 | Portal **Step 3 · Optimize** → *Downloads* → **Download all as .zip** |
| the held-out result (`*.json`) | M10 | Portal **Step 3 · Train** → *Held-out evaluation* → **Download result** |

Drop either here as it is. The run reads the package's own `model_artifact.json` for the run id and
unpacks it to `<arch>/runs/<run_id>/model-package/` itself — never pick a run id by hand, and never
unzip it yourself. A package whose `lock_sha256` is not this project's lock is refused, naming both
hashes, and nothing is written.
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_tree(root: str) -> str:
    """A stable hash of a folder: every file's relative path and bytes, in sorted order.

    `sim/` is staged as a zip, so its source is a folder. Hashing the tree rather than the zip keeps
    the comparison meaningful — a zip's bytes change with its timestamps, the data does not.
    """
    h = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            with open(full, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
    return h.hexdigest()


def _read_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


#: `model_proposed.md` names the runner in the operator's words; RUNNERS are the routing ids.
_RUNNER_WORDS = {
    "package": "portal-package", "portal-package": "portal-package", "training-package": "portal-package",
    "fine-tune": "portal-finetune", "finetune": "portal-finetune", "portal-finetune": "portal-finetune",
    "offline": "offline", "local": "offline",
}


def runner_of(dest: str) -> str | None:
    """The runner approved at M7. None when M7 has not run yet.

    `model_proposed.md` is the record: M7 writes the decision there under `## Runner`, in the words
    the proposal uses (`package`), and the approval is against that document. `run.json` is checked
    first for a run that records it structurally, but a project whose proposal says `package` and
    whose run.json does not mention a runner has still approved one -- reading only run.json showed
    the CNC project as having no route at all.
    """
    run = _read_json(os.path.join(dest, "run.json"))
    for key in ("runner", "approved_runner"):
        value = run.get(key)
        if isinstance(value, str) and value in RUNNERS:
            return value
    stages = run.get("stages") if isinstance(run.get("stages"), dict) else {}
    value = (stages.get("model-select") or {}).get("runner") if isinstance(stages, dict) else None
    if isinstance(value, str) and value in RUNNERS:
        return value

    proposal = os.path.join(dest, "model_proposed.md")
    try:
        with open(proposal, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    section = re.split(r"^##\s+Runner\s*$", text, flags=re.M)
    if len(section) < 2:
        return None
    head = re.split(r"^##\s", section[1], flags=re.M)[0]

    # Every runner NAMED in the section, with the line it was named on. Taking the first one was
    # wrong: the section also argues which runners were rejected, so a proposal reading
    # "**`offline`** was tried first ... ultimately **`portal-package`**" returned `offline` --
    # a valid runner id, so nothing downstream could tell it was the wrong one. A name whose line
    # rejects it is dropped, and anything still ambiguous returns None rather than a guess.
    rejected = re.compile(r"(?i)\b(not the runner|rejected|ruled out|was tried|instead of|rather than)\b")
    candidates: list[str] = []
    for line in head.splitlines():
        for token in re.findall(r"[*`\"']([A-Za-z][A-Za-z-]*)[*`\"']", line):
            runner = _RUNNER_WORDS.get(token.lower())
            if runner and not rejected.search(line):
                candidates.append(runner)
    unique = list(dict.fromkeys(candidates))
    return unique[0] if len(unique) == 1 else None


def _architectures(dest: str) -> list[str]:
    """Folders that look like an M8 architecture: they hold a train.py."""
    out = []
    for name in sorted(os.listdir(dest)) if os.path.isdir(dest) else []:
        folder = os.path.join(dest, name)
        if os.path.isdir(folder) and os.path.exists(os.path.join(folder, "train.py")):
            out.append(name)
    return out


def architecture_of(dest: str) -> str | None:
    """The architecture whose artifacts are this project's, or None when that is ambiguous.

    One objective is usually built more than once -- the CNC project holds both `1DCNN/` and
    `MiniRocket/`, a deep model and its baseline. Taking the alphabetically first would have staged
    and uploaded the abandoned one whenever the approved architecture sorted later, with nothing
    downstream able to tell. Precedence, strongest evidence first:

      1. the only architecture that produced a model package (M9 ran there)
      2. the only one holding a training-package.zip -- M8's deliverable, and what the runner
         executes; a baseline folder inside the same package has no zip of its own
      3. the one `model_proposed.md` names, when exactly one matches
      4. the sole architecture, when there is only one

    Anything else is ambiguous, and an ambiguous project is told so rather than guessed at.
    """
    archs = _architectures(dest)
    if not archs:
        return None
    if len(archs) == 1:
        return archs[0]

    # 0. the architecture the portal's own package named, recorded when intake unpacked it
    unpacked = ((_read_json(os.path.join(dest, "inputs", "inputs.json")).get("inputs") or {})
                .get("model_package") or {}).get("arch")
    if unpacked in archs:
        return unpacked

    built = [a for a in archs
             if any(os.path.isdir(os.path.join(dest, a, "runs", r, "model-package"))
                    for r in (os.listdir(os.path.join(dest, a, "runs"))
                              if os.path.isdir(os.path.join(dest, a, "runs")) else []))]
    if len(built) == 1:
        return built[0]

    packaged = [a for a in archs if os.path.isfile(os.path.join(dest, a, "training-package.zip"))]
    if len(packaged) == 1:
        return packaged[0]

    try:
        with open(os.path.join(dest, "model_proposed.md"), encoding="utf-8") as fh:
            head = fh.read(4000)
    except OSError:
        head = ""
    named = [a for a in archs if re.search(rf"\b{re.escape(a)}\b", head, re.I)]
    return named[0] if len(named) == 1 else None


def _latest_run(dest: str, arch: str) -> str | None:
    """The run whose package intake unpacked (read from the package), else the newest run folder."""
    recorded = (_read_json(os.path.join(dest, "inputs", "inputs.json")).get("inputs") or {}).get("model_package") or {}
    if recorded.get("arch") == arch and recorded.get("run_id") \
            and os.path.isdir(os.path.join(dest, arch, "runs", recorded["run_id"])):
        return recorded["run_id"]
    runs = os.path.join(dest, arch, "runs")
    if not os.path.isdir(runs):
        return None
    names = sorted(n for n in os.listdir(runs) if os.path.isdir(os.path.join(runs, n)))
    return names[-1] if names else None


def _resolve(dest: str, template: str, arch: str | None, run_id: str | None) -> str | None:
    """The canonical source path for an outbound artifact, or None when it cannot be named yet."""
    if "{arch}" in template and not arch:
        return None
    if "{run_id}" in template and not run_id:
        return None
    rel = template.format(arch=arch or "", run_id=run_id or "")
    return os.path.join(dest, rel.rstrip("/")) if rel else None


def plan(dest: str) -> list[dict[str, Any]]:
    """Every outbound artifact, whether its source exists, and whether this runner needs it."""
    runner = runner_of(dest)
    arch = architecture_of(dest)
    run_id = _latest_run(dest, arch) if arch else None
    rows: list[dict[str, Any]] = []
    for ordinal, milestone, kind, template, screen, runners in OUTBOUND:
        source = _resolve(dest, template, arch, run_id)
        is_dir = template.endswith("/")
        exists = bool(source) and (os.path.isdir(source) if is_dir else os.path.isfile(source))
        rows.append({
            "ordinal": ordinal,
            "milestone": milestone,
            "kind": kind,
            "source": source,
            "is_dir": is_dir,
            "exists": exists,
            "portal_screen": screen,
            "applies": runner is None or runner in runners,
            "runners": list(runners),
            "staged_name": f"{ordinal}-{milestone}-{kind}.zip",
        })
    return rows


def _rename_staged(dest: str, old: str, new: str) -> None:
    """Carry a copy staged under an earlier name to the current one, wherever it now sits."""
    for folder in (TO_DIR, SENT_DIR):
        src, dst = os.path.join(dest, folder, old), os.path.join(dest, folder, new)
        if os.path.exists(src) and not os.path.exists(dst):
            os.replace(src, dst)


def stage(dest: str) -> list[str]:
    """Copy every outbound artifact that exists into `to-neuroedge/`, and record it.

    A folder source (`sim/`) is zipped here, so the operator never zips by hand. Re-staging an
    artifact whose source changed replaces the copy and re-records its hash.
    """
    folder = os.path.join(dest, TO_DIR)
    os.makedirs(folder, exist_ok=True)
    for name, text in (("README.md", TO_README), (".gitignore", TO_GITIGNORE)):
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)

    record = _read_json(os.path.join(dest, HANDOFF_JSON))
    artifacts: dict[str, Any] = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    lines: list[str] = []
    for row in plan(dest):
        if not row["applies"] or not row["exists"]:
            continue
        source, target = row["source"], os.path.join(folder, row["staged_name"])
        source_sha = sha256_tree(source) if row["is_dir"] else sha256_file(source)
        previous = artifacts.get(row["ordinal"]) or {}
        if previous.get("staged_name") and previous["staged_name"] != row["staged_name"]:
            _rename_staged(dest, previous["staged_name"], row["staged_name"])
            previous["staged_name"] = row["staged_name"]
        # `sent` MOVES the copy to sent/, so the staged path no longer exists for an artifact that
        # was already uploaded. Looking only there made an unchanged, already-sent artifact fall
        # through to the re-copy below, which rebuilt the entry with sent_at/registration_id reset
        # to None -- losing the portal's registration id irrecoverably, and inviting the operator
        # to upload it a second time.
        already_here = os.path.exists(target) or os.path.exists(
            os.path.join(dest, SENT_DIR, row["staged_name"]))
        if previous.get("source_sha256") == source_sha and already_here:
            state = "sent" if previous.get("sent_at") else "unchanged"
            lines.append(f"  {row['staged_name']:<34} {state}")
            continue
        if row["is_dir"]:
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
                for dirpath, dirnames, filenames in os.walk(source):
                    dirnames.sort()
                    for name in sorted(filenames):
                        full = os.path.join(dirpath, name)
                        zf.write(full, os.path.relpath(full, os.path.dirname(source)).replace(os.sep, "/"))
        else:
            shutil.copyfile(source, target)
        artifacts[row["ordinal"]] = {
            "kind": row["kind"],
            "milestone": row["milestone"],
            "source": os.path.relpath(source, dest).replace(os.sep, "/"),
            "source_sha256": source_sha,
            "staged_name": row["staged_name"],
            "staged_sha256": sha256_file(target),
            "staged_at": _now(),
            "portal_screen": row["portal_screen"],
            # A re-stage after a real source change supersedes what was sent, so the previous
            # registration is kept as history rather than dropped: it says what the portal holds.
            "sent_at": None,
            "registration_id": None,
            "superseded": ([*previous.get("superseded", []),
                            {"registration_id": previous.get("registration_id"),
                             "sent_at": previous.get("sent_at"),
                             "source_sha256": previous.get("source_sha256")}]
                           if previous.get("sent_at") else previous.get("superseded", [])),
        }
        lines.append(f"  {row['staged_name']:<34} staged")
    record.update({"schema": "agentforge-ml-handoff/1", "runner": runner_of(dest),
                   "updated_at": _now(), "artifacts": artifacts})
    os.makedirs(os.path.join(dest, TO_DIR), exist_ok=True)
    with open(os.path.join(dest, HANDOFF_JSON), "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    write_start_here(dest)
    return lines or ["  nothing to stage yet"]


def verify(dest: str) -> tuple[int, list[str]]:
    """Re-hash every staged artifact's source. A copy that no longer matches is named, not fixed."""
    record = _read_json(os.path.join(dest, HANDOFF_JSON))
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    lines, drift = [], 0
    for ordinal in sorted(artifacts):
        entry = artifacts[ordinal]
        name = entry.get("staged_name", ordinal)
        source = os.path.join(dest, entry.get("source", ""))
        if not os.path.exists(source):
            lines.append(f"  {name:<34} SOURCE GONE  {entry.get('source')}")
            drift += 1
            continue
        now = sha256_tree(source) if os.path.isdir(source) else sha256_file(source)
        if now != entry.get("source_sha256"):
            lines.append(f"  {name:<34} STALE  {entry.get('source')} changed since it was staged; "
                         "re-run `handoff stage`")
            drift += 1
        else:
            lines.append(f"  {name:<34} current")
    if not lines:
        return 0, ["  nothing staged yet"]
    return (1 if drift else 0), lines


def sent(dest: str, ordinal: str, registration: str) -> str:
    """Record that a staged artifact was uploaded, and move it to `sent/`.

    `registration` is the portal's id, or its refusal. A refusal is recorded verbatim: a portal 422
    is a defect to fix upstream, not a second opinion to argue with (ADR-0025).
    """
    path = os.path.join(dest, HANDOFF_JSON)
    record = _read_json(path)
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    entry = artifacts.get(ordinal)
    if not entry:
        raise ValueError(f"nothing staged as {ordinal!r}; run `handoff stage` and see `handoff show`")
    entry["sent_at"] = _now()
    entry["registration_id"] = registration
    staged = os.path.join(dest, TO_DIR, entry["staged_name"])
    if os.path.exists(staged):
        os.makedirs(os.path.join(dest, SENT_DIR), exist_ok=True)
        os.replace(staged, os.path.join(dest, SENT_DIR, entry["staged_name"]))
    record["updated_at"] = _now()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    write_start_here(dest)
    return f"{entry['staged_name']} recorded as sent ({registration})"


# --------------------------------------------------------------------------- show

ROUTE_LABEL = {"portal-package": "Trained on the portal (training package)",
               "portal-finetune": "Fine-tuned on the portal",
               "offline": "Trained offline"}
#: What a route means for M9, said once, for the operator who has been handed a project.
ROUTE_NOTE = {
    "portal-package": "The portal runs the training package; the model comes back as a package you download.",
    "portal-finetune": "The portal's own trainer fine-tunes the base model on the dataset you upload.",
    "offline": "M9 runs RUN_ON_GPU.md on your own machine; nothing goes to the portal before the return "
               "package, which is how the model enters the portal at all.",
}


def _steps() -> list[tuple[str, Any]]:
    """Outbound and inbound in the order they happen: the package comes back after training ran."""
    steps: list[tuple[str, Any]] = []
    for row in OUTBOUND:
        steps.append(("out", row))
        steps += [("in", inbound) for inbound in INBOUND if inbound[5] == row[0]]
    return steps


def _inbound_state(dest: str, intake_kind: str) -> str:
    recorded = (_read_json(os.path.join(dest, "inputs", "inputs.json")).get("inputs") or {}).get(intake_kind)
    if recorded and recorded.get("path"):
        return f"received · {recorded['path']}"
    return f"awaited — drop it in {FROM_DIR}/ as downloaded, then `intake check --need {intake_kind}`"


def show(dest: str) -> list[str]:
    """What to do next, for this project's runner -- the route not taken is shown too, greyed, not hidden."""
    runner = runner_of(dest)
    record = _read_json(os.path.join(dest, HANDOFF_JSON))
    artifacts = record.get("artifacts") if isinstance(record.get("artifacts"), dict) else {}
    rows = {row["ordinal"]: row for row in plan(dest)}

    out = [f"Runner: {runner}  (approved at M7; model_proposed.md § Runner)" if runner
           else "Runner: not approved yet (M7) — every route is shown"]
    archs = _architectures(dest)
    arch = architecture_of(dest)
    if arch:
        out.append(f"Architecture: {arch}")
    elif len(archs) > 1:
        out.append(f"  ⚠ {len(archs)} architectures here ({', '.join(archs)}) and nothing says which is this "
                   "project's. Anything resolved per architecture is shown as not produced.")
    out.append("")

    ordered = [runner] if runner else []
    ordered += [r for r in RUNNERS if r != runner]
    for route in ordered:
        mine = route == runner
        if mine:
            out.append(f"  {ROUTE_LABEL[route]} — this project's route")
        elif runner:
            out.append(f"  {ROUTE_LABEL[route]} — not this project's route")
        else:
            out.append(f"  {ROUTE_LABEL[route]}")
        out.append(f"    {ROUTE_NOTE[route]}")
        n = 0
        for direction, item in _steps():
            if route not in (item[5] if direction == "out" else item[4]):
                continue
            n += 1
            if direction == "out":
                row = rows[item[0]]
                optional = "  (optional: a demo only)" if row["kind"] == "demo-simulator-data" else ""
                if not (mine or runner is None):
                    out.append(f"    ·  upload   {row['staged_name']}{optional}")
                    continue
                entry = artifacts.get(row["ordinal"]) or {}
                if entry.get("sent_at"):
                    state = f"sent · {entry.get('registration_id')}"
                elif os.path.exists(os.path.join(dest, TO_DIR, row["staged_name"])):
                    state = "STAGED — upload it"
                elif row["exists"]:
                    state = "ready — run `handoff stage`"
                else:
                    state = f"not produced yet ({row['milestone']})"
                out.append(f"    {n}. upload   {TO_DIR}/{row['staged_name']}{optional}")
                out.append(f"                → {row['portal_screen']}")
                out.append(f"                {state}")
            else:
                kind, intake_kind, milestone, screen, _runners, _after = item
                if not (mine or runner is None):
                    out.append(f"    ·  download {kind} ({milestone})")
                    continue
                out.append(f"    {n}. download the {kind.replace('-', ' ')} ({milestone})")
                out.append(f"                ← {screen}")
                out.append(f"                {_inbound_state(dest, intake_kind)}")
        out.append("")
    return out


# --------------------------------------------------------------------------- 00-START-HERE.md (D-5)

START_HERE = "00-START-HERE.md"

#: M0-M13: the stage id `run.json` records, what the milestone does, and where its output lands.
#: The folders are the paths code reads -- never renamed (ADR-0031 D-5); this table is the navigation.
MILESTONES: tuple[tuple[str, str, str, str], ...] = (
    ("M0", "destination", "lock the use case", "inputs/, use_case.lock.json, audit/M0.md"),
    ("M1", "scout", "find a dataset", "data/dataset-card.md"),
    ("M2", "plan", "price and scope the download", "data/fetch-plan.json"),
    ("M3", "download", "download it", "data/raw/"),
    ("M4", "verify", "measure it, split it, build the contract set", "data/splits/, data/contract/, audit/M4.md"),
    ("M5", "label", "label it and review the split", "data/label-manifest.md, data/split-review.md"),
    ("M6", "synth", "synthetic data, or a recorded skip", "data/synthetic/, data/synth-review.md"),
    ("M7", "model-select", "propose the model and the runner", "model_proposed.md, model/base/"),
    ("M8", "model-build", "generate the training code and package", "{arch}/, audit/M8.md"),
    ("M9", "train", "train it, on the runner approved at M7", "{arch}/runs/<run_id>/model-package/"),
    ("M10", "eval", "the held-out evaluation", "{arch}/runs/<run_id>/portal_held_out.json"),
    ("M11", "return", "build the return package", "{arch}/runs/<run_id>/return/, audit/M11.md"),
    ("M12", "data-simulator", "simulator data (and a demo replay)", "sim/, sim-demo/"),
    ("M13", "model-card", "the model card", "model-card.md"),
)
GUIDES = (("dataset.md", "M4", "what the data is, where each number comes from, what is unconfirmed"),
          ("model.md", "M8", "what the model is, its KPI, how to read the number, what would move it"),
          ("demo.md", "M12", "how to run the demo, what to watch, what should happen and when"))


def _stage_status(run: dict[str, Any], gates: dict[str, Any], stage: str) -> str:
    stages = run.get("stages") if isinstance(run.get("stages"), dict) else {}
    value = stages.get(stage)
    status = value.get("status") if isinstance(value, dict) else value
    if status == "complete":
        return "done"
    owed = [gid for gid, g in gates.items()
            if isinstance(g, dict) and g.get("stage") == stage and g.get("status") == "pending"]
    if owed:
        return f"gated ({', '.join(owed)})"
    pending = run.get("gate") if isinstance(run.get("gate"), dict) else {}
    if pending.get("pending") and pending.get("stage") == stage:
        return "awaiting you" if pending.get("reason") == "waiting_external" else "gated"
    if status == "in_progress":
        return "in progress"
    if status == "skipped":
        return "skipped"
    return "not started"


def start_here(dest: str) -> str:
    """The generated index: where am I, and what produced this -- without moving a path a tool reads."""
    run = _read_json(os.path.join(dest, "run.json"))
    gates = _read_json(os.path.join(dest, "gates.json")).get("gates") or {}
    arch = architecture_of(dest) or "<arch>"
    runner = runner_of(dest)
    lines = [
        f"# {os.path.basename(os.path.abspath(dest))} — start here",
        "",
        "Generated by `/agentforge-ml` on every stage transition; do not edit it, it is rewritten. "
        "The folders below are where code reads its inputs, so they keep their names; this page is the map.",
        "",
        f"- **Objective:** {run.get('objective') or 'not recorded'}",
        f"- **Runner (M7):** {runner or 'not approved yet'}",
        f"- **Architecture:** {architecture_of(dest) or 'not decided yet'}",
        "",
        "## Milestones",
        "",
        "| | Stage | What it does | Status | Output lands in |",
        "|---|---|---|---|---|",
    ]
    for milestone, stage_id, verb, where in MILESTONES:
        status = _stage_status(run, gates, stage_id)
        lines.append(f"| {milestone} | `{stage_id}` | {verb} | {status} | `{where.format(arch=arch)}` |")
    lines += [
        "",
        "## The boundary with NeuroEdge",
        "",
        f"- **`{FROM_DIR}/`** — what the portal (or the device) gives this run. Drop downloads there as they are.",
        f"- **`{TO_DIR}/`** — what this run gives the portal, numbered in upload order. "
        "Run `/agentforge-ml handoff` to see what is next, and where each file goes.",
        "",
        "## Guides",
        "",
    ]
    for name, milestone, what in GUIDES:
        present = os.path.isfile(os.path.join(dest, "guides", name))
        lines.append(f"- [`guides/{name}`](guides/{name}) ({milestone}) — {what}"
                     + ("" if present else " · *not written yet*"))
    lines.append("")
    return "\n".join(lines)


def write_start_here(dest: str) -> str:
    path = os.path.join(dest, START_HERE)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(start_here(dest))
    return path


# --------------------------------------------------------------------------- guides/ (D-6)


def place_guide(dest: str, name: str, draft: str) -> str:
    """Put a generated guide in `guides/`, never over a human's edit (ADR-0031 D-6).

    Absent: written. Identical: unchanged. Different: the draft is written BESIDE the existing file
    as `<name>.proposed.md` and the difference is reported, so a person decides what survives.
    """
    if name not in {g[0] for g in GUIDES}:
        raise ValueError(f"unknown guide {name!r}, expected one of {[g[0] for g in GUIDES]}")
    with open(draft, encoding="utf-8") as fh:
        text = fh.read()
    folder = os.path.join(dest, "guides")
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, name)
    if not os.path.exists(target):
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(text)
        write_start_here(dest)
        return f"guides/{name} written"
    with open(target, encoding="utf-8") as fh:
        current = fh.read()
    if current == text:
        return f"guides/{name} unchanged"
    import difflib  # noqa: PLC0415

    beside = os.path.join(folder, name.replace(".md", ".proposed.md"))
    with open(beside, "w", encoding="utf-8") as fh:
        fh.write(text)
    diff = list(difflib.unified_diff(current.splitlines(), text.splitlines(), f"guides/{name}",
                                     f"guides/{os.path.basename(beside)}", lineterm="", n=0))
    changed = sum(1 for d in diff if d[:1] in "+-" and not d.startswith(("+++", "---")))
    return (f"guides/{name} differs from the new draft ({changed} changed line(s)); the draft is at "
            f"guides/{os.path.basename(beside)} and the existing file was left as it is")


def _cli(argv: list[str] | None = None) -> int:
    # The walk-through uses arrows and a middle dot; a Windows console on cp1252 cannot print them.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(prog="handoff", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, helptext in (("stage", "copy outbound artifacts into to-neuroedge/"),
                           ("show", "what to upload next, and what is awaited back"),
                           ("verify", "re-hash each staged artifact's source"),
                           ("index", "regenerate 00-START-HERE.md")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--dest", required=True)
    p = sub.add_parser("sent", help="record an upload and move the artifact to sent/")
    p.add_argument("--dest", required=True)
    p.add_argument("--artifact", required=True, help="the ordinal, e.g. 04")
    p.add_argument("--registration", required=True, help="the portal's registration id, or its refusal")
    p = sub.add_parser("guide", help="place a generated guide in guides/, never over a human edit")
    p.add_argument("--dest", required=True)
    p.add_argument("--name", required=True, choices=[g[0] for g in GUIDES])
    p.add_argument("--file", required=True, help="the draft to place")
    args = parser.parse_args(argv)

    if args.cmd == "stage":
        print("\n".join(stage(args.dest)))
        return 0
    if args.cmd == "show":
        print("\n".join(show(args.dest)))
        return 0
    if args.cmd == "index":
        print(write_start_here(args.dest))
        return 0
    if args.cmd == "verify":
        code, lines = verify(args.dest)
        print("\n".join(lines))
        return code
    if args.cmd == "guide":
        print(place_guide(args.dest, args.name, args.file))
        return 0
    try:
        print(sent(args.dest, args.artifact, args.registration))
    except ValueError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
