#!/usr/bin/env python3
"""config.py — ExchangeChoice/ExchangeConfig persistence + adapter factory (ADR-0012
EP-01, LLD §3.4).

Mirrors qa/vendor_config.py exactly (JSON, tolerant load, DECIDE_LATER never
persists — a re-run must prompt again). Owns load/save only, never the
AskUserQuestion prompt itself — that cannot run inside a subagent (D1). The calling
command/skill checks `config.choice == ExchangeChoice.UNSET` and, if so, prompts in
the main session and calls `set_choice`/`save`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
import sys
from collections.abc import Callable
from enum import Enum
from pathlib import Path

from exchange.adapter import (
    ExchangeAdapter,
    MisconfiguredExchangeAdapter,
    NoneExchangeAdapter,
)


class ExchangeChoice(str, Enum):
    UNSET = "unset"
    GIT = "git"
    NONE = "none"
    DECIDE_LATER = "decide_later"


def _tolerant_ingest_sources(raw) -> dict[str, str]:
    """Sanitize a hand-edited/corrupt `ingest_sources` value into a well-shaped dict,
    never raising (mirrors `_tolerant_drivers` exactly, one field over). A malformed
    per-source entry (not a string root path) is DROPPED, not coerced — ADR-0012
    Direction 2, FR-01: this allowlist is fail-closed by construction. A source_id
    absent here (including the default empty dict) is REJECTED by
    `ingestion.sources.GitLocalSource.pull_artifacts`, never silently defaulted to a
    real driver (TC-02-02-03/04)."""
    if not isinstance(raw, dict):
        return {}
    sources: dict[str, str] = {}
    for source_id, root in raw.items():
        if isinstance(root, str):
            sources[str(source_id)] = root
    return sources


def _tolerant_drivers(raw) -> dict[str, list[str]]:
    """Sanitize a hand-edited/corrupt `drivers` value into a well-shaped dict, never
    raising. A malformed per-identity entry (not a list) is DROPPED, not coerced — a
    string value in particular must never reach exchange.authz.authorize, where
    Python's `in` operator would silently treat it as a substring-membership test
    instead of a permitted-actions list."""
    if not isinstance(raw, dict):
        return {}
    drivers: dict[str, list[str]] = {}
    for identity, actions in raw.items():
        if isinstance(actions, list):
            drivers[str(identity)] = [str(a) for a in actions]
    return drivers


# ---------------------------------------------------------------------------
# Provider registry (TD-016 D2)
# ---------------------------------------------------------------------------
#
# provider key -> zero-arg factory returning something satisfying ExchangeAdapter.
#
# Factories are lazy so an unconfigured provider costs nothing: the module is imported
# only when that provider is actually selected, and a provider whose optional dependency
# is missing degrades to NoneExchangeAdapter instead of breaking import of this module.
#
# Adding a provider is ONE entry here. `register_provider()` below lets a target add one
# without editing this file at all, which is the requirement that drove the change — a
# team patching AgentForge into their own repo must be able to add Jira without a core
# edit or a carried patch.


def _choice_value(choice: ExchangeChoice | str) -> str:
    """The on-disk string for a choice, whether it is a sentinel member or a provider key."""
    return choice.value if isinstance(choice, ExchangeChoice) else str(choice)


def _coerce_choice(raw: object) -> ExchangeChoice | str:
    """A sentinel string becomes its ExchangeChoice member; any other string stays a
    provider key. A non-string (hand-edited config) degrades to UNSET rather than
    raising, matching this module's tolerance elsewhere."""
    if isinstance(raw, ExchangeChoice):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return ExchangeChoice.UNSET
    try:
        return ExchangeChoice(raw)
    except ValueError:
        return raw


def _report(reason: str) -> ExchangeAdapter:
    """Surface a configuration error two ways, then degrade without raising.

    stderr so a human sees it at once even if the caller ignores the return value, and a
    `MisconfiguredExchangeAdapter` so the same reason reaches the caller through the
    ordinary result object. Deliberately NOT an exception: `get_adapter()` is called from
    inside stage execution, and an integration must never be the reason a stage dies.
    """
    print(f"[exchange] CONFIG ERROR: {reason}", file=sys.stderr)
    return MisconfiguredExchangeAdapter(reason=reason)


def _git_provider() -> ExchangeAdapter:
    from exchange.git_adapter import GitExchangeAdapter

    return GitExchangeAdapter()


