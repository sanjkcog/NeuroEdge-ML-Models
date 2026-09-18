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
"""
from __future__ import annotations

import argparse
import copy
import json
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
    if modality in {"timeseries", "vision_anomaly"} and _get(uc, "task.type") != "timeseries_classification":
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
    # at_fpr may sit on the accuracy target or on the business KPI link (where Step 1 writes it);
    # the default applies only when the use case states neither, and the lock says which it used.
    at_fpr, at_fpr_source = accuracy.get("at_fpr"), "performance_targets.accuracy.at_fpr"
    if at_fpr is None:
        at_fpr, at_fpr_source = _get(uc, "business_requirement.kpi_link.at_fpr"), "business_requirement.kpi_link.at_fpr"
    if at_fpr is None:
        at_fpr, at_fpr_source = _DEFAULT_AT_FPR, "default"
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
    v = sub.add_parser("verify", help="check the lock is intact and the use case has not changed since")
    v.add_argument("--dest", required=True)
    v.add_argument("--use-case", help="re-hash this YAML and compare with the lock")
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
        if a.use_case:
            _, raw = _load_yaml(a.use_case)
            if not source_matches(raw, lock["use_case_sha256"]):
                print("the use case changed since the lock was built: re-lock, and re-run every stage after M0",
                      file=sys.stderr)
                return 1
        print(f"lock {lock['lock_sha256'][:12]} intact ({lock['modality']}, use case {lock['use_case_id']})")
        return 0
    except LockError as exc:
        print("refused:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
