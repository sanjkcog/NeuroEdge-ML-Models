#!/usr/bin/env python3
"""run_state.py — atomic, resumable state for one /agentforge run.

The orchestrator sequences three existing agents (researcher -> epic-writer ->
task-writer) and must survive interruption without a transcript (FR-02). Every stage
transition is written to run.json, and a run reconstructs from that file alone.

Design (ADR-0001):
  - A stage is written `in_progress` BEFORE its agent spawns and `complete` only AFTER
    the agent returns success, so an interrupted stage reads `in_progress` on resume and
    is re-run rather than skipped. Writing `complete` on entry is the invisible skip bug
    this ordering exists to prevent.
  - Writes are atomic: a temp file is `os.replace`d into place, so a crash mid-write
    leaves the previous valid file, never a truncated one.
  - A file that fails to parse or validate is rejected on load with the offending field
    named — never partially resumed.

Nothing here spawns an agent or asks the user: those are the main session's job (D1).
`run_sequence` drives the state machine with injected agent callables so the logic is
testable; in production the /agentforge command performs the real spawns and calls the
`init`/`start`/`complete`/`fail` CLI subcommands (or these same primitives) to record
each transition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

_SCHEMA_PATH = Path(__file__).with_name("run_schema.json")
SCHEMA_VERSION = "1.0"

# The full stage sequence S0->enablement, and the agent (or, for command-only stages
# with no owning agent, a descriptive marker) that owns each one. Zero new agent
# definitions beyond roles.plan.md's own 8 (AC-1) plus the reused reviewer/PM agents —
# every stage below spawns something that already existed before this extension.
#
# "test-plan"/"trace-matrix" (qa-engineer, EP-04), "sprint-plan"/"sprint-close"
# (project-manager, EP-08), and "test-run" (no owning agent, EP-05) are command-driven:
# the orchestrator invokes the standalone command directly rather than spawning a
# subagent, exactly as it already reads/writes docs.PRD.md via product-manager at S2 —
# same "one artifact, one skill, two entry points" relationship those commands'
# "Standalone vs. orchestrated" sections document.
#
# Order follows the canonical SDLC (docs/decisions/ADR-0008-canonical-sdlc-stages.md):
# linear through the backlog and sprint plan, then the Dev lane (architecture ->
# build) and the QA lane (test-plan -> automation -> run -> triage), converging on the
# overall traceability / release-readiness check, the PR review gate, then ship/deploy
# and close-out. ADR-0008 changes from the earlier graph:
#   * architecture moves out of a standalone up-front gated stage into the Dev lane
#     (after sprint-plan). ADR-0008 originally left it un-gated (review folded into
#     the PR review gate); ADR-0013 (Accepted) reverses that point: the S7 HLD and
#     LLD are EACH a hard gate, approved by a human architect, before build starts.
#     Hard-gated stages are S2 requirements, S5 sprint-plan, S6 test-plan, S7
#     architecture (HLD + LLD) and S13 review (the PR gate). This module holds no
#     gate list: the orchestrator opens each gate in gates.json (gate_state.py) per
#     commands/agentforge.md, and scripts/hooks/pre-write-hitl-gate.js enforces it.
#   * sprint-plan moves ahead of the Dev/QA work (planning precedes the fork).
#   * test-plan derives from the user stories (not architecture), so it can precede
#     the Dev build; its hard gate stays.
#   * trace-matrix becomes the convergence release-readiness check (after triage),
#     the point the PM confirms requirements <-> code <-> tests <-> results before
#     the PR review gate and deploy.
# run.json still advances a single linear cursor; the Dev/QA "lanes" are a role view
# (ADR-0008), realised here as a contiguous serialization the orchestrator walks.
STAGE_SEQUENCE: tuple[str, ...] = (
    "onboarding", "research", "requirements", "epics", "tasks",
    "sprint-plan",
    "test-plan",
    "architecture", "build",
    "test-automation", "test-run", "triage",
    "trace-matrix",
    "review",
    "ship",
    "deploy",
    "sprint-close",
    "enablement",
)
STAGE_AGENTS: dict[str, str] = {
    "onboarding": "legacy-modernizer",
    "research": "researcher",
    "requirements": "product-manager",
    "architecture": "architect",
    "epics": "epic-writer",
    "tasks": "task-writer",
    "test-plan": "qa-engineer",
    "trace-matrix": "qa-engineer",
    "sprint-plan": "project-manager",
    "build": "developer",
    "test-automation": "qa-automation-engineer",
    "test-run": "none (/test-run command — no owning agent, EP-05)",
    "triage": "test-triage",
    "review": "team-lead",
    "ship": "none (bookkeeping only — unblocked the instant the PR review gate is approved)",
    "deploy": "devops",
    "sprint-close": "project-manager",
    "enablement": "none (/product-doc, /marketing-video --technical-walkthrough)",
}

# The ML pipeline (ADR-0022 D-3/D-4) — `/agentforge-ml`'s stage graph, reusing this
# same state machine rather than a second module. M0 `destination` is the orchestrator
# resolving/confirming the model folder (ADR-0021); M7 `train` and M9 `return` are
# likewise orchestrator/external steps with no owning agent. Two agents cover the rest:
# `ml-data-engineer` (scout/verify/label/synth) and `ml-modeler` (model-select through
# model-card).
ML_STAGE_SEQUENCE: tuple[str, ...] = (
    "destination", "scout",
    # plan/download split out of verify (ADR-0024 D-3, D-12): planning is priced from the
    # archive's index and transfers nothing, transfer is long and resumable, and verify is
    # left free to profile and reach its gate instead of being starved by a download.
    "plan", "download",
    "verify", "label", "synth",
    "model-select", "model-build",
    "train",
    "eval",
    "return",
    # M12 (NeuroEdge-Web ADR-0008): simulator data exported from the same split data the
    # model was trained and evaluated on, stamped with the use-case lock of the returned model.
    "data-simulator",
    "model-card",
)
ML_STAGE_AGENTS: dict[str, str] = {
    "destination": "none (orchestrator — resolves the model folder, ADR-0021/0022)",
    "scout": "ml-data-engineer",
    "plan": "ml-data-engineer",
    "download": "none (orchestrator executes the fetch plan; resumable, budget-guarded)",
    "verify": "ml-data-engineer",
    "label": "ml-data-engineer",
    "synth": "ml-data-engineer",
    "model-select": "ml-modeler",
    "model-build": "ml-modeler",
    "train": "none (external — laptop GPU / AWS VM / portal; dependency-wait)",
    "eval": "none (orchestrator runs eval.py on the withheld test split)",
    "return": "none (POST upload-return-package to the portal)",
    "data-simulator": "none (orchestrator exports simulator data from the split data, ADR-0008)",
    "model-card": "ml-modeler",
}

# Registry of named stage sequences (ADR-0022 D-3): `run.json`'s "sequence" field
# selects one entry. "sdlc" is /agentforge's own STAGE_SEQUENCE/STAGE_AGENTS above,
# kept as module-level names so every existing importer (pm/refresh.py, tests) is
# unaffected. "ml" is /agentforge-ml's. One file, one schema field, no second state
# machine — every function below reads the sequence named by the state it is given,
# via _seq()/_agents(), rather than reaching for the module-level SDLC pair directly.
DEFAULT_SEQUENCE = "sdlc"
SEQUENCES: dict[str, tuple[tuple[str, ...], dict[str, str]]] = {
    "sdlc": (STAGE_SEQUENCE, STAGE_AGENTS),
    "ml": (ML_STAGE_SEQUENCE, ML_STAGE_AGENTS),
}


def _seq(sequence: str) -> tuple[str, ...]:
    """The ordered stage ids for `sequence`. Raises ValueError naming it, if unknown."""
    try:
        return SEQUENCES[sequence][0]
    except KeyError:
        raise ValueError(
            f"unknown sequence {sequence!r}, expected one of {sorted(SEQUENCES)}"
        ) from None


def _agents(sequence: str) -> dict[str, str]:
    """The stage -> agent mapping for `sequence`. Raises ValueError naming it, if unknown."""
    try:
        return SEQUENCES[sequence][1]
    except KeyError:
        raise ValueError(
            f"unknown sequence {sequence!r}, expected one of {sorted(SEQUENCES)}"
        ) from None


# Every stage id across every registered sequence, for the CLI's `choices=` (D-3): a
# subcommand accepts the union up front and validates against the loaded run's own
# sequence at runtime (see main()'s per-command checks below), because argparse choices
# are resolved before run.json is even read.
ALL_STAGE_IDS: tuple[str, ...] = tuple(
    dict.fromkeys(sid for seq, _ in SEQUENCES.values() for sid in seq)
)

# Escalate to the human after this many consecutive failed spawns on one stage.
MAX_CONSECUTIVE_FAILURES = 2

# Stages whose completion must assert a verdict, and the token that asserts it
# (TD-014). Only S12 trace-matrix qualifies today: it is the release-readiness
# convergence check, so "completed" and "converged" have to mean the same thing.
#
# Default-deny is deliberate. Rejecting the literal "PARTIAL" would be bypassed by
# rephrasing ("coverage incomplete for EP-02"), so silence fails closed instead.
# Scoped to this one stage on purpose — imposing a verdict vocabulary on `build`
# or `research` would break every existing caller for no benefit.
VERDICT_STAGES: dict[str, str] = {"trace-matrix": "PASS"}


def _asserts_verdict(artifact: str, required: str) -> bool:
    """True when `artifact` states the verdict, rather than merely containing its letters.

    The verdict must appear parenthesised — `qa/traceability.md (PASS)` — because a
    bare substring test is satisfied by accident: "PASS" is inside COMPASS, BYPASS,
    SURPASS, PASSWORD. A guard that a stray filename can satisfy is not the
    mechanical enforcement TD-014 needed, and this one exists precisely because the
    prose version was not enforceable (found in code review of this change).
    """
    return f"({required})" in artifact


class InvalidRunState(Exception):
    """run.json is malformed or fails schema validation. Message names the field."""


class RunExists(Exception):
    """A run.json already exists and overwrite was not authorised (Task 33)."""


class VerdictRequired(InvalidRunState):
    """A verdict-bearing stage was completed without asserting its verdict (TD-014).

    Raised only for stages in VERDICT_STAGES. S12 trace-matrix is the release-
    readiness convergence check, described as fail-loud — but nothing enforced that,
    so it was once closed with a "PARTIAL by design" artifact note and never re-run
    after the later EPICs landed. A stage that can complete partially stops being a
    gate, so a non-PASS completion is refused here rather than trusted to prose.

    Subclasses InvalidRunState so existing callers that catch that keep working.
    """


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

# Usage provenance (TD-018). The keystone of that entry: a figure must never be
# readable as a measurement unless it is one. `usage` numbers are supplied by the
# caller — this repo never observes tokens — so the ledger records WHERE each figure
# came from alongside the figure itself.
SOURCE_MEASURED = "measured"        # transcribed from a real reported usage figure
SOURCE_ESTIMATED = "estimated"      # derived by a stated method; never a bare guess
SOURCE_UNRECORDED = "unrecorded"    # no figure was available — NOT the same as zero
# Written only by the legacy loader for pre-TD-018 run.json files that carry figures
# but no provenance. Inferring "measured" for those would invent the very claim this
# field exists to stop being invented.
SOURCE_UNSPECIFIED = "unspecified"

VALID_SOURCES = frozenset({SOURCE_MEASURED, SOURCE_ESTIMATED, SOURCE_UNRECORDED})


@dataclass
class Usage:
    """Per-stage usage, with the provenance of the figures (TD-018).

    `source` defaults to `unrecorded` so silence is honest by construction: a stage
    completed without usage flags reports "no figure available", never a zero that
    reads as "this stage was free".
    """
    tokens_in: int = 0
    tokens_out: int = 0
    api_calls: int = 0
    cost_usd: float = 0.0
    source: str = SOURCE_UNRECORDED

    def __post_init__(self) -> None:
        """Figures without a stated provenance are `unspecified`, never `unrecorded`.

        Load-bearing, and found by an existing test rather than by design: every
        programmatic `Usage(tokens_in=..., cost_usd=...)` construction leaves `source`
        at its default, and `_accumulate_usage` skips anything not `is_reported()` —
        so without this the figures were SILENTLY DROPPED. That is precisely the
        defect class TD-018 exists to close, reintroduced by TD-018's own fix.

        `unspecified` rather than `measured`: the caller supplied numbers but said
        nothing about where they came from, and inventing that claim is the thing this
        field is for preventing.
        """
        if self.source == SOURCE_UNRECORDED and (
            self.tokens_in or self.tokens_out or self.api_calls or self.cost_usd
        ):
            self.source = SOURCE_UNSPECIFIED

    def is_reported(self) -> bool:
        """True when a figure was actually supplied (measured, estimated, or legacy)."""
        return self.source != SOURCE_UNRECORDED

    def plus(self, other: Usage) -> Usage:
        """Accumulated total of two passes over the same stage (TD-018 Problem 2).

        Provenance degrades to the weaker of the two: measured + estimated is an
        estimate, because part of the total is. An unrecorded operand contributes its
        (zero) figures but never upgrades the result's provenance.
        """
        if not self.is_reported():
            return Usage(other.tokens_in, other.tokens_out, other.api_calls,
                         other.cost_usd, other.source)
        if not other.is_reported():
            return Usage(self.tokens_in, self.tokens_out, self.api_calls,
                         self.cost_usd, self.source)
        merged = SOURCE_MEASURED
        for s in (self.source, other.source):
            if s != SOURCE_MEASURED:
                merged = SOURCE_ESTIMATED if s == SOURCE_ESTIMATED else SOURCE_UNSPECIFIED
        return Usage(
            tokens_in=self.tokens_in + other.tokens_in,
            tokens_out=self.tokens_out + other.tokens_out,
            api_calls=self.api_calls + other.api_calls,
            cost_usd=round(self.cost_usd + other.cost_usd, 6),
            source=merged,
        )


@dataclass
class Spawn:
    """One agent-spawn attempt on a stage."""
    spawned_by: str          # "orchestrator" | "human" | "external" (ADR-0012 EP-02, additive)
    at: str
    result: str              # "in_progress" | "complete" | "failed"
    identity: str = ""       # WHO proposed it (ADR-0012 US-02-02, additive, optional).
    # Independent of spawned_by (WHICH category): an inbound drive intent's identity is
    # stamped here verbatim for audit attribution, never trusted as an approval
    # credential. "" (default) preserves every pre-existing enter_stage() call site.


@dataclass
class StageState:
    agent: str
    status: str = "pending"  # pending | in_progress | complete | failed
    artifacts: list[str] = field(default_factory=list)
    consecutive_failures: int = 0
    spawns: list[Spawn] = field(default_factory=list)
    # `usage` is the CUMULATIVE total for this stage across every pass; each individual
    # pass is preserved in `usage_history` (TD-018 Problem 2 — reopen used to erase the
    # superseded pass's cost, mirroring the spawn history reopen_stage already keeps).
    usage: Usage = field(default_factory=Usage)
    usage_history: list[Usage] = field(default_factory=list)


@dataclass
class AgentOutcome:
    """What a (stubbed or real) agent spawn returns to the orchestrator."""
    status: str              # "complete" | "failed"
    artifacts: list[str] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _usage_from_dict(raw: dict) -> Usage:
    """Rebuild a Usage, inferring provenance for pre-TD-018 records.

    A legacy record carries figures but no `source`. It is loaded as `unspecified`
    rather than `measured`: those files genuinely do not say where their numbers came
    from, and asserting "measured" would manufacture the exact claim TD-018 exists to
    stop being manufactured. An all-zero legacy record is `unrecorded`, which is what
    it always meant.
    """
    if not isinstance(raw, dict):
        return Usage()
    tokens_in = raw.get("tokens_in", 0)
    tokens_out = raw.get("tokens_out", 0)
    api_calls = raw.get("api_calls", 0)
    cost_usd = raw.get("cost_usd", 0.0)
    source = raw.get("source")
    if source is None:
        has_figures = bool(tokens_in or tokens_out or api_calls or cost_usd)
        source = SOURCE_UNSPECIFIED if has_figures else SOURCE_UNRECORDED
    return Usage(tokens_in=tokens_in, tokens_out=tokens_out, api_calls=api_calls,
                 cost_usd=cost_usd, source=source)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_KEY_RE = re.compile(r'"([^"\\]*)"\s*:')


def _last_key_before(text: str, pos: int) -> str | None:
    """The last JSON object key that appears before byte offset `pos`.

    Lets a decode error on a truncated file name the field parsing reached rather than
    reporting only "invalid JSON", which tells an operator nothing (Task 27 GOTCHA).
    """
    keys = [m.group(1) for m in _KEY_RE.finditer(text, 0, max(pos, 0))]
    return keys[-1] if keys else None


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(data: dict) -> None:
    """Reject a structurally-invalid run.json, naming the first offending field.

    Required lists are read from run_schema.json so the schema stays the single source
    of truth — the validator cannot fall out of step with the documented shape.
    """
    if not isinstance(data, dict):
        raise InvalidRunState("INVALID run.json: top-level value is not an object")

    schema = _load_schema()
    for key in schema.get("required", []):
        if key not in data:
            raise InvalidRunState(f"INVALID run.json: missing required field {key!r}")

    gate = data.get("gate")
    if not isinstance(gate, dict):
        raise InvalidRunState("INVALID run.json: field 'gate' must be an object")
    for key in schema["properties"]["gate"]["required"]:
        if key not in gate:
            raise InvalidRunState(f"INVALID run.json: gate missing required field {key!r}")

    if not isinstance(data.get("stages"), dict):
        raise InvalidRunState("INVALID run.json: field 'stages' must be an object")

    # "sequence" (ADR-0022 D-3) is optional and defaults to "sdlc" so a pre-existing
    # run.json with no such key loads unchanged. An explicit value must still name a
    # registered sequence — an unknown one is rejected by name, same as any other
    # corrupt field, rather than surfacing as a KeyError inside _seq() below.
    sequence = data.get("sequence", DEFAULT_SEQUENCE)
    if sequence not in SEQUENCES:
        raise InvalidRunState(
            f"INVALID run.json: field 'sequence' has unknown value {sequence!r}, "
            f"expected one of {sorted(SEQUENCES)}"
        )

    # A run.json created under an OLDER, shorter stage sequence for its own "sequence"
    # (e.g. before roles.plan.md extended STAGE_SEQUENCE from 3 to 6 stages) loads this
    # far without incident, then crashes with a raw KeyError on the very next
    # transition — enter_stage/complete_stage/fail_stage all subscript state.stages[stage]
    # for every id in the CURRENT sequence, and complete_stage's all-complete scan
    # iterates it too. Reject it here instead, by name, matching this module's "never
    # partially resume a corrupt file" contract — a stage-set mismatch is exactly that,
    # even though the file is syntactically well-formed (code-review HIGH finding).
    loaded_stages = set(data["stages"])
    current_stages = set(_seq(sequence))
    if loaded_stages != current_stages:
        missing = current_stages - loaded_stages
        extra = loaded_stages - current_stages

        # A PURELY ADDITIVE change — the run knows a subset of today's stages and nothing
        # this sequence has never heard of — is sequence evolution, not corruption. ADR-0024
        # inserted `plan` and `download` into the ml sequence mid-flight, and a run already
        # past `scout` must survive that: stage ids are the contract, so gaining one is not
        # a reason to discard a run's history. Backfill the newcomers as pending, which is
        # what they would have been, and the KeyError this guard exists to prevent cannot
        # occur because every current id is now present.
        if missing and not extra:
            for sid in missing:
                # Serialised from StageState rather than hand-written, so a newcomer is
                # byte-for-byte what `new()` would have produced and cannot drift from the
                # schema as fields are added.
                data["stages"][sid] = asdict(StageState(agent=_agents(sequence)[sid]))

            # Re-point the cursor at the earliest outstanding stage — the same rule
            # `reopen_stage` had to learn. A newcomer can land BEFORE the recorded
            # current_stage (ADR-0024 inserted `plan`/`download` ahead of a run sitting at
            # `verify`), which would otherwise leave the cursor reporting a stage with
            # pending work in front of it. Every other path maintains the invariant that
            # current_stage implies everything earlier is complete; `status` and `resume`
            # read it verbatim, so breaking it here would have them announce `verify` while
            # the scope gate that must precede any transfer had never been asked (D-3a).
            order = _seq(sequence)
            outstanding = [s for s in order if data["stages"][s].get("status") != "complete"]
            data["current_stage"] = outstanding[0] if outstanding else None
        else:
            detail = []
            if missing:
                detail.append(f"missing {sorted(missing)}")
            if extra:
                detail.append(f"unexpected {sorted(extra)}")
            raise InvalidRunState(
                f"INVALID run.json: field 'stages' does not match the current {sequence!r} "
                f"sequence ({', '.join(detail)}) — this run.json was likely created under "
                "an older stage graph; start a new run rather than resuming this one"
            )

    stage_schema = schema["properties"]["stages"]["additionalProperties"]
    stage_required = stage_schema["required"]
    status_enum = stage_schema["properties"]["status"]["enum"]
    usage_required = stage_schema["properties"]["usage"]["required"]
    spawn_required = stage_schema["properties"]["spawns"]["items"]["required"]
    spawned_by_enum = stage_schema["properties"]["spawns"]["items"]["properties"]["spawned_by"]["enum"]
    result_enum = stage_schema["properties"]["spawns"]["items"]["properties"]["result"]["enum"]

    for name, stage in data["stages"].items():
        if not isinstance(stage, dict):
            raise InvalidRunState(f"INVALID run.json: stage {name!r} must be an object")
        for key in stage_required:
            if key not in stage:
                raise InvalidRunState(
                    f"INVALID run.json: stage {name!r} missing required field {key!r}"
                )
        # Enum checks matter as much as presence checks: run_sequence's skip-on-complete
        # logic and complete_stage's all-complete check both key off status directly, so
        # a corrupted value (e.g. a typo'd "compelete") would silently defeat both
        # without this — the same class of fail-open bug gate_state.py was hardened
        # against this session (ported here per third-round code review).
        if stage["status"] not in status_enum:
            raise InvalidRunState(
                f"INVALID run.json: stage {name!r} field 'status' has invalid value "
                f"{stage['status']!r}, expected one of {status_enum}"
            )
        usage = stage.get("usage")
        if not isinstance(usage, dict):
            raise InvalidRunState(
                f"INVALID run.json: stage {name!r} field 'usage' must be an object"
            )
        for key in usage_required:
            if key not in usage:
                raise InvalidRunState(
                    f"INVALID run.json: stage {name!r} usage missing required field {key!r}"
                )
        # Spawns are reconstructed field-by-field below, but validate them here so a
        # missing field is reported as a named InvalidRunState rather than surfacing as
        # a raw TypeError deep inside from_dict — the load contract is that a corrupt
        # file is rejected with the offending field named, never partially resumed.
        spawns = stage.get("spawns")
        if not isinstance(spawns, list):
            raise InvalidRunState(
                f"INVALID run.json: stage {name!r} field 'spawns' must be an array"
            )
        for i, spawn in enumerate(spawns):
            if not isinstance(spawn, dict):
                raise InvalidRunState(
                    f"INVALID run.json: stage {name!r} spawn #{i} must be an object"
                )
            for key in spawn_required:
                if key not in spawn:
                    raise InvalidRunState(
                        f"INVALID run.json: stage {name!r} spawn #{i} missing required field {key!r}"
                    )
            if spawn["spawned_by"] not in spawned_by_enum:
                raise InvalidRunState(
                    f"INVALID run.json: stage {name!r} spawn #{i} field 'spawned_by' "
                    f"has invalid value {spawn['spawned_by']!r}, expected one of "
                    f"{spawned_by_enum}"
                )
            if spawn["result"] not in result_enum:
                raise InvalidRunState(
                    f"INVALID run.json: stage {name!r} spawn #{i} field 'result' has "
                    f"invalid value {spawn['result']!r}, expected one of {result_enum}"
                )


# ---------------------------------------------------------------------------
# RunState
# ---------------------------------------------------------------------------

@dataclass
class RunState:
    objective: str
    stages: dict[str, StageState]
    current_stage: str | None = None
    completed_stages: list[str] = field(default_factory=list)
    gate: dict = field(default_factory=lambda: {"pending": False, "stage": None, "reason": None})
    escalation: dict | None = None
    sprint_id: str | None = None
    schema_version: str = SCHEMA_VERSION
    created: str = ""
    updated: str = ""
    # ADR-0022 D-3: which named stage sequence this run walks — "sdlc" (/agentforge,
    # STAGE_SEQUENCE/STAGE_AGENTS) or "ml" (/agentforge-ml, ML_STAGE_SEQUENCE/
    # ML_STAGE_AGENTS). Defaults to "sdlc" so a pre-existing run.json with no such key
    # loads unchanged.
    sequence: str = DEFAULT_SEQUENCE
    # NeuroEdge-Web ADR-0008 L-1 (ml sequence): the use-case lock this run was built on --
    # {"path", "lock_sha256", "use_case_id"}. None for runs that predate it, and for sdlc runs.
    use_case_lock: dict | None = None

    def enrol_sprint(self, sprint_id: str) -> None:
        """Set at S5 enrolment (D23) — the run.json-side pointer to its cross-run
        sprint container (ADR-0005). Persisted on the next save() like any other field."""
        self.sprint_id = sprint_id

    @classmethod
    def new(cls, objective: str, sequence: str = DEFAULT_SEQUENCE) -> RunState:
        now = _now_iso()
        seq, agents = _seq(sequence), _agents(sequence)
        stages = {sid: StageState(agent=agents[sid]) for sid in seq}
        return cls(
            objective=objective,
            stages=stages,
            current_stage=seq[0],
            created=now,
            updated=now,
            sequence=sequence,
        )

    def to_dict(self) -> dict:
        self.updated = _now_iso()
        return {
            "schema_version": self.schema_version,
            "objective": self.objective,
            "created": self.created,
            "updated": self.updated,
            "current_stage": self.current_stage,
            "completed_stages": list(self.completed_stages),
            "escalation": self.escalation,
            "sprint_id": self.sprint_id,
            "sequence": self.sequence,
            "gate": self.gate,
            **({"use_case_lock": self.use_case_lock} if self.use_case_lock else {}),
            "stages": {
                name: {
                    "agent": st.agent,
                    "status": st.status,
                    "artifacts": list(st.artifacts),
                    "consecutive_failures": st.consecutive_failures,
                    "spawns": [asdict(s) for s in st.spawns],
                    "usage": asdict(st.usage),
                    "usage_history": [asdict(u) for u in st.usage_history],
                }
                for name, st in self.stages.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> RunState:
        stages: dict[str, StageState] = {}
        for name, st in data["stages"].items():
            stages[name] = StageState(
                agent=st.get("agent", ""),
                status=st.get("status", "pending"),
                artifacts=list(st.get("artifacts", [])),
                consecutive_failures=int(st.get("consecutive_failures", 0)),
                # Built field-by-field rather than Spawn(**s)/Usage(**s): a **-splat
                # raises TypeError on any unexpected key (e.g. a field added by a newer
                # schema), which would escape load()'s InvalidRunState contract. Missing
                # required fields are already rejected by _validate before we get here.
                spawns=[
                    Spawn(
                        spawned_by=s.get("spawned_by", ""),
                        at=s.get("at", ""),
                        result=s.get("result", ""),
                        identity=s.get("identity", ""),
                    )
                    for s in st.get("spawns", [])
                ],
                usage=_usage_from_dict(st.get("usage", {})),
                usage_history=[_usage_from_dict(u) for u in st.get("usage_history", [])],
            )
        return cls(
            objective=data["objective"],
            stages=stages,
            current_stage=data.get("current_stage"),
            completed_stages=list(data.get("completed_stages", [])),
            gate=data.get("gate", {"pending": False, "stage": None, "reason": None}),
            escalation=data.get("escalation"),
            sprint_id=data.get("sprint_id"),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            created=data.get("created", ""),
            updated=data.get("updated", ""),
            sequence=data.get("sequence", DEFAULT_SEQUENCE),
            use_case_lock=data.get("use_case_lock"),
        )

    def save(self, path: str | Path) -> None:
        """Atomically persist to `path`.

        Written to a sibling temp file then `os.replace`d in — atomic on both Windows
        and POSIX — so a crash mid-write can never leave a truncated run.json. Matches
        install.py's encoding/newline convention so the file is byte-stable across
        platforms.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> RunState:
        """Reconstruct a run from run.json alone — no transcript (FR-02).

        Raises InvalidRunState (naming the field) on malformed or incomplete JSON so a
        corrupt file is never partially resumed.
        """
        path = Path(path)
        raw = path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            near = _last_key_before(raw, exc.pos)
            where = f" (last field parsed: {near!r})" if near else ""
            raise InvalidRunState(
                f"INVALID run.json: malformed JSON at line {exc.lineno} col {exc.colno}"
                f"{where}: {exc.msg}"
            ) from exc
        _validate(data)
        return cls.from_dict(data)