def _github_provider() -> ExchangeAdapter:
    from exchange.github_adapter import GithubExchangeAdapter

    return GithubExchangeAdapter.from_env()


_PROVIDERS: dict[str, Callable[[], ExchangeAdapter]] = {
    "git": _git_provider,        # gh-CLI based; retained unchanged for existing configs
    "github": _github_provider,  # REST/API based (ADR-0012 D1 prefers API over CLI)
}


def register_provider(name: str, factory: Callable[[], ExchangeAdapter]) -> None:
    """Register a provider from outside this module — the target-extensibility seam.

    Deliberately an explicit CALL rather than an import path read from config. A config
    string naming `module:ClassName` would make a hand-edited exchange_config.json into
    arbitrary code execution at adapter-resolution time, which contradicts the
    fail-closed posture used for `drivers` and `ingest_sources` in this same file.
    Credentials in config are inert data; an import path is not, so the two are not
    equivalent even though both are "user-supplied config".

    A target registers its provider from its own code (a coded tool, a conftest, or an
    `agentforge_custom_plugin` module), then selects it by name in exchange_config.json.
    Re-registering an existing name replaces it, so a target can also override `github`
    with its own enterprise variant.
    """
    _PROVIDERS[name] = factory


def registered_providers() -> tuple[str, ...]:
    """Provider keys currently resolvable — for diagnostics and for prompting a user."""
    return tuple(sorted(_PROVIDERS))


