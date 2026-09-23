"""The portal's model recommendation, and how M7 must answer it (ADR-0028 D-9).

The portal rates its catalogue against the use case and the device, the user picks, and the portal exports
``model_recommendation.json``. A human drops it in ``from-neuroedge/``; ``intake`` records it. Nothing here calls
the portal (ADR-0025 D-1), and ``/model-select`` runs without the file exactly as it did before.

The two can disagree, because they know different things: the portal knows the device and its catalogue, and
``/model-select`` knows the data. The rules that reconcile them:

1. the proposal must address the portal's pick: adopt it, or reject it with the reason;
2. a candidate the portal marked ``does_not_fit`` is **binding**: the proposal may not choose it unless the human
   overrides it at the M7 gate, and the override is recorded;
3. a candidate marked ``unverified`` binds nothing;
4. any other catalogue entry, or a model outside the catalogue, may be chosen (it reaches the portal as "unlisted").

    python -m agentforge.src.ml_contract.recommendation show  --dest <model folder>
    python -m agentforge.src.ml_contract.recommendation check --dest <model folder> --model-id <proposed id>
                                                              [--override "<the human's reason>" --identity <who>]

``check`` exits 0 when nothing binds, 3 on a binding ``does_not_fit``, and 4 when a recommendation WAS recorded
but cannot be read. "No file" and "a file this cannot read" are different: the second must not silently lift the
binding rule, so it is a WARN and a stop until the human exports the file again.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from . import intake
from .model_fetch import OWNER_DECISION, FetchError, FetchRequest, is_internal_only

OVERRIDE_FILE = "model/recommendation-override.json"
OVERRIDE_SCHEMA = "model-recommendation-override/1"
BINDING_EXIT, UNUSABLE_EXIT = 3, 4


def load(dest: str) -> tuple[dict[str, Any] | None, str | None]:
    """(recommendation, problem). ``(None, None)`` means none was recorded. ``(None, reason)`` means one WAS
    recorded and cannot be used: its ``does_not_fit`` ratings are unknown, which is not the same as absent."""
    entry = intake.read_inputs(dest).get("model_recommendation")
    if not entry or not entry.get("path"):
        return None, None
    path = os.path.join(dest, entry["path"])
    if not os.path.exists(path):
        return None, f"{entry['path']} was recorded but is no longer in the model folder"
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, f"{entry['path']} is not readable JSON ({exc})"
    if not isinstance(data, dict) or data.get("schema") != intake.RECOMMENDATION_SCHEMA:
        got = data.get("schema") if isinstance(data, dict) else None
        return None, f"{entry['path']} has schema {got!r}, expected {intake.RECOMMENDATION_SCHEMA!r}"
    return data, None


def read(dest: str) -> dict[str, Any] | None:
    """The recorded recommendation when it is usable, else None. Use :func:`load` to tell absent from unusable."""
    return load(dest)[0]


def candidate(recommendation: dict[str, Any] | None, model_id: str) -> dict[str, Any] | None:
    for entry in (recommendation or {}).get("candidates") or []:
        if isinstance(entry, dict) and entry.get("id") == model_id:
            return entry
    return None


def binding_conflict(recommendation: dict[str, Any] | None, model_id: str) -> dict[str, Any] | None:
    """Rule 2, as a pure function: does ``model_id`` pick a candidate the portal marked ``does_not_fit``?

    Returns None when nothing binds: no recommendation, a model outside the list, ``fits`` or ``unverified``.
    Otherwise the candidate's id and the portal's reasons, which the M7 gate shows to the human.
    """
    entry = candidate(recommendation, model_id)
    if entry is None or entry.get("state") != "does_not_fit":
        return None
    return {"id": model_id, "state": "does_not_fit", "reasons": [str(r) for r in entry.get("reasons") or []]}


def relation_to_pick(recommendation: dict[str, Any] | None, model_id: str) -> str:
    """How the proposed model relates to the portal's pick: what §Alternatives must say (rule 1)."""
    if recommendation is None:
        return "no_recommendation"
    pick = recommendation.get("pick") if isinstance(recommendation.get("pick"), dict) else None
    if pick is None:
        return "no_pick"
    if pick.get("id") == model_id:
        return "adopts_pick"
    return "other_catalogue_entry" if candidate(recommendation, model_id) else "unlisted"