# ---------------------------------------------------------------------------
# Transition primitives — shared by run_sequence and the CLI
# ---------------------------------------------------------------------------

def create_run(
    path: str | Path,
    objective: str,
    *,
    overwrite: bool = False,
    start_stage: str | None = None,
    sequence: str = DEFAULT_SEQUENCE,
) -> RunState:
    """Create a fresh run.json. Refuses to clobber an existing one unless authorised.

    The refusal is the testable core of Task 33: the /agentforge command asks the user
    via AskUserQuestion (main session only, D1) and passes overwrite=True only if they
    accept. A decline leaves the existing file byte-identical.

    `sequence` (ADR-0022 D-3) selects the named stage graph this run walks — "sdlc"
    (default, /agentforge) or "ml" (/agentforge-ml).

    `start_stage` (EP-07, ADR-0006, `--stage` on /agentforge) lets a run join the
    pipeline past stage 0 — a user who already has neuroedge/docs/PRD.md by hand shouldn't have
    the orchestrator redo S1/S2. Every stage entry (in `sequence`) before `start_stage`
    is marked complete with a note that it was supplied outside this run, never
    fabricated as if /agentforge produced it. Requires no change to run_sequence: its
    own `if status == "complete": continue` (already in the loop) does the rest.
    """
    seq = _seq(sequence)
    if start_stage is not None and start_stage not in seq:
        raise ValueError(
            f"unknown start_stage {start_stage!r} for sequence {sequence!r}, expected "
            f"one of {seq}"
        )
    path = Path(path)
    if path.exists() and not overwrite:
        raise RunExists(f"run.json already exists at {path}; refusing to overwrite")
    state = RunState.new(objective, sequence=sequence)
    if start_stage is not None:
        idx = seq.index(start_stage)
        for sid in seq[:idx]:
            # enforce_verdict=False: this records provenance ("supplied outside this
            # run"), not a verdict. Demanding a PASS here would break --start-stage
            # for any stage after trace-matrix (review/ship/deploy/…), or force this
            # backfill to fabricate a convergence result that never happened.
            complete_stage(
                state, sid,
                AgentOutcome("complete", ["(supplied outside this run — not produced by /agentforge)"]),
                enforce_verdict=False,
            )
        state.current_stage = start_stage
    state.save(path)
    return state


