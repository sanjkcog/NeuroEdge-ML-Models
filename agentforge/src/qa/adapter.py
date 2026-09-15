#!/usr/bin/env python3
"""adapter.py — the pluggable test-management adapter protocol (EP-04, US-04-03).

Every adapter returns an explicit UploadResult rather than raising on failure — mirrors
the subprocess-result-checking discipline hardened in gate_state.py this session (never
assume an external call succeeded; never let a caller's control flow depend on catching
an adapter-specific exception type). D12: with no vendor configured or a vendor
unreachable, the repo-local matrix still renders and the run continues with a reported
upload failure — never an unhandled exception that aborts anything else.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class UploadResult:
    """The outcome of one upload attempt. Never an exception — always this."""
    success: bool
    detail: str = ""


class TestManagementAdapter(Protocol):
    """The pluggable interface every vendor (and the no-vendor fallback) implements.

    Deliberately a single method: uploading already-produced JUnit XML. Nothing here
    assumes a CLI or a network call exists — see NoneAdapter, the first-class fallback,
    not a stub to delete once a "real" adapter exists.
    """

    def upload_junit_xml(self, path: Path) -> UploadResult: ...


class NoneAdapter:
    """The D12/D16 fallback: repo-local only, always succeeds, uploads nothing.

    This is what `/test-plan --push` and `/trace-matrix` fall back to when no vendor is
    configured — not an error state, not a degraded mode, a fully legitimate choice.
    """

    def upload_junit_xml(self, path: Path) -> UploadResult:
        return UploadResult(
            success=True,
            detail=f"No vendor configured — {path} was not uploaded anywhere (repo-local only, D12).",
        )
