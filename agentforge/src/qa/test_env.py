#!/usr/bin/env python3
"""test_env.py — test-env.json schema, atomic persistence, provisioning (EP-05, US-05-03).

JSON, not YAML (ADR-0004 Task 10 GOTCHA, same D8 stdlib-first, zero-new-dependency
reasoning EP-04's `vendor_config.py` already established): this repo has no YAML
dependency, and every state/config file this codebase owns is JSON. Unlike
`vendor_config.py` (purely machine-written/read), `test-env.json` is meant to be
hand-authored by whoever configures a target environment — a real UX tradeoff (no
comments, stricter syntax than YAML) accepted knowingly, not silently.

Atomic load/save mirrors `ATOMIC_STATE_IO` (agentforge/src/state/gate_state.py:335-345).
Provisioning's subprocess calls mirror `SUBPROCESS_DISCIPLINE` (gate_state.py:385-433):
argv lists via `shlex.split`, never `shell=True`, explicit timeouts, non-zero exits
turned into an explicit result, never left to propagate as an unhandled exception.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_PROBE_TIMEOUT_SECONDS = 30
_PROBE_POLL_INTERVAL_SECONDS = 1
_COMMAND_TIMEOUT_SECONDS = 300


@dataclass
class HealthProbe:
    url: str
    timeout_seconds: int = _DEFAULT_PROBE_TIMEOUT_SECONDS


@dataclass
class EnvironmentSpec:
    up: list[str] = field(default_factory=list)
    health_probe: HealthProbe | None = None
    seed: list[str] | None = None
    teardown: list[str] = field(default_factory=list)


@dataclass
class ProvisionResult:
    """The outcome of one provision/teardown attempt. Never an exception — a failed
    `up` command or a probe that never passes is reported here, mirroring
    `RunResult`/`UploadResult`'s existing 'never raises' contract."""

    success: bool
    detail: str = ""


@dataclass
class TestEnvConfig:
    environments: dict[str, EnvironmentSpec] = field(default_factory=dict)

    def save(self, path: str | Path) -> None:
        """Atomically persist — temp file + os.replace, mirrors `ATOMIC_STATE_IO`."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._to_dict(), indent=2) + "\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> TestEnvConfig:
        """Missing, corrupted, or non-dict JSON all report an empty config — never an
        exception. Parametrized from the start over `null`/a list/a bare number, not
        as an afterthought (closing the exact non-dict-JSON gap class EP-04's code
        review found twice)."""
        path = Path(path)
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return cls()
        if not isinstance(data, dict):
            return cls()
        raw_environments = data.get("environments", {})
        if not isinstance(raw_environments, dict):
            return cls()

        environments: dict[str, EnvironmentSpec] = {}
        for name, raw_spec in raw_environments.items():
            if not isinstance(raw_spec, dict):
                continue
            raw_probe = raw_spec.get("health_probe")
            health_probe = None
            if isinstance(raw_probe, dict) and "url" in raw_probe:
                health_probe = HealthProbe(
                    url=raw_probe["url"],
                    timeout_seconds=raw_probe.get(
                        "timeout_seconds", _DEFAULT_PROBE_TIMEOUT_SECONDS
                    ),
                )
            environments[name] = EnvironmentSpec(
                up=list(raw_spec.get("up", [])),
                health_probe=health_probe,
                seed=raw_spec.get("seed"),
                teardown=list(raw_spec.get("teardown", [])),
            )
        return cls(environments=environments)

    def _to_dict(self) -> dict:
        return {
            "environments": {
                name: {
                    "up": spec.up,
                    "health_probe": (
                        {"url": spec.health_probe.url, "timeout_seconds": spec.health_probe.timeout_seconds}
                        if spec.health_probe
                        else None
                    ),
                    "seed": spec.seed,
                    "teardown": spec.teardown,
                }
                for name, spec in self.environments.items()
            }
        }

    def provision(self, name: str) -> ProvisionResult:
        """A target with no matching entry runs locally with no provisioning — this is
        never a failure mode (US-05-03's own boundary-case AC)."""
        if name not in self.environments:
            return ProvisionResult(
                success=True,
                detail=f"No test-env.json entry for target '{name}' — running locally, no provisioning.",
            )

        spec = self.environments[name]

        for cmd in spec.up:
            result = _run_command(cmd)
            if not result.success:
                return ProvisionResult(
                    success=False,
                    detail=f"'up' command failed for target '{name}': {result.detail}",
                )

        if spec.health_probe is not None:
            probe_result = _poll_health_probe(spec.health_probe)
            if not probe_result.success:
                return probe_result

        if spec.seed:
            for cmd in spec.seed:
                result = _run_command(cmd)
                if not result.success:
                    return ProvisionResult(
                        success=False,
                        detail=f"'seed' command failed for target '{name}': {result.detail}",
                    )

        return ProvisionResult(success=True, detail=f"Target '{name}' provisioned.")

    def teardown(self, name: str) -> ProvisionResult:
        """Always runs `teardown` commands for `name` — the caller is responsible for
        calling this from a `finally` block, never conditionally, so a failed or
        aborted provision never leaves an orphaned environment."""
        if name not in self.environments:
            return ProvisionResult(success=True, detail=f"No test-env.json entry for target '{name}' — nothing to tear down.")

        spec = self.environments[name]
        failures: list[str] = []
        for cmd in spec.teardown:
            result = _run_command(cmd)
            if not result.success:
                failures.append(result.detail)

        if failures:
            return ProvisionResult(
                success=False,
                detail=f"teardown for '{name}' had failures: {'; '.join(failures)}",
            )
        return ProvisionResult(success=True, detail=f"Target '{name}' torn down.")


def _run_command(cmd: str) -> ProvisionResult:
    try:
        proc = subprocess.run(
            shlex.split(cmd),
            check=False,
            timeout=_COMMAND_TIMEOUT_SECONDS,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        return ProvisionResult(success=False, detail=f"command not found: {cmd} ({exc})")
    except subprocess.TimeoutExpired:
        return ProvisionResult(success=False, detail=f"command timed out after {_COMMAND_TIMEOUT_SECONDS}s: {cmd}")

    if proc.returncode != 0:
        return ProvisionResult(
            success=False,
            detail=f"'{cmd}' exited {proc.returncode}: {proc.stdout[-500:]}{proc.stderr[-500:]}",
        )
    return ProvisionResult(success=True, detail=f"'{cmd}' succeeded.")


def _poll_health_probe(probe: HealthProbe) -> ProvisionResult:
    deadline = time.monotonic() + probe.timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(probe.url, timeout=_PROBE_POLL_INTERVAL_SECONDS) as response:
                if 200 <= response.status < 300:
                    return ProvisionResult(success=True, detail=f"health probe {probe.url} -> {response.status}")
                last_error = f"HTTP {response.status}"
        except urllib.error.HTTPError as exc:
            last_error = f"HTTP {exc.code} {exc.reason}"
        except urllib.error.URLError as exc:
            last_error = str(exc.reason)
        time.sleep(_PROBE_POLL_INTERVAL_SECONDS)

    return ProvisionResult(
        success=False,
        detail=f"health probe {probe.url} never passed within {probe.timeout_seconds}s: {last_error}",
    )
