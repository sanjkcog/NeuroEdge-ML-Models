"""Scenario bundle model + loader (simulator-mvp Group B Task B1; design §4, §9.4, D-3/D-9).

One directory = one runnable scenario. The manifest (``scenario.yaml``) is a thin index that
**references files, never embeds content** (D-9): entity tables and timelines are CSV, route
tables are JSON. Adapters are declared per hub, with a ``shared:`` section for systems more than
one hub legitimately touches (D-7 revised) -- ``--hub <id>`` runs one hub's slice plus shared.

Manifest shape::

    scenario: pump_bearing_failure
    seed: 42
    clock: { compression: 60 }
    entities: entities.csv            # optional
    timeline: events.csv              # optional
    hubs:
      plant:
        api:
          - { name: cmms, port: 9101, routes: stubs/cmms.routes.json }
        mqtt: { host: 127.0.0.1, port: 1883 }
    shared:
      api: []

Timeline CSV columns: ``offset_ms, hub, adapter, target, payload`` -- ``adapter`` is one of
``mqtt`` (target = topic), ``webhook`` (target = URL), ``feed`` (target = feed name served by an
api stub's feed route); ``payload`` is a JSON object string.

A hub may also declare the three things a per-hub simulator needs (ADR-0038 D-3/D-4)::

    hubs:
      dealer_north:
        port: 9102                       # declared, not assigned; 0 asks the OS
        sim: hubs/dealer_north/sim.yaml   # the systems THIS hub fronts
        env:                              # the endpoint overlay -- the simulation switch
          DEALER_NORTH_DMS_URL: http://127.0.0.1:9102

and ``sim.yaml`` names them::

    systems:
      - id: dealer_north_dms
        routes: routes/dms.routes.json
        fixtures: fixtures/dms.json

🔴 **An external system is simulated exactly once.** Two hubs declaring the same system ``id`` is
refused at load, naming both locations: two copies of one system are free to disagree, which is the
fixture equivalent of a split brain. Loud at load, never mid-run.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import Optional


class ScenarioError(ValueError):
    """A bundle that cannot run as declared -- always names what is wrong."""


#: Adapter keys a hub section may declare. Anything else is refused by name: a typo'd adapter
#: that silently starts nothing is the "declared signal source that never fires" defect class.
KNOWN_ADAPTERS = frozenset({"api", "mqtt"})

#: Keys a hub (or the ``shared``) section may carry beyond its adapters: its declared port, the
#: file naming the systems it simulates, and its endpoint overlay.
KNOWN_HUB_KEYS = KNOWN_ADAPTERS | frozenset({"port", "sim", "env", "capture_topics"})

#: Keys one entry of a ``sim.yaml`` ``systems:`` list may carry. Refused by name when misspelled --
#: a mistyped ``fixtures`` that silently configures nothing is the defect this file exists to catch.
KNOWN_SYSTEM_KEYS = frozenset({"id", "description", "routes", "fixtures", "seed", "models", "mcp"})

#: Timeline adapters -- where a timeline row can be sent.
KNOWN_TIMELINE_ADAPTERS = frozenset({"mqtt", "webhook", "feed"})


@dataclass
class ApiStubDecl:
    """One API stub server declaration."""

    name: str
    routes_file: Path
    port: int = 0  # 0 = OS-assigned; the runner reports the bound port
    routes: list[dict] = field(default_factory=list)


@dataclass
class MqttDecl:
    """One hub's broker address for timeline mqtt rows."""

    host: str = "127.0.0.1"
    port: int = 1883
    topic_prefix: str = ""


@dataclass
class SimSystem:
    """One external system a hub's simulator stands in for.

    The unit of the simulate-exactly-once invariant: ``id`` is what two hubs may not both claim.
    Every path is optional because a system is entitled to be simulated one way only -- a document
    store needs routes and no seed; a database needs a seed and no fixtures.
    """

    id: str
    description: str = ""
    routes_file: Optional[Path] = None
    fixtures_file: Optional[Path] = None
    seed_dir: Optional[Path] = None
    models_file: Optional[Path] = None
    #: The directory holding this system's tool-server face: a generated ``servers.json`` and an
    #: authored ``responses.json``. A directory rather than a file because the two halves have
    #: different owners -- see the loader.
    mcp_dir: Optional[Path] = None
    routes: list[dict] = field(default_factory=list)


