"""The unit of replay: a single Record emitted over a transport."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Record:
    """One thing the simulator emits.

    ``seq``     monotonically increasing emit index (0-based, across the whole run).
    ``ts``      emit timestamp (epoch seconds, set at send time).
    ``source``  the input file this record came from (basename).
    ``kind``    "timeseries" or "media".
    ``payload`` the actual data dict. For timeseries this is the row/object; for
                media it carries frame metadata plus either a ``uri`` (ref mode)
                or ``data_b64`` (base64 mode).
    """

    seq: int
    ts: float
    source: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def flatten(self, drop_blob: bool = True) -> dict[str, Any]:
        """Flat, CSV-friendly view — payload keys hoisted to the top level.

        The envelope (``seq``, ``emit_ts``, ``source``, ``kind``) stays
        authoritative: a payload that carries its own ``ts`` keeps it (the
        envelope's emit timestamp is named ``emit_ts`` precisely to avoid that
        very common collision), and any payload key that still clashes with an
        envelope name is kept under a ``payload_`` prefix rather than silently
        overwriting the envelope.

        With ``drop_blob`` a large ``data_b64`` value is replaced by its length in
        a ``data_b64_len`` column so a CSV row stays readable.
        """
        envelope: dict[str, Any] = {
            "seq": self.seq,
            "emit_ts": self.ts,
            "source": self.source,
            "kind": self.kind,
        }
        flat = dict(envelope)
        for key, value in self.payload.items():
            if drop_blob and key == "data_b64" and isinstance(value, str):
                flat["data_b64_len"] = len(value)
                continue
            out_key = f"payload_{key}" if key in envelope else key
            flat[out_key] = value
        return flat
