"""The use-case lock: fix the input contract from the use case at M0 (NeuroEdge-Web ADR-0008 L-1, L-2).

`/agentforge-ml` used to start from a free-text objective and never read the use-case YAML
until M10. On the first real run that let training settle on 3 channels at 500 Hz while the
use case said 4 channels at 100 Hz, and nothing downstream compared the two. The lock turns
the use case into the one contract every later stage reads:

* **Shared core** (every modality): use case id and sha256, modality, ordered class names,
  head, target metric and ``at_fpr``.
* **One block per modality**: ``timeseries`` (channels with unit and definition, rate, window,
  stride), ``vision`` (input geometry, preprocessing, output schema), ``vision_anomaly``.

Building refuses, rather than guesses, whenever the use case lacks what the modality needs or
disagrees with what the run expected. The fix is then made in the use case, not in the run.

    python -m agentforge.src.ml_contract.lock build  --use-case <yaml> --dest <model folder>
    python -m agentforge.src.ml_contract.lock verify --dest <model folder> [--use-case <yaml>]

After the lock, only a change to a model-contract field needs a re-lock (ADR-0030): ``compare_use_case``
is the one comparison behind ``verify``, the intake check and the audit. The file hash is recorded, and a
file changed outside the contract is reported, never refused.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
from typing import Any

from ..state.lock_digest import lock_digest, source_digest, source_matches

LOCK_SCHEMA = "use-case-lock/1"
LOCK_FILE = "use_case.lock.json"

_TS_TASKS = {"anomaly_detection", "forecasting", "timeseries_classification", "ts_classification"}
_VISION_TASKS = {"object_detection", "classification", "image_classification", "segmentation"}
_VISION_ANOMALY_TASKS = {"visual_anomaly_detection"}
_DEFAULT_AT_FPR = 0.05
# Same spelling for the same unit, so "µm" in a use case and "um" in a data spec agree.
_UNIT_ALIASES = {"µm": "um", "μm": "um", "micron": "um", "microns": "um", "n·m": "nm", "n m": "nm"}


class LockError(ValueError):
    """The use case cannot produce a trustworthy contract. Each problem is listed; none is guessed past."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def normalise_unit(unit: str | None) -> str | None:
    """Canonical comparison form of a unit string (case, spacing and µm spellings folded)."""
    if unit is None:
        return None
    u = str(unit).strip().lower()
    return _UNIT_ALIASES.get(u, u)


def _get(d: dict[str, Any], path: str) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


_REDUCE_MODES = {"last", "mean", "rms"}


def modality_of(use_case: dict[str, Any]) -> str | None:
    task_type = str(_get(use_case, "task.type") or "")
    if task_type in _VISION_ANOMALY_TASKS:
        return "vision_anomaly"
    if task_type in _TS_TASKS or isinstance(_get(use_case, "task.timeseries"), dict):
        return "timeseries"
    if task_type in _VISION_TASKS:
        return "vision"
    return None


def head_shape_of(use_case: dict[str, Any], modality: str | None) -> str:
    """The head a lock built from this use case records: a time-series or visual-anomaly score is scalar,
    except a time-series classification task, which is multiclass like every vision task."""
    if modality in {"timeseries", "vision_anomaly"} and _get(use_case, "task.type") != "timeseries_classification":
        return "scalar"
    return "multiclass"


def effective_at_fpr(use_case: dict[str, Any]) -> tuple[Any, str]:
    """The ``at_fpr`` a lock built from this use case records, and where it came from.

    at_fpr may sit on the accuracy target or on the business KPI link (where Step 1 writes it); the
    default applies only when the use case states neither, and the lock says which it used.
    """
    accuracy = _get(use_case, "performance_targets.accuracy")
    at_fpr = accuracy.get("at_fpr") if isinstance(accuracy, dict) else None
    if at_fpr is not None:
        return at_fpr, "performance_targets.accuracy.at_fpr"
    at_fpr = _get(use_case, "business_requirement.kpi_link.at_fpr")
    if at_fpr is not None:
        return at_fpr, "business_requirement.kpi_link.at_fpr"
    return _DEFAULT_AT_FPR, "default"


