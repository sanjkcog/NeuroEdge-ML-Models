"""One simulator runtime per scenario run (Group B Tasks B4/B5; design §3, D-2/D-7).

``run_scenario(manifest)`` loads a bundle, starts only the adapters it declares, plays the
timeline on the virtual clock, and writes everything to the run log. All agents of the use case
share this one process -- one clock, one entity store, one ordered log (D-7); ``hub=<id>`` runs a
single hub's slice plus ``shared`` as a debug mode (§9.4).

Emission reuses the transport layer where one exists (mqtt via ``paho``), and posts webhooks
directly -- **raw payloads on the wire**, never the replay-engine ``Record`` envelope: the agent
side subscribes to derived-event shapes (``{"battery_soh": 22}``), and wrapping them would change
what the trigger filter sees.
"""

from __future__ import annotations

import json
import random
import sys
import threading
from pathlib import Path
from typing import Any
from typing import Optional

from .api_stub import ApiStubServer
from .fixtures import FixtureEntry
from .fixtures import FixtureStore
from .fixtures import ManifestError
from .fixtures import SimManifest
from .fixtures import SimRole
from .mcp_face import MCP_PATH_PREFIX
from .mcp_face import McpFace
from .mcp_face import load_mcp_responses
from .mcp_face import load_mcp_servers
from .model_face import ModelResponses
from .model_face import load_model_responses
from .scenario import ScenarioBundle
from .scenario import TimelineEvent
from .queue_capture import QueueCapture
from .scenario import load_scenario
from .sql_seed import seed_sqlite
from .simcore import EntityStore
from .simcore import RunLog
from .simcore import VirtualClock
from .stub_server import FeedBuffer
from .stub_server import StubServer


#: A run's own artefacts, beside the bundle: the port map, the run log, the scenario database.
#: Generated, and truncated by the host at the start of each run -- nothing authored belongs here.
RUN_DIR_NAME = "run"

#: The scenario's database, built from the bundle's seed CSVs at start (ADR-0038 D-5 / FR-11).
#: Lives under ``run/`` because it is derived: it is rebuilt from the CSVs every run, so editing it
#: directly would be editing something the next run discards.
SCENARIO_DB_FILENAME = "scenario.sqlite"

#: The scope name for systems several hubs legitimately call. Its sim runs in its OWN process,
#: exactly once -- never one copy inside each hub's process.
SHARED_SCOPE = "shared"


def port_map_filename(scope: Optional[str]) -> str:
    """Where one process records what it bound.

    🔴 **One file per process, not one per scenario.** With a simulator per hub (ADR-0038 D-4)
    every process would otherwise write the same ``ports.json`` and clobber the others', so the
    map would describe whichever process happened to finish last. The host reads the file for the
    scope it launched.
    """
    return f"ports.{scope or 'all'}.json"


def run_log_filename(scope: Optional[str]) -> str:
    """Where one process writes its ordered run log, under ``run/`` beside its port map.

    Scoped for the same reason as :func:`port_map_filename`: the log is truncated when a run
    starts, so with a simulator per hub a single shared file would be wiped by whichever
    process started last.
    """
    return f"run.{scope or 'all'}.log.jsonl"


def _model_entries(system: Any) -> list:
    """One system's canned model answers, as raw entries for :class:`ModelResponses`.

    Read through the same loader the face uses, so a malformed file is refused identically whether
    it is loaded here or directly -- one parser, one set of error messages.
    """
    face = load_model_responses(system.models_file)
    return [
        {"model_ref": model_ref, "prompt_fingerprint": fingerprint, "returns": returns}
        for (model_ref, fingerprint), returns in face.entries()
    ]