def enter_stage(
    state: RunState, stage: str, *, spawned_by: str = "orchestrator", identity: str = ""
) -> StageState:
    """Mark a stage in_progress and record the spawn attempt. Persist BEFORE spawning.

    `identity` (ADR-0012 US-02-02, additive, optional) records WHO proposed this spawn
    — independent of `spawned_by` (WHICH category). Defaults to "" so every existing
    call site (orchestrator/human spawns) keeps working unchanged.
    """
    st = state.stages[stage]
    state.current_stage = stage
    st.status = "in_progress"
    st.spawns.append(Spawn(spawned_by=spawned_by, at=_now_iso(), result="in_progress", identity=identity))
    return st


def complete_stage(
    state: RunState,
    stage: str,
    outcome: AgentOutcome,
    *,
    enforce_verdict: bool = True,
) -> StageState:
    """Record a successful stage: artifacts, usage, reset failure counter, advance cursor.

    Raises VerdictRequired if `stage` is a VERDICT_STAGES member and no artifact
    asserts the required verdict (TD-014). The stage is left untouched in that case
    — a refused completion must not half-close it.

    `enforce_verdict=False` is for completions that record a stage as *supplied
    outside this run* rather than produced by it (create_run's --start-stage
    backfill). Those artifacts assert provenance, not a verdict, so demanding a
    PASS from them would either break --start-stage or force the backfill to
    fabricate a convergence result that never happened. Skipping a gate via
    --start-stage is an existing, documented property of that flag, not a hole
    this opens.
    """
    required = VERDICT_STAGES.get(stage) if enforce_verdict else None
    if required is not None and not any(_asserts_verdict(a, required) for a in outcome.artifacts):
        raise VerdictRequired(
            f"stage {stage!r} may only be completed on an explicit ({required}) verdict; "
            f"got artifacts {list(outcome.artifacts)!r}. A partial or absent verdict "
            f"leaves the stage open — re-run it once the outstanding work has landed "
            f"(see `reopen` if it was completed earlier in this run)."
        )

    st = state.stages[stage]
    st.status = "complete"
    st.artifacts = list(outcome.artifacts)
    # ACCUMULATE, never overwrite (TD-018 Problem 2). A straight assignment here erased
    # the superseded pass's cost on every reopen -> re-complete cycle: 240,000 tokens
    # recorded, reopened, re-completed with 18,000, and the rollup then reported 18,000.
    # reopen_stage already preserves the *spawn* trail for exactly this reason; the cost
    # trail is preserved the same way, and `usage` stays the cumulative figure the
    # rollup sums.
    _accumulate_usage(st, outcome.usage)
    st.consecutive_failures = 0
    if st.spawns:
        st.spawns[-1].result = "complete"
    if stage not in state.completed_stages:
        state.completed_stages.append(stage)
    # If this stage had escalated (failed twice) and now recovered on a resumed run,
    # clear the stale escalation and gate — otherwise a run that a human fixed and
    # re-ran would still report itself halted forever.
    if state.escalation and state.escalation.get("stage") == stage:
        state.escalation = None
        state.gate = {"pending": False, "stage": None, "reason": None}
    # Null the cursor once every stage is done, so a finished run reads current_stage
    # == null however it was driven (CLI transitions or run_sequence). ADR-0001 defines
    # current_stage as null when the run is complete.
    if all(state.stages[sid].status == "complete" for sid in _seq(state.sequence)):
        state.current_stage = None
    return st


