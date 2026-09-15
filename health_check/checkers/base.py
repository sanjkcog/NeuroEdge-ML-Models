from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class CheckResult:
    name: str
    status: Status
    summary: str
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == Status.PASS
