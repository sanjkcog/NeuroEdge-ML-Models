#!/usr/bin/env python3
"""git_adapter.py — GitExchangeAdapter: push the exchange record to a repo-local file
and one GitHub Issue per open/blocked gate; pull inbound drive intents from Issues
(ADR-0012 EP-01, LLD §3.3).

RESULT-OBJECT-NEVER-RAISE (mirrors qa/adapter.py + qa/zephyr_adapter.py exactly): any
`gh_runner` failure — missing `gh`, a raised OSError, a non-zero exit, malformed JSON
— is captured in PushResult/PullResult, never raised. The repo-local file is written
FIRST and unconditionally in `push`, before any `gh` call is attempted, so a fully
offline environment (or one with no `gh` at all) still gets a correct, current
exchange.json — only the Issue projection is best-effort.

`gh_runner` is injected (a `Callable[[list[str]], CompletedProcess]`) so every test in
this module runs with zero network access — production wires it to a thin subprocess
wrapper (`_default_gh_runner`), never used directly here.

SECURITY (mirrors gate_state._notify's HIGH-finding fix): Issue title/body are always
passed as separate argv elements to `gh_runner`, never joined into a shell string —
there is no shell-interpolation code path in this module to harden, by construction.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Callable

from exchange.adapter import DriveIntent, PullArtifactsResult, PullResult, PushResult

_TIMEOUT_SECONDS = 30
_ISSUE_TITLE_PREFIX = "[AgentForge] Gate:"

# Outbound projection of a gates.json gate `status` (ADR-0012 US-01-03, FR-03). Keyed
# on the exact gates_schema.json status enum ("pending", "approved",
# "changes_requested", "rejected") so this can never silently fall out of step with
# what gate_state.py itself can produce.
_STATUS_LABELS: dict[str, list[str]] = {
    "pending": ["gate:blocked", "gate:awaiting-human"],
    "approved": ["gate:cleared"],
    "changes_requested": ["gate:changes-requested"],
    "rejected": ["gate:rejected"],
}


def gate_status_labels(status: str) -> list[str]:
    """Map one gates.json gate `status` value to its outbound Issue-label projection.

    Pure and read-only by construction, not merely by convention: this takes an
    already-extracted status STRING, never gates.json (or even the exchange record)
    itself, so it has no way to write anything — the "projection is read-only on
    gates.json" invariant holds at the signature level. Falls back to a literal
    "gate:<status>" label for any future/unrecognised status value rather than raising,
    mirroring pull_intents' own tolerant-skip discipline for unknown input.
    """
    return list(_STATUS_LABELS.get(status, [f"gate:{status}"]))


def _default_gh_runner(argv: list[str]) -> subprocess.CompletedProcess:
    """The production `gh_runner`: a thin, real subprocess call. Never called by any
    test in this suite — every test injects its own gh_runner (LLD §3.3)."""
    return subprocess.run(argv, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS)


def _issue_title(artifact: str) -> str:
    return f"{_ISSUE_TITLE_PREFIX} {artifact}"


def _issue_body(artifact: str, gate: dict) -> str:
    return (
        "Gate status projection (ADR-0012) — a read-only view of gates.json, "
        "not itself authoritative. Do not approve/clear this gate here; only a "
        "recorded human decision via `gate_state.py decide` (main session, D1) "
        "clears a hard gate.\n\n"
        f"- artifact: {artifact}\n"
        f"- stage: {gate.get('stage', '?')}\n"
        f"- type: {gate.get('type', '?')}\n"
        f"- status: {gate.get('status', '?')}\n"
    )


def _parse_issue_number(stdout: str) -> int | None:
    """`gh issue create`/`gh issue edit` print a plain URL (not JSON) on success."""
    stdout = stdout.strip()
    match = re.search(r"/issues/(\d+)\s*$", stdout)
    if match:
        return int(match.group(1))
    if stdout.isdigit():
        return int(stdout)
    return None


def _load_driveintent_action_enum() -> set[str]:
    """Read the single-source action enum from exchange_schema.json's
    $defs.driveIntent — never hardcoded twice (mirrors exchange_record._validate's
    schema-driven approach)."""
    import exchange.exchange_record as exchange_record

    schema = json.loads(exchange_record._SCHEMA_PATH.read_text(encoding="utf-8"))
    return set(schema["$defs"]["driveIntent"]["properties"]["action"]["enum"])


def _label_value(labels: list, prefix: str) -> str | None:
    for label in labels or []:
        name = label.get("name", "") if isinstance(label, dict) else str(label)
        if name.startswith(prefix):
            return name[len(prefix):]
    return None


def _parse_intent(issue: dict) -> DriveIntent | None:
    """Convert one `gh issue list --json` entry into a DriveIntent, or None if the
    Issue carries no recognisable intent labels at all (an ordinary, non-drive Issue
    — tolerantly skipped, never an error)."""
    labels = issue.get("labels", [])
    action = _label_value(labels, "intent:")
    if action is None:
        return None
    target = _label_value(labels, "target:") or ""
    author = issue.get("author")
    identity = author.get("login", "") if isinstance(author, dict) else (author or "")
    return DriveIntent(
        action=action,
        target=target,
        identity=identity,
        raw_id=f"issue-{issue.get('number')}",
    )


class GitExchangeAdapter:
    """Implements ExchangeAdapter against a repo-local file + `gh` Issues.

    `repo_file` is the canonical, repo-committed projection path (default
    exchange.json in the current directory); `record_path` passed to `push` is
    wherever the caller built/saved the ExchangeRecord (may be the same path or a
    working copy) — `push` always publishes its content into `repo_file` atomically.
    """

    def __init__(
        self,
        gh_runner: Callable[[list[str]], subprocess.CompletedProcess] = _default_gh_runner,
        repo_file: str | Path = Path("exchange.json"),
    ):
        self.gh_runner = gh_runner
        self.repo_file = Path(repo_file)

    # -- push -------------------------------------------------------------------

    def push(self, record_path: Path) -> PushResult:
        record_path = Path(record_path)
        try:
            payload = record_path.read_text(encoding="utf-8")
        except OSError as exc:
            return PushResult(success=False, detail=f"could not read {record_path}: {exc}")

        # The repo-local file is written FIRST, unconditionally — every failure below
        # is an Issue-projection failure only, never a reason to withhold the write.
        self._write_repo_file(payload)

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            return PushResult(
                success=False,
                detail=f"{record_path} written to {self.repo_file}, but is not valid JSON: {exc}",
            )

        gates = [gate for gate in data.get("gates", []) if isinstance(gate, dict)]
        pending_gates = [gate for gate in gates if gate.get("status") == "pending"]
        # ADR-0012 US-01-03 (FR-03): a gate that left "pending" (approved /
        # changes_requested / rejected) is ALSO projected outbound — "gate:blocked,
        # awaiting-human plus its cleared/rejected states" — but only onto an Issue
        # that already exists for it; see _project_resolved_gate.
        resolved_gates = [
            gate for gate in gates
            if gate.get("status") in _STATUS_LABELS and gate.get("status") != "pending"
        ]

        if not pending_gates and not resolved_gates:
            return PushResult(
                success=True,
                detail=f"{self.repo_file}: written; no gates to project.",
            )

        failures: list[str] = []
        projected = 0
        for gate in pending_gates:
            artifact = gate.get("artifact", "?")
            ok, detail = self._upsert_issue(artifact, gate)
            if ok:
                projected += 1
            else:
                failures.append(f"{artifact}: {detail}")
        for gate in resolved_gates:
            artifact = gate.get("artifact", "?")
            ok, detail = self._project_resolved_gate(artifact, gate)
            if ok:
                projected += 1
            else:
                failures.append(f"{artifact}: {detail}")

        total = len(pending_gates) + len(resolved_gates)
        if failures:
            return PushResult(
                success=False,
                detail=(
                    f"{self.repo_file} written; {projected}/{total} gate(s) "
                    f"projected; failures: " + "; ".join(failures)
                ),
            )
        return PushResult(
            success=True,
            detail=f"{self.repo_file} written; {projected} gate(s) projected via gh.",
        )

    def _write_repo_file(self, payload: str) -> None:
        """Atomically write `payload` to `self.repo_file` — deliberately NOT wrapped in
        the module's never-raise discipline.

        The RESULT-OBJECT-NEVER-RAISE contract documented at the top of this module is
        scoped to `gh_runner` failures only (an external system: missing binary,
        network, auth, rate limit — all expected, all recoverable by the caller
        inspecting PushResult). This local repo-file write is not that: `repo_file` is
        the authoritative, repo-committed exchange projection (see the class docstring
        — "record_path passed to push() ... push always publishes its content into
        repo_file atomically"), so an OSError here (disk full, permission denied, a
        parent directory that cannot be created) is a genuine local-filesystem failure
        with no adapter-level fallback that would make swallowing it meaningful — it is
        deliberately allowed to propagate (fail loud) rather than being caught and
        turned into a misleadingly generic PushResult(success=False), which would look
        identical to an ordinary "gh is unreachable" projection failure and hide a real
        local-disk problem behind the same soft-fail path (code-review MEDIUM finding).
        """
        import os

        self.repo_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.repo_file.with_name(self.repo_file.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, self.repo_file)

    def _upsert_issue(self, artifact: str, gate: dict) -> tuple[bool, str]:
        title = _issue_title(artifact)
        body = _issue_body(artifact, gate)
        labels = ",".join(gate_status_labels(gate.get("status", "pending")))

        try:
            existing = self._find_open_issue(title)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return False, f"gh unreachable while searching: {exc}"

        try:
            if existing is not None:
                result = self.gh_runner(
                    ["gh", "issue", "edit", str(existing), "--title", title, "--body", body, "--add-label", labels]
                )
            else:
                result = self.gh_runner(
                    ["gh", "issue", "create", "--title", title, "--body", body, "--label", labels]
                )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"gh unreachable: {exc}"

        if result.returncode != 0:
            return False, f"gh exited {result.returncode}: {(result.stderr or '').strip()}"

        number = existing if existing is not None else _parse_issue_number(result.stdout)
        if number is None:
            return False, f"could not determine Issue number from gh output: {result.stdout!r}"

        # Read-back after write (LLD §3.3: "not every mutating verb returns JSON").
        try:
            view = self.gh_runner(["gh", "issue", "view", str(number), "--json", "number,title,body,state"])
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"gh unreachable during read-back: {exc}"
        if view.returncode != 0:
            return False, f"read-back failed: gh exited {view.returncode}: {(view.stderr or '').strip()}"
        try:
            seen = json.loads(view.stdout)
        except json.JSONDecodeError as exc:
            return False, f"read-back returned invalid JSON: {exc}"
        if seen.get("title") != title:
            return False, f"read-back title mismatch: expected {title!r}, got {seen.get('title')!r}"

        return True, f"Issue #{number} upserted and verified"

    def _project_resolved_gate(self, artifact: str, gate: dict) -> tuple[bool, str]:
        """Project a gate that has LEFT "pending" (approved / changes_requested /
        rejected) onto an EXISTING Issue only (ADR-0012 US-01-03 AC1, "plus its
        cleared/rejected states").

        Deliberately never creates a new Issue: a gate that resolved without one ever
        having been opened for it (e.g. a soft gate approved without projection, or a
        gate resolved before an exchange substrate was configured) has nothing to
        close — manufacturing an Issue at that point would be noise, not a projection.
        Read-only on gates.json by construction: `gate` here is a plain dict already
        extracted from exchange.json by push(); this method never opens gates.json.
        """
        title = _issue_title(artifact)
        labels = ",".join(gate_status_labels(gate.get("status", "")))

        try:
            existing = self._find_open_issue(title)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return False, f"gh unreachable while searching: {exc}"
        if existing is None:
            return True, "no open Issue to resolve (gate was never projected while pending)"

        try:
            edit_result = self.gh_runner(["gh", "issue", "edit", str(existing), "--add-label", labels])
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"gh unreachable: {exc}"
        if edit_result.returncode != 0:
            return False, f"gh exited {edit_result.returncode}: {(edit_result.stderr or '').strip()}"

        try:
            close_result = self.gh_runner(["gh", "issue", "close", str(existing)])
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"gh unreachable while closing: {exc}"
        if close_result.returncode != 0:
            return False, f"gh exited {close_result.returncode}: {(close_result.stderr or '').strip()}"

        return True, f"Issue #{existing} relabeled {labels!r} and closed"

    def _find_open_issue(self, title: str) -> int | None:
        result = self.gh_runner(["gh", "issue", "list", "--state", "open", "--search", title, "--json", "number,title"])
        if result.returncode != 0:
            raise OSError(f"gh issue list exited {result.returncode}: {(result.stderr or '').strip()}")
        try:
            issues = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"gh issue list returned invalid JSON: {exc}") from exc
        for issue in issues:
            if issue.get("title") == title:
                return issue.get("number")
        return None

    # -- pull_intents -------------------------------------------------------------

    def pull_artifacts(self) -> PullArtifactsResult:
        """Required by ExchangeAdapter; not implemented by this provider.

        Added 2026-07-29 (TD-016): this class was typed against `ExchangeAdapter` but
        implemented only `push` and `pull_intents`, so `pull_artifacts()` raised
        AttributeError. Protocols are structural and checked at type-check time, not at
        runtime — and nothing type-checks this repo (no mypy/pyright), so the gap was
        invisible. Inbound ingestion is `ingestion.sources.GitLocalSource`'s job; this
        returns an honest empty success so the Protocol is satisfied and a caller can
        tell "nothing to ingest" from "cannot ingest" by reading `detail`.
        """
        return PullArtifactsResult(
            success=True, docs=[],
            detail="git provider does not implement inbound artifact pull "
                   "(see ingestion.sources.GitLocalSource)",
        )

    def pull_intents(self) -> PullResult:
        try:
            result = self.gh_runner(["gh", "issue", "list", "--json", "number,title,body,labels,author"])
        except (OSError, subprocess.SubprocessError) as exc:
            return PullResult(success=False, intents=[], detail=f"gh unreachable: {exc}")
        if result.returncode != 0:
            return PullResult(
                success=False, intents=[],
                detail=f"gh exited {result.returncode}: {(result.stderr or '').strip()}",
            )
        try:
            issues = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            return PullResult(success=False, intents=[], detail=f"gh issue list returned invalid JSON: {exc}")

        allowed_actions = _load_driveintent_action_enum()
        intents: list[DriveIntent] = []
        skipped = 0
        for issue in issues:
            intent = _parse_intent(issue)
            if intent is None or intent.action not in allowed_actions:
                skipped += 1
                continue
            intents.append(intent)

        detail = f"parsed {len(intents)} intent(s)"
        if skipped:
            detail += f", skipped {skipped} unrecognized Issue(s)"
        return PullResult(success=True, intents=intents, detail=detail)
