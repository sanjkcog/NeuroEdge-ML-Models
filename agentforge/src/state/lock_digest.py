"""The one definition of how a use-case lock and its source YAML are hashed (NeuroEdge-Web ADR-0008).

Stdlib only, so `run_state.py` (run as a plain script) and `ml_contract/lock.py` share it instead
of each carrying a copy of the recipe that could drift apart.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def lock_digest(lock: dict[str, Any]) -> str:
    """sha256 of the lock's canonical JSON, excluding its own ``lock_sha256`` field."""
    body = {k: v for k, v in lock.items() if k != "lock_sha256"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def source_digest(raw: bytes) -> str:
    """sha256 of a use-case YAML with line endings normalised.

    The same commit checked out on Windows (core.autocrlf, CRLF) and on Linux/WSL (LF) must
    lock to the same hash; otherwise an identical use case looks "changed" across the
    Windows/WSL boundary this project works across.
    """
    # A UTF-8 BOM (added by some Windows editors on save) is not content either.
    body = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw
    return hashlib.sha256(body.replace(b"\r\n", b"\n")).hexdigest()
