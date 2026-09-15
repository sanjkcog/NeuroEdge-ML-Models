#!/usr/bin/env python3
"""sprint_state.py — cross-run sprint container (EP-08, D23, ADR-0005).

Mirrors gate_state.py's design exactly (ATOMIC_STATE_IO, SCHEMA_DRIVEN_VALIDATION):
temp-file + os.replace writes, schema-driven validation before construction, and a
load() that raises InvalidSprintState naming the offending field rather than letting a
corrupt file partially resume.

The one addition gate_state.py has no analog for is the `runs` accumulator: a sprint
spans many /agentforge runs (D23), and run.json is a single active-run file with no
archival (ADR-0005) — so this module is the durable record of what each enrolled run
has produced, refreshed on every PM-lane transition, not only once at the end.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("sprint_schema.json")
SCHEMA_VERSION = "1.0"


class InvalidSprintState(Exception):
    """sprint-NN.json is malformed or fails schema validation. Message names the field."""


class SprintNotOpen(Exception):
    """Enrolment/commitment attempted against a missing or closed sprint (US-08-02)."""


_KEY_RE = re.compile(r'"([^"\\]*)"\s*:')


def _last_key_before(text: str, pos: int) -> str | None:
    """The last JSON object key before byte offset `pos` — mirrors
    gate_state._last_key_before exactly, so a truncated sprint-NN.json names the last
    field it got through, not just "malformed JSON" (code-review LOW finding: this
    module's docstring claims to mirror gate_state.py's design "exactly"; this
    diagnostic was the one piece that had been left out)."""
    keys = [m.group(1) for m in _KEY_RE.finditer(text, 0, max(pos, 0))]
    return keys[-1] if keys else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fits_within_capacity(*, remaining: float, points: float) -> bool:
    """A story exactly filling remaining capacity is committed whole, never split
    (US-08-04 boundary AC) — the caller (sprint-planning skill) calls this before
    deciding whether to propose a split at the S5 gate."""
    return points <= remaining


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass
class CommittedItem:
    id: str
    points: float
    status: str = "committed"  # "committed" | "done"
    source_story: str | None = None


@dataclass
class RunSnapshot:
    last_stage: str
    updated_at: str
    tokens_in: int = 0
    tokens_out: int = 0
    api_calls: int = 0
    cost_usd: float = 0.0


@dataclass
class ClosureReport:
    delivered: list[str]
    carry_over: list[str]


@dataclass
class BurndownSnapshot:
    at: str
    remaining_points: float


# ---------------------------------------------------------------------------
# SprintState
# ---------------------------------------------------------------------------

@dataclass
class SprintState:
    sprint_id: str
    status: str = "open"  # "open" | "closed"
    opened_at: str = ""
    closed_at: str | None = None
    capacity_points: float = 0
    committed_items: list[CommittedItem] = field(default_factory=list)
    runs: dict[str, RunSnapshot] = field(default_factory=dict)
    burndown_snapshots: list[BurndownSnapshot] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION
    updated: str = ""

    @staticmethod
    def _schema_path() -> Path:
        return _SCHEMA_PATH

    @classmethod
    def open(cls, sprint_id: str, *, capacity_points: float) -> SprintState:
        return cls(sprint_id=sprint_id, status="open", opened_at=_now_iso(), capacity_points=capacity_points)

    def _require_open(self) -> None:
        if self.status != "open":
            raise SprintNotOpen(f"sprint {self.sprint_id!r} is {self.status!r}, cannot commit/enrol")

    def committed_points(self) -> float:
        return sum(item.points for item in self.committed_items)

    def remaining_capacity(self) -> float:
        return self.capacity_points - self.committed_points()

    def undelivered_points(self) -> float:
        """Committed minus delivered — the burn-down metric. Distinct from
        remaining_capacity() (capacity minus committed): a burn-down needs how much
        committed work is still outstanding, not how much headroom is left to commit
        more (skills/SDLC/pm/sprint-reporting.md's own Procedure step 2)."""
        delivered = sum(item.points for item in self.committed_items if item.status == "done")
        return self.committed_points() - delivered

    def record_burndown_snapshot(self) -> BurndownSnapshot:
        """Append a data point — never overwritten, unlike `runs` (US-08-06's chart
        needs history, not just the latest instant)."""
        snapshot = BurndownSnapshot(at=_now_iso(), remaining_points=self.undelivered_points())
        self.burndown_snapshots.append(snapshot)
        return snapshot

    def commit_item(self, item_id: str, *, points: float, source_story: str | None = None) -> CommittedItem:
        self._require_open()
        item = CommittedItem(id=item_id, points=points, source_story=source_story)
        self.committed_items.append(item)
        return item

    def split_story(self, story_id: str, *, points: float, first_points: float) -> tuple[CommittedItem, CommittedItem]:
        """Split a story exceeding remaining capacity into two committed items that
        each fit within one sprint (US-08-04), preserving the FR->EP->US chain via
        `source_story` on both halves. The split is proposed here; the caller (the
        sprint-planning skill) confirms it at the S5 gate before committing it —
        never applied silently (US-08-04's own AC)."""
        second_points = points - first_points
        if first_points <= 0 or second_points <= 0:
            raise ValueError(
                f"story {story_id!r} ({points} pts) is un-splittable at first_points="
                f"{first_points} — no task seam produces two positive halves"
            )
        first = CommittedItem(id=f"{story_id}a", points=first_points, source_story=story_id)
        second = CommittedItem(id=f"{story_id}b", points=second_points, source_story=story_id)
        return first, second

    def mark_done(self, item_id: str) -> None:
        for item in self.committed_items:
            if item.id == item_id:
                item.status = "done"
                return
        raise KeyError(f"no committed item {item_id!r} in sprint {self.sprint_id!r}")

    def record_run_snapshot(
        self, run_id: str, *, last_stage: str, tokens_in: int, tokens_out: int, api_calls: int, cost_usd: float
    ) -> RunSnapshot:
        """Fold a run's current cumulative usage into the container. Overwrites the
        prior entry for this run_id rather than appending — the caller passes the
        run's up-to-date total (read from run.json), so an interrupted run still
        contributes its partial usage on the next refresh (ADR-0005)."""
        snapshot = RunSnapshot(
            last_stage=last_stage, updated_at=_now_iso(),
            tokens_in=tokens_in, tokens_out=tokens_out, api_calls=api_calls, cost_usd=cost_usd,
        )
        self.runs[run_id] = snapshot
        return snapshot

    def merge_run_snapshot(
        self, path: str | Path, run_id: str, *,
        last_stage: str, tokens_in: int, tokens_out: int, api_calls: int, cost_usd: float,
    ) -> RunSnapshot:
        """Read-merge-write against `path` instead of trusting this instance's
        possibly-stale in-memory state (code-review CRITICAL finding: a sprint spans
        many concurrent /agentforge runs by design, D23, and a plain load-modify-save
        cycle silently drops a sibling run's snapshot if two refreshes race — whichever
        saves last wins with its own snapshot only, the other vanishes with no error).

        Re-reads the current on-disk `committed_items`/`status`/`capacity_points` too,
        not only `runs` — a concurrent /sprint-plan commitment must not be clobbered by
        a refresh() call that started before it landed. This narrows, but does not
        eliminate, the race window (a lock-free read-merge-write still has a TOCTOU gap
        between the re-read and the final os.replace) — a perfect fix needs OS-level
        file locking, out of scope here per this repo's no-new-dependency posture (D8).

        Also appends a burn-down snapshot (S16 sprint-close chart data) on every call — this is the
        PM-lane refresh() call site the S6-S12 graph extension reuses for that history,
        not a new cadence of its own.
        """
        path = Path(path)
        if path.is_file():
            on_disk = SprintState.load(path)
            self.runs = on_disk.runs
            self.committed_items = on_disk.committed_items
            self.status = on_disk.status
            self.capacity_points = on_disk.capacity_points
            self.closed_at = on_disk.closed_at
            self.burndown_snapshots = on_disk.burndown_snapshots
        snapshot = self.record_run_snapshot(
            run_id, last_stage=last_stage,
            tokens_in=tokens_in, tokens_out=tokens_out, api_calls=api_calls, cost_usd=cost_usd,
        )
        self.record_burndown_snapshot()
        self.save(path)
        return snapshot

    def total_usage(self) -> RunSnapshot:
        """Sum of every enrolled run's latest usage snapshot — /budget-report's AI
        runtime cost source (ADR-0005)."""
        return RunSnapshot(
            last_stage="",
            updated_at=_now_iso(),
            tokens_in=sum(s.tokens_in for s in self.runs.values()),
            tokens_out=sum(s.tokens_out for s in self.runs.values()),
            api_calls=sum(s.api_calls for s in self.runs.values()),
            cost_usd=sum(s.cost_usd for s in self.runs.values()),
        )

    def close(self) -> ClosureReport:
        """Delivered vs. carry-over, never dropped (US-08-07 failure case: unresolved
        in-progress items are carry-over, not marked delivered)."""
        delivered = [item.id for item in self.committed_items if item.status == "done"]
        carry_over = [item.id for item in self.committed_items if item.status != "done"]
        self.status = "closed"
        self.closed_at = _now_iso()
        return ClosureReport(delivered=delivered, carry_over=carry_over)

    def to_dict(self) -> dict:
        self.updated = _now_iso()
        return {
            "schema_version": self.schema_version,
            "updated": self.updated,
            "sprint_id": self.sprint_id,
            "status": self.status,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "capacity_points": self.capacity_points,
            "committed_items": [asdict(item) for item in self.committed_items],
            "runs": {run_id: asdict(snap) for run_id, snap in self.runs.items()},
            "burndown_snapshots": [asdict(snap) for snap in self.burndown_snapshots],
        }

    @classmethod
    def from_dict(cls, data: dict) -> SprintState:
        return cls(
            sprint_id=data["sprint_id"],
            status=data.get("status", "open"),
            opened_at=data.get("opened_at", ""),
            closed_at=data.get("closed_at"),
            capacity_points=data.get("capacity_points", 0),
            committed_items=[
                CommittedItem(
                    id=item.get("id", ""),
                    points=item.get("points", 0),
                    status=item.get("status", "committed"),
                    source_story=item.get("source_story"),
                )
                for item in data.get("committed_items", [])
            ],
            runs={
                run_id: RunSnapshot(
                    last_stage=snap.get("last_stage", ""),
                    updated_at=snap.get("updated_at", ""),
                    tokens_in=snap.get("tokens_in", 0),
                    tokens_out=snap.get("tokens_out", 0),
                    api_calls=snap.get("api_calls", 0),
                    cost_usd=snap.get("cost_usd", 0.0),
                )
                for run_id, snap in data.get("runs", {}).items()
            },
            burndown_snapshots=[
                BurndownSnapshot(
                    at=snap.get("at", ""),
                    remaining_points=snap.get("remaining_points", 0),
                )
                for snap in data.get("burndown_snapshots", [])
            ],
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            updated=data.get("updated", ""),
        )

    def save(self, path: str | Path) -> None:
        """Atomically persist — temp file + os.replace, mirrors gate_state.save."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> SprintState:
        """Reconstruct from sprint-NN.json alone. Raises InvalidSprintState naming
        the offending field on corruption, never a partial resume."""
        path = Path(path)
        raw = path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            near = _last_key_before(raw, exc.pos)
            where = f" (last field parsed: {near!r})" if near else ""
            raise InvalidSprintState(
                f"INVALID sprint.json: malformed JSON at line {exc.lineno} col {exc.colno}"
                f"{where}: {exc.msg}"
            ) from exc
        _validate(data)
        return cls.from_dict(data)


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(data: dict) -> None:
    """Reject a structurally-invalid sprint-NN.json, naming the first offending
    field — mirrors gate_state.py's per-field isinstance/enum rigor (code-review
    HIGH finding: this previously only checked top-level key PRESENCE, never type,
    so a wrong-shaped field passed validation and crashed from_dict() with a raw,
    unnamed exception instead of InvalidSprintState)."""
    if not isinstance(data, dict):
        raise InvalidSprintState("INVALID sprint.json: top-level value is not an object")
    schema = _load_schema()
    for key in schema.get("required", []):
        if key not in data:
            raise InvalidSprintState(f"INVALID sprint.json: missing required field {key!r}")

    status_enum = schema["properties"]["status"]["enum"]
    if data["status"] not in status_enum:
        raise InvalidSprintState(
            f"INVALID sprint.json: field 'status' has invalid value {data['status']!r}, "
            f"expected one of {status_enum}"
        )

    item_schema = schema["properties"]["committed_items"]["items"]
    item_required = item_schema["required"]
    if not isinstance(data["committed_items"], list):
        raise InvalidSprintState("INVALID sprint.json: field 'committed_items' must be an array")
    for i, item in enumerate(data["committed_items"]):
        if not isinstance(item, dict):
            raise InvalidSprintState(f"INVALID sprint.json: committed_items[{i}] must be an object")
        for key in item_required:
            if key not in item:
                raise InvalidSprintState(
                    f"INVALID sprint.json: committed_items[{i}] missing required field {key!r}"
                )
        item_status_enum = item_schema["properties"]["status"]["enum"]
        if item["status"] not in item_status_enum:
            raise InvalidSprintState(
                f"INVALID sprint.json: committed_items[{i}] field 'status' has invalid "
                f"value {item['status']!r}, expected one of {item_status_enum}"
            )

    run_schema = schema["properties"]["runs"]["additionalProperties"]
    run_required = run_schema["required"]
    if not isinstance(data["runs"], dict):
        raise InvalidSprintState("INVALID sprint.json: field 'runs' must be an object")
    for run_id, snapshot in data["runs"].items():
        if not isinstance(snapshot, dict):
            raise InvalidSprintState(f"INVALID sprint.json: runs[{run_id!r}] must be an object")
        for key in run_required:
            if key not in snapshot:
                raise InvalidSprintState(
                    f"INVALID sprint.json: runs[{run_id!r}] missing required field {key!r}"
                )

    # burndown_snapshots is optional (added without migration, ADR-0001) — validated for
    # shape only when present, never required.
    if "burndown_snapshots" in data:
        burndown_schema = schema["properties"]["burndown_snapshots"]["items"]
        burndown_required = burndown_schema["required"]
        if not isinstance(data["burndown_snapshots"], list):
            raise InvalidSprintState("INVALID sprint.json: field 'burndown_snapshots' must be an array")
        for i, snap in enumerate(data["burndown_snapshots"]):
            if not isinstance(snap, dict):
                raise InvalidSprintState(f"INVALID sprint.json: burndown_snapshots[{i}] must be an object")
            for key in burndown_required:
                if key not in snap:
                    raise InvalidSprintState(
                        f"INVALID sprint.json: burndown_snapshots[{i}] missing required field {key!r}"
                    )


def resolve_sprint(path: str | Path, *, require_open: bool = False) -> SprintState | None:
    """The single entry point for 'is there an active sprint here'. A missing file
    returns None — an explicit 'no active sprint' state, never an exception (US-08-02
    boundary case: the orchestrator prompts to open one rather than silently creating
    a single-feature sprint). Set require_open=True to enforce enrolment/commitment
    rules, which raise SprintNotOpen naming the actual status on a closed sprint or a
    missing one (US-08-02 failure case)."""
    path = Path(path)
    if not path.is_file():
        if require_open:
            raise SprintNotOpen(f"no sprint file at {path} — open one first")
        return None
    sprint = SprintState.load(path)
    if require_open and sprint.status != "open":
        raise SprintNotOpen(f"sprint {sprint.sprint_id!r} is {sprint.status!r}, cannot enrol")
    return sprint


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read and update a sprint-NN.json container.")
    parser.add_argument("--path", required=True, help="Path to sprint-NN.json")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_open = sub.add_parser("open", help="Open a new sprint container")
    p_open.add_argument("sprint_id")
    p_open.add_argument("--capacity", type=float, required=True, dest="capacity_points")

    sub.add_parser("status", help="Print sprint status and remaining capacity")
    sub.add_parser("close", help="Close the sprint, printing delivered vs. carry-over")

    args = parser.parse_args(argv)
    path = Path(args.path)

    if args.cmd == "open":
        sprint = SprintState.open(args.sprint_id, capacity_points=args.capacity_points)
        sprint.save(path)
        print(f"opened: {args.sprint_id} (capacity {args.capacity_points} pts)")
        return 0

    try:
        sprint = SprintState.load(path)
    except FileNotFoundError:
        print(f"No sprint at {path}.")
        return 1
    except InvalidSprintState as exc:
        print(exc)
        return 1

    if args.cmd == "close":
        report = sprint.close()
        sprint.save(path)
        print(f"delivered: {report.delivered}")
        print(f"carry_over: {report.carry_over}")
        return 0

    # status
    print(f"sprint_id:  {sprint.sprint_id}")
    print(f"status:     {sprint.status}")
    print(f"capacity:   {sprint.capacity_points}")
    print(f"committed:  {sprint.committed_points()}")
    print(f"remaining:  {sprint.remaining_capacity()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
