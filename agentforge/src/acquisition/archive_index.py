"""Read a remote archive's index without transferring its payload (ADR-0024 D-1, D-5).

Every container format worth acquiring from carries a table of contents: ZIP has a central
directory at the end, tar has a header before each member. Reading that table costs kilobytes
and prices the whole archive -- which file types dominate, which logical units exist, what any
given selection would cost. On the reference run (KIT CNC, 44.58 GB) the entire acquisition
plan came from 64 KB of index.

This module emits one normalised row type regardless of format, so `fetch_plan` and the
per-modality selectors never learn what container they came from.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Callable, Iterable

# A fetcher is any callable (start, end_exclusive) -> bytes. Injected so this module is
# testable without a network and reusable over a local file (see `local_fetcher`).
Fetcher = Callable[[int, int], bytes]

EOCD_SIG = b"PK\x05\x06"
EOCD64_LOCATOR_SIG = b"PK\x06\x07"
EOCD64_SIG = b"PK\x06\x06"
CENTRAL_SIG = b"PK\x01\x02"
LOCAL_SIG = b"PK\x03\x04"

# ZIP stores 0xFFFFFFFF / 0xFFFF as "look in the zip64 extra field".
ZIP64_MARKER_32 = 0xFFFFFFFF
ZIP64_MARKER_16 = 0xFFFF

# The local header is 30 fixed bytes plus a filename and an extra field. An entry's payload
# therefore starts AFTER a variable-length run that the central directory does not record, so
# a span computed as `offset + compressed_size` is short by that run. See fetch_plan.HEADER_MARGIN.
LOCAL_HEADER_FIXED = 30


@dataclass(frozen=True)
class Entry:
    """One archive member, normalised across formats (ADR-0024 D-1).

    `offset` is where the member's *header* begins, not its data -- consumers that fetch a
    byte span must allow for the header (fetch_plan does).
    """

    path: str
    offset: int
    compressed: int
    uncompressed: int
    method: int          # 0 = stored, 8 = deflate
    crc: int | None = None   # ZIP CRC32 when present; enables free duplicate detection

    @property
    def is_dir(self) -> bool:
        return self.path.endswith("/")


def local_fetcher(path: str) -> Fetcher:
    """A Fetcher over a local file -- used by tests and by re-reading a cached archive."""

    def _fetch(start: int, end: int) -> bytes:
        with open(path, "rb") as fh:
            fh.seek(start)
            return fh.read(end - start)

    return _fetch


def _find_eocd(tail: bytes) -> int:
    """Offset of the EOCD record within `tail`, searching backwards and verifying each hit.

    The signature alone is not proof: the EOCD is followed by a variable-length comment, and
    a comment containing the four bytes `PK\\x05\\x06` produces a match at a *higher* offset
    than the real record — which a plain `rfind` would return. The declared comment length
    settles it: for the true record, the comment must run exactly to the end of the file.
    Without this check a crafted (or merely unlucky) comment redirects the entire index to
    arbitrary bytes and every offset downstream is wrong but plausible.
    """
    idx = tail.rfind(EOCD_SIG)
    while idx >= 0:
        if idx + 22 <= len(tail):
            comment_len = struct.unpack("<H", tail[idx + 20 : idx + 22])[0]
            if idx + 22 + comment_len == len(tail):
                return idx
        idx = tail.rfind(EOCD_SIG, 0, idx)
    raise ValueError(
        "no EOCD record found whose comment length reaches the end of the archive — "
        "not a ZIP, tail too short, or the trailer is corrupt"
    )


def read_zip_index(fetch: Fetcher, size: int, base: int = 0, tail_bytes: int = 400_000) -> list[Entry]:
    """Read a ZIP central directory via `fetch`, without reading any member's payload.

    `base` is the archive's own start offset inside a larger container (a ZIP nested in a
    tar); all returned offsets are relative to that base, matching the ZIP's internal view.
    """
    tail_len = min(tail_bytes, size)
    tail = fetch(base + size - tail_len, base + size)
    eocd = _find_eocd(tail)

    count = struct.unpack("<H", tail[eocd + 10 : eocd + 12])[0]
    cd_size = struct.unpack("<I", tail[eocd + 12 : eocd + 16])[0]
    cd_offset = struct.unpack("<I", tail[eocd + 16 : eocd + 20])[0]

    # ZIP64: the 32-bit fields saturate and the real values live in the ZIP64 EOCD, found
    # via a locator that sits immediately before the EOCD.
    if cd_offset == ZIP64_MARKER_32 or cd_size == ZIP64_MARKER_32 or count == ZIP64_MARKER_16:
        loc = tail.rfind(EOCD64_LOCATOR_SIG, 0, eocd)
        if loc < 0:
            raise ValueError("ZIP64 markers present but no ZIP64 EOCD locator found")
        eocd64_offset = struct.unpack("<Q", tail[loc + 8 : loc + 16])[0]
        head = fetch(base + eocd64_offset, base + eocd64_offset + 56)
        if head[:4] != EOCD64_SIG:
            raise ValueError("ZIP64 EOCD signature missing at the offset the locator gave")
        count = struct.unpack("<Q", head[32:40])[0]
        cd_size = struct.unpack("<Q", head[40:48])[0]
        cd_offset = struct.unpack("<Q", head[48:56])[0]

    cd = fetch(base + cd_offset, base + cd_offset + cd_size)
    return _parse_central_directory(cd, count)


def _parse_central_directory(cd: bytes, count: int) -> list[Entry]:
    entries: list[Entry] = []
    pos = 0
    for _ in range(count):
        if cd[pos : pos + 4] != CENTRAL_SIG:
            raise ValueError(f"central directory entry {len(entries)} lacks its signature")
        crc = struct.unpack("<I", cd[pos + 16 : pos + 20])[0]
        comp = struct.unpack("<I", cd[pos + 20 : pos + 24])[0]
        uncomp = struct.unpack("<I", cd[pos + 24 : pos + 28])[0]
        method = struct.unpack("<H", cd[pos + 10 : pos + 12])[0]
        name_len = struct.unpack("<H", cd[pos + 28 : pos + 30])[0]
        extra_len = struct.unpack("<H", cd[pos + 30 : pos + 32])[0]
        comment_len = struct.unpack("<H", cd[pos + 32 : pos + 34])[0]
        offset = struct.unpack("<I", cd[pos + 42 : pos + 46])[0]

        name = cd[pos + 46 : pos + 46 + name_len].decode("utf-8", "replace")
        extra = cd[pos + 46 + name_len : pos + 46 + name_len + extra_len]

        uncomp, comp, offset = _apply_zip64_extra(extra, uncomp, comp, offset)
        entries.append(Entry(name, offset, comp, uncomp, method, crc))
        pos += 46 + name_len + extra_len + comment_len
    return entries


def _apply_zip64_extra(extra: bytes, uncomp: int, comp: int, offset: int) -> tuple[int, int, int]:
    """Override saturated 32-bit fields from the ZIP64 extra field (0x0001).

    APPNOTE fixes the order -- uncompressed, compressed, local-header offset, disk -- and
    only the saturated fields are present, so they must be consumed in that order rather
    than read at fixed positions.
    """
    pos = 0
    while pos + 4 <= len(extra):
        tag, size = struct.unpack("<HH", extra[pos : pos + 4])
        body = extra[pos + 4 : pos + 4 + size]
        if tag == 0x0001:
            cur = 0
            if uncomp == ZIP64_MARKER_32 and cur + 8 <= len(body):
                uncomp = struct.unpack("<Q", body[cur : cur + 8])[0]
                cur += 8
            if comp == ZIP64_MARKER_32 and cur + 8 <= len(body):
                comp = struct.unpack("<Q", body[cur : cur + 8])[0]
                cur += 8
            if offset == ZIP64_MARKER_32 and cur + 8 <= len(body):
                offset = struct.unpack("<Q", body[cur : cur + 8])[0]
                cur += 8
            break
        pos += 4 + size

    # A sentinel that survived means the ZIP64 extra field was absent or too short to cover
    # it. Returning it would hand downstream a concrete-looking 4294967295 instead of a
    # failure, and that number would silently become an entry's size or offset.
    if ZIP64_MARKER_32 in (uncomp, comp, offset):
        raise ValueError(
            "ZIP64 sentinel left unresolved — the extra field is missing or truncated "
            f"(uncompressed={uncomp}, compressed={comp}, offset={offset})"
        )
    return uncomp, comp, offset


def parse_tar_size(field: bytes) -> int:
    """Decode a tar header size field: octal, or GNU base-256 for values >= 8 GB.

    An octal-only parser returns 0 for a large member instead of failing, which is how a
    44 GB payload silently reads as empty. The high bit of byte 0 marks base-256.
    """
    if field and field[0] & 0x80:
        value = field[0] & 0x7F
        for byte in field[1:]:
            value = (value << 8) | byte
        return value
    text = field.split(b"\0")[0].strip()
    return int(text, 8) if text else 0


def find_tar_member(fetch: Fetcher, name_suffix: str, search_bytes: int = 8 << 20) -> tuple[int, int]:
    """Locate a member inside an (uncompressed) tar by walking its headers.

    Returns `(data_offset, size)`. Used to find an archive nested in a distribution tar --
    e.g. BagIt, which wraps the real payload one level down.
    """
    head = fetch(0, search_bytes)
    pos = 0
    while pos + 512 <= len(head):
        block = head[pos : pos + 512]
        if block[:1] == b"\0":
            break
        name = block[0:100].split(b"\0")[0].decode("utf-8", "replace")
        size = parse_tar_size(block[124:136])
        data = pos + 512
        if name.endswith(name_suffix):
            return data, size
        pos = data + ((size + 511) // 512) * 512
    raise ValueError(f"no tar member ending in {name_suffix!r} within {search_bytes} bytes")


def write_manifest(entries: Iterable[Entry], path: str) -> int:
    """Persist the index as the D-1 artifact. Returns the row count written.

    Written as TSV because it is read far more often by eye and by one-off aggregation than
    by a parser, and paths may contain commas.
    """
    rows = 0
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("path\toffset\tcompressed\tuncompressed\tmethod\tcrc\n")
        for e in entries:
            crc = "" if e.crc is None else str(e.crc)
            fh.write(f"{e.path}\t{e.offset}\t{e.compressed}\t{e.uncompressed}\t{e.method}\t{crc}\n")
            rows += 1
    return rows


def read_manifest(path: str) -> list[Entry]:
    """Load a previously written manifest — re-scoping costs zero requests (ADR-0024 D-1)."""
    entries: list[Entry] = []
    with open(path, encoding="utf-8") as fh:
        header = fh.readline()
        if not header.startswith("path\t"):
            raise ValueError(f"{path} is not an archive manifest")
        for line in fh:
            if not line.strip():
                continue
            p, off, comp, uncomp, method, crc = line.rstrip("\n").split("\t")
            entries.append(
                Entry(p, int(off), int(comp), int(uncomp), int(method), int(crc) if crc else None)
            )
    return entries