def _accumulate_usage(st: StageState, new: Usage) -> None:
    """Fold `new` into the stage's cumulative usage, preserving each pass.

    A first report simply becomes the total. A subsequent one (a re-completion after
    `reopen`, or a retry after `fail`) is ADDED, with the prior total pushed onto
    `usage_history` so the individual passes stay auditable rather than being replaced.
    An unrecorded report is a no-op: it must not append an empty pass to the history.
    """
    if not new.is_reported():
        return
    if st.usage.is_reported():
        st.usage_history.append(st.usage)
    st.usage = st.usage.plus(new)


def reopen_stage(state: RunState, stage: str) -> StageState:
    """Re-arm a completed stage so `run_sequence` will execute it again (TD-014).

    Deliberately mirrors `gate_state.reopen_gate`, including its central rule: the
    audit trail survives. `spawns` is left intact, so a reopened stage still shows
    that it ran earlier and was superseded — that history is exactly what was
    missing when a stale S12 verdict went unnoticed for five EPICs.

    Why this has to exist: `run_sequence` skips any stage whose status is
    "complete", and nothing else can undo that. Without it, a convergence check
    completed early can never be refreshed once later work lands, so the only
    recourse was hand-editing run.json — which is what the state machine exists to
    make unnecessary.

    Raises KeyError for an unknown stage, matching this module's other stage
    lookups (a typo must fail loudly rather than silently no-op).
    """
    st = state.stages[stage]
    st.status = "pending"
    st.consecutive_failures = 0
    while stage in state.completed_stages:
        state.completed_stages.remove(stage)

    # Re-point the cursor at the earliest stage that is now outstanding. Two cases
    # matter and an earlier version of this only handled the first:
    #   - the run had finished, so current_stage was None;
    #   - the run had moved *past* this stage — which is the actual TD-014 shape,
    #     where S12 went stale while S13+ carried on. Leaving the cursor at, say,
    #     "deploy" made `status` and `resume` report a stage the operator had just
    #     reopened work in front of (found in code review of this change).
    outstanding = [s for s in _seq(state.sequence) if state.stages[s].status != "complete"]
    state.current_stage = outstanding[0] if outstanding else None
    return st