@dataclass
class HubAdapters:
    """What one hub (or the shared section) declares: its adapters, its sim, and its address."""

    api: list[ApiStubDecl] = field(default_factory=list)
    mqtt: Optional[MqttDecl] = None
    #: The port this hub's simulator is *declared* at. 0 asks the OS -- see the module docstring.
    port: int = 0
    #: The ``sim.yaml`` this hub's systems were read from, kept for error messages that have to
    #: name where a duplicate system was configured.
    sim_file: Optional[Path] = None
    systems: list[SimSystem] = field(default_factory=list)
    #: Topics a tool of this hub is expected to publish to (ADR-0038 D-5 / FR-08). Declared so a
    #: publish to anything else is a loud failure rather than a message recorded under a topic
    #: nobody asked for -- which would make "published to the wrong topic" invisible.
    capture_topics: list = field(default_factory=list)
    #: The endpoint overlay: variable name -> address. The one mechanism that points a capability
    #: at this simulator, and the same field an operator edits to point it back at production.
    env: dict = field(default_factory=dict)


@dataclass
class TimelineEvent:
    """One row of the timeline."""

    offset_ms: float
    hub: str
    adapter: str
    target: str
    payload: dict


@dataclass
class ScenarioBundle:
    """A loaded, validated bundle."""

    name: str
    root: Path
    seed: int = 42
    compression: float = 1.0
    #: Which key inside the caller header names the caller, **in this host's own spelling**.
    #:
    #: 🔴 The simulator has always accepted this (``StubServer(caller_key=...)``, whose docstring
    #: names ``hub_id``/``tenant``/``branch`` as plausible host spellings) and nothing ever passed
    #: one, so every server ran on the default ``"caller"``. A host sending any other spelling had
    #: its caller resolve to the empty string on every call -- which is the *shared-fact* key, so
    #: caller-scoped fixtures silently fell back to the general answer and a bundle that looked
    #: configured was not. Measured against a real server before this field existed.
    #:
    #: It belongs to the bundle rather than to the simulator because the spelling is the host's
    #: fact, not the simulator's: naming a particular one in this package would be exactly the
    #: host vocabulary a generic asset must not carry.
    caller_key: str = ""
    hubs: dict[str, HubAdapters] = field(default_factory=dict)
    shared: HubAdapters = field(default_factory=HubAdapters)
    timeline: list[TimelineEvent] = field(default_factory=list)
    entities_file: Optional[Path] = None

    def env_for(self, hub: str) -> dict:
        """The endpoint overlay one hub's children see: the shared addresses plus its own.

        Shared entries are visible to every hub on purpose -- a system in ``shared/`` is one that
        several hubs legitimately call, so withholding its address would make it unreachable. A
        hub's own entry wins a collision, because the more specific statement is the deliberate one.
        """
        return {**self.shared.env, **(self.hubs[hub].env if hub in self.hubs else {})}

    def systems(self) -> list:
        """Every ``(location, system)`` pair in the bundle, hubs first then shared."""
        located = [(f"hubs.{hub_id}", system) for hub_id, hub in self.hubs.items() for system in hub.systems]
        return located + [("shared", system) for system in self.shared.systems]

    def slice_for(self, hub: Optional[str]) -> "ScenarioBundle":
        """The ``--hub`` view: that hub's adapters plus ``shared``, and only its timeline rows.
        ``None`` returns self (the full run)."""
        if hub is None:
            return self
        if hub not in self.hubs:
            raise ScenarioError(f"scenario '{self.name}' declares no hub '{hub}' (hubs: {sorted(self.hubs)})")
        return ScenarioBundle(
            name=self.name,
            root=self.root,
            seed=self.seed,
            compression=self.compression,
            # 🔴 Carried, and this is the line that matters most for it: the orchestrator runs ONE
            # process per hub, so every real run reaches its server through this slice. A rebuild
            # that dropped the key would leave the whole-scenario path working and every per-hub
            # path silently back on the default spelling -- the same silent miss, reachable only
            # in the configuration anybody actually uses.
            caller_key=self.caller_key,
            hubs={hub: self.hubs[hub]},
            shared=self.shared,
            timeline=[event for event in self.timeline if event.hub == hub],
            entities_file=self.entities_file,
        )


