"""Turn a selection of archive entries into a costed fetch plan (ADR-0024 D-2, D-8, D-9).

This is the module that makes acquisition cheap, and it transfers nothing. Given the index
and a selector, it answers: what does each candidate scope cost in wire bytes, in disk bytes,
and in wall-clock -- before a payload byte moves. On the reference run every saving was found
here (88% redundant by file type, a further 56% out of scope), from a 64 KB index.

The merge threshold is derived, not guessed (D-8). Fetching N scattered entries as N requests
is wrong when the host throttles per request, and fetching one span across the whole archive
is wrong when most of it is unwanted. The crossover is where the wasted bytes in a gap cost
the same as one more throttled request:

    gap_threshold = transfer_rate x per_request_penalty

On the reference host (0.51 MB/s, ~90 s penalty) that is ~46 MB, against an empirically swept
optimum of 50-200 MB.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from .archive_index import LOCAL_HEADER_FIXED, Entry

# An entry's `offset` points at its local header; the payload begins after a filename and an
# extra field whose lengths the central directory does not record. A span ending at
# `offset + compressed` is therefore short by that run -- which truncates the LAST entry of
# every span, silently, while every other entry in the span extracts fine.
HEADER_MARGIN = 4096

Selector = Callable[[Entry], bool]


@dataclass(frozen=True)
class Span:
    """One contiguous byte range to fetch, and the entries it is expected to yield."""

    start: int
    end: int
    entries: tuple[Entry, ...]

    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def wanted_bytes(self) -> int:
        return sum(e.compressed for e in self.entries)

    @property
    def wasted_bytes(self) -> int:
        return max(self.length - self.wanted_bytes, 0)


@dataclass(frozen=True)
class Plan:
    """A costed fetch plan. `wire_bytes` and `disk_bytes` are separate budgets (D-9)."""

    spans: tuple[Span, ...]
    base: int = 0

    @property
    def wire_bytes(self) -> int:
        """What crosses the network, including bytes wasted inside merged gaps."""
        return sum(s.length for s in self.spans)

    @property
    def disk_bytes(self) -> int:
        """What lands on disk once inflated — a different constraint from wire_bytes."""
        return sum(e.uncompressed for s in self.spans for e in s.entries)

    @property
    def entry_count(self) -> int:
        return sum(len(s.entries) for s in self.spans)

    @property
    def request_count(self) -> int:
        return len(self.spans)

    def projected_seconds(self, rate_bytes_per_s: float, per_request_penalty_s: float) -> float:
        """Wall-clock estimate: transfer time plus the throttle penalty per request."""
        if rate_bytes_per_s <= 0:
            return float("inf")
        return self.wire_bytes / rate_bytes_per_s + self.request_count * per_request_penalty_s


def merge_threshold(rate_bytes_per_s: float, per_request_penalty_s: float) -> int:
    """The D-8 crossover: tolerate a gap only while it is cheaper than another request."""
    return int(max(rate_bytes_per_s, 0.0) * max(per_request_penalty_s, 0.0))


def build_plan(
    entries: Iterable[Entry],
    select: Selector,
    *,
    rate_bytes_per_s: float,
    per_request_penalty_s: float,
    base: int = 0,
    gap_bytes: int | None = None,
    limit: int | None = None,
) -> Plan:
    """Select entries, merge them into spans, and cost the result.

    `base` is the archive's offset inside an outer container; spans are returned as absolute
    positions ready to hand to a fetcher. `gap_bytes` overrides the derived threshold, for
    a caller who has measured something the formula cannot see.

    `limit` is the total size of the resource being fetched. Pass it whenever it is known:
    HEADER_MARGIN pushes the final span past the last byte, and a server answering such a
    range clamps it and returns FEWER bytes than asked for — which `ranged_fetch` correctly
    refuses as a short body. Clamping here keeps that strict check intact rather than
    loosening it, and without it the last span of a non-nested archive always fails.
    """
    chosen = sorted((e for e in entries if not e.is_dir and select(e)), key=lambda e: e.offset)
    if not chosen:
        return Plan(spans=(), base=base)

    tolerance = merge_threshold(rate_bytes_per_s, per_request_penalty_s) if gap_bytes is None else gap_bytes

    groups: list[list[Entry]] = [[chosen[0]]]
    reach = chosen[0].offset + chosen[0].compressed
    for entry in chosen[1:]:
        if entry.offset - reach <= tolerance:
            groups[-1].append(entry)
        else:
            groups.append([entry])
        reach = max(reach, entry.offset + entry.compressed)

    def _end(group: list[Entry]) -> int:
        # + HEADER_MARGIN so the last entry's local header and payload both fall inside.
        end = base + max(e.offset + e.compressed for e in group) + HEADER_MARGIN
        return min(end, limit) if limit is not None else end

    spans = tuple(
        Span(start=base + g[0].offset, end=_end(g), entries=tuple(g))
        for g in groups
    )
    return Plan(spans=spans, base=base)


def group_sizes(entries: Iterable[Entry], key: Callable[[Entry], str]) -> list[tuple[str, int, int]]:
    """Aggregate compressed bytes by an arbitrary key, largest first.

    The whole of D-2 rests on this being cheap: grouping by file type is what exposed that
    88% of the reference archive was a derivable duplicate, and grouping by logical unit is
    what exposed that 56% of the rest was out of scope. Neither needed a payload byte.

    Returns `(key, compressed_bytes, entry_count)`.
    """
    totals: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    for entry in entries:
        if entry.is_dir:
            continue
        k = key(entry)
        totals[k] += entry.compressed
        counts[k] += 1
    return [(k, totals[k], counts[k]) for k, _ in totals.most_common()]


def duplicate_groups(entries: Iterable[Entry]) -> list[tuple[int, list[Entry]]]:
    """Entries sharing a CRC and size — duplicates detectable with no payload fetched (D-1).

    Free deduplication: the index already carries the checksum, so identical members are
    knowable before deciding what to fetch. Most valuable where duplicated files are endemic,
    which in practice means image datasets.
    """
    buckets: dict[tuple[int, int], list[Entry]] = {}
    for entry in entries:
        if entry.is_dir or entry.crc is None:
            continue
        buckets.setdefault((entry.crc, entry.uncompressed), []).append(entry)
    return [(crc, group) for (crc, _), group in buckets.items() if len(group) > 1]


def pending(entries: Sequence[Entry], is_complete: Callable[[Entry], bool]) -> list[Entry]:
    """Drop entries already satisfied on disk — the basis of resume (D-7).

    A transfer that outlives its session resumes from what exists rather than replaying a
    transcript; the caller supplies the completeness test (normally: file present and its
    size equals `uncompressed`).
    """
    return [e for e in entries if not e.is_dir and not is_complete(e)]
