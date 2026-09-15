#!/usr/bin/env python3
"""exchange_record.py — the neutral manifest an external agentic app reads to monitor
an /agentforge run (ADR-0012 EP-01).

`build(run_state, gate_state)` composes an ExchangeRecord from the two authoritative
state objects (already loaded by the caller) — COMPOSE_AT_BOUNDARY_ONLY, mirroring
run_state._print_status's own run_state+gate_state composition. Neither `run_state` nor
`gate_state` is imported here, at module scope or otherwise: `build()` only reads
attributes it is handed (duck typing), so this module carries no dependency on either
state module at all — the one-directional boundary (exchange depends on state, state
never depends on exchange) holds trivially, not just by convention.

Everything else (atomic save, schema-driven validate/load naming the offending field)
mirrors run_state.py / gate_state.py exactly (ATOMIC_STATE_IO, SCHEMA_DRIVEN_VALIDATION).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("exchange_schema.json")
SCHEMA_VERSION = "1.0"


class InvalidExchangeRecord(Exception):
    """exchange.json is malformed or fails schema validation. Message names the field."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_KEY_RE = re.compile(r'"([^"\\]*)"\s*:')


def _last_key_before(text: str, pos: int) -> str | None:
    """The last JSON object key before byte offset `pos` — see run_state._last_key_before."""
    keys = [m.group(1) for m in _KEY_RE.finditer(text, 0, max(pos, 0))]
    return keys[-1] if keys else None


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(data: dict) -> None:
    """Reject a structurally-invalid exchange.json, naming the first offending field.

    Required lists/enums are read from exchange_schema.json so the schema stays the
    single source of truth, exactly as run_state._validate / gate_state._validate do.
    """
    if not isinstance(data, dict):
        raise InvalidExchangeRecord("INVALID exchange.json: top-level value is not an object")

    schema = _load_schema()
    for key in schema.get("required", []):
        if key not in data:
            raise InvalidExchangeRecord(f"INVALID exchange.json: missing required field {key!r}")

    if not isinstance(data.get("stages"), dict):
        raise InvalidExchangeRecord("INVALID exchange.json: field 'stages' must be an object")

    if not isinstance(data.get("gates"), list):
        raise InvalidExchangeRecord("INVALID exchange.json: field 'gates' must be an array")

    gate_schema = schema["properties"]["gates"]["items"]
    gate_required = gate_schema["required"]
    type_enum = gate_schema["properties"]["type"]["enum"]
    status_enum = gate_schema["properties"]["status"]["enum"]

    for i, gate in enumerate(data["gates"]):
        if not isinstance(gate, dict):
            raise InvalidExchangeRecord(f"INVALID exchange.json: gate #{i} must be an object")
        for key in gate_required:
            if key not in gate:
                raise InvalidExchangeRecord(
                    f"INVALID exchange.json: gate #{i} missing required field {key!r}"
                )
        if gate["type"] not in type_enum:
            raise InvalidExchangeRecord(
                f"INVALID exchange.json: gate #{i} field 'type' has invalid value "
                f"{gate['type']!r}, expected one of {type_enum}"
            )
        if gate["status"] not in status_enum:
            raise InvalidExchangeRecord(
                f"INVALID exchange.json: gate #{i} field 'status' has invalid value "
                f"{gate['status']!r}, expected one of {status_enum}"
            )

    if not isinstance(data.get("blocked_on"), list):
        raise InvalidExchangeRecord("INVALID exchange.json: field 'blocked_on' must be an array")

    if not isinstance(data.get("artifacts"), list):
        raise InvalidExchangeRecord("INVALID exchange.json: field 'artifacts' must be an array")


# ---------------------------------------------------------------------------
# ExchangeRecord
# ---------------------------------------------------------------------------

@dataclass
class ExchangeRecord:
    objective: str
    current_stage: str | None
    stages: dict[str, str]            # stage id -> status
    gates: list[dict]                 # {artifact, stage, type, status}
    blocked_on: list[str]             # artifacts with a pending HARD gate
    artifacts: list[str]              # all produced artifact paths, de-duplicated
    schema_version: str = SCHEMA_VERSION
    generated: str = ""               # ISO-8601, stamped by to_dict()

    def to_dict(self) -> dict:
        self.generated = _now_iso()
        return {
            "schema_version": self.schema_version,
            "generated": self.generated,
            "objective": self.objective,
            "current_stage": self.current_stage,
            "stages": dict(self.stages),
            "gates": [dict(g) for g in self.gates],
            "blocked_on": list(self.blocked_on),
            "artifacts": list(self.artifacts),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ExchangeRecord:
        return cls(
            objective=data["objective"],
            current_stage=data.get("current_stage"),
            stages=dict(data.get("stages", {})),
            gates=[dict(g) for g in data.get("gates", [])],
            blocked_on=list(data.get("blocked_on", [])),
            artifacts=list(data.get("artifacts", [])),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            generated=data.get("generated", ""),
        )

    def save(self, path: str | Path) -> None:
        """Atomically persist to `path` — temp file + os.replace, mirrors run_state.save."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> ExchangeRecord:
        """Reconstruct from exchange.json alone. Raises InvalidExchangeRecord naming
        the offending field on malformed/incomplete JSON — never partially loaded."""
        path = Path(path)
        raw = path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            near = _last_key_before(raw, exc.pos)
            where = f" (last field parsed: {near!r})" if near else ""
            raise InvalidExchangeRecord(
                f"INVALID exchange.json: malformed JSON at line {exc.lineno} col {exc.colno}"
                f"{where}: {exc.msg}"
            ) from exc
        _validate(data)
        return cls.from_dict(data)


def build(run_state, gate_state) -> ExchangeRecord:
    """Compose an ExchangeRecord from the authoritative RunState + GateState.

    Pure/compose only — no external IO, reads both inputs and never mutates either.
    `blocked_on` is exactly what drive.apply_intent's fence refuses to advance past:
    artifacts whose gate is pending AND type=="hard" (soft gates are advisory and never
    appear here, mirroring gate_state.any_pending's own soft-gate exclusion). Canonical
    FR-NN / artifact-path IDs pass through verbatim — no rendering, no re-formatting.
    """
    stages = {name: stage.status for name, stage in run_state.stages.items()}

    gates: list[dict] = []
    blocked_on: list[str] = []
    for artifact, gate in gate_state.gates.items():
        gates.append({
            "artifact": artifact,
            "stage": gate.stage,
            "type": gate.type,
            "status": gate.status,
        })
        if gate.status == "pending" and gate.type == "hard":
            blocked_on.append(artifact)

    artifacts: list[str] = []
    for stage in run_state.stages.values():
        for artifact_path in stage.artifacts:
            if artifact_path not in artifacts:
                artifacts.append(artifact_path)

    return ExchangeRecord(
        objective=run_state.objective,
        current_stage=run_state.current_stage,
        stages=stages,
        gates=gates,
        blocked_on=blocked_on,
        artifacts=artifacts,
    )