def _resolve_reference(raw: Any, *, base: Path, where: str, key: str, directory: bool = False) -> Optional[Path]:
    """One optional path from a manifest, checked to exist.

    Loud at load: a ``fixtures:`` line naming a file that is not there would otherwise surface
    mid-run as "no fixture configured", which reads as an authoring gap rather than a typo.
    """
    if raw is None:
        return None
    resolved = base / str(raw)
    if directory and not resolved.is_dir():
        raise ScenarioError(f"{where} '{key}' names a missing directory: {raw}")
    if not directory and not resolved.is_file():
        raise ScenarioError(f"{where} '{key}' names a missing file: {raw}")
    return resolved


def _load_routes_file(path: Path, *, where: str) -> list[dict]:
    routes_doc = json.loads(path.read_text(encoding="utf-8"))
    routes = routes_doc.get("routes") if isinstance(routes_doc, dict) else None
    if not isinstance(routes, list):
        raise ScenarioError(f"{where} routes file {path.name} must contain an object with a 'routes' list")
    return routes


def _load_sim_file(path: Path, *, where: str) -> list[SimSystem]:
    """The systems one hub fronts, read from its ``sim.yaml``.

    Paths inside are relative to the ``sim.yaml`` itself, so a hub directory can be copied whole
    from ``_base`` and moved between use cases without rewriting every reference.
    """
    import yaml  # lazy, mirroring the transports' import convention  # pylint: disable=import-outside-toplevel

    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(document, dict):
        raise ScenarioError(f"{where} sim file {path.name} must be a mapping")
    raw_systems = document.get("systems") or []
    if not isinstance(raw_systems, list):
        raise ScenarioError(f"{where} sim file {path.name}: 'systems' must be a list")

    base = path.parent
    systems: list[SimSystem] = []
    for entry in raw_systems:
        if not isinstance(entry, dict):
            raise ScenarioError(f"{where} sim file {path.name}: a system is {type(entry).__name__}, not a mapping")
        unknown = sorted(set(entry) - KNOWN_SYSTEM_KEYS)
        if unknown:
            raise ScenarioError(
                f"{where} sim file {path.name}: system declares unknown key(s) {unknown} -- "
                f"known: {sorted(KNOWN_SYSTEM_KEYS)}"
            )
        system_id = str(entry.get("id") or "")
        if not system_id:
            raise ScenarioError(f"{where} sim file {path.name}: a system has no 'id'")
        scope = f"{where} system '{system_id}'"
        routes_file = _resolve_reference(entry.get("routes"), base=base, where=scope, key="routes")
        systems.append(
            SimSystem(
                id=system_id,
                description=str(entry.get("description", "")),
                routes_file=routes_file,
                fixtures_file=_resolve_reference(entry.get("fixtures"), base=base, where=scope, key="fixtures"),
                seed_dir=_resolve_reference(entry.get("seed"), base=base, where=scope, key="seed", directory=True),
                models_file=_resolve_reference(entry.get("models"), base=base, where=scope, key="models"),
                # 🔴 A directory, not a file, and that is the derived/authored split made visible.
                # It holds `servers.json` (generated from what was discovered from the real servers,
                # never hand-written) beside `responses.json` (authored answers, never generated).
                # One key naming one file would have put both under one owner.
                mcp_dir=_resolve_reference(entry.get("mcp"), base=base, where=scope, key="mcp", directory=True),
                routes=_load_routes_file(routes_file, where=scope) if routes_file else [],
            )
        )
    return systems