@dataclass
class ExchangeConfig:
    choice: ExchangeChoice = ExchangeChoice.UNSET
    # ADR-0012 sprint-03, US-03-02, FR-10, OQ-2: identity -> permitted inbound intent
    # actions. Deliberately fail-closed — an identity absent here (including the
    # default empty dict) is authorized for NOTHING; see exchange.authz.authorize,
    # the single consumer of this field. Decoupled from GitHub repo write access
    # ("can write the repo" != "authorized to drive").
    drivers: dict[str, list[str]] = field(default_factory=dict)
    # ADR-0012 Direction 2, FR-01 (EP-02): source_id -> local root path, an inbound
    # ingestion allowlist. Deliberately fail-closed like `drivers` above — a
    # source_id absent here (including the default empty dict) is REJECTED by
    # ingestion.sources.GitLocalSource.pull_artifacts, never silently pulled from an
    # unlisted location (TC-02-02-03). A corrupt config file loads as UNSET/empty
    # here too (TC-02-02-04), never a silent default driver.
    ingest_sources: dict[str, str] = field(default_factory=dict)
    # TD-021: whether the orchestrator projects run-state outbound on stage transitions.
    #
    # Defaults FALSE deliberately. Configuring a provider is not consent to a commit per
    # stage: every push() writes a commit (measured on the 2026-07-29 live GitHub run), so
    # auto-exporting all 18 transitions would put 18 `chore(agentforge): publish exchange
    # record` commits per run into someone's repository. Opt-in beats surprise.
    #
    # This is a POLICY flag — config declares whether, `/exchange export` remains the
    # mechanism. Inbound has no equivalent flag on purpose: import/apply mutate local
    # state from an outside source and must stay an explicit human act (ADR-0012
    # Direction 2's review gate exists to force exactly that).
    auto_export: bool = False

    def set_choice(self, choice: ExchangeChoice) -> None:
        self.choice = choice

    def save(self, path: str | Path) -> None:
        """Atomically persist — temp file + os.replace, mirrors vendor_config.save.

        DECIDE_LATER is deliberately never written to disk as itself: persisting it
        would let a future load treat "decide_later" as a terminal answer rather than
        "still unset, ask again." Writing UNSET here is what actually enforces the
        "re-run prompts again" contract, not a check at load time.
        """
        path = Path(path)
        to_write = ExchangeChoice.UNSET if self.choice == ExchangeChoice.DECIDE_LATER else self.choice
        # `_choice_value` rather than `to_write.value`: since TD-016, `choice` may hold a
        # free-form provider string ("github", "jira") as well as an ExchangeChoice
        # member, and `str` has no `.value`. A bare `.value` here raised AttributeError on
        # exactly the config the integration guide documents — the registry worked
        # in-memory and could not be PERSISTED, which is the only path production uses.
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "choice": _choice_value(to_write),
                "drivers": self.drivers,
                "ingest_sources": self.ingest_sources,
                "auto_export": bool(self.auto_export),
            },
            indent=2,
        ) + "\n"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str | Path) -> ExchangeConfig:
        """Missing or corrupted file both report UNSET, never an exception — a caller
        deciding whether to prompt must not crash on a config file it hasn't written
        yet, or one a human hand-edited into an invalid state."""
        path = Path(path)
        if not path.is_file():
            return cls(choice=ExchangeChoice.UNSET)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return cls(choice=ExchangeChoice.UNSET)
            raw_choice = data.get("choice", ExchangeChoice.UNSET.value)
            # NOT `ExchangeChoice(raw_choice)`: that raises ValueError for any provider
            # name outside the 4 sentinels, and the ValueError was caught by the
            # corrupt-file handler below — so `{"choice": "github"}` loaded as UNSET and
            # silently resolved to NoneExchangeAdapter. A sentinel becomes its enum
            # member; anything else is kept as a provider key for the registry to resolve
            # (and to REPORT if unknown — see get_adapter).
            choice = _coerce_choice(raw_choice)
        except json.JSONDecodeError:
            return cls(choice=ExchangeChoice.UNSET)
        drivers = _tolerant_drivers(data.get("drivers", {}))
        ingest_sources = _tolerant_ingest_sources(data.get("ingest_sources", {}))
        # Fail closed on a non-boolean: a hand-edited "auto_export": "yes" must not be
        # read as truthy and start committing. Only a real `true` enables it.
        auto_export = data.get("auto_export", False) is True
        return cls(choice=choice, drivers=drivers, ingest_sources=ingest_sources,
                   auto_export=auto_export)

    def get_adapter(self) -> ExchangeAdapter:
        """Resolve the configured provider, or NoneExchangeAdapter.

        UNSET, NONE, and DECIDE_LATER (never actually stored, see save()) all mean the
        same thing to an adapter caller: fall back to NoneExchangeAdapter (D12) — a
        caller that needs to know whether a prompt is still owed checks `.choice`
        directly, not this method.

        Provider resolution is a REGISTRY LOOKUP, not an if-chain (TD-016 D2). Before
        this, `choice` was a closed 4-member enum switched on with a hardcoded branch, so
        a target that wanted Jira had to add an enum member AND a branch — both in
        AgentForge core, which the target does not own. That was the whole genericity
        blocker; adding a provider now means one registry entry.

        Unknown or unresolvable providers fall back to NoneExchangeAdapter rather than
        raising, matching this module's fail-closed posture everywhere else: a corrupt or
        hand-edited config degrades to "no vendor configured", which is a legitimate
        state, never an exception in the middle of a stage.
        """
        provider = self.provider_name()
        if provider is None:
            return NoneExchangeAdapter()

        factory = _PROVIDERS.get(provider)
        if factory is None:
            # TELL THE USER. Falling back to NoneExchangeAdapter here was the original
            # behaviour and it was wrong: `"choice": "githbu"` would silently push
            # nothing, look like a clean run, and leave the operator believing the
            # integration was live. A typo is a mistake to report, not a preference to
            # honour. Mirrors llm_config.hocon, where `"class"` takes a short known name
            # from a documented set and a wrong value is an error.
            known = ", ".join(registered_providers())
            return _report(
                f"unknown exchange provider {provider!r} — known providers: {known}. "
                f"Fix `choice` in exchange_config.json, or register the provider first with "
                f"exchange.config.register_provider({provider!r}, <factory>)."
            )
        try:
            return factory()
        except Exception as exc:  # noqa: BLE001 — must report, never raise mid-stage
            return _report(
                f"exchange provider {provider!r} is registered but failed to load: "
                f"{type(exc).__name__}: {exc}. Check its dependencies and credentials "
                f"(see .env.example)."
            )

    def should_auto_export(self) -> bool:
        """True only when auto-export is enabled AND a provider is actually configured.

        Both conditions matter: `auto_export: true` with no provider would otherwise have
        the orchestrator invoke an export that can only ever report "not projected", once
        per stage, for nothing.
        """
        return bool(self.auto_export) and self.provider_name() is not None

    def provider_name(self) -> str | None:
        """The configured provider key, or None when no vendor is selected.

        `choice` remains the field of record so every existing config keeps working:
        "git" still resolves to the gh-based adapter. Any other non-sentinel string is
        treated as a provider key and looked up in the registry.
        """
        value = self.choice.value if isinstance(self.choice, ExchangeChoice) else str(self.choice)
        if value in (ExchangeChoice.UNSET.value, ExchangeChoice.NONE.value,
                     ExchangeChoice.DECIDE_LATER.value):
            return None
        return value
