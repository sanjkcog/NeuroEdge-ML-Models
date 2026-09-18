"""Extract archive members from fetched byte spans (ADR-0024 D-5, D-7).

The counterpart to `fetch_plan`: given the bytes of a span and the entries it was planned to
contain, inflate each one and write it out. Every write is verified against the size the
index declared, because a span that is short by a few bytes truncates its last entry while
every other entry in it extracts perfectly -- a failure that is invisible without the check.

Member paths come from the archive and are therefore untrusted: a member named `../../etc/x`
would escape the destination if joined naively. `safe_destination` refuses that.
"""
from __future__ import annotations

import os
import zlib
from dataclasses import dataclass

from .archive_index import LOCAL_SIG, Entry

STORED = 0
DEFLATE = 8


class ExtractError(RuntimeError):
    """A member could not be extracted, or could not be vouched for once it was."""


class UnsafePath(ExtractError):
    """A member's path would escape the destination directory."""


class PartialExtract(ExtractError):
    """A span extracted some entries and then failed. Carries the ones that did land.

    Without this, a caller that treats a span as all-or-nothing loses credit for files
    genuinely on disk — and a driver deciding "did this pass make progress?" from that count
    can conclude nothing happened and stop early, with a report that is simply wrong.
    """

    def __init__(self, message: str, written: list["Extracted"]):
        super().__init__(message)
        self.written = written


@dataclass(frozen=True)
class Extracted:
    entry: Entry
    path: str
    bytes_written: int


def safe_destination(dest_root: str, member_path: str, strip_prefix: str = "") -> str:
    """Resolve a member's path under `dest_root`, refusing anything that escapes it.

    Archive member names are attacker-controlled in the general case. `os.path.normpath`
    collapses `..` segments, and the containment check is made on the *realpath* so that a
    symlinked destination cannot be used to sidestep it.
    """
    relative = member_path
    if strip_prefix and relative.startswith(strip_prefix):
        relative = relative[len(strip_prefix) :]
    relative = relative.replace("\\", "/").lstrip("/")

    root = os.path.realpath(dest_root)
    target = os.path.realpath(os.path.join(root, os.path.normpath(relative)))
    if target != root and not target.startswith(root + os.sep):
        raise UnsafePath(f"member {member_path!r} resolves outside the destination")
    return target


def _payload_offset(span: bytes, rel_header: int, entry: Entry) -> int:
    """Where a member's compressed payload starts, read from its local header.

    The central directory does not record the filename and extra-field lengths of the *local*
    header, so they must be read here rather than assumed — they differ from the central
    entry's own lengths.
    """
    header = span[rel_header : rel_header + 30]
    if len(header) < 30 or header[:4] != LOCAL_SIG:
        raise ExtractError(
            f"no local header for {entry.path!r} at span offset {rel_header} — "
            "the span is misaligned or too short"
        )
    name_len = int.from_bytes(header[26:28], "little")
    extra_len = int.from_bytes(header[28:30], "little")
    return rel_header + 30 + name_len + extra_len


def extract_entry(span: bytes, span_start: int, entry: Entry, dest_root: str,
                  strip_prefix: str = "", base: int = 0) -> Extracted:
    """Extract one member from an in-memory span. Raises rather than writing a partial file."""
    rel_header = base + entry.offset - span_start
    if rel_header < 0:
        raise ExtractError(f"{entry.path!r} starts before the span it was planned into")

    start = _payload_offset(span, rel_header, entry)
    raw = span[start : start + entry.compressed]
    if len(raw) != entry.compressed:
        raise ExtractError(
            f"{entry.path!r} needs {entry.compressed} B but the span holds {len(raw)} B — "
            "refusing to write a truncated member"
        )

    if entry.method == DEFLATE:
        try:
            data = zlib.decompressobj(-15).decompress(raw)
        except zlib.error as exc:
            # Not an ExtractError by inheritance, so it would otherwise escape a caller
            # written to survive one bad entry and take the whole transfer with it.
            raise ExtractError(f"{entry.path!r} failed to inflate: {exc}") from exc
    elif entry.method == STORED:
        data = raw
    else:
        raise ExtractError(f"{entry.path!r} uses unsupported compression method {entry.method}")

    if len(data) != entry.uncompressed:
        raise ExtractError(
            f"{entry.path!r} inflated to {len(data)} B, index declared {entry.uncompressed} B"
        )

    target = safe_destination(dest_root, entry.path, strip_prefix)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(data)
    except OSError as exc:
        # Disk full, permissions, a path the filesystem rejects — all survivable for one
        # entry, none an ExtractError unless said so.
        raise ExtractError(f"{entry.path!r} could not be written to {target}: {exc}") from exc
    return Extracted(entry=entry, path=target, bytes_written=len(data))


def extract_span(span: bytes, span_start: int, entries: tuple[Entry, ...], dest_root: str,
                 strip_prefix: str = "", base: int = 0) -> list[Extracted]:
    """Extract every member planned into one span, in order.

    On failure raises `PartialExtract` carrying the entries already written, so a caller can
    credit real progress instead of discarding the whole span.
    """
    written: list[Extracted] = []
    for entry in entries:
        try:
            written.append(extract_entry(span, span_start, entry, dest_root, strip_prefix, base))
        except ExtractError as exc:
            raise PartialExtract(str(exc), written) from exc
    return written


def is_complete(dest_root: str, entry: Entry, strip_prefix: str = "") -> bool:
    """Whether a member is already on disk at its declared size — the resume test (D-7)."""
    try:
        target = safe_destination(dest_root, entry.path, strip_prefix)
    except UnsafePath:
        return False
    return os.path.exists(target) and os.path.getsize(target) == entry.uncompressed