def fail_stage(state: RunState, stage: str, usage: Usage | None = None) -> bool:
    """Record a failed spawn. Return True when this failure triggers escalation.

    Counts *consecutive* failures per stage (reset on success in complete_stage) so two
    unrelated failures across different stages do not escalate spuriously (Task 32).

    `usage` (TD-018 Problem 1) records what the failed attempt actually cost. Before
    this, usage could only attach at `complete`, so every token spent on a stage that
    failed — or failed twice and escalated — was structurally unrecordable, and failed
    spawns are frequently the expensive ones. Accumulates exactly as a completion does,
    so a fail-then-retry-then-complete sequence sums all three passes.
    """
    st = state.stages[stage]
    st.status = "failed"
    if usage is not None:
        _accumulate_usage(st, usage)
    st.consecutive_failures += 1
    if st.spawns:
        st.spawns[-1].result = "failed"
    if st.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        state.escalation = {
            "stage": stage,
            "reason": f"{st.consecutive_failures} consecutive agent failures",
            "at": _now_iso(),
        }
        state.gate = {
            "pending": True,
            "stage": stage,
            "reason": "escalated to human after repeated failure",
        }
        return True
    return False


def plan_sequence(state: RunState) -> list[tuple[str, str]]:
    """Pure preview — the (stage_id, agent) pairs `run_sequence` would still run,
    in order, with zero I/O and zero side effects (EP-07, ADR-0006, `--dry-run` on
    /agentforge). Mirrors run_sequence's own `if status == "complete": continue`
    filter exactly, so the preview can never drift from what a real run would do."""
    agents = _agents(state.sequence)
    return [
        (stage, agents[stage])
        for stage in _seq(state.sequence)
        if state.stages[stage].status != "complete"
    ]


def manual_invocation_count(state: RunState) -> int:
    """Spawns not initiated by the orchestrator — the 'manual invocations' metric (Task 34)."""
    return sum(
        1
        for st in state.stages.values()
        for sp in st.spawns
        if sp.spawned_by != "orchestrator"
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

TARGET_ONBOARDED = "onboarded"
TARGET_BROWNFIELD = "brownfield"
TARGET_GREENFIELD = "greenfield"

# Directories that never count as the target's own source when deciding whether there is
# anything to reverse-engineer. Without this, a bare repo with an installed virtualenv
# looks like a million-file legacy monolith.
_NON_SOURCE_DIRS = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "dist", "build",
    ".idea", ".vscode", "site-packages", ".claude", "agentic-assets", "agentforge",
})
_SOURCE_SUFFIXES = frozenset({
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".rb", ".php",
    ".cs", ".c", ".h", ".cc", ".cpp", ".hpp", ".swift", ".scala", ".dart", ".m", ".mm",
    ".sql", ".sh", ".ps1", ".hocon",
})
# Enough real source files that a human would call this an existing codebase rather than
# a scaffold. Deliberately low: the cost of onboarding a near-empty repo is one wasted
# read-only scan, while the cost of skipping a real one is an unmapped legacy codebase.
_BROWNFIELD_MIN_SOURCE_FILES = 5


def has_memory_bank(project_root: Path) -> bool:
    """True when the target already carries a memory bank — a checkable filesystem fact,
    not a judgment call (roles.plan.md Task 15 GOTCHA)."""
    return (project_root / "docs" / "context" / "REPO_MAP.md").is_file()


def _count_source_files(project_root: Path, stop_at: int) -> int:
    """Count the target's own source files, short-circuiting once `stop_at` is reached.

    Only ever used for a threshold comparison, so it never walks a large tree to
    completion.
    """
    seen = 0
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if d not in _NON_SOURCE_DIRS and not d.startswith(".")]
        for name in filenames:
            if Path(name).suffix.lower() in _SOURCE_SUFFIXES:
                seen += 1
                if seen >= stop_at:
                    return seen
    return seen


def classify_target(project_root: Path) -> str:
    """Classify an /agentforge target into the three states S0 actually has.

    The original gate had only two (`_is_brownfield` == "has a memory bank"), which
    conflated "already onboarded" with "greenfield" and so **skipped onboarding on
    exactly the repos that needed it** — an un-onboarded legacy codebase has no
    REPO_MAP.md by definition, and was therefore read as greenfield.

    - `TARGET_ONBOARDED`  — memory bank present; nothing for S0 to reverse-engineer.
    - `TARGET_BROWNFIELD` — real source, no memory bank; S0 must run `legacy-modernizer`.
    - `TARGET_GREENFIELD` — no memory bank and no meaningful source; nothing to map yet.
    """
    if has_memory_bank(project_root):
        return TARGET_ONBOARDED
    if _count_source_files(project_root, _BROWNFIELD_MIN_SOURCE_FILES) >= _BROWNFIELD_MIN_SOURCE_FILES:
        return TARGET_BROWNFIELD
    return TARGET_GREENFIELD


