"""Output writers — log what was emitted to ``sim_output/`` as JSON or CSV.

Formats:
  json  -> a single JSON array (buffered, written on close) — easy to re-load
  jsonl -> newline-delimited JSON, one record per line (streamed, append-safe)
  csv   -> flattened rows; base64 media blobs are replaced by a length column
  none  -> no output file (transport is the only sink)

All writers implement open() / write(record) / close().
"""

from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .record import Record


class Writer(ABC):
    def open(self) -> None:  # optional hook
        ...

    @abstractmethod
    def write(self, record: Record) -> None:
        ...

    def close(self) -> None:  # optional hook
        ...


class NullWriter(Writer):
    def write(self, record: Record) -> None:
        pass


class JsonlWriter(Writer):
    """Streams one JSON object per line — safe to tail, never needs buffering."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh: Any = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8", newline="\n")

    def write(self, record: Record) -> None:
        self._fh.write(json.dumps(record.to_dict(), ensure_ascii=False, default=str) + "\n")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()


class JsonArrayWriter(Writer):
    """Buffers records and writes a single JSON array on close."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._records: list[dict[str, Any]] = []

    def write(self, record: Record) -> None:
        self._records.append(record.to_dict())

    def close(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._records, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
            newline="\n",
        )


class CsvWriter(Writer):
    """Flattened CSV. The header is taken from the first record; later records
    that introduce new keys get them appended as trailing columns via a growing
    fieldname set (rewritten on close so every row lines up)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._rows: list[dict[str, Any]] = []
        self._fields: list[str] = []

    def write(self, record: Record) -> None:
        flat = record.flatten(drop_blob=True)
        for key in flat:
            if key not in self._fields:
                self._fields.append(key)
        self._rows.append(flat)

    def close(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=self._fields, extrasaction="ignore")
            writer.writeheader()
            for row in self._rows:
                writer.writerow(row)


def build_writer(output_format: str, path: Path) -> Writer:
    fmt = output_format.lower()
    if fmt == "none":
        return NullWriter()
    if fmt == "jsonl":
        return JsonlWriter(path)
    if fmt == "json":
        return JsonArrayWriter(path)
    if fmt == "csv":
        return CsvWriter(path)
    raise ValueError(f"unknown output format {output_format!r}")


def default_output_path(output_dir: Path, output_format: str) -> Path:
    ext = {"json": "json", "jsonl": "jsonl", "csv": "csv"}.get(output_format, "log")
    return output_dir / f"sent.{ext}"