def _timeseries_block(uc: dict[str, Any], definitions: dict[str, str], problems: list[str],
                      notes: list[str]) -> dict[str, Any]:
    ts = _get(uc, "task.timeseries") or {}
    channels_in = ts.get("channels") if isinstance(ts, dict) else None
    if not isinstance(channels_in, list) or not channels_in:
        problems.append("task.timeseries.channels is empty: the use case must name every signal, in order")
        channels_in = []
    channels = []
    for i, ch in enumerate(channels_in):
        name = ch.get("name") if isinstance(ch, dict) else None
        if not name:
            problems.append(f"task.timeseries.channels[{i}] has no name")
            continue
        unit = ch.get("unit")
        if not unit:
            problems.append(f"channel {name!r} has no unit: the device never reads units, so the contract must")
        definition = ch.get("definition") or definitions.get(name)
        if not definition:
            problems.append(
                f"channel {name!r} has no definition (what one sample is, e.g. '100 ms mean of spindle torque'). "
                "Add it to the use case, or pass --definitions until the portal schema carries it (ADR-0008 W2)"
            )
        elif not ch.get("definition"):
            notes.append(f"definition of {name!r} supplied by the run, not the use case (ADR-0008 W2)")
        # The machine-readable half of the definition: how the device reduces the samples of one
        # timestep window. Without it the device keeps the last sample, whatever training did.
        reduce = ch.get("reduce")
        if reduce not in _REDUCE_MODES:
            problems.append(
                f"channel {name!r} has no reduce (last | mean | rms): how one timestep is built from the "
                "samples inside it. Without it the device point-samples, whatever the definition says"
            )
        channels.append({"name": name, "unit": unit, "definition": definition, "reduce": reduce})

    names = [c["name"] for c in channels]
    sensors = _get(uc, "ingress.sensors") or []
    feature_order = sensors[0].get("feature_order") if sensors and isinstance(sensors[0], dict) else None
    if feature_order is not None and list(feature_order) != names:
        problems.append(
            f"ingress.sensors[0].feature_order {list(feature_order)} differs from task.timeseries.channels "
            f"{names}: the device feed and the model would disagree on channel order"
        )

    rate = _get(uc, "task.input.sample_rate_hz")
    try:
        rate = float(rate) if rate is not None else None
    except (TypeError, ValueError):
        rate = None
    if not rate or rate <= 0:
        problems.append("task.input.sample_rate_hz is missing: the device counts rows, so the rate must be declared")

    window = ts.get("window_samples") if isinstance(ts, dict) else None
    if window is None and isinstance(ts, dict) and ts.get("window_seconds") and rate:
        window = round(float(ts["window_seconds"]) * rate)
    if not window or int(window) <= 0:
        problems.append("task.timeseries.window_samples (or window_seconds) is missing")
        window = None
    stride = ts.get("stride_samples") if isinstance(ts, dict) else None
    if stride is None and isinstance(ts, dict) and ts.get("stride_seconds") and rate:
        stride = round(float(ts["stride_seconds"]) * rate)
    if not stride or int(stride) <= 0:
        problems.append("task.timeseries.stride_samples (or stride_seconds) is missing: stride sets the cycle budget")
        stride = None

    return {
        "channels": channels,
        "sample_rate_hz": rate,
        "window_samples": int(window) if window else None,
        "window_seconds": round(int(window) / rate, 6) if window and rate else None,
        "stride_samples": int(stride) if stride else None,
        "layout": "[1,features,window]",
        "scaling": "in_graph",
    }


def _vision_block(uc: dict[str, Any], problems: list[str]) -> dict[str, Any]:
    res = _get(uc, "task.input.resolution")
    if not (isinstance(res, list) and len(res) == 2 and all(isinstance(v, (int, float)) and v > 0 for v in res)):
        problems.append("task.input.resolution must be [height, width] for a vision task")
        res = None
    return {
        "input": {"height": int(res[0]) if res else None, "width": int(res[1]) if res else None,
                  "color_order": _get(uc, "task.input.color_order") or "RGB", "layout": "NCHW"},
        "preprocess": _get(uc, "task.input.preprocess") or "letterbox",
        "normalize": "in_graph",
        "output_schema": _get(uc, "task.output_schema"),
    }


