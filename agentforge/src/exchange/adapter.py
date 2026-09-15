#!/usr/bin/env python3
"""adapter.py — the pluggable Git exchange substrate adapter protocol (ADR-0012 EP-01).

The second implementation of the ADR-0003 adapter port (generalizes
agentforge/src/qa/adapter.py's TestManagementAdapter/UploadResult/NoneAdapter shape):
every external call returns a result object, never raises — mirrors the exact
never-raise discipline hardened in qa/zephyr_adapter.py. `NoneExchangeAdapter` is the
D12 fallback: with no exchange substrate configured, the exchange record still saves to
the repo-local file and the run continues unaffected — never an unhandled exception.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class PushResult:
    """The outcome of one push attempt. Never an exception — always this."""
    success: bool
    detail: str = ""


@dataclass
class DriveIntent:
    """One inbound drive intent parsed from an external system (e.g. a GitHub Issue).

    `action` is validated by the adapter that parses it against exchange_schema.json's
    $defs.driveIntent.action enum ({"advance", "approve_gate", "comment",
    "request_run"}) — the enum is declared once, in the schema, never hardcoded twice.
    `target` is a stage id for "advance" or an artifact path for gate-related actions.
    """
    action: str
    target: str
    identity: str
    raw_id: str


@dataclass
class PullResult:
    """The outcome of one pull attempt. Never an exception — always this."""
    success: bool
    intents: list[DriveIntent] = field(default_factory=list)
    detail: str = ""


@dataclass
class IngestedDoc:
    """One document pulled by an inbound ingestion source (ADR-0012 Direction 2,
    FR-01). `source_id` + `locator` are the pull coordinates every downstream
    consumer (mapper.py, provenance.py) needs to build a `sources.md` row — never
    dropped, never synthesized (see provenance.resolve_source)."""
    source_id: str
    locator: str
    content: str = ""


@dataclass
class PullArtifactsResult:
    """The outcome of one pull-artifacts attempt. Never an exception — always this.
    Mirrors PullResult exactly, one level up: drive intents vs ingested documents."""
    success: bool
    docs: list[IngestedDoc] = field(default_factory=list)
    detail: str = ""


class ExchangeAdapter(Protocol):
    """The pluggable interface every exchange substrate (and the no-substrate
    fallback) implements — push the record out, pull drive intents in, pull inbound
    artifacts in (ADR-0012 Direction 2, FR-01). Nothing here assumes a CLI or a
    network call exists — see NoneExchangeAdapter, the first-class fallback, not a
    stub to delete once a "real" adapter exists.

    `pull_artifacts()` extends this Protocol (never forks it, M4): every ingestion
    source (GitLocalSource today; Jira/Confluence/S3 backlog) implements it exactly
    like push()/pull_intents() — never-raise, result-object-always."""

    def push(self, record_path: Path) -> PushResult: ...

    def pull_intents(self) -> PullResult: ...

    def pull_artifacts(self) -> PullArtifactsResult: ...


@dataclass
class MisconfiguredExchangeAdapter:
    """Returned when config names a provider that cannot be resolved (TD-016).

    Distinct from `NoneExchangeAdapter` on purpose, and the distinction is the whole
    point: `None` means *"the user chose no vendor"* — a legitimate, deliberate state.
    This means *"the user chose a vendor and we could not honour it"* — a mistake that
    must be told to them.

    Falling back to `NoneExchangeAdapter` on a typo was the original behaviour and it was
    wrong: a config saying `"choice": "githbu"` would silently push nothing, look like a
    clean run, and leave the operator believing the integration was live. Mirrors the
    `llm_config.hocon` precedent, where `"class"` takes a short known name from a
    documented set — a wrong value there is an error, not a silent no-op.

    Still never raises. Every verb reports the same reason through the ordinary result
    object, so the failure travels the path callers already handle rather than
    interrupting a stage.
    """

    reason: str

    def push(self, record_path: Path) -> PushResult:
        return PushResult(success=False, detail=self.reason)

    def pull_intents(self) -> PullResult:
        return PullResult(success=False, intents=[], detail=self.reason)

    def pull_artifacts(self) -> PullArtifactsResult:
        return PullArtifactsResult(success=False, docs=[], detail=self.reason)


class NoneExchangeAdapter:
    """The D12 fallback: repo-local only, always succeeds, projects nothing externally.

    This is what `get_adapter()` returns when no exchange substrate is configured —
    not an error state, not a degraded mode, a fully legitimate choice (mirrors
    qa/adapter.py's NoneAdapter exactly).
    """

    def push(self, record_path: Path) -> PushResult:
        return PushResult(
            success=True,
            detail=(
                f"No exchange substrate configured — {record_path} was not projected "
                "anywhere (repo-local only, D12)."
            ),
        )

    def pull_intents(self) -> PullResult:
        return PullResult(success=True, intents=[])

    def pull_artifacts(self) -> PullArtifactsResult:
        return PullArtifactsResult(success=True, docs=[], detail="no substrate")