def needs_onboarding(project_root: Path) -> bool:
    """True only for an un-onboarded existing codebase — the one case S0 exists to serve."""
    return classify_target(project_root) == TARGET_BROWNFIELD


_SKIP_NOTE = {
    TARGET_ONBOARDED: "(skipped — target already onboarded, memory bank present)",
    TARGET_GREENFIELD: "(skipped — greenfield target, no existing code to map)",
}


def run_sequence(
    path: str | Path,
    state: RunState,
    agents: dict[str, Callable[[], AgentOutcome]],
    *,
    spawned_by: str = "orchestrator",
    project_root: Path | None = None,
) -> RunState:
    """Drive the stage sequence, persisting run.json after every transition.

    `agents` maps each stage id to a zero-arg callable returning an AgentOutcome — a
    stub in tests, the real subagent spawn in production. Already-complete stages are
    skipped, so re-running against a resumed state continues where it stopped. Stops and
    sets `escalation` after MAX_CONSECUTIVE_FAILURES consecutive failures on a stage.

    `project_root`, when given, gates the `onboarding` stage on `classify_target`:
    `legacy-modernizer` is spawned only for a `TARGET_BROWNFIELD` target (real source, no
    memory bank). An already-onboarded or genuinely greenfield target has the stage marked
    complete with the reason recorded, and `agents` need not even carry an `"onboarding"`
    key for that run. Omitting `project_root` runs `onboarding` unconditionally, matching
    prior behaviour for any caller that hasn't opted into the check yet.

    An agent callable that raises (a simulated kill) leaves the stage `in_progress` on
    disk, because entry is persisted before the spawn — that is what makes resume re-run
    an interrupted stage instead of skipping it (Task 28).
    """
    path = Path(path)
    for stage in _seq(state.sequence):
        if state.stages[stage].status == "complete":
            continue
        if stage == "onboarding" and project_root is not None:
            target = classify_target(project_root)
            if target != TARGET_BROWNFIELD:
                complete_stage(state, stage, AgentOutcome("complete", [_SKIP_NOTE[target]]))
                state.save(path)
                continue
        while True:
            enter_stage(state, stage, spawned_by=spawned_by)
            state.save(path)                     # in_progress persisted before the spawn
            outcome = agents[stage]()            # may raise -> in_progress remains on disk
            if outcome.status == "complete":
                complete_stage(state, stage, outcome)
                state.save(path)
                break
            escalated = fail_stage(state, stage)
            state.save(path)
            if escalated:
                return state                     # stop the whole run; human takes over
            # otherwise retry the same stage (next spawn)
    state.current_stage = None
    state.save(path)
    return state


# ---------------------------------------------------------------------------
# CLI — how the /agentforge markdown command records transitions
# ---------------------------------------------------------------------------

def _cli_artifact_list(values: list[str] | None) -> list[str]:
    return list(values) if values else []


def usage_rollup(state: RunState) -> dict:
    """Aggregate per-stage token/cost usage into a reporting-ready summary.

    Returns a dict with per-stage figures (in STAGE_SEQUENCE order, only stages that
    reported non-zero usage), the totals, and the single top-consuming stage by total
    tokens — the actionable signal for "where is the token budget going?". Pure and
    side-effect free so both the human report and a --json consumer share one source.
    """
    per_stage: list[dict] = []
    unrecorded: list[str] = []
    total_in = total_out = total_calls = 0
    total_cost = 0.0
    for sid in _seq(state.sequence):
        u = state.stages[sid].usage
        stage_tokens = u.tokens_in + u.tokens_out
        stage_cost = round(u.cost_usd, 4)
        total_in += u.tokens_in
        total_out += u.tokens_out
        total_calls += u.api_calls
        # Sum the *rounded* per-stage cost so the reported total always equals the sum of
        # the displayed rows (round-then-sum, not sum-then-round) — otherwise a table of
        # two $0.0001 rows could show a $0.0001 total and read as an arithmetic error.
        total_cost += stage_cost
        if stage_tokens or u.api_calls or stage_cost or u.is_reported():
            per_stage.append({
                "stage": sid,
                "tokens_in": u.tokens_in,
                "tokens_out": u.tokens_out,
                "tokens_total": stage_tokens,
                "api_calls": u.api_calls,
                "cost_usd": stage_cost,
                "source": u.source,
                "passes": len(state.stages[sid].usage_history) + 1,
            })
        elif state.stages[sid].status in ("complete", "failed"):
            # TD-018 Problem 4: a stage that DID work but reported nothing used to be
            # omitted entirely — not shown as 0, absent. So "free" and "never recorded"
            # were indistinguishable, and there was no row to notice. It is now listed
            # explicitly as unrecorded, and excluded from the summed totals because an
            # unknown is not a zero.
            unrecorded.append(sid)
    total_tokens = total_in + total_out
    # Top stage by total tokens. None both when nothing was reported and when everything
    # reported was cost/API-only (zero tokens) — "top token consumer" is meaningless with
    # no tokens, so we don't point a user at a zero-token stage. Ties keep the earliest
    # stage in STAGE_SEQUENCE order (max replaces only on strict >).
    top = max(per_stage, key=lambda s: s["tokens_total"], default=None)
    top_stage = top["stage"] if top and top["tokens_total"] > 0 else None
    return {
        "per_stage": per_stage,
        "totals": {
            "tokens_in": total_in,
            "tokens_out": total_out,
            "tokens_total": total_tokens,
            "api_calls": total_calls,
            "cost_usd": round(total_cost, 4),
        },
        "top_stage": top_stage,
        "reported": bool(per_stage),
        # Named so every consumer can see how much of the run the totals do NOT cover.
        # A total is a lower bound whenever this is non-empty.
        "unrecorded_stages": unrecorded,
        "complete": not unrecorded,
    }


def _print_usage(state: RunState) -> None:
    """Human-readable per-stage token/cost breakdown with totals and top consumer."""
    roll = usage_rollup(state)
    print(f"Objective: {state.objective}")
    if not roll["reported"]:
        print("Usage: no token telemetry recorded yet "
              "(pass --tokens-in/--tokens-out to `complete`).")
        return
    print(f"{'Stage':<16}{'In':>12}{'Out':>12}{'Total':>12}{'Calls':>8}{'Cost $':>10}  Source")
    for s in roll["per_stage"]:
        passes = f" x{s['passes']}" if s.get("passes", 1) > 1 else ""
        print(f"{s['stage']:<16}{s['tokens_in']:>12,}{s['tokens_out']:>12,}"
              f"{s['tokens_total']:>12,}{s['api_calls']:>8}{s['cost_usd']:>10.4f}"
              f"  {s.get('source', SOURCE_UNSPECIFIED)}{passes}")
    for sid in roll["unrecorded_stages"]:
        # Dashes, not zeros: this stage ran and reported nothing. Printing 0 here is the
        # bug TD-018 Problem 4 records.
        print(f"{sid:<16}{'-':>12}{'-':>12}{'-':>12}{'-':>8}{'-':>10}  unrecorded")
    tt = roll["totals"]
    print(f"{'TOTAL':<16}{tt['tokens_in']:>12,}{tt['tokens_out']:>12,}"
          f"{tt['tokens_total']:>12,}{tt['api_calls']:>8}{tt['cost_usd']:>10.4f}")
    if roll["unrecorded_stages"]:
        # State the limit of the number rather than letting a partial sum read as a total.
        print(f"INCOMPLETE: {len(roll['unrecorded_stages'])} stage(s) did work but "
              f"reported no usage ({', '.join(roll['unrecorded_stages'])}) - "
              f"TOTAL is a LOWER BOUND, not the run's cost.")
    if roll["top_stage"]:
        caveat = " (of the recorded stages only)" if roll["unrecorded_stages"] else ""
        print(f"Top consumer: {roll['top_stage']}{caveat} - target optimization here first.")


