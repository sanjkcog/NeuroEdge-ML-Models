#!/usr/bin/env python3
"""sources.py — GitLocalSource: the Git/local inbound ingestion driver (ADR-0012
Direction 2, FR-01, EP-02).

Implements the `pull_artifacts()` verb added to `exchange.adapter.ExchangeAdapter`
(never a fork — one Protocol, +1 method, M4). Reuses, never re-invents:

- `exchange.ledger.AppliedIntentLedger` for per-doc idempotency, keyed on
  `f"{source_id}:{locator}:{content_hash}"` — a changed file (new hash) at the same
  locator is a NEW doc; an unchanged file at a repeated pull is not (M6, TC-02-02-02).
- `exchange.config.ExchangeConfig.ingest_sources` for the fail-closed source
  allowlist — an unlisted source_id is REJECTED, never silently pulled
  (TC-02-02-03); a corrupt config loads as UNSET/empty (TC-02-02-04), which this
  module also refuses fail-closed.

RESULT-OBJECT-NEVER-RAISE (mirrors qa/adapter.py, exchange/git_adapter.py exactly):
every local-filesystem failure (missing root, permission error, an injected backend
failure) is caught here and reported as `PullArtifactsResult(success=False, ...)` —
no exception ever escapes `pull_artifacts()`.

Zero external auth by construction: this driver only ever touches the local
filesystem (`Path.rglob`), never a network call or credential — TC-02-02-01's "no
auth prompt/call" holds trivially, not merely by discipline.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from exchange.adapter import IngestedDoc, PullArtifactsResult
from exchange.config import ExchangeConfig
from exchange.ledger import AppliedIntentLedger

# Only text-like docs are ingested — a deliberately small, explicit allowlist rather
# than "every file", so a stray binary asset under the corpus root is silently
# skipped, not misread as UTF-8 and passed downstream as garbled "content".
_INGESTIBLE_SUFFIXES = (".md", ".txt", ".rst")


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class GitLocalSource:
    """A repo/local directory of docs, pulled with zero external auth.

    `root` is the local corpus directory; `ledger` is the caller-owned
    AppliedIntentLedger (reused, not forked) that makes a re-pull of an unchanged
    source idempotent at the per-doc granularity.
    """

    source_id: str
    root: Path
    ledger: AppliedIntentLedger

    def pull_artifacts(self) -> PullArtifactsResult:
        """Walk `self.root` for ingestible docs, skipping any already-applied
        (source_id, locator, content-hash) triple recorded in the ledger.

        Never raises: any OSError while walking/reading the tree (missing root, a
        permission error, an injected backend failure) is caught and reported as
        success=False with a non-empty detail — mirrors PullResult/PushResult's own
        never-raise contract for this exact reason (TC-02-01-01).
        """
        root = Path(self.root)
        try:
            if not root.is_dir():
                return PullArtifactsResult(
                    success=False, docs=[],
                    detail=f"GitLocalSource: root {root} is not a directory (or does not exist)",
                )
            paths = sorted(
                p for suffix in _INGESTIBLE_SUFFIXES for p in root.rglob(f"*{suffix}") if p.is_file()
            )
        except OSError as exc:
            return PullArtifactsResult(
                success=False, docs=[], detail=f"GitLocalSource: pull failed: {exc}"
            )

        docs: list[IngestedDoc] = []
        for path in paths:
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as exc:
                return PullArtifactsResult(
                    success=False, docs=[], detail=f"GitLocalSource: could not read {path}: {exc}"
                )
            locator = path.relative_to(root).as_posix()
            raw_id = f"{self.source_id}:{locator}:{_content_hash(content)}"
            if self.ledger.has_applied(raw_id):
                continue   # already ingested at this exact content — TC-02-02-02
            self.ledger.mark_applied(raw_id)
            docs.append(IngestedDoc(source_id=self.source_id, locator=locator, content=content))

        return PullArtifactsResult(
            success=True, docs=docs, detail=f"pulled {len(docs)} doc(s) from {root}"
        )

    @classmethod
    def pull_from_config(
        cls, *, source_id: str, config: ExchangeConfig, ledger: AppliedIntentLedger
    ) -> PullArtifactsResult:
        """Fail-closed entry point: refuses any `source_id` not present in
        `config.ingest_sources` — an unlisted source is REJECTED before any
        filesystem access is attempted (TC-02-02-03). A corrupt config (already
        normalised to `ingest_sources == {}` by ExchangeConfig.load's own tolerant
        load) rejects every source_id the same way — never a silent default
        (TC-02-02-04)."""
        root = config.ingest_sources.get(source_id)
        if root is None:
            return PullArtifactsResult(
                success=False, docs=[],
                detail=(
                    f"GitLocalSource: source_id {source_id!r} is not in the "
                    "ingest_sources allowlist — refused (fail-closed)"
                ),
            )
        return cls(source_id=source_id, root=Path(root), ledger=ledger).pull_artifacts()