def _load_fixtures(system: Any) -> tuple:
    """One system's fixture entries, from the file its ``sim.yaml`` names.

    Accepts either a bare list or ``{"fixtures": [...]}`` -- the second is the shape a human
    reaches for when they want to add a comment key beside the data, and refusing it would be a
    rule with no purpose. Anything else is refused by name rather than read as "no fixtures":
    a malformed file silently treated as empty reports "nothing configured" for a file full of it.
    """
    if system.fixtures_file is None:
        return ()
    try:
        loaded = json.loads(Path(system.fixtures_file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"fixtures file '{system.fixtures_file}' is unreadable: {exc}") from exc
    entries = loaded.get("fixtures") if isinstance(loaded, dict) else loaded
    if not isinstance(entries, list):
        raise ManifestError(
            f"fixtures file '{system.fixtures_file}' must hold a list of fixtures, "
            "or an object with a 'fixtures' list"
        )
    return tuple(FixtureEntry.from_dict(entry) for entry in entries)


class ScenarioRunner:
    """Owns every adapter of one run; ``run()`` is start -> play -> stop."""

    def __init__(self, bundle: ScenarioBundle, hub: Optional[str] = None) -> None:
        #: What this process was asked to serve: one hub, ``shared``, or the whole scenario.
        self.scope = hub
        self.bundle = bundle.slice_for(None if hub == SHARED_SCOPE else hub)
        self.run_log = RunLog(self.bundle.root / RUN_DIR_NAME / run_log_filename(hub))
        self.entities = EntityStore()
        if self.bundle.entities_file is not None:
            self.entities.load_entities_csv(self.bundle.entities_file)
        self.rng = random.Random(self.bundle.seed)
        #: One lock for the one shared RNG (review H-5) -- passed to every stub.
        self.rng_lock = threading.Lock()
        self.clock = VirtualClock(self.bundle.compression)
        #: Feed name -> buffer, shared across every stub so a feed declared on one hub's stub can
        #: be filled by any timeline row (the entity-coherence rule, applied to feeds).
        self.feeds: dict[str, FeedBuffer] = {}
        self.stubs: dict[str, ApiStubServer] = {}
        self._mqtt_clients: dict[tuple, Any] = {}
        #: ``{table: row_count}`` seeded at start; empty when the bundle declares no seed CSVs.
        self.database_tables: dict = {}
        #: ``{server_id: url}`` -- where each simulated tool server answers, filled at start.
        self.tool_server_urls: dict = {}
        #: What tools published, per topic (ADR-0038 D-5 / FR-08). Built from every section's
        #: `capture_topics`, so a scenario that declares none captures nothing and costs nothing.
        self.queue_capture = QueueCapture(
            [topic for _scope, adapters in self._sections_for(bundle, hub) for topic in adapters.capture_topics],
            run_log=self.run_log,
        )
        self._capture_client: Any = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ lifecycle

    @staticmethod
    def _sections_for(bundle: ScenarioBundle, hub: Optional[str]) -> list:
        """The sections a slice will run, computed before ``self.bundle`` exists.

        Needed because the capture sink is built in ``__init__`` from the declared topics, and the
        slice it must cover is the one this process is about to serve -- not the whole scenario.
        """
        sliced = bundle.slice_for(None if hub == SHARED_SCOPE else hub)
        return [(SHARED_SCOPE, sliced.shared)] + list(sliced.hubs.items())

    def _sections(self) -> list:
        """``(scope, adapters)`` for everything this slice runs -- ``shared`` first, then hubs."""
        return [(SHARED_SCOPE, self.bundle.shared)] + list(self.bundle.hubs.items())

    def _sim_sections(self) -> list:
        """Which sections get a **sim** in THIS process (ADR-0038 D-4).

        🔴 **Deliberately narrower than :meth:`_sections`, and the difference is a real bug it
        fixes.** ``slice_for`` keeps ``shared`` in every hub's slice -- correct for the ``api:``
        adapters, which have always worked that way -- but starting the *shared sim* in every hub's
        process would spawn N copies of it, all racing to bind one declared port. The first would
        win and the rest would die with "address already in use" before ever reaching their own
        hub's port. ``scenario.yaml`` says shared systems are "simulated once, in their own
        process"; this is what makes that true rather than aspirational.
        """
        if self.scope == SHARED_SCOPE:
            return [(SHARED_SCOPE, self.bundle.shared)]
        if self.scope is None:
            return self._sections()
        return [(self.scope, self.bundle.hubs[self.scope])]

    def _start_hub_sim(self, scope: str, adapters: Any) -> Optional[StubServer]:
        """One server for one hub's whole simulated world (ADR-0038 D-4/D-5).

        🔴 **One process per hub, one port per hub, every system that hub fronts behind it.** Not
        one server per system: the workflow this exists to serve is a person typing an address into
        a config and later typing the real one back, and a hub whose five systems answered on five
        ports would need five such edits to go real. Systems are told apart by the address *inside*
        the port -- a route path, or a ``/<role>/<capability>`` pair whose role is the system id.
        """
        if not adapters.systems:
            return None
        routes: list[dict] = []
        roles: list = []
        model_entries: list = []
        tool_servers: list = []
        tool_responses: dict = {}
        for system in adapters.systems:
            routes.extend(system.routes)
            roles.append(SimRole(id=system.id, description=system.description, fixtures=_load_fixtures(system)))
            if system.models_file is not None:
                # Merged across the hub's systems on purpose: `model_ref` is globally unique by
                # ADR-0005's pin, so two systems naming the same one mean the same artifact -- and
                # `ModelResponses` refuses a duplicate key rather than picking a winner.
                model_entries.extend(_model_entries(system))
            if system.mcp_dir is not None:
                # Merged the same way, and `McpFace` refuses a duplicate server id for the same
                # reason: two systems each holding their own copy of one tool server are free to
                # advertise different surfaces, which is the split brain the loader exists to stop.
                tool_servers.extend(load_mcp_servers(system.mcp_dir))
                for server_id, fixtures in load_mcp_responses(system.mcp_dir).items():
                    tool_responses.setdefault(server_id, []).extend(fixtures)
        mcp = (
            McpFace(
                tuple(tool_servers),
                {server_id: tuple(fixtures) for server_id, fixtures in tool_responses.items()},
                name=f"{scope}.sim",
                rng=self.rng,
                rng_lock=self.rng_lock,
            )
            if tool_servers
            else None
        )
        stub_kwargs: dict = {}
        if self.bundle.caller_key:
            # 🔴 Passed only when the bundle declares one, so a bundle that says nothing keeps the
            # server's own default rather than being handed an empty string that matches no key.
            # The simulator has accepted this parameter since it was written and nothing ever set
            # it -- see `ScenarioBundle.caller_key` for what that cost.
            stub_kwargs["caller_key"] = self.bundle.caller_key
        stub = StubServer(
            f"{scope}.sim",
            routes=routes,
            store=FixtureStore(SimManifest(scenario=self.bundle.name, roles=tuple(roles))),
            models=ModelResponses(model_entries) if model_entries else None,
            mcp=mcp,
            entities=self.entities,
            run_log=self.run_log,
            rng=self.rng,
            feeds=self.feeds,
            port=adapters.port,
            rng_lock=self.rng_lock,
            **stub_kwargs,
        )
        stub.start()
        if mcp is not None:
            # 🔴 Recorded for the same reason the ports and the DSN are: this is the address the
            # bundle's overlay puts in front of a tool-server capability, and one nobody can
            # discover is one nobody can dial. Written only after `start()`, so an OS-assigned port
            # is the bound one rather than 0.
            for server_id in mcp.server_ids():
                self.tool_server_urls[server_id] = f"{stub.base_url}/{MCP_PATH_PREFIX}/{server_id}"
        return stub

    def _seed_database(self) -> dict:
        """Build the scenario's SQLite from every system's seed CSVs (ADR-0038 D-5 / FR-11).

        🔴 **A real file with the scenario's data in it, not a protocol fake.** The read transport
        opens SQLite read-only, so the honest simulation is a database -- which is why `sql_seed`
        was written and then, for two ADRs, never called. This is the call.

        Returns ``{table: row_count}`` so the run log can say what was seeded; an empty dict means
        no system declared a seed directory, which is legal and common.
        """
        seeded: dict = {}
        seed_dirs = [system.seed_dir for _scope, system in self.bundle.systems() if system.seed_dir is not None]
        if not seed_dirs:
            return seeded
        run_dir = self.bundle.root / RUN_DIR_NAME
        run_dir.mkdir(parents=True, exist_ok=True)
        database = run_dir / SCENARIO_DB_FILENAME
        for seed_dir in seed_dirs:
            # Merged into one database on purpose: a hub's query joins across the systems it
            # fronts, and one file per system would make that unexpressible. `seed_sqlite` names
            # each table after its CSV, so two systems can only collide by naming a table the same
            # thing -- which is a bundle-authoring mistake worth surfacing as a real SQL error
            # rather than hiding behind separate files.
            seeded.update(seed_sqlite(seed_dir, database))
        self.run_log.append("database_seeded", path=str(database), tables=seeded)
        return seeded

    def start(self) -> dict[str, str]:
        """Start every declared stub; returns ``{"<scope>.<name>": base_url}``.

        Two shapes coexist deliberately. ``api:`` declarations are the original per-adapter stubs
        and keep their own ports -- existing bundles must not change meaning. ``sim:`` declarations
        (ADR-0038) give a hub **one** server for every system it fronts.
        """
        endpoints: dict[str, str] = {}
        self.database_tables = self._seed_database()
        for scope, adapters in self._sections():
            for decl in adapters.api:
                stub = ApiStubServer(
                    name=f"{scope}.{decl.name}",
                    routes=decl.routes,
                    entities=self.entities,
                    run_log=self.run_log,
                    rng=self.rng,
                    feeds=self.feeds,
                    port=decl.port,
                    rng_lock=self.rng_lock,
                )
                stub.start()
                self.stubs[f"{scope}.{decl.name}"] = stub
                endpoints[f"{scope}.{decl.name}"] = stub.base_url
                self.run_log.append("stub_started", stub=f"{scope}.{decl.name}", base_url=stub.base_url)
        for scope, adapters in self._sim_sections():
            hub_sim = self._start_hub_sim(scope, adapters)
            if hub_sim is not None:
                self.stubs[f"{scope}.sim"] = hub_sim
                endpoints[f"{scope}.sim"] = hub_sim.base_url
                self.run_log.append(
                    "stub_started",
                    stub=f"{scope}.sim",
                    base_url=hub_sim.base_url,
                    systems=[system.id for system in adapters.systems],
                )
        self._start_queue_capture()
        self._write_port_map(endpoints)
        return endpoints

    def _on_captured_message(self, _client: Any, _userdata: Any, message: Any) -> None:
        """Record one delivered message, refusing loudly without killing the capture.

        🔴 **The guard is load-bearing, and it was missing.** `paho`'s `_handle_on_message` logs a
        callback exception and then **re-raises** it unless `suppress_exceptions` is set; the raise
        propagates out of `loop_forever` into `_thread_main`, which has no `except`. So an
        `UndeclaredTopicError` raised here killed the network thread outright -- capture stopped for
        **every** topic, silently, with only the start line in the run log and a bare traceback on
        stderr. A deliberate refusal became a total, invisible failure.

        The refusal stays loud; it is simply recorded rather than thrown into a thread that cannot
        survive it. `suppress_exceptions = True` would also have stopped the death, but it would
        have swallowed the refusal too -- and the refusal is the finding.
        """
        try:
            self.queue_capture.record(message.topic, message.payload)
        except Exception as exc:  # noqa: BLE001 - a bad message must not end the capture
            self.run_log.append("queue_capture_refused", topic=getattr(message, "topic", "?"), reason=str(exc))
            print(f"[scenario] warning: {exc}", file=sys.stderr)

    def _start_queue_capture(self) -> None:
        """Subscribe to the declared topics so a tool's publish is observed (FR-08).

        🔴 Subscribes to the DECLARED topics one at a time, never to ``#``. A wildcard would record
        whatever arrived, which makes a capability that published to the wrong topic
        indistinguishable from one that published correctly -- the exact defect this capture exists
        to catch.

        Degrades loudly and keeps serving: a bundle can declare capture topics on a machine with no
        broker, and taking the whole simulator down for the half that needs one would make every
        other face unusable for want of `paho`.
        """
        topics = self.queue_capture.declared_topics
        if not topics:
            return
        decl = self.bundle.shared.mqtt or next(
            (adapters.mqtt for adapters in self.bundle.hubs.values() if adapters.mqtt is not None), None
        )
        if decl is None:
            print(
                "[scenario] warning: capture_topics declared but no mqtt broker is configured; "
                "nothing will be captured",
                file=sys.stderr,
            )
            return
        try:
            import paho.mqtt.client as mqtt  # lazy, matching the emit path  # pylint: disable=import-outside-toplevel

            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            client.on_message = self._on_captured_message
            client.connect(decl.host, decl.port)
            for topic in topics:
                client.subscribe(topic)
            client.loop_start()
            self._capture_client = client
            self.run_log.append("queue_capture_started", topics=list(topics))
        except Exception as exc:  # noqa: BLE001 - a missing broker must not take the run down
            print(f"[scenario] warning: queue capture could not start: {exc}", file=sys.stderr)

    def _write_port_map(self, endpoints: dict) -> None:
        """Record where everything actually bound, in ``run/ports.<scope>.json`` (see :func:`port_map_filename`).

        🔴 Written for **declared and OS-assigned ports alike**, and that is the point: ``port: 0``
        exists so CI and parallel runs need not reserve numbers, but an address nobody can discover
        is an address nobody can dial. The host reads this file rather than guessing, so the two
        cases differ in the manifest and nowhere else.

        A run's own artefacts only -- ``run/`` is generated, and a failure to write it must not
        take down a simulator that is otherwise serving correctly.
        """
        run_dir = self.bundle.root / RUN_DIR_NAME
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "scenario": self.bundle.name,
                # The DSN a `db_query` binding points at. Recorded beside the ports for the same
                # reason: an address nobody can discover is an address nobody can dial.
                "database": str(self.bundle.root / RUN_DIR_NAME / SCENARIO_DB_FILENAME)
                if self.database_tables
                else None,
                "endpoints": dict(sorted(endpoints.items())),
                # Where each simulated tool server answers. Kept apart from `endpoints` because it
                # is keyed by the server id a capability's binding names, not by scope and stub.
                "tool_servers": dict(sorted(self.tool_server_urls.items())),
                "ports": {
                    name: stub.port for name, stub in sorted(self.stubs.items()) if stub.port  # bound port
                },
            }
            (run_dir / port_map_filename(self.scope)).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            print(f"[scenario] warning: could not write {port_map_filename(self.scope)}: {exc}", file=sys.stderr)

    def play(self) -> int:
        """Play the timeline to its end (or until ``request_stop``). Returns rows emitted."""
        self.clock.start()
        emitted = 0
        for event in self.bundle.timeline:
            if not self.clock.wait_until(event.offset_ms, stop=self._stop):
                break
            self._dispatch(event)
            emitted += 1
        return emitted

    def request_stop(self) -> None:
        self._stop.set()

    def stop(self) -> None:
        # Every teardown individually guarded (review H-4): one stub failing to close must not
        # leak the ports and threads of every stub after it -- the engine's _safe_close rule.
        for name, stub in self.stubs.items():
            try:
                stub.stop()
            except Exception as exc:  # noqa: BLE001 - teardown must not raise
                print(f"[scenario] warning: stub {name} close failed: {exc}", file=sys.stderr)
        if self._capture_client is not None:
            try:
                self._capture_client.loop_stop()
                self._capture_client.disconnect()
            except Exception:  # noqa: BLE001 - teardown must not raise (engine._safe_close rule)
                pass
            self._capture_client = None
        for client in self._mqtt_clients.values():
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:  # noqa: BLE001 - teardown must not raise (engine._safe_close rule)
                pass
        self._mqtt_clients.clear()

    def serve_until_stopped(self) -> None:
        """Keep the stub servers answering after the timeline has played (review C-2).

        The timeline is the *push* half of a scenario; the stubs are the *pull* half, and agents
        keep calling them for the life of the run -- a simulator that exits when the last timeline
        row plays takes every endpoint down mid-run. Blocks until :meth:`request_stop` (or
        Ctrl-C at the CLI)."""
        while not self._stop.wait(0.5):
            pass

    def run(self, serve: bool = False) -> dict[str, Any]:
        """Start -> play -> (optionally serve until stopped) -> stop.

        ``serve=True`` is what the orchestrator-launched process uses: the run outlives its
        timeline. ``serve=False`` plays the timeline and tears down -- the batch/test mode."""
        endpoints = self.start()
        try:
            emitted = self.play()
            self.run_log.append("timeline_complete", scenario=self.bundle.name, events_emitted=emitted, serving=serve)
            if serve:
                self.serve_until_stopped()
        finally:
            self.stop()
        summary = {
            "scenario": self.bundle.name,
            "endpoints": endpoints,
            "events_emitted": emitted,
            "run_log": str(self.run_log.path),
        }
        self.run_log.append("run_complete", **{k: v for k, v in summary.items() if k != "run_log"})
        return summary

    # ------------------------------------------------------------------ dispatch

    def _dispatch(self, event: TimelineEvent) -> None:
        if event.adapter == "feed":
            self.feeds.setdefault(event.target, FeedBuffer()).release(event.payload)
            self.run_log.append("emit", adapter="feed", hub=event.hub, target=event.target, payload=event.payload)
            return
        if event.adapter == "webhook":
            self._post_webhook(event)
            return
        if event.adapter == "mqtt":
            self._publish_mqtt(event)
            return
        raise AssertionError(f"unreachable: loader validated adapter {event.adapter!r}")

    def _post_webhook(self, event: TimelineEvent) -> None:
        from .transports import _require_requests  # lazy, same convention as the transports

        requests = _require_requests()
        try:
            response = requests.post(event.target, json=event.payload, timeout=10)
            self.run_log.append(
                "emit",
                adapter="webhook",
                hub=event.hub,
                target=event.target,
                payload=event.payload,
                status=response.status_code,
            )
        except Exception as exc:  # noqa: BLE001 - one dead receiver must not kill the timeline
            self.run_log.append("emit_failed", adapter="webhook", hub=event.hub, target=event.target, error=str(exc))

    def _publish_mqtt(self, event: TimelineEvent) -> None:
        adapters = self.bundle.hubs.get(event.hub)
        mqtt_decl = adapters.mqtt if adapters is not None and adapters.mqtt is not None else self.bundle.shared.mqtt
        if mqtt_decl is None:
            self.run_log.append(
                "emit_failed",
                adapter="mqtt",
                hub=event.hub,
                target=event.target,
                error=f"hub '{event.hub}' declares no mqtt broker in the manifest",
            )
            return
        key = (mqtt_decl.host, mqtt_decl.port)
        try:
            client = self._mqtt_clients.get(key)
            if client is None:
                try:
                    import paho.mqtt.client as mqtt  # lazy
                except ImportError as exc:
                    raise RuntimeError("paho-mqtt is required for mqtt timeline rows") from exc
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
                client.connect(mqtt_decl.host, mqtt_decl.port)
                client.loop_start()
                self._mqtt_clients[key] = client
            topic = f"{mqtt_decl.topic_prefix}{event.target}"
            client.publish(topic, json.dumps(event.payload, ensure_ascii=False), qos=1)
            self.run_log.append("emit", adapter="mqtt", hub=event.hub, target=topic, payload=event.payload)
        except Exception as exc:  # noqa: BLE001 - one dead broker must not kill the timeline (same rule as webhook)
            self.run_log.append("emit_failed", adapter="mqtt", hub=event.hub, target=event.target, error=str(exc))


def run_scenario(manifest_path: Path, hub: Optional[str] = None, serve: bool = False) -> dict[str, Any]:
    """Load and run one bundle end to end. The CLI's `--scenario` entry point.

    ``serve=True`` keeps the stub servers up after the timeline plays (review C-2) -- the mode
    the orchestrator's launched subprocess runs in."""
    return ScenarioRunner(load_scenario(Path(manifest_path)), hub=hub).run(serve=serve)