def fetch_request(dest: str) -> FetchRequest:
    """The exact source the recorded pick names, for ``/model-fetch --from-recommendation`` (D-2)."""
    recommendation, problem = load(dest)
    if problem:
        raise FetchError([f"the recorded recommendation cannot be used: {problem}"])
    pick = (recommendation or {}).get("pick")
    if not isinstance(pick, dict):
        raise FetchError(["no model_recommendation.json with a pick is recorded: name the source yourself "
                          "(--hub, --ref, --revision, --loader, --model-id)"])
    source = pick.get("source") if isinstance(pick.get("source"), dict) else {}
    licence = pick.get("licence") if isinstance(pick.get("licence"), dict) else {}
    # The file is a dropped, untrusted input: a licence it names is a claim, never evidence, so it reaches the
    # human gate unless the caller read the licence in the download (--licence-evidence). One exception, the
    # owner's: an AGPL-3.0 claim gets the MORE restrictive outcome (internal and demo use only), and that outcome
    # comes from the owner's decision, not from the file.
    evidence = None
    if is_internal_only(licence.get("spdx")):
        evidence = f"{OWNER_DECISION}; the AGPL-3.0 claim itself comes from model_recommendation.json, unverified"
    return FetchRequest(hub=str(source.get("hub") or ""), ref=str(source.get("ref") or ""),
                        revision=source.get("revision"), loader=str(pick.get("loader") or ""),
                        model_id=str(pick.get("id") or ""), licence_spdx=licence.get("spdx"),
                        licence_evidence=evidence, catalogue_id=pick.get("id"))


def record_override(dest: str, conflict: dict[str, Any], *, identity: str, reason: str) -> str:
    """Keep the human's override of a binding ``does_not_fit`` beside the model. Returns the file written."""
    if not identity.strip() or not reason.strip():
        raise ValueError("an override needs who decided it and their reason")
    path = os.path.join(dest, OVERRIDE_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {"schema": OVERRIDE_SCHEMA, **conflict, "overridden_by": identity.strip(), "reason": reason.strip(),
              "recorded_at": datetime.now(timezone.utc).isoformat()}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")
    return path


def overridden(dest: str, model_id: str) -> bool:
    path = os.path.join(dest, OVERRIDE_FILE)
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("id") == model_id
    except (OSError, ValueError):
        return False


def summary(recommendation: dict[str, Any]) -> list[str]:
    pick = recommendation.get("pick") if isinstance(recommendation.get("pick"), dict) else None
    lines = [f"catalogue {recommendation.get('catalogue_version')} · generated {recommendation.get('generated_at')}",
             f"pick: {pick['id']} ({pick.get('loader')}, {pick.get('path')})" if pick else "pick: none"]
    for entry in recommendation.get("candidates") or []:
        if isinstance(entry, dict):
            binds = "  BINDING" if entry.get("state") == "does_not_fit" else ""
            lines.append(f"  [{entry.get('state')}] {entry.get('id')} ({entry.get('loader')}, {entry.get('path')})"
                         f"{binds}: {'; '.join(str(r) for r in entry.get('reasons') or [])}")
    return lines


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="recommendation", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("show", help="print the recorded recommendation: the pick and every rated candidate")
    s.add_argument("--dest", required=True)
    c = sub.add_parser("check", help="exit 3 when the proposed model is one the portal marked does_not_fit, "
                                     "4 when a recorded recommendation cannot be read")
    c.add_argument("--dest", required=True)
    c.add_argument("--model-id", required=True)
    c.add_argument("--override", metavar="REASON", help="the human's reason for overriding a does_not_fit")
    c.add_argument("--identity", help="who overrode it")
    a = p.parse_args(argv)

    recommendation, problem = load(a.dest)
    if problem:
        print(f"[WARN] a model recommendation was recorded but cannot be used: {problem}. Its does_not_fit ratings "
              "are unknown, so nothing is assumed to fit. Ask the human to export it again and drop it in from-neuroedge/.")
        return UNUSABLE_EXIT
    if recommendation is None:
        print("no model recommendation is recorded: /model-select proposes from the data and the task alone")
        return 0
    if a.cmd == "show":
        print("\n".join(summary(recommendation)))
        return 0
    print(f"relation to the portal's pick: {relation_to_pick(recommendation, a.model_id)}")
    conflict = binding_conflict(recommendation, a.model_id)
    if conflict is None:
        return 0
    print(f"BINDING: the portal marked {a.model_id!r} does_not_fit: {'; '.join(conflict['reasons']) or 'no reason given'}")
    if a.override:
        try:
            print(f"override recorded in {record_override(a.dest, conflict, identity=a.identity or '', reason=a.override)}")
        except ValueError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 1
        return 0
    if overridden(a.dest, a.model_id):
        print(f"already overridden by a human ({OVERRIDE_FILE})")
        return 0
    print("Choose another model, or ask the human at the M7 gate. Only their recorded override lifts it.")
    return BINDING_EXIT


if __name__ == "__main__":
    sys.exit(main())
