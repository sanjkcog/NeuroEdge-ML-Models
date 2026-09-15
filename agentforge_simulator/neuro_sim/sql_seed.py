"""Seed a real SQLite database from bundle CSV sheets (Group B Task B4; design §3.2 SQL adapter).

No protocol faking: ``database.read_query`` (the P3 tool) opens SQLite read-only, so the honest
simulation is a real file with the scenario's data in it. Each CSV becomes one table named after
the file's stem; every column is TEXT unless every non-empty value parses as a number (SQLite's
affinity rules make this good enough for stub data, and it keeps the seeding dependency-free).
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path


def _column_type(values: list[str]) -> str:
    non_empty = [value for value in values if value != ""]
    if not non_empty:
        return "TEXT"
    try:
        for value in non_empty:
            float(value)
    except ValueError:
        return "TEXT"
    return "NUMERIC"


def seed_sqlite(seed_dir: Path, db_path: Path) -> dict[str, int]:
    """Build ``db_path`` from every ``*.csv`` in ``seed_dir``. Returns ``{table: row_count}``.

    Overwrites an existing file: a seed database is derived output, and a stale one asserting a
    previous scenario is worse than none.
    """
    seed_dir = Path(seed_dir)
    db_path = Path(db_path)
    sheets = sorted(seed_dir.glob("*.csv"))
    if not sheets:
        raise ValueError(f"no *.csv seed sheets in {seed_dir}")
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    conn = sqlite3.connect(db_path)
    try:
        for sheet in sheets:
            with sheet.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader, None)
                if not header:
                    raise ValueError(f"seed sheet {sheet.name} has no header row")
                rows = [row for row in reader if any(cell != "" for cell in row)]
            table = sheet.stem
            types = [_column_type([row[i] if i < len(row) else "" for row in rows]) for i in range(len(header))]
            columns = ", ".join(f'"{name}" {ctype}' for name, ctype in zip(header, types))
            conn.execute(f'CREATE TABLE "{table}" ({columns})')
            placeholders = ", ".join("?" for _ in header)
            normalized = [tuple(row[i] if i < len(row) else None for i in range(len(header))) for row in rows]
            conn.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', normalized)
            counts[table] = len(normalized)
        conn.commit()
    finally:
        conn.close()
    return counts
