#!/usr/bin/env python3
"""vendor_config.py — D16's prompt-once test-management vendor persistence (EP-04).

Owns load/save only, never the AskUserQuestion prompt itself — that cannot run inside a
subagent (D1). The calling command/skill checks `config.choice == VendorChoice.UNSET`
and, if so, prompts in the main session and calls `set_choice`/`save`. `DECIDE_LATER`
is the one choice that must never persist — a re-run has to prompt again, matching
"skipping falls back to none... the prompt fires once per project" (D16) meaning once
per *answered* project, not once regardless of whether an answer was actually given.

JSON, not YAML (see qa-traceability.plan.md Task 8 GOTCHA): this repo has no YAML
dependency, and run.json/gates.json are both JSON already.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from adapter import NoneAdapter, TestManagementAdapter


class VendorChoice(str, Enum):
    UNSET = "unset"
    ZEPHYR_SCALE = "zephyr_scale"
    TESTRAIL = "testrail"
    NONE = "none"
    DECIDE_LATER = "decide_later"


@dataclass
class VendorConfig:
    choice: VendorChoice = VendorChoice.UNSET

    def set_choice(self, choice: VendorChoice) -> None:
        self.choice = choice

    def save(self, path: str | Path) -> None:
        """Atomically persist — temp file + os.replace, mirrors gate_state.save.

        DECIDE_LATER is deliberately never written to disk as itself: persisting it
        would make future loads see "decide_later" and (depending on a caller's own
        logic) potentially treat that as a terminal answer rather than "still unset,
        ask again." Writing UNSET here is what actually enforces the "re-run prompts
        again" contract, not a check at load time.
        """
        path = Path(path)
        to_write = VendorChoice.UNSET if self.choice == VendorChoice.DECIDE_LATER else self.choice
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"choice": to_write.value}, indent=2) + "\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> VendorConfig:
        """Missing or corrupted file both report UNSET, never an exception — a caller
        deciding whether to prompt must not crash on a config file it hasn't written
        yet, or one a human hand-edited into an invalid state."""
        path = Path(path)
        if not path.is_file():
            return cls(choice=VendorChoice.UNSET)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return cls(choice=VendorChoice.UNSET)
            choice = VendorChoice(data.get("choice", VendorChoice.UNSET.value))
        except (json.JSONDecodeError, ValueError):
            return cls(choice=VendorChoice.UNSET)
        return cls(choice=choice)

    def get_adapter(self) -> TestManagementAdapter:
        """UNSET, NONE, and DECIDE_LATER (never actually stored, see save()) all mean
        the same thing to an adapter caller: fall back to NoneAdapter (D12) — a caller
        that needs to know whether a prompt is still owed checks `.choice` directly,
        not this method."""
        if self.choice == VendorChoice.ZEPHYR_SCALE:
            from zephyr_adapter import ZephyrAdapter

            base_url = os.environ.get("ZEPHYR_BASE_URL", "")
            api_token = os.environ.get("ZEPHYR_API_TOKEN", "")
            return ZephyrAdapter(base_url=base_url, api_token=api_token)
        if self.choice == VendorChoice.TESTRAIL:
            from testrail_adapter import TestRailAdapter

            base_url = os.environ.get("TESTRAIL_BASE_URL", "")
            api_key = os.environ.get("TESTRAIL_API_KEY", "")
            return TestRailAdapter(base_url=base_url, api_key=api_key)
        return NoneAdapter()