def build_lock(
    use_case: dict[str, Any],
    use_case_bytes: bytes,
    *,
    definitions: dict[str, str] | None = None,
    expect_channels: list[str] | None = None,
) -> dict[str, Any]:
    """Derive the lock from a parsed use case. Raises :class:`LockError` listing every problem found."""
    problems: list[str] = []
    notes: list[str] = []
    uc = copy.deepcopy(use_case)

    uc_id = uc.get("id")
    if not uc_id:
        problems.append("use case has no id")
    modality = modality_of(uc)
    if modality is None:
        problems.append(f"task.type {_get(uc, 'task.type')!r} is not a modality /agentforge-ml trains")

    classes = _get(uc, "task.classes")
    if not isinstance(classes, list) or not classes:
        problems.append("task.classes is empty")
        classes = []
    classes = [str(c) for c in classes]

    head: dict[str, Any]
    if head_shape_of(uc, modality) == "scalar":
        # A scalar anomaly score is thresholded, never argmaxed: exactly two names, nominal first.
        head = {"shape": "scalar", "threshold": "calibrated_on_val", "nominal_class": classes[0] if classes else None}
        if len(classes) != 2:
            problems.append(
                f"a scalar head needs exactly two class names [nominal, anomaly]; the use case has {classes}. "
                "An argmax over a length-1 output always reports class 0"
            )
    else:
        head = {"shape": "multiclass", "output_length": len(classes)}

    accuracy = _get(uc, "performance_targets.accuracy") or {}
    accuracy = accuracy if isinstance(accuracy, dict) else {}
    at_fpr, at_fpr_source = effective_at_fpr(uc)
    target = {
        "metric": accuracy.get("metric"),
        "min_value": accuracy.get("min_value"),
        "at_fpr": at_fpr,
        "at_fpr_source": at_fpr_source,
    }

    lock: dict[str, Any] = {
        "schema": LOCK_SCHEMA,
        "use_case_id": uc_id,
        "use_case_sha256": source_digest(use_case_bytes),
        "modality": modality,
        "class_names": classes,
        "head": head,
        "target": target,
    }
    if modality == "timeseries":
        block = _timeseries_block(uc, definitions or {}, problems, notes)
        lock["timeseries"] = block
        if expect_channels is not None:
            got = [c["name"] for c in block["channels"]]
            if got != list(expect_channels):
                problems.append(
                    f"the run expected channels {list(expect_channels)} but the use case declares {got}. "
                    "Fix the use case (Step 1), not the run"
                )
    elif modality in {"vision", "vision_anomaly"}:
        lock["vision"] = _vision_block(uc, problems)
        if modality == "vision_anomaly":
            lock["vision_anomaly"] = {"training": "normal_only", "score": "image_level"}

    if problems:
        raise LockError(problems)
    if notes:
        lock["notes"] = notes
    lock["lock_sha256"] = lock_digest(lock)
    return lock


# --------------------------------------------------------------------------- use case vs lock (ADR-0030)
#
# After the first lock the dataset and the model are not redone, so the use case's FILE hash no longer
# gates anything: a re-saved YAML, a new target device or egress topic changes those bytes without
# changing what the model computes. Only the fields below do. The rules mirror the portal's
# `services/model_contract.py` (NeuroEdge-Web e773bda), so portal and model project refuse the same edits.

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
# NeuroEdge-Web ADR-0009 C-6: a sensor `recall` target is recorded as `recall_at_fpr`; one target, not two.
_METRIC_ALIASES = {"recall": "recall_at_fpr"}
# A float that went through YAML, JSON and the lock digest may differ in its last bits; a real edit never does.
_REL_TOL = 1e-6
RELOCK_ADVICE = "re-lock (--force) and rebuild the package, or revert the edit"


def _contract_unit(value: Any) -> str | None:
    """A unit as written, with the micro sign spelled one way (the portal's rule: `µm` = `um`, `Nm` != `nm`)."""
    if value is None or not str(value).strip():
        return None
    return str(value).strip().replace("µ", "u").replace("μ", "u")


def _contract_metric(name: Any) -> str | None:
    if not name:
        return None
    key = str(name).strip()
    return _METRIC_ALIASES.get(key, key)


def _same_number(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) \
            and not isinstance(b, bool):
        return math.isclose(float(a), float(b), rel_tol=_REL_TOL)
    return a == b


