#!/usr/bin/env python3
"""jira_config.py — D16's prompt-once persistence, applied to Jira (EP-08, ADR-0005).

Mirrors agentforge/src/qa/vendor_config.py exactly, one choice narrower (Jira has no
second-vendor analog). Owns load/save only, never the AskUserQuestion prompt itself —
that cannot run inside a subagent (D1). The calling command/skill checks
`config.choice == JiraChoice.UNSET` and, if so, prompts in the main session and calls
`set_choice`/`save`. DECIDE_LATER is the one choice that must never persist — a re-run
prompts again, matching vendor_config.py's own contract.

Resolves OQ-7 (ADR-0005): with no Jira configured, `is_configured()` is False and every
caller (jira_sync.py, the sprint-planning/reporting skills) falls back to repo-local
sprint-NN.json state, per the same D12 precedent EP-04 established for the QA vendor.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class JiraChoice(str, Enum):
    UNSET = "unset"
    JIRA = "jira"
    NONE = "none"
    DECIDE_LATER = "decide_later"


@dataclass
class JiraConfig:
    choice: JiraChoice = JiraChoice.UNSET

    def set_choice(self, choice: JiraChoice) -> None:
        self.choice = choice

    def is_configured(self) -> bool:
        """True only when Jira was explicitly chosen — the single call sites
        (jira_sync.py) use to decide whether to attempt a push at all."""
        return self.choice == JiraChoice.JIRA

    def save(self, path: str | Path) -> None:
        """Atomically persist — temp file + os.replace, mirrors vendor_config.save.

        DECIDE_LATER is deliberately never written to disk as itself: writing UNSET
        here is what enforces the "re-run prompts again" contract, not a check at
        load time (identical rationale to vendor_config.py's own save()).
        """
        path = Path(path)
        to_write = JiraChoice.UNSET if self.choice == JiraChoice.DECIDE_LATER else self.choice
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"choice": to_write.value}, indent=2) + "\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> JiraConfig:
        """Missing or corrupted file both report UNSET, never an exception — a caller
        deciding whether to prompt must not crash on a config file it hasn't written
        yet, or one a human hand-edited into an invalid state."""
        path = Path(path)
        if not path.is_file():
            return cls(choice=JiraChoice.UNSET)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return cls(choice=JiraChoice.UNSET)
            choice = JiraChoice(data.get("choice", JiraChoice.UNSET.value))
        except (json.JSONDecodeError, ValueError):
            return cls(choice=JiraChoice.UNSET)
        return cls(choice=choice)
