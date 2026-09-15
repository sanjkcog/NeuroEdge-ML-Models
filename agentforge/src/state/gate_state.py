#!/usr/bin/env python3
"""gate_state.py — atomic, resumable approval ledger for gated artifacts (EP-02).

Mirrors run_state.py's design exactly (ATOMIC_STATE_IO, SCHEMA_DRIVEN_VALIDATION):
temp-file + os.replace writes, schema-driven validation before construction (never a
bare **-splat on untrusted JSON — this session's run_state.py hardening, applied here
from the start), and a load() that raises InvalidGateState naming the offending field
rather than letting a corrupt file partially resume.

The one-shot design (gates-mvp.plan.md Task 1's GOTCHA, confirmed by the user against
TS-02-02's 100%-recorded requirement): `status` on a gate IS the one-shot mechanism.
`pending` is the only status stop-hitl-gate.js blocks on; once ANY decision is recorded
(approved, changes_requested, or rejected) status leaves `pending` and Stop no longer
force-blocks. Only `approved` unblocks writes — that check is owned entirely by
pre-write-hitl-gate.js reading `status` directly, never re-implemented in Python.
There is no second "already asked" flag — inventing one would let the two hooks
disagree about what "resolved" means.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("gates_schema.json")
SCHEMA_VERSION = "1.0"

_OUTCOMES = ("approved", "changes_requested", "rejected")


class InvalidGateState(Exception):
    """gates.json is malformed or fails schema validation. Message names the field."""


class SelfApprovalError(Exception):
    """Refused: the identity that opened a gate (drove the artifact to it) attempted
    to also approve it (ADR-0012 US-02-03, prevent-self-review analogue). A distinct
    identity must clear it — mirrors "an author cannot approve their own PR."."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_KEY_RE = re.compile(r'"([^"\\]*)"\s*:')


def _last_key_before(text: str, pos: int) -> str | None:
    """The last JSON object key before byte offset `pos` — see run_state._last_key_before."""
    keys = [m.group(1) for m in _KEY_RE.finditer(text, 0, max(pos, 0))]
    return keys[-1] if keys else None


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(data: dict) -> None:
    """Reject a structurally-invalid gates.json, naming the first offending field.

    Required lists are read from gates_schema.json so the schema stays the single
    source of truth, exactly as run_state._validate does for run.json.
    """
    if not isinstance(data, dict):
        raise InvalidGateState("INVALID gates.json: top-level value is not an object")

    schema = _load_schema()
    for key in schema.get("required", []):
        if key not in data:
            raise InvalidGateState(f"INVALID gates.json: missing required field {key!r}")

    if not isinstance(data.get("gates"), dict):
        raise InvalidGateState("INVALID gates.json: field 'gates' must be an object")

    gate_schema = schema["properties"]["gates"]["additionalProperties"]
    gate_required = gate_schema["required"]
    status_enum = gate_schema["properties"]["status"]["enum"]
    type_enum = gate_schema["properties"]["type"]["enum"]
    decision_required = gate_schema["properties"]["decisions"]["items"]["required"]
    outcome_enum = gate_schema["properties"]["decisions"]["items"]["properties"]["outcome"]["enum"]

    for artifact, gate in data["gates"].items():
        if not isinstance(gate, dict):
            raise InvalidGateState(f"INVALID gates.json: gate {artifact!r} must be an object")
        for key in gate_required:
            if key not in gate:
                raise InvalidGateState(
                    f"INVALID gates.json: gate {artifact!r} missing required field {key!r}"
                )
        # Enum checks matter as much as presence checks here: stop-hitl-gate.js blocks
        # only on status=="pending" and pre-write-hitl-gate.js unblocks only on
        # status=="approved" — a corrupted value (e.g. a typo'd "aproved") would be
        # silently invisible to BOTH enforcement points at once, a fail-open outcome
        # for a security-relevant control (code-reviewer MEDIUM finding).
        if gate["status"] not in status_enum:
            raise InvalidGateState(
                f"INVALID gates.json: gate {artifact!r} field 'status' has invalid "
                f"value {gate['status']!r}, expected one of {status_enum}"
            )
        if gate["type"] not in type_enum:
            raise InvalidGateState(
                f"INVALID gates.json: gate {artifact!r} field 'type' has invalid "
                f"value {gate['type']!r}, expected one of {type_enum}"
            )
        decisions = gate.get("decisions")
        if not isinstance(decisions, list):
            raise InvalidGateState(
                f"INVALID gates.json: gate {artifact!r} field 'decisions' must be an array"
            )
        for i, decision in enumerate(decisions):
            if not isinstance(decision, dict):
                raise InvalidGateState(
                    f"INVALID gates.json: gate {artifact!r} decision #{i} must be an object"
                )
            for key in decision_required:
                if key not in decision:
                    raise InvalidGateState(
                        f"INVALID gates.json: gate {artifact!r} decision #{i} "
                        f"missing required field {key!r}"
                    )
            if decision["outcome"] not in outcome_enum:
                raise InvalidGateState(
                    f"INVALID gates.json: gate {artifact!r} decision #{i} field "
                    f"'outcome' has invalid value {decision['outcome']!r}, expected "
                    f"one of {outcome_enum}"
                )


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    identity: str
    timestamp: str
    outcome: str          # "approved" | "changes_requested" | "rejected"
    reason: str = ""


@dataclass
class Gate:
    stage: str
    type: str = "hard"    # "hard" | "soft"
    status: str = "pending"
    opened_at: str = ""
    decisions: list[Decision] = field(default_factory=list)
    opened_by: str = ""   # identity that drove the artifact to this gate (ADR-0012
    # US-02-03, additive). "" means unknown/not recorded — no self-approval check
    # applies, preserving every pre-existing open_gate() call site unchanged.


@dataclass
class AuditReport:
    total_gates: int
    approved_count: int
    approval_rate: float


# ---------------------------------------------------------------------------
# GateState
# ---------------------------------------------------------------------------

@dataclass
class GateState:
    gates: dict[str, Gate] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    updated: str = ""

    @classmethod
    def new(cls) -> GateState:
        return cls()

    def open_gate(
        self, artifact: str, *, stage: str, gate_type: str = "hard", opened_by: str = ""
    ) -> Gate:
        """Register a NEW pending gate for an artifact never gated before.

        Overwrites any prior Gate at this key wholesale — use reopen_gate to re-arm an
        existing gate (e.g. after a rejection) without discarding its decision history.

        `opened_by` (ADR-0012 US-02-03, optional) records the identity that drove the
        artifact to this gate, enabling the self-approval check in record_decision.
        Defaults to "" (unknown) so every pre-existing call site keeps working unchanged.
        """
        gate = Gate(
            stage=stage, type=gate_type, status="pending", opened_at=_now_iso(), opened_by=opened_by
        )
        self.gates[artifact] = gate
        try:
            _notify(f"Gate opened: {artifact} (stage {stage})")
        except Exception:
            pass  # a courtesy notification must never block the gate opening itself
        return gate

    def reopen_gate(self, artifact: str) -> Gate:
        """Re-arm an existing gate back to `pending`, preserving its decision history.

        Distinct from open_gate: a reject -> re-arm -> approve cycle must not erase the
        earlier rejection from the audit trail (gates_schema.json's decisions field is
        documented as append-only) — reopen_gate resets only `status`, never replacing
        the Gate object or clearing `decisions` (code-reviewer MEDIUM finding).
        """
        gate = self.gates[artifact]
        gate.status = "pending"
        gate.opened_at = _now_iso()
        try:
            _notify(f"Gate re-opened: {artifact} (stage {gate.stage})")
        except Exception:
            pass
        return gate

    def record_decision(
        self, artifact: str, outcome: str, *, identity: str, reason: str = ""
    ) -> Decision:
        """Append a decision and set status from the outcome directly.

        Never collapses non-approved outcomes to a single value — the audit (Task 15)
        must be able to distinguish "explicitly rejected" from "still pending".

        Self-approval rejection (ADR-0012 US-02-03): when `outcome == "approved"` and
        the gate recorded an `opened_by` identity, `identity` may not equal it — the
        identity that drove the artifact to this gate cannot also be the one that
        approves it (raises SelfApprovalError, no decision recorded). Scoped to
        "approved" only, not every outcome: rejecting/requesting changes on your own
        artifact is not self-review and stays permitted (zero false positives, AC-3).
        `opened_by == ""` (unknown/pre-existing gates) never triggers this check.

        Identity guard (code-review MEDIUM, 2026-07-24): `identity` must be non-empty
        after stripping whitespace — an unattributed decision is never recordable,
        mirroring the outcome-enum guard immediately above. The self-approval
        comparison itself is case-insensitive (`.strip().casefold()` on both sides) so
        a case-variant identity (e.g. "Dev-A" vs the recorded "dev-a") cannot bypass
        the check the way a bare `==` would have let it.
        """
        if outcome not in _OUTCOMES:
            raise ValueError(f"unknown outcome {outcome!r}, expected one of {_OUTCOMES}")
        if not identity or not identity.strip():
            raise ValueError(
                "identity must not be empty — an unattributed decision cannot be recorded"
            )
        gate = self.gates[artifact]
        if (
            outcome == "approved"
            and gate.opened_by
            and identity.strip().casefold() == gate.opened_by.strip().casefold()
        ):
            raise SelfApprovalError(
                f"refused: identity {identity!r} opened gate {artifact!r} and cannot "
                "also approve it — self-approval is not permitted; a distinct "
                "identity must clear it"
            )
        decision = Decision(identity=identity, timestamp=_now_iso(), outcome=outcome, reason=reason)
        gate.decisions.append(decision)
        gate.status = outcome
        return decision

    def is_pending(self, artifact: str) -> bool:
        gate = self.gates.get(artifact)
        return gate is not None and gate.status == "pending"

    def any_pending(self) -> list[str]:
        """Artifacts whose gate is pending AND blocking — what stop-hitl-gate.js forces.

        Excludes type=="soft": gates_schema.json documents soft gates as advisory,
        "does not block writes" — stop-hitl-gate.js must not force a response over one
        either, or "advisory" would be a lie for half of what "advisory" is supposed to
        mean (third-round code-review finding; mirrored in stop-hitl-gate.js itself,
        which reads gates.json independently and applies the same exclusion in JS).
        """
        return [
            artifact
            for artifact, gate in self.gates.items()
            if gate.status == "pending" and gate.type != "soft"
        ]

    def to_dict(self) -> dict:
        self.updated = _now_iso()
        return {
            "schema_version": self.schema_version,
            "updated": self.updated,
            "gates": {
                artifact: {
                    "stage": gate.stage,
                    "type": gate.type,
                    "status": gate.status,
                    "opened_at": gate.opened_at,
                    "decisions": [asdict(d) for d in gate.decisions],
                    "opened_by": gate.opened_by,
                }
                for artifact, gate in self.gates.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> GateState:
        gates: dict[str, Gate] = {}
        for artifact, g in data["gates"].items():
            gates[artifact] = Gate(
                stage=g.get("stage", ""),
                type=g.get("type", "hard"),
                status=g.get("status", "pending"),
                opened_at=g.get("opened_at", ""),
                decisions=[
                    Decision(
                        identity=d.get("identity", ""),
                        timestamp=d.get("timestamp", ""),
                        outcome=d.get("outcome", ""),
                        reason=d.get("reason", ""),
                    )
                    for d in g.get("decisions", [])
                ],
                opened_by=g.get("opened_by", ""),
            )
        return cls(
            gates=gates,
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            updated=data.get("updated", ""),
        )

    def save(self, path: str | Path) -> None:
        """Atomically persist to `path` — temp file + os.replace, mirrors run_state.save."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> GateState:
        """Reconstruct from gates.json alone. Raises InvalidGateState naming the field."""
        path = Path(path)
        raw = path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            near = _last_key_before(raw, exc.pos)
            where = f" (last field parsed: {near!r})" if near else ""
            raise InvalidGateState(
                f"INVALID gates.json: malformed JSON at line {exc.lineno} col {exc.colno}"
                f"{where}: {exc.msg}"
            ) from exc
        _validate(data)
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Best-effort OS notification (Task 19) — never blocks the caller
# ---------------------------------------------------------------------------

def _escape_applescript(text: str) -> str:
    """Escape text for embedding inside a double-quoted AppleScript string literal.

    Backslashes first (so escaping a quote doesn't double-escape an already-escaped
    one), then double-quotes. Newlines are flattened — a raw newline inside an
    AppleScript string is itself a syntax error, not just a cosmetic issue.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", "")


def _escape_powershell_single_quoted(text: str) -> str:
    """Escape text for embedding inside a single-quoted PowerShell string literal.

    PowerShell's single-quoted strings treat '' as a literal single quote and take
    everything else verbatim — no backslash escaping exists or is needed there.
    """
    return text.replace("'", "''").replace("\n", " ").replace("\r", "")


def _notify(message: str) -> None:
    """Best-effort desktop notification. Raises on failure — callers must swallow it.

    Deliberately allowed to raise rather than swallowing internally: open_gate wraps the
    call in its own try/except so a missing notifier never blocks the gate opening, and
    tests can stub this function to assert that guarantee independently (see
    test_open_gate_succeeds_when_notification_fails).

    `message` is built from artifact/branch names that are not fully trusted input (a
    crafted branch name could otherwise break out of the quoted literal embedded below
    and inject arbitrary AppleScript/PowerShell — code-reviewer HIGH finding). notify-send
    takes the message as a separate argv element with no shell/script interpretation, so
    it needs no escaping; osascript and PowerShell both interpret a script STRING, so the
    message is escaped for each one's literal-string syntax before interpolation.
    """
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "AgentForge gate", message], check=True, timeout=5)
    elif shutil.which("osascript"):
        safe_message = _escape_applescript(message)
        script = f'display notification "{safe_message}" with title "AgentForge gate"'
        subprocess.run(["osascript", "-e", script], check=True, timeout=5)
    elif shutil.which("powershell") or shutil.which("powershell.exe"):
        ps = shutil.which("powershell") or shutil.which("powershell.exe")
        safe_message = _escape_powershell_single_quoted(message)
        # WinRT toast API, not System.Windows.Forms.NotifyIcon.ShowBalloonTip: verified
        # live on Windows 11 that ShowBalloonTip renders nothing visible (it requires
        # .Visible = true first, and the one-shot -Command process typically exits
        # before Windows finishes drawing it) — TS-02-03-04 manual verification caught
        # this. The WinRT ToastNotificationManager path was confirmed to actually appear.
        cmd = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            "ContentType = WindowsRuntime] | Out-Null; "
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, "
            "ContentType = WindowsRuntime] | Out-Null; "
            "$template = [Windows.UI.Notifications.ToastNotificationManager]::"
            "GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            "$textNodes = $template.GetElementsByTagName('text'); "
            "$textNodes.Item(0).AppendChild($template.CreateTextNode('AgentForge gate')) "
            "| Out-Null; "
            f"$textNodes.Item(1).AppendChild($template.CreateTextNode('{safe_message}')) "
            "| Out-Null; "
            "$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
            "[Windows.UI.Notifications.ToastNotificationManager]::"
            "CreateToastNotifier('Windows PowerShell').Show($toast)"
        )
        subprocess.run([ps, "-NoProfile", "-Command", cmd], check=True, timeout=5)
    else:
        raise OSError("no supported OS notifier found on this machine")


# ---------------------------------------------------------------------------
# Audit (Task 15)
# ---------------------------------------------------------------------------

def audit(state: GateState) -> AuditReport:
    """Approval rate over recorded gates.json state only.

    Limitation, stated plainly rather than implied away: this can only see what's in
    gates.json. A write that bypassed the hook entirely leaves no trace here — this
    measures recorded compliance, not absolute prevention. True prevention is
    pre-write-hitl-gate.js's fail-closed behaviour, not this audit. There is no longer
    a sanctioned proceed-without-approval path to audit for — the PR gate's D3
    warn-with-override was reversed to hard/no-override, so "unapproved gates that
    proceeded" is no longer a distinct, measurable case here.
    """
    total = len(state.gates)
    approved = sum(1 for g in state.gates.values() if g.status == "approved")
    rate = (approved / total) if total else 1.0
    return AuditReport(
        total_gates=total,
        approved_count=approved,
        approval_rate=rate,
    )


# ---------------------------------------------------------------------------
# CLI — how the main-session AskUserQuestion flow and the hooks record decisions
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read and update a gates.json ledger.")
    parser.add_argument("--path", default="gates.json", help="Path to gates.json (default: gates.json)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_open = sub.add_parser("open", help="Open a new pending gate")
    p_open.add_argument("artifact")
    p_open.add_argument("--stage", required=True)
    p_open.add_argument("--type", dest="gate_type", default="hard", choices=["hard", "soft"])
    p_open.add_argument(
        "--opened-by", default="",
        help="Identity that drove the artifact to this gate (ADR-0012 US-02-03, optional) "
             "— enables self-approval rejection for this gate",
    )

    p_decide = sub.add_parser("decide", help="Record an AskUserQuestion decision (main session only, D1)")
    p_decide.add_argument("artifact")
    p_decide.add_argument("outcome", choices=list(_OUTCOMES))
    p_decide.add_argument("--identity", required=True)
    p_decide.add_argument("--reason", default="")

    p_reopen = sub.add_parser(
        "reopen", help="Re-arm an existing gate to pending, preserving its decision history"
    )
    p_reopen.add_argument("artifact")

    sub.add_parser("status", help="Print pending gates")
    sub.add_parser("audit", help="Print the approval-rate audit")

    args = parser.parse_args(argv)
    path = Path(args.path)

    if args.cmd == "open":
        state = GateState.load(path) if path.exists() else GateState.new()
        state.open_gate(
            args.artifact, stage=args.stage, gate_type=args.gate_type, opened_by=args.opened_by
        )
        state.save(path)
        print(f"opened: {args.artifact} (stage {args.stage}, {args.gate_type})")
        return 0

    try:
        state = GateState.load(path)
    except FileNotFoundError:
        print(f"No gates.json at {path} — nothing is gated yet.")
        return 0 if args.cmd == "status" else 1
    except InvalidGateState as exc:
        print(exc)
        return 1

    # decide/reopen both require an existing artifact key; report a clean message
    # rather than a raw KeyError traceback for a typo'd or stale artifact path
    # (third-round code-review finding — this was previously an unhandled crash).
    if args.cmd in ("decide", "reopen") and args.artifact not in state.gates:
        print(f"No gate open for {args.artifact!r} in {path}.")
        return 1

    if args.cmd == "decide":
        try:
            state.record_decision(args.artifact, args.outcome, identity=args.identity, reason=args.reason)
        except (SelfApprovalError, ValueError) as exc:
            # ValueError here is the identity guard (empty/whitespace-only --identity)
            # — reported cleanly like SelfApprovalError, never a raw traceback.
            print(exc)
            return 1
        state.save(path)
        print(f"{args.artifact}: {args.outcome}")
        return 0

    if args.cmd == "reopen":
        state.reopen_gate(args.artifact)
        state.save(path)
        print(f"{args.artifact}: re-opened (pending, history preserved)")
        return 0

    if args.cmd == "audit":
        report = audit(state)
        print(f"total_gates:          {report.total_gates}")
        print(f"approved:             {report.approved_count}")
        print(f"approval_rate:        {report.approval_rate:.2%}")
        return 0

    # status
    pending = state.any_pending()
    if not pending:
        print("Blocked: nothing")
    else:
        for artifact in pending:
            gate = state.gates[artifact]
            print(f"Blocked: {artifact} (stage {gate.stage}, opened {gate.opened_at})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