def _print_status(state: RunState, gates_path: Path) -> None:
    """Compose run.json + gates.json into one screen: stage, blocker, owner.

    Takes an already-loaded RunState rather than reloading it — main() loads it once
    for every subcommand. Composed at the CLI layer only: run_state and gate_state stay
    independently loadable, neither importing the other's internals, so a run.json-only
    test suite (or a gates.json-only one) can never break from this composition
    (gates-mvp.plan.md Task 16 GOTCHA).
    """
    import gate_state  # local import: run_state must stay loadable with no gate_state present

    print(f"Objective: {state.objective}")
    print(f"Stage:     {state.current_stage or '(none — run complete)'}")
    print(f"Completed: {', '.join(state.completed_stages) or '(none)'}")
    print(f"Escalation: {state.escalation or 'none'}")
    print(f"Manual spawns: {manual_invocation_count(state)}")
    roll = usage_rollup(state)
    if roll["reported"]:
        t = roll["totals"]
        top = f", top: {roll['top_stage']}" if roll["top_stage"] else ""
        bound = " LOWER BOUND" if roll["unrecorded_stages"] else ""
        print(f"Tokens:    {t['tokens_total']:,} total{bound} "
              f"({t['tokens_in']:,} in / {t['tokens_out']:,} out), "
              f"${t['cost_usd']:.4f}{top}  --  full breakdown: `usage`")
        if roll["unrecorded_stages"]:
            print(f"           {len(roll['unrecorded_stages'])} stage(s) unrecorded - "
                  f"see `usage`")

    if gates_path.exists():
        try:
            gstate = gate_state.GateState.load(gates_path)
            pending = gstate.any_pending()
        except gate_state.InvalidGateState as exc:
            print(f"Blocked: unknown ({exc})")
            return
    else:
        pending = []

    if not pending:
        print("Blocked: nothing")
    else:
        for artifact in pending:
            gate = gstate.gates[artifact]
            print(f"Blocked: {artifact} (stage {gate.stage}, opened {gate.opened_at})")
        # No per-gate assignee field exists in gates.json (MVP scope) — role agents
        # that would differentiate gate ownership (product-manager, qa-engineer, ...)
        # don't exist until EP-03. "Developer / Tech Lead" is named explicitly, not a
        # bare "you", because it's the actual, sole active persona for Phase 1/2
        # (epics-and-user-stories.md:8) — manual trial feedback (TS-02-03-06) found
        # a generic pronoun made "who" ambiguous even though it was technically
        # answerable from context.
        # TODO(EP-03, roles.plan.md Part A/C): once gates carry a real per-gate
        # assignee (product-manager/qa-engineer/etc.), replace this hardcoded owner —
        # it will otherwise silently print the wrong persona for a gate it doesn't
        # apply to (code-review LOW finding).
        print(
            "Owner:   Developer / Tech Lead — respond via AskUserQuestion in the main "
            "session (D1)"
        )
        # Manual timed-trial feedback (TS-02-03-06): naming the blocker was clear, but
        # the runnable command to actually resolve it was not — an operator had to
        # infer `gate_state.py decide` from memory rather than read it off the screen.
        # Print the exact command for the first pending artifact so re-orientation
        # doesn't require recalling CLI syntax under time pressure. Only the first
        # artifact gets a worked example — `Blocked:` above already enumerates every
        # pending one by name, so nobody is misled about how many exist, but repeated
        # gates need the same command run again per artifact (code-review LOW finding).
        example = pending[0]
        remaining_note = f" ({len(pending)} gates pending — repeat per artifact)" if len(pending) > 1 else ""
        print(
            "Next:    python agentforge/src/state/gate_state.py "
            f"--path {gates_path} decide {example} <approved|changes_requested|rejected> "
            f"--identity <who>{remaining_note}"
        )


# Exit code for "resume succeeded, but a gate blocks advancing" — distinct from 1
# (load/validation error) so a caller can tell "state is fine, a human is needed" apart
# from "something is actually broken."
RESUME_BLOCKED_BY_GATE = 3


