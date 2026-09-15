#!/usr/bin/env python3
"""budget.py — two-category cost computation, never blended (EP-08, D20).

Delivery cost (completed points x a configured `1 SP = $X` rate) and AI runtime cost
(summed from sprint-NN.json's usage accumulator, ADR-0005) are always reported as two
distinct figures — BudgetReport's own shape makes blending them a caller error, not
just a documentation convention (D20: "the two categories answer different questions
and must never be summed").

RateConfig mirrors jira_config.py's D16 prompt-once/persist pattern: the rate is
elicited from the user on first use (AskUserQuestion, main session only, D1) and
persisted, never assumed or defaulted to zero (US-08-08's own failure-case AC).

Known gap, disclosed rather than silently absorbed: `sprint_state.RunSnapshot` stores
each run's *cumulative* usage, not a per-stage or per-model breakdown (that data lives
only in the currently-active run.json, which has no archival — see ADR-0005 and
pm-delivery-management.plan.md's NOT Building section). `monthly_rollup` therefore
aggregates by sprint only; a by-model/by-stage breakdown is deferred, not fabricated.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from sprint_state import SprintState

ASSUMED_SPRINTS_PER_MONTH = 2


@dataclass
class RateConfig:
    rate_usd_per_point: float | None = None

    def set_rate(self, rate: float) -> None:
        self.rate_usd_per_point = rate

    def save(self, path: str | Path) -> None:
        """Atomically persist — temp file + os.replace, mirrors jira_config.save."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"rate_usd_per_point": self.rate_usd_per_point}, indent=2) + "\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> RateConfig:
        """Missing or corrupted file both report unset (None), never an exception —
        mirrors jira_config.load / vendor_config.load exactly."""
        path = Path(path)
        if not path.is_file():
            return cls(rate_usd_per_point=None)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return cls(rate_usd_per_point=None)
            rate = data.get("rate_usd_per_point")
            return cls(rate_usd_per_point=float(rate) if rate is not None else None)
        except (json.JSONDecodeError, ValueError, TypeError):
            return cls(rate_usd_per_point=None)


@dataclass
class BudgetReport:
    delivery_cost: float | None
    delivery_cost_reason: str | None
    runtime_cost: float
    completed_points: float
    rate_usd_per_point: float | None


def compute_budget_report(sprint: SprintState, rate_config: RateConfig) -> BudgetReport:
    """Two independently-guarded figures. A missing rate marks delivery cost
    unavailable with a reason — never defaults to zero or a guess (US-08-08 failure
    case). Zero completed points WITH a rate configured is a real, computed $0,
    distinguishable from "unavailable" (US-08-08 boundary case)."""
    completed_points = sum(item.points for item in sprint.committed_items if item.status == "done")
    runtime_cost = sprint.total_usage().cost_usd

    if rate_config.rate_usd_per_point is None:
        return BudgetReport(
            delivery_cost=None,
            delivery_cost_reason="no $/pt rate configured — delivery cost unavailable, not assumed zero",
            runtime_cost=runtime_cost,
            completed_points=completed_points,
            rate_usd_per_point=None,
        )
    delivery_cost = completed_points * rate_config.rate_usd_per_point
    return BudgetReport(
        delivery_cost=delivery_cost,
        delivery_cost_reason=None,
        runtime_cost=runtime_cost,
        completed_points=completed_points,
        rate_usd_per_point=rate_config.rate_usd_per_point,
    )


@dataclass
class MonthlyBudgetReport:
    month: str
    assumed_sprints_per_month: int
    actual_sprint_count: int
    deviates_from_assumption: bool
    total_runtime_cost: float
    incomplete_sprints: list[str] = field(default_factory=list)


def monthly_rollup(sprints: list[SprintState], *, month: str) -> MonthlyBudgetReport:
    """Aggregate AI runtime cost across every sprint passed in (the caller resolves
    which sprint-NN.json files fall in `month`, e.g. by opened_at). A sprint with no
    run snapshots (never refreshed) is named as incomplete and excluded from the
    total — never silently counted as $0 spend (US-08-09 failure case)."""
    incomplete = [s.sprint_id for s in sprints if not s.runs]
    total = sum(s.total_usage().cost_usd for s in sprints if s.runs)
    actual_count = len(sprints)
    return MonthlyBudgetReport(
        month=month,
        assumed_sprints_per_month=ASSUMED_SPRINTS_PER_MONTH,
        actual_sprint_count=actual_count,
        deviates_from_assumption=(actual_count != ASSUMED_SPRINTS_PER_MONTH),
        total_runtime_cost=total,
        incomplete_sprints=incomplete,
    )
