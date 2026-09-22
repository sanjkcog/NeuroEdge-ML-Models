"""M10's baseline rule: ``beats_baseline`` is required only when the package declares a baseline (ADR-0028 D-11).

The use case's success criteria and a baseline answer different questions. The criteria answer "is it good enough
to ship", and M10 compares ``metrics.json`` with them on **every** path. A baseline answers "is the result
believable, and does this model earn its cost". It exists only where a cheap floor exists:

* a **training package** that declares a baseline (a time-series package always does: MiniRocket on the same
  split), or a model whose own ``model_artifact.json`` reports a ``baseline`` block, must report
  ``beats_baseline: true``; ``false`` or a missing flag opens the hard ``kpi`` gate;
* on the **fine-tune path** the portal's trainer produces no baseline, so there is no training package here and
  M10 records ``baseline: not_applicable``. The pretrained model evaluated as it is, is not a baseline.

**Which split the comparison was measured on matters.** ``train.py`` compares on validation, the split that also
picked the best epoch, and reports it about itself. When ``eval.py`` scored the model and its baseline on the
held-out test split (``metrics.json`` with ``eval_split: held_out_test``, ``baseline`` and ``beats_baseline``), that
comparison is the one used. Every verdict says which it was (``measured_on``). A pass measured on validation only
is reported as ``beats_baseline_val_only`` with a caveat: it is not a clean pass, and M10 repeats the caveat.

This never judges the KPI numbers. That comparison stays with M10, which knows the use case's metric.

    python -m agentforge.src.ml_contract.kpi baseline --dest <model folder> --arch <Arch> --model-package <folder>
                                                      [--metrics <held-out metrics.json>]
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

from .heldout import ACCEPTED_FILE
from .package import PACKAGE_FILE, ZIP_NAME

RECORD_FILE = "baseline_check.json"
NOT_APPLICABLE, BEATS, DOES_NOT_BEAT, MISSING = "not_applicable", "beats_baseline", "does_not_beat", "missing"
BEATS_VAL_ONLY = "beats_baseline_val_only"
HELD_OUT, VAL = "held_out_test", "self_reported_val"
VAL_CAVEAT = ("the comparison was measured on validation only, the split that also picked the best epoch, and the "
              "training script reported it about itself: it is not a held-out result. Repeat this in the KPI gate "
              "and in the model card")


def declares_baseline(package: dict[str, Any] | None) -> bool:
    """True when this training package runs a baseline. A package built before the ``baseline`` key is read by
    its entry points: the baseline step runs first, so two steps mean one was declared."""
    if not package:
        return False
    declared = package.get("baseline")
    if isinstance(declared, dict):
        return bool(declared.get("declared"))
    return len(package.get("entrypoint") or []) > 1


def _held_out_comparison(metrics: dict[str, Any] | None) -> dict[str, Any] | None:
    """The baseline block of a held-out ``metrics.json``, with its flag, when eval.py scored both. Else None."""
    if not metrics or metrics.get("eval_split") != HELD_OUT or not isinstance(metrics.get("baseline"), dict):
        return None
    return {**metrics["baseline"], "beats_baseline": metrics.get("beats_baseline"), "measured_on": HELD_OUT}


def baseline_verdict(package: dict[str, Any] | None, artifact: dict[str, Any] | None,
                     metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    """What M10 records about the baseline, and whether the hard ``kpi`` gate opens for it. Pure.

    ``metrics`` is the held-out ``metrics.json``. Its comparison is preferred over the one the training script
    reported about itself in ``model_artifact.json``. The verdict always says which split it was measured on.
    """
    block = _held_out_comparison(metrics) or ((artifact or {}).get("extras") or {}).get("baseline")
    # A model whose train.py ran its own baseline (the transformers template's linear probe) reports the block
    # itself. A reported baseline is a declared one, whichever file says so.
    if not declares_baseline(package) and not isinstance(block, dict):
        why = ("the training package declares no baseline" if package else
               "no training package: the portal fine-tuned the model with its own recipe, which has no baseline")
        return {"baseline": NOT_APPLICABLE, "opens_gate": False, "measured_on": None, "reason": why}
    flag = block.get("beats_baseline") if isinstance(block, dict) else None
    # A train-time block that does not say where it was measured was measured by the training script: validation.
    measured_on = (block.get("measured_on") or VAL) if isinstance(block, dict) else None
    if flag is True and measured_on == HELD_OUT:
        return {"baseline": BEATS, "opens_gate": False, "name": block.get("name"), "measured_on": HELD_OUT,
                "reason": "the model beats its declared baseline on the held-out test split, same metrics"}
    if flag is True:
        return {"baseline": BEATS_VAL_ONLY, "opens_gate": False, "name": block.get("name"),
                "measured_on": measured_on, "caveat": VAL_CAVEAT,
                "reason": f"the model beats its declared baseline on {measured_on} only. No held-out comparison "
                          "was found: eval.py did not score the baseline"}
    if flag is False:
        return {"baseline": DOES_NOT_BEAT, "opens_gate": True, "name": block.get("name"), "measured_on": measured_on,
                "reason": f"the model does not beat its declared baseline (measured on {measured_on}): it does not "
                          "earn its cost yet"}
    return {"baseline": MISSING, "opens_gate": True, "measured_on": None,
            "reason": "the package declares a baseline, but model_artifact.json carries no beats_baseline flag: "
                      "run the baseline in train.py, never hand-write the flag"}


def _read_package(dest: Path, arch: str) -> dict[str, Any] | None:
    zip_path = dest / arch / ZIP_NAME
    if not zip_path.is_file():
        return None
    with zipfile.ZipFile(zip_path) as z:
        return json.loads(z.read(PACKAGE_FILE)) if PACKAGE_FILE in z.namelist() else None


def _held_out_metrics(dest: Path, arch: str, model_package: Path, explicit: str | None) -> dict[str, Any] | None:
    """The held-out metrics of this run: the file named, else the portal's accepted result, else the package's own."""
    def load(path: Path, key: str | None = None) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        data = data.get(key) if key and isinstance(data, dict) else data
        return data if isinstance(data, dict) and data.get("eval_split") == HELD_OUT else None

    if explicit:
        return load(Path(explicit))
    return load(dest / arch / ACCEPTED_FILE, "metrics") or load(model_package / "metrics.json")


def check(dest: str, arch: str, model_package: str, metrics_file: str | None = None) -> dict[str, Any]:
    """Apply the rule to this run and keep the verdict as ``<arch>/baseline_check.json``."""
    artifact_path = Path(model_package) / "model_artifact.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8")) if artifact_path.is_file() else None
    metrics = _held_out_metrics(Path(dest), arch, Path(model_package), metrics_file)
    verdict = baseline_verdict(_read_package(Path(dest), arch), artifact, metrics)
    out = Path(dest) / arch / RECORD_FILE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    return verdict


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kpi", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baseline", help="exit 1 when the baseline rule opens the kpi gate")
    b.add_argument("--dest", required=True)
    b.add_argument("--arch", required=True)
    b.add_argument("--model-package", required=True, help="<arch>/runs/<run_id>/model-package")
    b.add_argument("--metrics", help="the held-out metrics.json eval.py wrote (default: the portal's accepted result, "
                                     "else <model-package>/metrics.json when it is a held-out one)")
    a = p.parse_args(argv)
    try:
        verdict = check(a.dest, a.arch, a.model_package, a.metrics)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"could not check the baseline: {exc}", file=sys.stderr)
        return 2
    print(f"baseline: {verdict['baseline']} · measured on: {verdict['measured_on'] or '-'} ({verdict['reason']})")
    if verdict.get("caveat"):
        print(f"CAVEAT: {verdict['caveat']}")
    if verdict["opens_gate"]:
        print("open the hard gate: gate_state.py open kpi --stage eval --type hard")
    return 1 if verdict["opens_gate"] else 0


if __name__ == "__main__":
    sys.exit(main())