def contract_differences(lock: dict[str, Any], use_case: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Compare the model-contract fields of ``lock`` with the current ``use_case`` (ADR-0030 D-1).

    Returns ``(differences, skipped)``. Each difference names the field, the locked value, the current
    value and the way out. ``skipped`` names each field the lock does not carry (or the use case no
    longer states), so the output says what was not compared instead of passing it silently.
    Deliberately NOT compared: ``min_value`` (a changed bar is judged against the measured metric),
    channel ``definition`` prose, and every field outside the model contract.
    """
    uc = copy.deepcopy(use_case)
    diffs: list[str] = []
    skipped: list[str] = []

    def differ(field: str, locked: Any, current: Any) -> None:
        diffs.append(f"{field}: locked {locked!r}, the use case now says {current!r} — {RELOCK_ADVICE}")

    modality = modality_of(uc)
    if lock.get("modality") != modality:
        differ("modality", lock.get("modality"), modality)

    current_classes = [str(c) for c in (_get(uc, "task.classes") or [])] \
        if isinstance(_get(uc, "task.classes"), list) else []
    if "class_names" not in lock:
        skipped.append("class_names: the lock has none")
    elif not current_classes:
        skipped.append("class_names: the use case lists none")
    elif [str(c) for c in lock["class_names"]] != current_classes:
        differ("class_names (order matters)", lock["class_names"], current_classes)

    locked_head = (lock.get("head") or {}).get("shape") if isinstance(lock.get("head"), dict) else None
    if locked_head is None:
        skipped.append("head shape: the lock has none")
    elif locked_head != head_shape_of(uc, modality):
        differ("head shape", locked_head, head_shape_of(uc, modality))

    target = lock.get("target") if isinstance(lock.get("target"), dict) else {}
    at_fpr, source = effective_at_fpr(uc)
    if target.get("at_fpr") is None:
        skipped.append("at_fpr: the lock has none")
    elif not _same_number(target["at_fpr"], at_fpr):
        differ(f"at_fpr (effective, from {source})", target["at_fpr"], at_fpr)

    accuracy = _get(uc, "performance_targets.accuracy")
    current_metric = accuracy.get("metric") if isinstance(accuracy, dict) else None
    if not target.get("metric"):
        skipped.append("target metric: the lock has none")
    elif not current_metric:
        skipped.append("target metric: the use case states none")
    elif _contract_metric(target["metric"]) != _contract_metric(current_metric):
        differ("target metric", target["metric"], current_metric)

    if modality == "timeseries" and lock.get("modality") == "timeseries":
        _timeseries_differences(lock, uc, differ, skipped)
    elif modality in {"vision", "vision_anomaly"} and lock.get("modality") == modality:
        _vision_differences(lock, uc, differ, skipped)
    return diffs, skipped


def _timeseries_differences(lock: dict[str, Any], uc: dict[str, Any], differ: Any, skipped: list[str]) -> None:
    """Units and the tensor shape: channel names and order, reduce, rate, window, stride (ADR-0008 L-2)."""
    block = lock.get("timeseries") if isinstance(lock.get("timeseries"), dict) else None
    if block is None:
        skipped.append("timeseries block: the lock has none (channels, units, reduce, rate, window, stride)")
        return
    # The builder's own derivation (window_seconds x rate and all), so the value compared is the value a lock
    # built from this use case today would record. Its problems are the builder's business, not this check's.
    try:
        now = _timeseries_block(uc, {}, [], [])
    except (TypeError, ValueError) as exc:  # e.g. a window of "sixty-four": the builder would refuse it too
        differ("timeseries block", "readable", f"unreadable ({exc})")
        return
    locked_channels = [c for c in block.get("channels") or [] if isinstance(c, dict)]
    locked_names = [c.get("name") for c in locked_channels]
    current_names = [c["name"] for c in now["channels"]]
    if not locked_channels:
        skipped.append("channels: the lock has none")
    elif locked_names != current_names:
        differ("channel names and order", locked_names, current_names)
    current_by_name = {c["name"]: c for c in now["channels"]}
    for ch in locked_channels:
        cur = current_by_name.get(ch.get("name"))
        if cur is None:
            continue  # a removed channel is already named by the channel-order difference
        locked_unit, cur_unit = _contract_unit(ch.get("unit")), _contract_unit(cur.get("unit"))
        if locked_unit is None or cur_unit is None:
            skipped.append(f"unit of channel {ch.get('name')!r}: not stated on both sides")
        elif locked_unit != cur_unit:
            differ(f"unit of channel {ch.get('name')!r}", ch.get("unit"), cur.get("unit"))
        if "reduce" not in ch:
            skipped.append(f"reduce of channel {ch.get('name')!r}: the lock has none")
        elif ch.get("reduce") != cur.get("reduce"):
            differ(f"reduce of channel {ch.get('name')!r}", ch.get("reduce"), cur.get("reduce"))
    for key in ("sample_rate_hz", "window_samples", "stride_samples"):
        if block.get(key) is None:
            skipped.append(f"{key}: the lock has none")
        elif not _same_number(block[key], now.get(key)):
            differ(key, block[key], now.get(key))


def _vision_differences(lock: dict[str, Any], uc: dict[str, Any], differ: Any, skipped: list[str]) -> None:
    """The input tensor of a vision lock: height, width, colour order and preprocessing (ADR-0008 L-2)."""
    block = lock.get("vision") if isinstance(lock.get("vision"), dict) else None
    if block is None:
        skipped.append("vision block: the lock has none (input geometry, preprocess)")
        return
    now = _vision_block(uc, [])
    locked_input = block.get("input") if isinstance(block.get("input"), dict) else {}
    for key in ("height", "width", "color_order"):
        if locked_input.get(key) is None:
            skipped.append(f"input {key}: the lock has none")
        elif locked_input[key] != now["input"].get(key):
            differ(f"input {key}", locked_input[key], now["input"].get(key))
    if block.get("preprocess") is None:
        skipped.append("preprocess: the lock has none")
    elif block["preprocess"] != now.get("preprocess"):
        differ("preprocess", block["preprocess"], now.get("preprocess"))


def compare_use_case(lock: dict[str, Any], use_case: dict[str, Any], raw: bytes) -> list[tuple[str, str, str]]:
    """``(level, check, detail)`` lines for a use case against its lock: the one check behind intake, the
    audit and ``lock verify`` (ADR-0030). FAIL only for a model-contract difference; a file that changed
    outside the contract is a WARN, and a field that could not be compared is a WARN naming it.
    """
    diffs, skipped = contract_differences(lock, use_case)
    out: list[tuple[str, str, str]] = [(FAIL, "model contract", d) for d in diffs]
    out += [(WARN, "model contract", f"not compared — {s}") for s in skipped]
    if not diffs:
        out.append((PASS, "model contract", "unchanged since the lock was built"))
    stored = lock.get("use_case_sha256")
    if source_matches(raw, stored):
        out.append((PASS, "lock", "identical to the use case the lock was built from"))
    elif not diffs:
        out.append((WARN, "lock", f"the use case changed outside the contract (file hash {source_digest(raw)[:12]}, "
                                  f"locked {str(stored)[:12]}); the lock still holds"))
    return out


def read_lock(dest: str) -> dict[str, Any]:
    """Load ``<dest>/use_case.lock.json`` and confirm it has not been edited since it was built."""
    path = os.path.join(dest, LOCK_FILE)
    with open(path, encoding="utf-8") as fh:
        lock = json.load(fh)
    if lock.get("lock_sha256") != lock_digest(lock):
        raise LockError([f"{path} was edited after it was built (lock_sha256 no longer matches); rebuild it"])
    return lock


def _load_yaml(path: str) -> tuple[dict[str, Any], bytes]:
    import yaml  # pyyaml

    with open(path, "rb") as fh:
        raw = fh.read()
    data = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise LockError([f"{path} is not a use-case mapping"])
    return data, raw


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="derive use_case.lock.json from the use-case YAML")
    b.add_argument("--use-case", required=True, help="path to the portal use-case YAML")
    b.add_argument("--dest", required=True, help="the model folder")
    b.add_argument("--definitions", help="JSON {channel: definition} for channels the use case does not define yet")
    b.add_argument("--expect-channels", help="comma-separated channel names the run expects, in order")
    b.add_argument("--force", action="store_true", help="replace an existing lock")
    v = sub.add_parser("verify", help="check the lock is intact and the use case's model contract has not changed")
    v.add_argument("--dest", required=True)
    v.add_argument("--use-case", help="compare this YAML's model-contract fields with the lock (ADR-0030)")
    a = p.parse_args(argv)

    try:
        if a.cmd == "build":
            out = os.path.join(a.dest, LOCK_FILE)
            if os.path.exists(out) and not a.force:
                print(f"{out} exists; pass --force to replace it (the run's later stages were built on it)",
                      file=sys.stderr)
                return 2
            uc, raw = _load_yaml(a.use_case)
            defs = {}
            if a.definitions:
                with open(a.definitions, encoding="utf-8") as fh:
                    defs = json.load(fh)
            expect = [c.strip() for c in a.expect_channels.split(",")] if a.expect_channels else None
            lock = build_lock(uc, raw, definitions=defs, expect_channels=expect)
            os.makedirs(a.dest, exist_ok=True)
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(lock, fh, indent=2, ensure_ascii=False)
            print(f"lock {lock['lock_sha256'][:12]} ({lock['modality']}) -> {out}")
            return 0
        lock = read_lock(a.dest)
        print(f"lock {lock['lock_sha256'][:12]} intact ({lock['modality']}, use case {lock['use_case_id']})")
        if a.use_case:
            uc, raw = _load_yaml(a.use_case)
            # ADR-0030: only a model-contract difference fails; a file changed outside the contract is a note.
            lines = compare_use_case(lock, uc, raw)
            for level, check, detail in lines:
                print(f"  [{level}] {check}: {detail}", file=sys.stderr if level == FAIL else sys.stdout)
            if any(level == FAIL for level, _, _ in lines):
                return 1
        return 0
    except LockError as exc:
        print("refused:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
