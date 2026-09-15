"""Coherence core for scenario runs (simulator-mvp Group B; design §3.1, D-3/D-6).

Three small services every adapter shares -- the reason a use case gets ONE simulator runtime
rather than per-protocol islands (design D-7):

  EntityStore  the one world model. Seeded from ``entities.csv``; captured writes are folded
               back in, so a record created through one hub's stub is visible to every later
               read in the run.
  RunLog       the ordered JSONL assertion surface. Every emitted event and received call lands
               here with a monotonic ``seq``; tests assert against this file, not against
               adapter internals.
  VirtualClock compression applies to inter-event gaps (design F-8). The in-flight floor --
               "no event released while a prior event's triggered agent run is still running" --
               needs a run-feedback channel the MVP does not have yet; until then compression is
               the only dial, stated here rather than silently absent.

``render`` is the shared templating: ``${seq}`` and ``${input.<field>}`` inside stub responses,
recursively over dicts/lists. Deliberately minimal -- the design's entity templating grows here
when a scenario needs it, not speculatively.
"""

from __future__ import annotations

import csv
import json
import threading
import time
from pathlib import Path
from typing import Any
from typing import Iterator
from typing import Optional


class EntityStore:
    """Named collections of records -- the scenario's single world model."""

    def __init__(self) -> None:
        self._collections: dict[str, list[dict]] = {}
        self._lock = threading.Lock()

    def load_entities_csv(self, path: Path, collection: str = "entities") -> int:
        """Seed a collection from a CSV (one record per row). Returns the row count."""
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
        with self._lock:
            self._collections.setdefault(collection, []).extend(rows)
        return len(rows)

    def add(self, collection: str, record: dict) -> None:
        """Fold one captured write back into the world (design D-4)."""
        with self._lock:
            self._collections.setdefault(collection, []).append(dict(record))

    def get(self, collection: str) -> list[dict]:
        """A snapshot copy -- callers can never mutate the store through a read."""
        with self._lock:
            return [dict(record) for record in self._collections.get(collection, [])]


class RunLog:
    """Ordered JSONL log of everything that crossed the seam. The assertion surface (O-4)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._seq = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Truncate: one file per run; a stale log asserting a previous run is worse than none.
        self.path.write_text("", encoding="utf-8")

    def append(self, kind: str, **fields: Any) -> int:
        """Write one entry; returns its seq. ``kind`` names what happened (emit/call/capture/
        unmatched/error), fields carry the specifics."""
        with self._lock:
            seq = self._seq
            self._seq += 1
            entry = {"seq": seq, "kind": kind, **fields}
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        return seq

    def entries(self) -> Iterator[dict]:
        """Parsed entries, in order -- the reader tests use."""
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)


class VirtualClock:
    """Compresses inter-event gaps: 1 real second = ``compression`` scenario seconds."""

    def __init__(self, compression: float = 1.0) -> None:
        if compression <= 0:
            raise ValueError("clock compression must be > 0")
        self.compression = compression
        self._start: Optional[float] = None

    def start(self) -> None:
        self._start = time.monotonic()

    def wait_until(self, offset_ms: float, stop: Optional[threading.Event] = None) -> bool:
        """Sleep until the scenario offset is due (compressed). Returns False if stopped early."""
        if self._start is None:
            self.start()
        due = self._start + (offset_ms / 1000.0) / self.compression
        while True:
            remaining = due - time.monotonic()
            if remaining <= 0:
                return True
            if stop is not None and stop.wait(min(remaining, 0.05)):
                return False
            if stop is None:
                time.sleep(min(remaining, 0.05))


def render(value: Any, *, seq: int, inputs: Optional[dict] = None) -> Any:
    """Recursively substitute ``${seq}`` / ``${input.<field>}`` in a stub template.

    A string that is *exactly* one placeholder keeps the substituted value's type
    (``"${seq}"`` becomes the integer, not ``"3"``); placeholders embedded in longer strings
    substitute textually. Unknown ``${...}`` shapes pass through untouched -- a stub author's
    literal ``${...}`` must not vanish silently.
    """
    if isinstance(value, dict):
        return {key: render(item, seq=seq, inputs=inputs) for key, item in value.items()}
    if isinstance(value, list):
        return [render(item, seq=seq, inputs=inputs) for item in value]
    if not isinstance(value, str):
        return value

    def _lookup(token: str) -> tuple[bool, Any]:
        if token == "seq":
            return True, seq
        if token.startswith("input.") and inputs is not None:
            field = token[len("input.") :]
            if field in inputs:
                return True, inputs[field]
        return False, None

    if value.startswith("${") and value.endswith("}") and value.count("${") == 1:
        known, resolved = _lookup(value[2:-1])
        return resolved if known else value

    out = value
    start = 0
    while True:
        begin = out.find("${", start)
        if begin < 0:
            return out
        end = out.find("}", begin)
        if end < 0:
            return out
        known, resolved = _lookup(out[begin + 2 : end])
        if known:
            out = out[:begin] + str(resolved) + out[end + 1 :]
            start = begin + len(str(resolved))
        else:
            start = end + 1