def _load_env(raw: Any, *, where: str) -> dict:
    """The endpoint overlay's shape. Its *values* are guarded by the host that applies it.

    Shape only, deliberately: whether an address is a permitted one is a host policy question --
    the simulator is generic and has no opinion about which hosts a project may dial. What it can
    check is that the overlay is a flat map of variable names to strings, so a nested block does
    not silently overlay nothing.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ScenarioError(f"{where} 'env' must be a mapping of variable name -> address")
    overlay: dict = {}
    for name, value in raw.items():
        if isinstance(value, (dict, list)):
            raise ScenarioError(f"{where} env '{name}' is a {type(value).__name__}, not an address")
        overlay[str(name)] = str(value)
    return overlay


def _load_capture_topics(raw: Any, *, where: str) -> list:
    """The topics a tool of this section is expected to publish to (ADR-0038 D-5 / FR-08).

    🔴 **An MQTT wildcard is refused, and the reason is not pedantry.** The capture records under
    the topic it *declared*, so a subscription to ``neuroedge/+/containment`` would succeed and then
    every arriving message would carry a concrete topic that matches no declared key -- the sink
    would refuse message one, and (before the callback was guarded) that refusal killed the capture
    thread for every topic. Even guarded, a wildcard silently captures nothing, which is the
    "declared signal source that never fires" defect this loader exists to catch.

    It is also the ``#`` argument in smaller form: a wildcard makes "published to the wrong topic"
    indistinguishable from "published correctly", which is what declaring topics is *for*.
    """
    topics = []
    for topic in raw or []:
        text = str(topic)
        if "+" in text or "#" in text:
            raise ScenarioError(
                f"{where} capture_topics entry {text!r} contains an MQTT wildcard. The capture "
                "records under the topic it declared, so a wildcard subscribes successfully and "
                "then matches nothing that arrives. List the concrete topics instead."
            )
        topics.append(text)
    return topics


def _load_hub_adapters(section: Any, *, where: str, root: Path) -> HubAdapters:
    if section is None:
        return HubAdapters()
    if not isinstance(section, dict):
        raise ScenarioError(f"{where} must be a mapping of adapter kinds, got {type(section).__name__}")
    unknown = set(section) - KNOWN_HUB_KEYS
    if unknown:
        raise ScenarioError(f"{where} declares unknown key(s) {sorted(unknown)} -- known: {sorted(KNOWN_HUB_KEYS)}")
    adapters = HubAdapters(
        port=int(section.get("port", 0)),
        env=_load_env(section.get("env"), where=where),
        capture_topics=_load_capture_topics(section.get("capture_topics"), where=where),
    )
    if section.get("sim"):
        sim_file = root / str(section["sim"])
        if not sim_file.is_file():
            raise ScenarioError(f"{where} 'sim' names a missing file: {section['sim']}")
        adapters.sim_file = sim_file
        adapters.systems = _load_sim_file(sim_file, where=where)
    for decl in section.get("api") or []:
        routes_file = root / str(decl["routes"])
        if not routes_file.is_file():
            raise ScenarioError(f"{where} api stub '{decl.get('name')}' names a missing routes file: {decl['routes']}")
        routes_doc = json.loads(routes_file.read_text(encoding="utf-8"))
        routes = routes_doc.get("routes")
        if not isinstance(routes, list):
            raise ScenarioError(f"routes file {decl['routes']} must contain an object with a 'routes' list")
        adapters.api.append(
            ApiStubDecl(
                name=str(decl.get("name", routes_file.stem)),
                routes_file=routes_file,
                port=int(decl.get("port", 0)),
                routes=routes,
            )
        )
    if "mqtt" in section and section["mqtt"] is not None:
        mqtt = section["mqtt"]
        adapters.mqtt = MqttDecl(
            host=str(mqtt.get("host", "127.0.0.1")),
            port=int(mqtt.get("port", 1883)),
            topic_prefix=str(mqtt.get("topic_prefix", "")),
        )
    return adapters


def _load_timeline(path: Path) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), start=2):
            adapter = (row.get("adapter") or "").strip()
            if adapter not in KNOWN_TIMELINE_ADAPTERS:
                raise ScenarioError(
                    f"{path.name} line {line_number}: adapter {adapter!r} is not one of "
                    f"{sorted(KNOWN_TIMELINE_ADAPTERS)}"
                )
            try:
                payload = json.loads(row.get("payload") or "{}")
            except ValueError as exc:
                raise ScenarioError(f"{path.name} line {line_number}: payload is not valid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ScenarioError(f"{path.name} line {line_number}: payload must be a JSON object")
            events.append(
                TimelineEvent(
                    offset_ms=float(row.get("offset_ms") or 0),
                    hub=(row.get("hub") or "").strip(),
                    adapter=adapter,
                    target=(row.get("target") or "").strip(),
                    payload=payload,
                )
            )
    events.sort(key=lambda event: event.offset_ms)
    return events


def _refuse_duplicate_systems(bundle: ScenarioBundle) -> None:
    """🔴 One external system, simulated once.

    Two hubs each holding their own copy of the same system are free to answer differently, and
    nothing in a run would say which copy was consulted -- the fixture equivalent of a split brain.
    Refused at load, naming **both** locations, because the fix is to delete one of them and the
    author needs to know which two to choose between.
    """
    seen: dict = {}
    for location, system in bundle.systems():
        if system.id in seen:
            raise ScenarioError(
                f"system '{system.id}' is simulated twice, in {seen[system.id]} and in {location}. "
                "An external system is simulated exactly once -- in the sim of the hub that fronts "
                "it, or in 'shared' when several hubs call it. Two copies can disagree, and a run "
                "would not say which answered."
            )
        seen[system.id] = location


def load_scenario(manifest_path: Path) -> ScenarioBundle:
    """Load and validate one bundle from its ``scenario.yaml``.

    :raises ScenarioError: Anything that would make the run lie -- unknown adapter kinds,
        missing referenced files, malformed timeline rows. Loud at load, never mid-run.
    """
    import yaml  # lazy, mirroring the transports' import convention

    manifest_path = Path(manifest_path)
    if not manifest_path.is_file():
        raise ScenarioError(f"no scenario manifest at {manifest_path}")
    root = manifest_path.parent
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if not isinstance(manifest, dict) or not manifest.get("scenario"):
        raise ScenarioError(f"{manifest_path.name} must be a mapping with a 'scenario' name")

    clock = manifest.get("clock") or {}
    caller_key = manifest.get("caller_key")
    if caller_key is not None:
        # Refused rather than defaulted: a bundle that declares the key at all is stating that its
        # host spells the caller differently, and quietly falling back to the built-in spelling
        # would restore exactly the silent miss this field exists to end.
        if not isinstance(caller_key, str) or not caller_key.strip():
            raise ScenarioError("'caller_key' must be a non-empty string naming a key in the caller header")
        # 🔴 The delimiters are refused for the same reason, and the reason is not tidiness. The
        # header is `key=value;key=value`, and the parser splits on `;` then partitions on the
        # FIRST `=` -- so a parsed key can never itself contain either character. A `caller_key`
        # holding one is therefore guaranteed to match nothing, on every call, forever: precisely
        # the silent fall-back to the shared-fact answer this field was added to end, reachable
        # again through a typo. Raised in review of the fix; a validator that admits a value which
        # cannot work is a validator that only looks like one.
        offending = sorted({character for character in ("=", ";") if character in caller_key})
        if offending:
            raise ScenarioError(
                f"'caller_key' {caller_key!r} contains {offending}, which the caller header uses as "
                "delimiters -- a key spelled this way can never be parsed out of the header, so "
                "every caller-scoped fixture would silently fall back to the shared-fact answer."
            )
    bundle = ScenarioBundle(
        name=str(manifest["scenario"]),
        root=root,
        seed=int(manifest.get("seed", 42)),
        compression=float(clock.get("compression", 1.0)),
        caller_key=str(caller_key).strip() if caller_key else "",
    )

    hubs = manifest.get("hubs") or {}
    if not isinstance(hubs, dict):
        raise ScenarioError("'hubs' must be a mapping of hub id -> adapters")
    for hub_id, section in hubs.items():
        bundle.hubs[str(hub_id)] = _load_hub_adapters(section, where=f"hubs.{hub_id}", root=root)
    bundle.shared = _load_hub_adapters(manifest.get("shared"), where="shared", root=root)
    _refuse_duplicate_systems(bundle)

    if manifest.get("entities"):
        entities_file = root / str(manifest["entities"])
        if not entities_file.is_file():
            raise ScenarioError(f"'entities' names a missing file: {manifest['entities']}")
        bundle.entities_file = entities_file

    if manifest.get("timeline"):
        timeline_file = root / str(manifest["timeline"])
        if not timeline_file.is_file():
            raise ScenarioError(f"'timeline' names a missing file: {manifest['timeline']}")
        bundle.timeline = _load_timeline(timeline_file)

    return bundle
