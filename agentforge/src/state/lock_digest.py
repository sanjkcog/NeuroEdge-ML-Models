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


def _normalised(raw: bytes) -> bytes:
    """The bytes with what is not content removed: a UTF-8 BOM, and CRLF folded to LF.

    The same commit checked out on Windows (core.autocrlf, CRLF) and on Linux/WSL (LF) must
    lock to the same hash; some Windows editors also prepend a BOM on save.
    """
    body = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw
    return body.replace(b"\r\n", b"\n")


def source_digest(raw: bytes) -> str:
    """sha256 of a use-case YAML, normalised, with trailing newlines stripped.

    The portal adds a final newline when it saves the spec, so a downloaded file differs from the
    working-tree copy by exactly that byte (ADR-0026 D-4). Locks built before D-4 stored a digest
    that kept trailing newlines; compare with :func:`source_matches`, never with ``==``.
    """
    return hashlib.sha256(_normalised(raw).rstrip(b"\n")).hexdigest()


def source_matches(raw: bytes, stored: str | None) -> bool:
    """True when ``raw`` is the use case a lock recorded as ``stored``, whatever newlines it ends in.

    ``stored`` may come from either algorithm: the current one, or the pre-D-4 one that hashed the
    normalised bytes as they were. For the old one, try the file with no final newline and with
    exactly one, so a lock built from either shape keeps verifying when the portal adds or drops that
    byte (code review, HIGH: a straight algorithm change invalidated every lock built from a file
    that ended in a newline).
    """
    if not stored:
        return False
    stripped = _normalised(raw).rstrip(b"\n")
    return stored in (
        hashlib.sha256(stripped).hexdigest(),
        hashlib.sha256(stripped + b"\n").hexdigest(),
    )
