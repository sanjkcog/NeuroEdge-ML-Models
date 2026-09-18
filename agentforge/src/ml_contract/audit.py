"""`/usecase-audit`: do the use case, the dataset, the simulator and the device agree? (ADR-0025 D-6)

Each of those four carries its own copy of channel order, rate, window, units, classes and runtime
expectations. This module compares whichever of them exist, and reports every check as PASS, WARN,
FAIL or NOT_YET. NOT_YET means the source does not exist at this checkpoint by design. A source that
should exist but does not is a FAIL.

    python -m agentforge.src.ml_contract.audit --dest <dest> --checkpoint M0|M4|M8|M11
    python -m agentforge.src.ml_contract.audit --dest <dest>          (everything that exists; no gate)

With a checkpoint it writes ``audit/<checkpoint>.{md,json}`` and records the gate ``audit/<checkpoint>``:
approved automatically when nothing FAILs, otherwise left pending for a human.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

from ..state.lock_digest import source_matches
from . import gates as gt
from . import intake
from .lock import LockError, normalise_unit, read_lock

PASS, WARN, FAIL, NOT_YET = "PASS", "WARN", "FAIL", "NOT_YET"
CHECKPOINTS = ("M0", "M4", "M8", "M11")
CHECKPOINT_STAGE = {"M0": "destination", "M4": "verify", "M8": "model-build", "M11": "return"}
ONNX_OPSET = 13  # the device runtime's pinned opset (Web ADR-0001 W-3)


class Audit:
    def __init__(self, checkpoint: str | None):
        self.checkpoint = checkpoint
        self.findings: list[dict[str, str]] = []

    def reached(self, cp: str) -> bool:
        """True when this audit runs at or after ``cp`` (or standalone, which checks everything present)."""
        return self.checkpoint is None or CHECKPOINTS.index(self.checkpoint) >= CHECKPOINTS.index(cp)

    def add(self, level: str, area: str, check: str, detail: str) -> None:
        self.findings.append({"level": level, "area": area, "check": check, "detail": detail})

    def equal(self, area: str, check: str, got: Any, want: Any, *, level: str = FAIL) -> None:
        if got == want:
            self.add(PASS, area, check, f"{got!r}")
        else:
            self.add(level, area, check, f"{got!r}, expected {want!r}")

    def missing(self, area: str, what: str, needed_from: str) -> None:
        """A source is absent: FAIL once its checkpoint is reached, NOT_YET before."""
        if self.reached(needed_from):
            self.add(FAIL, area, "present", f"{what} is missing (needed from {needed_from})")
        else:
            self.add(NOT_YET, area, "present", f"{what} arrives at {needed_from}")

    @property
    def failed(self) -> bool:
        return any(f["level"] == FAIL for f in self.findings)


def _json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _get(d: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(part)
    return d


def _lock_channels(lock: dict[str, Any]) -> list[dict[str, Any]]:
    return (lock.get("timeseries") or {}).get("channels") or []


# --------------------------------------------------------------------------- use case <-> device


def check_use_case(a: Audit, dest: str, lock: dict[str, Any]) -> dict[str, Any] | None:
    path = intake.stored_path(dest, "use_case")
    if path is None or not os.path.exists(path):
        a.missing("use case", "inputs/use_case.yaml (record it with ml_contract.intake)", "M0")
        return None
    import yaml  # pyyaml

    with open(path, "rb") as fh:
        raw = fh.read()
    same = source_matches(raw, lock.get("use_case_sha256"))
    a.add(PASS if same else FAIL, "use case", "input is the use case the lock was built from",
          f"lock {str(lock.get('use_case_sha256'))[:12]}" + ("" if same else ": the input differs; re-lock"))
    uc = yaml.safe_load(raw.decode("utf-8"))
    order = None
    for sensor in _get(uc, "ingress.sensors") or []:
        if isinstance(sensor, dict) and sensor.get("feature_order"):
            order = list(sensor["feature_order"])
            break
    if _lock_channels(lock):
        want = [c["name"] for c in _lock_channels(lock)]
        if order is None:
            a.add(WARN, "use case", "ingress feature_order", "no ingress sensor declares a feature_order")
        else:
            a.equal("use case", "ingress feature_order = lock channel order", order, want)
    return uc


def check_device(a: Audit, dest: str, lock: dict[str, Any], uc: dict[str, Any] | None) -> None:
    path = intake.stored_path(dest, "capability_manifest")
    if path is None or not os.path.exists(path):
        a.missing("device", "inputs/capability_manifest.json (record it with ml_contract.intake)", "M0")
        return
    cap = _json(path)
    area = "use case <-> device"
    a.equal("device", "manifest status", cap.get("status"), "success")
    generated = cap.get("generated_at")
    if generated:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(generated.replace("Z", "+00:00"))).days
            a.add(WARN if age > intake.MANIFEST_MAX_AGE_DAYS else PASS, "device", "manifest age",
                  f"{age} days (generated {generated})")
        except ValueError:
            a.add(WARN, "device", "manifest age", f"unreadable generated_at {generated!r}")
    formats = [str(f).lower() for f in cap.get("supported_export_formats") or []]
    a.add(PASS if "onnx" in formats else FAIL, area, "device accepts ONNX", f"supported_export_formats {formats}")
    providers = (cap.get("runtime") or {}).get("providers") or []
    if providers and not any(p.get("available") for p in providers):
        a.add(WARN, "device", "ONNX Runtime providers",
              "no execution provider reported available (ort_version "
              f"{(cap.get('runtime') or {}).get('ort_version')!r}); re-assess the device before deployment")
    if uc is None:
        a.add(NOT_YET, area, "use case target", "no use case input to compare")
        return
    task = _get(uc, "task.type")
    tasks = cap.get("supported_tasks") or []
    a.add(PASS if task in tasks else FAIL, area, "task supported", f"task {task!r}; device supports {tasks}")
    want_rt = _get(uc, "target.runtime_profile")
    profiles = list(dict.fromkeys((_get(cap, "l2.runtime_profiles") or []) + (_get(cap, "runtime.runtime_profiles") or [])))
    a.add(PASS if want_rt in profiles else FAIL, area, "runtime_profile available",
          f"use case asks {want_rt!r}; device offers {profiles}")
    a.equal(area, "device_profile_id", _get(uc, "target.device_profile_id"), cap.get("device_profile_id"))
    linked = _get(uc, "target.capability_manifest_id")
    if linked is None:
        a.add(WARN, area, "capability_manifest_id", f"the use case links no manifest; recorded manifest is "
                                                    f"{cap.get('manifest_id')!r}")
    else:
        a.equal(area, "capability_manifest_id", linked, cap.get("manifest_id"))
    platform, family = _get(uc, "target.platform"), cap.get("platform_family")
    if platform and family and platform != family:
        a.add(WARN, area, "platform", f"use case {platform!r}, device family {family!r}")
    channels = [c["name"] for c in _lock_channels(lock)]
    sensors = cap.get("sensors") or []
    declared = {str(s.get("name") or s.get("id") or s) if isinstance(s, dict) else str(s) for s in sensors}
    if not channels:
        return
    if not declared:
        source = _get(cap, "diagnostics.fact_sources.sensors")
        a.add(WARN, area, "sensors cover the channels", f"the device declares no sensors (source {source!r}); "
                                                        f"{channels} cannot be confirmed on the device")
    else:
        absent = [c for c in channels if c not in declared]
        a.add(FAIL if absent else PASS, area, "sensors cover the channels",
              f"missing on device: {absent}" if absent else f"all of {channels}")


# --------------------------------------------------------------------------- dataset


def check_dataset(a: Audit, dest: str, lock: dict[str, Any]) -> str | None:
    path = os.path.join(dest, "data", "contract", "manifest.json")
    if not lock.get("timeseries"):
        a.add(NOT_YET, "dataset", "contract dataset", f"no contract dataset check for modality {lock.get('modality')!r}")
        return None
    if not os.path.exists(path):
        a.missing("dataset", "data/contract/manifest.json", "M4")
        return None
    m = _json(path)
    ts = lock["timeseries"]
    area = "use case <-> dataset"
    a.equal(area, "contract lock_sha256", str(m.get("lock_sha256"))[:12], lock["lock_sha256"][:12])
    a.equal(area, "sample_rate_hz", float(m.get("sample_rate_hz") or 0), float(ts["sample_rate_hz"]))
    a.equal(area, "window_samples", m.get("window_samples"), ts["window_samples"])
    a.equal(area, "stride_samples", m.get("stride_samples"), ts["stride_samples"])
    got = [(c.get("name"), normalise_unit(c.get("unit")), c.get("reduce")) for c in m.get("channels") or []]
    want = [(c["name"], normalise_unit(c.get("unit")), c.get("reduce")) for c in ts["channels"]]
    a.equal(area, "channels (order, unit, reduce)", got, want)
    hashes = {"contract": m.get("split_hash")}
    for split in ("train", "val"):  # never test: M5+ may not open it, and train/val carry the same hash
        sp = os.path.join(dest, "data", "splits", f"{split}.json")
        if os.path.exists(sp):
            hashes[split] = _json(sp).get("split_hash")
    distinct = {h for h in hashes.values() if h}
    a.add(PASS if len(distinct) == 1 and None not in hashes.values() else FAIL, area, "split_hash agrees",
          ", ".join(f"{k} {str(v)[:12]}" for k, v in hashes.items()))
    split_hash = m.get("split_hash")
    syn = os.path.join(dest, "data", "synthetic", "manifest.json")
    if os.path.exists(syn):
        s = _json(syn)
        for key, want_v in (("lock_sha256", lock["lock_sha256"]), ("split_hash", split_hash)):
            if s.get(key) is None:
                a.add(FAIL, area, f"synthetic set stamped with {key}", "unstamped; re-run /synth-data")
            else:
                a.equal(area, f"synthetic set {key}", str(s[key])[:12], str(want_v)[:12])
    return split_hash


# --------------------------------------------------------------------------- simulator, scaffold, package


def check_simulator(a: Audit, dest: str, lock: dict[str, Any], split_hash: str | None) -> None:
    path = os.path.join(dest, "sim", "manifest.json")
    if not os.path.exists(path):
        a.add(NOT_YET, "use case <-> simulator", "present", "no sim/manifest.json yet (M12 exports it)")
        return
    m = _json(path)
    area = "use case <-> simulator"
    a.equal(area, "lock_sha256", str(m.get("lock_sha256"))[:12], lock["lock_sha256"][:12])
    if split_hash:
        a.equal(area, "split_hash", str(m.get("split_hash"))[:12], split_hash[:12])
    ts = lock.get("timeseries")
    if ts:
        names = [c["name"] for c in ts["channels"]]
        a.equal(area, "feature_order", m.get("feature_order"), names)
        a.equal(area, "sample_rate_hz", float(m.get("sample_rate_hz") or 0), float(ts["sample_rate_hz"]))
        a.equal(area, "units", {k: normalise_unit(v) for k, v in (m.get("units") or {}).items()},
                {c["name"]: normalise_unit(c.get("unit")) for c in ts["channels"]})
        a.equal(area, "reduce", m.get("reduce"), {c["name"]: c.get("reduce") for c in ts["channels"]})
    wrong = [f["path"] for f in m.get("files", []) if f.get("split") == "test" and f.get("purpose") != "acceptance_only"]
    a.add(FAIL if wrong else PASS, area, "test exported only for acceptance",
          f"not marked acceptance_only: {wrong}" if wrong else "no test file without acceptance_only")


def check_scaffold(a: Audit, dest: str, lock: dict[str, Any]) -> None:
    waived = intake.waiver(dest, "scaffold")
    if waived:
        a.add(PASS, "use case <-> scaffold", "scaffold", f"waived: {waived['reason']}; M8 uses the default "
                                                       "template, which writes the package itself (ADR-0026 D-3)")
        return
    path = intake.stored_path(dest, "scaffold")
    if path is None or not os.path.exists(path):
        a.missing("use case <-> scaffold", "inputs/scaffold: drop it, or waive it to use the default template "
                                          "(ml_contract.intake)", "M8")
        return
    with open(path, "rb") as fh:
        text = intake.scaffold_text(fh.read(), path)
    try:
        ctx = intake.scaffold_context(text)
    except ValueError as exc:
        a.add(FAIL, "use case <-> scaffold", "context", str(exc))
        return
    for f in intake.check_scaffold(ctx, text, lock):
        a.add(f["level"], "use case <-> scaffold", f["check"], f["detail"])
    cap = intake.stored_path(dest, "capability_manifest")
    if cap and os.path.exists(cap):
        a.equal("scaffold <-> device", "device_profile_id", _get(ctx, "target.device_profile_id"),
                _json(cap).get("device_profile_id"))


def check_package(a: Audit, dest: str, lock: dict[str, Any]) -> None:
    metas = sorted(glob.glob(os.path.join(dest, "*", "runs", "*", "model-package", "meta.json")))
    if not metas:
        a.missing("package", "<arch>/runs/<run_id>/model-package/meta.json", "M11")
        return
    ts = lock.get("timeseries") or {}
    for meta_path in metas:
        m = _json(meta_path)
        area = f"package {os.path.relpath(os.path.dirname(meta_path), dest)}"
        a.equal(area, "lock_sha256", str(m.get("lock_sha256"))[:12], lock["lock_sha256"][:12])
        a.equal(area, "class_names", m.get("class_names"), lock["class_names"])
        head = m.get("head")
        a.equal(area, "head shape", head.get("shape") if isinstance(head, dict) else head, lock["head"]["shape"])
        a.equal(area, "opset", m.get("opset"), ONNX_OPSET)
        if ts:
            a.equal(area, "feature_order", m.get("feature_order"), [c["name"] for c in ts["channels"]])
            a.equal(area, "window", m.get("window"), ts["window_samples"])
            a.equal(area, "stride", m.get("stride"), ts["stride_samples"])
            a.equal(area, "sample_rate_hz", float(m.get("sample_rate_hz") or 0), float(ts["sample_rate_hz"]))
            a.equal(area, "reduce", m.get("reduce"), {c["name"]: c.get("reduce") for c in ts["channels"]})
        if m.get("at_fpr") is not None:
            a.equal(area, "at_fpr", m.get("at_fpr"), lock["target"].get("at_fpr"), level=WARN)


# --------------------------------------------------------------------------- run


def run(dest: str, checkpoint: str | None) -> Audit:
    a = Audit(checkpoint)
    try:
        lock = read_lock(dest)
        a.add(PASS, "use case", "lock intact", f"{lock['lock_sha256'][:12]} ({lock.get('use_case_id')})")
    except (OSError, LockError) as exc:
        a.add(FAIL, "use case", "lock intact", str(exc))
        return a
    uc = check_use_case(a, dest, lock)
    check_device(a, dest, lock, uc)
    split_hash = check_dataset(a, dest, lock) if a.reached("M4") else None
    if not a.reached("M4"):
        a.add(NOT_YET, "use case <-> dataset", "contract dataset", "built at M4")
    if a.reached("M8"):
        check_scaffold(a, dest, lock)
    else:
        a.add(NOT_YET, "use case <-> scaffold", "present", "recorded at M8")
    if a.reached("M11"):
        check_package(a, dest, lock)
    else:
        a.add(NOT_YET, "package", "present", "built at M9, checked at M11")
    check_simulator(a, dest, lock, split_hash)
    return a


def to_markdown(a: Audit, dest: str) -> str:
    counts = {lvl: sum(f["level"] == lvl for f in a.findings) for lvl in (PASS, WARN, FAIL, NOT_YET)}
    title = f"checkpoint {a.checkpoint}" if a.checkpoint else "standalone"
    out = [
        f"# Use-case alignment audit — {title}",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat(timespec='seconds')} by `ml_contract.audit` for "
        f"`{os.path.basename(os.path.abspath(dest))}`. " + " · ".join(f"**{k}** {v}" for k, v in counts.items()),
        "",
        f"**Verdict: {'FAIL — a human must fix the source or approve a documented deviation' if a.failed else 'no FAIL'}**",
        "",
        "| Level | Area | Check | Detail |",
        "|---|---|---|---|",
    ]
    order = {FAIL: 0, WARN: 1, PASS: 2, NOT_YET: 3}
    for f in sorted(a.findings, key=lambda f: order[f["level"]]):
        detail = f["detail"].replace("|", "\\|")
        out.append(f"| {f['level']} | {f['area']} | {f['check']} | {detail} |")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="usecase-audit", description=__doc__.splitlines()[0])
    p.add_argument("--dest", required=True)
    p.add_argument("--checkpoint", choices=CHECKPOINTS,
                   help="the orchestrator's checkpoint; omit for a standalone check (no gate, no file)")
    p.add_argument("--no-gate", action="store_true", help="write the report without touching gates.json")
    args = p.parse_args(argv)
    a = run(args.dest, args.checkpoint)
    md = to_markdown(a, args.dest)
    print(md)
    if args.checkpoint:
        os.makedirs(os.path.join(args.dest, "audit"), exist_ok=True)
        base = os.path.join(args.dest, "audit", args.checkpoint)
        with open(base + ".md", "w", encoding="utf-8") as fh:
            fh.write(md)
        with open(base + ".json", "w", encoding="utf-8") as fh:
            json.dump({"checkpoint": args.checkpoint, "failed": a.failed, "findings": a.findings}, fh, indent=2,
                      ensure_ascii=False)
            fh.write("\n")
        if not args.no_gate:
            warns = [f"{f['area']}: {f['check']}" for f in a.findings if f["level"] == WARN]
            reason = f"audit/{args.checkpoint}.md — no FAIL; WARN: {'; '.join(warns) or 'none'}"
            outcome = gt.record_automatic(args.dest, f"audit/{args.checkpoint}",
                                          stage=CHECKPOINT_STAGE[args.checkpoint], passed=not a.failed, reason=reason)
            print(f"gate 'audit/{args.checkpoint}': {outcome}")
    return 1 if a.failed else 0


if __name__ == "__main__":
    sys.exit(main())