def _resume(state: RunState, gates_path: Path) -> int:
    """Restore stage + gate state from disk alone — no transcript replay (FR-02, D1).

    Takes an already-loaded RunState (see _print_status). This is largely already true
    by construction (RunState.load / GateState.load are full reconstructions with no
    transcript dependency) — --resume makes it an explicit, documented entry point
    rather than an implicit property, per TS-02-04-01. Reuses GateState.load verbatim;
    no second, parallel resume-specific loader is introduced (gates-mvp.plan.md Task 23
    GOTCHA).
    """
    import gate_state

    print(f"Resuming at stage: {state.current_stage or '(none — run complete)'}")

    if not gates_path.exists():
        print("Ready to advance — no gates recorded.")
        return 0

    try:
        gstate = gate_state.GateState.load(gates_path)
    except gate_state.InvalidGateState as exc:
        print(exc)
        return 1

    pending = gstate.any_pending()
    if pending:
        for artifact in pending:
            gate = gstate.gates[artifact]
            print(f"Cannot advance: {artifact} gate is still pending (stage {gate.stage}).")
        print(
            "The gate survived the break — respond via AskUserQuestion in the main "
            "session (D1) before continuing."
        )
        return RESUME_BLOCKED_BY_GATE

    print("Ready to advance — no gate blocks this run.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read and update an /agentforge run.json.")
    parser.add_argument("--path", default="run.json", help="Path to run.json (default: run.json)")
    parser.add_argument("--gates-path", default="gates.json", help="Path to gates.json (default: gates.json)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Create a fresh run.json for an objective")
    p_init.add_argument("--objective", required=True)
    p_init.add_argument("--force", action="store_true", help="Overwrite an existing run.json")
    p_init.add_argument(
        "--sequence", choices=sorted(SEQUENCES), default=DEFAULT_SEQUENCE,
        help="Named stage sequence this run walks (ADR-0022 D-3): 'sdlc' (/agentforge, "
             "default) or 'ml' (/agentforge-ml)",
    )
    p_init.add_argument(
        # The union of every sequence's stage ids (D-3): argparse resolves `choices`
        # before run.json (and therefore the run's own sequence) is even read, so the
        # full set is accepted here and --start-stage is re-validated against
        # --sequence specifically below.
        "--start-stage", choices=ALL_STAGE_IDS, default=None,
        help="Join the pipeline at this stage (EP-07, ADR-0006) — earlier stages are "
             "marked complete as supplied outside this run, not produced by it. Must "
             "belong to --sequence.",
    )

    p_lock = sub.add_parser(
        "record-lock",
        help="Record the use-case lock this ml run is built on (ADR-0008 L-1); refuses an edited lock",
    )
    p_lock.add_argument("lock_path", help="Path to use_case.lock.json")

    p_start = sub.add_parser("start", help="Mark a stage in_progress before spawning its agent")
    p_start.add_argument("stage", choices=ALL_STAGE_IDS)
    p_start.add_argument("--spawned-by", choices=["orchestrator", "human"], default="orchestrator")

    p_done = sub.add_parser("complete", help="Mark a stage complete with its artifacts")
    p_done.add_argument("stage", choices=ALL_STAGE_IDS)
    p_done.add_argument("--artifact", action="append", help="Artifact path (repeatable)")
    # Optional per-stage token telemetry. The numbers originate from the subagent's
    # spawn result and are supplied by the orchestrator; all default to 0 so callers
    # (and older run.json files) that omit them stay valid and simply report zero.
    p_done.add_argument("--tokens-in", type=int, default=0, help="Input tokens the stage's agent consumed")
    p_done.add_argument("--tokens-out", type=int, default=0, help="Output tokens the stage's agent produced")
    p_done.add_argument("--api-calls", type=int, default=0, help="Model API calls the stage made")
    p_done.add_argument("--cost-usd", type=float, default=0.0, help="Modelled USD cost for the stage")
    p_done.add_argument(
        "--source", choices=sorted(VALID_SOURCES), default=None,
        help="Provenance of the figures (TD-018). Defaults to 'measured' when any figure "
             "is supplied and 'unrecorded' when none is. Pass 'estimated' when the number "
             "was derived rather than reported -- e.g. an orchestrator-owned stage, which "
             "has no spawn result to read a real figure from.",
    )

    p_fail = sub.add_parser("fail", help="Record a failed spawn; escalates after two in a row")
    p_fail.add_argument("stage", choices=ALL_STAGE_IDS)
    # A failed attempt still cost tokens (TD-018 Problem 1) -- it just did not converge.
    p_fail.add_argument("--tokens-in", type=int, default=0, help="Input tokens the failed attempt consumed")
    p_fail.add_argument("--tokens-out", type=int, default=0, help="Output tokens the failed attempt produced")
    p_fail.add_argument("--api-calls", type=int, default=0, help="Model API calls the failed attempt made")
    p_fail.add_argument("--cost-usd", type=float, default=0.0, help="Modelled USD cost of the failed attempt")
    p_fail.add_argument("--source", choices=sorted(VALID_SOURCES), default=None,
                        help="Provenance of the figures (see `complete --source`)")

    p_reopen = sub.add_parser(
        "reopen",
        help="Re-arm a completed stage so it runs again (TD-014); preserves its spawn history",
    )
    p_reopen.add_argument("stage", choices=ALL_STAGE_IDS)

    sub.add_parser("status", help="Print stage + gate status (reads run.json and gates.json)")
    p_usage = sub.add_parser("usage", help="Print per-stage token/cost breakdown with totals and top consumer")
    p_usage.add_argument("--json", action="store_true", help="Emit the rollup as JSON instead of a table")
    sub.add_parser("resume", help="Restore stage + gate state after a session break; no transcript replay")
    sub.add_parser(
        "preview",
        help="Print the remaining stage sequence with zero side effects (--dry-run on /agentforge)",
    )
    p_classify = sub.add_parser(
        "classify-target",
        help="Print onboarded|brownfield|greenfield for a target (needs no run.json)",
    )
    p_classify.add_argument("--project-root", default=".", help="Target project root (default: .)")

    args = parser.parse_args(argv)
    path = Path(args.path)

    if args.cmd == "classify-target":
        # Deliberately ahead of every run.json concern: the S0 gate and /agentforge
        # --stage bootstrap both need this answer *before* a run exists.
        root = Path(args.project_root)
        target = classify_target(root)
        reason = {
            TARGET_ONBOARDED: "memory bank present (docs/context/REPO_MAP.md)",
            TARGET_BROWNFIELD: "existing source, no memory bank — onboarding required",
            TARGET_GREENFIELD: "no memory bank and no meaningful source",
        }[target]
        print(f"{target} — {reason}")
        return 0

    if args.cmd == "init":
        try:
            create_run(
                path, args.objective, overwrite=args.force,
                start_stage=args.start_stage, sequence=args.sequence,
            )
        except RunExists as exc:
            print(exc)
            return 1
        except ValueError as exc:
            print(exc)
            return 1
        started_at = args.start_stage or _seq(args.sequence)[0]
        print(
            f"run.json created at {path} for: {args.objective} "
            f"(sequence: {args.sequence}, starting at {started_at})"
        )
        return 0

    if args.cmd in ("status", "resume", "preview", "usage") and not path.exists():
        # Neither --status nor --resume on a missing run is an error (TS-02-03-03) —
        # every other subcommand below still exits 1 on FileNotFoundError. `usage` joins
        # them: reporting on a run that hasn't started is a no-op, not a failure.
        print("No run in progress.")
        return 0

    try:
        state = RunState.load(path)
    except FileNotFoundError:
        print(f"No run.json at {path} — run 'init' first.")
        return 1
    except InvalidRunState as exc:
        print(exc)
        return 1

    # `start`/`complete`/`fail`/`reopen` accept the UNION of every sequence's stage ids
    # at the argparse level (ALL_STAGE_IDS, D-3) because choices are resolved before
    # run.json is read. Re-check here against the sequence THIS run actually walks, so
    # e.g. `complete model-select` against an sdlc run is refused by name rather than
    # raising a bare KeyError deep inside complete_stage.
    if args.cmd in ("start", "complete", "fail", "reopen") and args.stage not in state.stages:
        print(
            f"{args.stage!r} is not a stage of this run's {state.sequence!r} sequence "
            f"(expected one of {_seq(state.sequence)})"
        )
        return 1

    if args.cmd == "status":
        _print_status(state, Path(args.gates_path))
        return 0

    if args.cmd == "usage":
        if args.json:
            print(json.dumps(usage_rollup(state), indent=2, ensure_ascii=False))
        else:
            _print_usage(state)
        return 0

    if args.cmd == "preview":
        plan = plan_sequence(state)
        if not plan:
            print("Nothing left to run — every stage is complete.")
            return 0
        print("Would run:")
        for stage, agent in plan:
            print(f"  {stage} -> {agent}")
        return 0

    if args.cmd == "resume":
        return _resume(state, Path(args.gates_path))

    if args.cmd == "record-lock":
        # Stdlib-only check, deliberately not importing ml_contract: an edited lock no
        # longer hashes to its own lock_sha256, and a run must not be pinned to one.
        try:
            lock = json.loads(Path(args.lock_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"cannot read lock {args.lock_path}: {exc}", file=sys.stderr)
            return 1
        body = {k: v for k, v in lock.items() if k != "lock_sha256"}
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        if lock.get("lock_sha256") != digest:
            print(f"{args.lock_path} was edited after it was built; rebuild it", file=sys.stderr)
            return 1
        state.use_case_lock = {
            "path": str(args.lock_path),
            "lock_sha256": lock["lock_sha256"],
            "use_case_id": lock.get("use_case_id"),
        }
        state.save(path)
        print(f"lock {lock['lock_sha256'][:12]} recorded ({lock.get('use_case_id')})")
        return 0

    if args.cmd == "start":
        enter_stage(state, args.stage, spawned_by=args.spawned_by)
        state.save(path)
        print(f"{args.stage}: in_progress (agent: {_agents(state.sequence)[args.stage]})")
        return 0

    def _usage_from_args(a) -> Usage | None:
        """Validate the four figures and resolve provenance. None means refuse.

        Rejects negatives and non-finite values. A negative would masquerade as the
        *cheapest* stage; a NaN/Infinity (reachable only via --cost-usd, since the int
        flags raise at argparse) is worse — it slips past `value < 0` (nan/inf < 0 is
        False), persists to run.json, and then permanently contaminates every future
        rollup because NaN is contagious in the cost sum. Zero is fine — it just means
        "not reported". math.isfinite is True for all ints.

        Provenance (TD-018): an explicit --source always wins. Otherwise supplying a
        figure asserts `measured`, and supplying none records `unrecorded` — which is
        NOT a measured zero and is reported separately by the rollup.
        """
        for label, value in (
            ("--tokens-in", a.tokens_in), ("--tokens-out", a.tokens_out),
            ("--api-calls", a.api_calls), ("--cost-usd", a.cost_usd),
        ):
            if value < 0 or not math.isfinite(value):
                print(f"INVALID usage: {label} must be a finite number >= 0, got {value}")
                return None
        has_figures = bool(a.tokens_in or a.tokens_out or a.api_calls or a.cost_usd)
        source = getattr(a, "source", None) or (
            SOURCE_MEASURED if has_figures else SOURCE_UNRECORDED
        )
        if source == SOURCE_UNRECORDED and has_figures:
            print("INVALID usage: --source unrecorded cannot carry figures — "
                  "pass no figures, or declare them measured/estimated")
            return None
        return Usage(tokens_in=a.tokens_in, tokens_out=a.tokens_out,
                     api_calls=a.api_calls, cost_usd=a.cost_usd, source=source)

    if args.cmd == "complete":
        usage = _usage_from_args(args)
        if usage is None:
            return 1
        outcome = AgentOutcome("complete", _cli_artifact_list(args.artifact), usage)
        try:
            complete_stage(state, args.stage, outcome)
        except VerdictRequired as exc:
            # Fail loudly and leave the stage open — the whole point of TD-014 is that
            # a convergence check must not be closeable on a partial verdict.
            print(f"REFUSED: {exc}")
            return 1
        state.save(path)
        total = usage.tokens_in + usage.tokens_out
        suffix = f" ({total:,} tokens)" if total else ""
        print(f"{args.stage}: complete{suffix}")
        return 0

    if args.cmd == "reopen":
        if state.stages[args.stage].status != "complete":
            print(f"{args.stage}: not complete — nothing to reopen")
            return 1
        reopen_stage(state, args.stage)
        state.save(path)
        print(f"{args.stage}: reopened (pending) — spawn history preserved; re-run it")
        return 0

    if args.cmd == "fail":
        fail_usage = _usage_from_args(args)
        if fail_usage is None:
            return 1
        escalated = fail_stage(state, args.stage, fail_usage)
        state.save(path)
        if escalated:
            print(f"{args.stage}: FAILED twice — escalated to human. Run halted.")
            return 2
        print(f"{args.stage}: failed (retry pending)")
        return 0

    return 0  # argparse's `choices` on cmd makes this unreachable; kept for clarity


if __name__ == "__main__":
    raise SystemExit(main())
