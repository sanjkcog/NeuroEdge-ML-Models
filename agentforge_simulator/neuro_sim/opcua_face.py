"""An OPC-UA egress face: the machine HMI an alert is supposed to reach (ADR-0029).

Every other face in this simulator stands in for something a hub **calls** or **publishes to**. This
one stands in for where a business action **lands**: an edge device decides "drift", publishes an
alert to a broker, and the use case's decision is "show the alarm on the machine's HMI via OPC-UA".
With no machine on the bench, that last hop had no evidence it ever happened -- the same gap broker
capture closed for publishes (ADR-0038 D-5 / FR-08), one step further downstream.

So this face is an **OPC-UA server whose nodes are driven by alert messages it receives from MQTT**
-- a stand-in for the real MQTT-to-OPC-UA gateway or PLC write -- and it records every alert and
every node write in the run log, so a test (or a Virtual Run) can assert "the alert reached the HMI".

🔴 **Declared topics, no wildcards, and an undeclared topic is a loud failure** -- queue capture's
discipline, reused rather than restated (:class:`~neuro_sim.queue_capture.UndeclaredTopicError`). A
bridge subscribed to ``#`` would light the HMI for an alert published to the wrong topic, which is
exactly the defect a rehearsal exists to catch.

🔴 **A payload without a readable score is a malformed alert, never an alarm showing 0.** Rendering
a missing score as ``0.0`` would put a confident-looking number on an HMI for a message that carried
none. The alert is recorded as malformed and no node is written.

**The payload fields read, and nothing else** (each name is configurable under ``fields:``):

    score          required -- a finite number, or a numeric string. Default keys tried in order:
                   ``score``, then ``drift_score`` (the edge app's cycle-event spelling)
    message        optional -- shown verbatim as the alarm text when present
    timestamp_ns   optional -- epoch nanoseconds; absent or unreadable falls back to the receive
                   time, and the run log says which one was used
    device_id      optional -- folded into a composed alarm text
    use_case_id    optional -- folded into a composed alarm text

**The nodes** (names configurable under ``nodes:``), each ``ns=<idx>;s=<object>.<name>``:

    DriftAlarm   Boolean   True on every alert; cleared by an operator Ack
    DriftScore   Double    the alert's score
    AlarmText    String    ``message``, or a text composed from score / device / use case
    LastAlertTs  DateTime  ``timestamp_ns`` as UTC, else the receive time
    AlertCount   UInt32    alerts accepted since start (malformed ones are not counted)
    Ack          Boolean   the ONE client-writable node: writing True clears DriftAlarm, so an
                           operator acknowledgement can be rehearsed. A new alert resets it to False

The asyncua half is imported lazily, so a scenario that declares no face never needs the package,
and one that does fails at start with an install hint rather than a bare ImportError.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import sys
import threading
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Callable
from typing import Optional
from urllib.parse import urlparse

from .queue_capture import UndeclaredTopicError

#: Loopback, like every stub this simulator serves (``stub_server`` binds 127.0.0.1). The Device
#: repo's OPC-UA simulator binds 0.0.0.0, but that one runs inside a device container; this one runs
#: on an author's machine, and a writable node on every interface is not a default worth having.
#: Set ``endpoint: opc.tcp://0.0.0.0:4840/...`` explicitly to reach it from another host.
DEFAULT_ENDPOINT = "opc.tcp://127.0.0.1:4840/neuroedge/hmi"

DEFAULT_NAMESPACE = "urn:neuroedge:sim:hmi"

#: The object the nodes hang under, and the prefix of every string node id.
DEFAULT_OBJECT = "Hmi"

#: Payload field -> the keys tried for it, in order. Lists so a spelling the edge app actually uses
#: (``drift_score``) is accepted without the tolerance being implicit: every accepted key is here.
DEFAULT_FIELDS: dict = {
    "score": ("score", "drift_score"),
    "message": ("message",),
    "timestamp_ns": ("timestamp_ns",),
    "device_id": ("device_id",),
    "use_case_id": ("use_case_id",),
}

#: Node role -> default browse name. The roles are fixed; their names are the author's.
DEFAULT_NODES: dict = {
    "alarm": "DriftAlarm",
    "score": "DriftScore",
    "text": "AlarmText",
    "last_alert_ts": "LastAlertTs",
    "alert_count": "AlertCount",
    "ack": "Ack",
}

#: Keys an ``opcua_face:`` block may carry. Anything else is refused by name -- a misspelled
#: ``topic:`` that silently bridged nothing is the "declared signal source that never fires" defect.
KNOWN_FACE_KEYS = frozenset({"endpoint", "namespace", "object", "broker", "topics", "fields", "nodes"})

#: A browse name that is also safe inside a string node id and readable in any OPC-UA client.
_NODE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")

#: The Ack node is watched through a server-side subscription; 50 ms keeps an operator's write and
#: the alarm clearing visibly simultaneous without busy-polling.
_ACK_SAMPLING_MS = 50

#: How long a caller waits for the server thread to come up, or for a node write to land. asyncua
#: loads its whole standard address space on init, which takes around a second on a laptop.
_START_TIMEOUT_S = 30.0
_WRITE_TIMEOUT_S = 10.0

#: How long a scenario waits for a bridge's subscriptions to be acknowledged before the timeline
#: plays. Without it, an alert the timeline publishes in its first moments reaches the broker before
#: the bridge has subscribed and is lost -- observed on the first run of the example bundle.
_SUBSCRIBE_WAIT_S = 5.0

#: The value LastAlertTs holds before any alert: the OPC-UA DateTime epoch, which clients render as
#: "no time" rather than as a plausible-looking moment.
_NO_TIME = datetime(1601, 1, 1, tzinfo=timezone.utc)


class OpcUaFaceError(ValueError):
    """A face declaration that cannot run as written, or a server that would not start."""


class MalformedAlertError(ValueError):
    """An alert that cannot be shown honestly -- recorded, never rendered."""


# --------------------------------------------------------------------------- #
# declaration
# --------------------------------------------------------------------------- #


@dataclass
class OpcUaFaceConfig:
    """One ``opcua_face:`` block, validated."""

    topics: tuple
    endpoint: str = DEFAULT_ENDPOINT
    namespace: str = DEFAULT_NAMESPACE
    object_name: str = DEFAULT_OBJECT
    #: ``mqtt://host:port`` for the bridge, or ``None`` to use the section's own ``mqtt:`` broker.
    broker: Optional[str] = None
    fields: dict = field(default_factory=lambda: dict(DEFAULT_FIELDS))
    nodes: dict = field(default_factory=lambda: dict(DEFAULT_NODES))

    def host_port(self) -> tuple:
        """``(host, port)`` the server binds, parsed from :attr:`endpoint`."""
        parsed = urlparse(self.endpoint)
        return parsed.hostname or "", parsed.port if parsed.port is not None else 4840

    def node_id(self, role: str, namespace_index: int = 2) -> str:
        """The string node id a client addresses a role's node by."""
        return f"ns={namespace_index};s={self.object_name}.{self.nodes[role]}"


def _parse_topics(raw: Any, *, where: str) -> tuple:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        raise OpcUaFaceError(f"{where} 'topics' must be a non-empty list of MQTT topics to bridge")
    topics = []
    for topic in raw:
        text = str(topic).strip()
        # Refused for queue capture's reason (scenario._load_capture_topics): the bridge accepts a
        # message only on a topic it declared, so a wildcard subscribes and then matches nothing.
        if not text or "+" in text or "#" in text:
            raise OpcUaFaceError(
                f"{where} topic {text!r} is empty or contains an MQTT wildcard. The bridge accepts "
                "only the topics it declares, so list the concrete alert topics instead."
            )
        topics.append(text)
    return tuple(topics)


def _parse_fields(raw: Any, *, where: str) -> dict:
    fields = dict(DEFAULT_FIELDS)
    if raw is None:
        return fields
    if not isinstance(raw, dict):
        raise OpcUaFaceError(f"{where} 'fields' must map a payload field to its key (or list of keys)")
    unknown = sorted(set(raw) - set(DEFAULT_FIELDS))
    if unknown:
        raise OpcUaFaceError(f"{where} 'fields' names unknown field(s) {unknown} -- known: {sorted(DEFAULT_FIELDS)}")
    for name, keys in raw.items():
        candidates = (keys,) if isinstance(keys, str) else tuple(keys or ())
        if not candidates or not all(isinstance(key, str) and key for key in candidates):
            raise OpcUaFaceError(f"{where} field '{name}' must name a payload key or a non-empty list of keys")
        fields[name] = candidates
    return fields


def _parse_nodes(raw: Any, *, where: str) -> dict:
    nodes = dict(DEFAULT_NODES)
    if raw is None:
        return nodes
    if not isinstance(raw, dict):
        raise OpcUaFaceError(f"{where} 'nodes' must map a node role to its browse name")
    unknown = sorted(set(raw) - set(DEFAULT_NODES))
    if unknown:
        raise OpcUaFaceError(f"{where} 'nodes' names unknown role(s) {unknown} -- known: {sorted(DEFAULT_NODES)}")
    nodes.update({role: str(name) for role, name in raw.items()})
    for role, name in nodes.items():
        if not _NODE_NAME_RE.match(name):
            raise OpcUaFaceError(f"{where} node '{role}' has an unusable browse name {name!r}")
    if len(set(nodes.values())) != len(nodes):
        # Two roles on one node would make an Ack write and an alarm write the same write.
        raise OpcUaFaceError(f"{where} 'nodes' gives two roles the same browse name: {nodes}")
    return nodes


def parse_broker(url: str, *, where: str = "opcua_face") -> tuple:
    """``mqtt://host:port`` -> ``(host, port)``. The port defaults to 1883."""
    parsed = urlparse(url)
    if parsed.scheme != "mqtt" or not parsed.hostname:
        raise OpcUaFaceError(f"{where} 'broker' must look like mqtt://host:1883, got {url!r}")
    return parsed.hostname, parsed.port or 1883


def load_opcua_face_config(raw: Any, *, where: str) -> Optional[OpcUaFaceConfig]:
    """Validate one ``opcua_face:`` block, or ``None`` when the section declares none.

    :raises OpcUaFaceError: Loud at load, naming the key -- never a face that starts and bridges nothing.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise OpcUaFaceError(f"{where} must be a mapping")
    unknown = sorted(set(raw) - KNOWN_FACE_KEYS)
    if unknown:
        raise OpcUaFaceError(f"{where} declares unknown key(s) {unknown} -- known: {sorted(KNOWN_FACE_KEYS)}")
    endpoint = str(raw.get("endpoint") or DEFAULT_ENDPOINT)
    if urlparse(endpoint).scheme != "opc.tcp" or not urlparse(endpoint).hostname:
        raise OpcUaFaceError(f"{where} 'endpoint' must look like opc.tcp://host:4840/path, got {endpoint!r}")
    object_name = str(raw.get("object") or DEFAULT_OBJECT)
    if not _NODE_NAME_RE.match(object_name):
        raise OpcUaFaceError(f"{where} 'object' has an unusable browse name {object_name!r}")
    broker = raw.get("broker")
    if broker is not None:
        parse_broker(str(broker), where=where)
    return OpcUaFaceConfig(
        topics=_parse_topics(raw.get("topics"), where=where),
        endpoint=endpoint,
        namespace=str(raw.get("namespace") or DEFAULT_NAMESPACE),
        object_name=object_name,
        broker=str(broker) if broker is not None else None,
        fields=_parse_fields(raw.get("fields"), where=where),
        nodes=_parse_nodes(raw.get("nodes"), where=where),
    )


# --------------------------------------------------------------------------- #
# payload -> node values (pure; no asyncua)
# --------------------------------------------------------------------------- #


def _first(payload: dict, keys: tuple) -> tuple:
    """``(key, value)`` for the first of ``keys`` present and not null, else ``(None, None)``."""
    for key in keys:
        if payload.get(key) is not None:
            return key, payload[key]
    return None, None


def _as_score(value: Any) -> float:
    # bool is an int subclass; True shown as a score of 1.0 would be a fabricated alarm level.
    if isinstance(value, bool):
        raise MalformedAlertError(f"score is a boolean ({value}), not a number")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise MalformedAlertError(f"score {value!r} is not a number") from exc
    if not math.isfinite(score):
        raise MalformedAlertError(f"score {value!r} is not finite")
    return score


def map_alert(payload: Any, fields: Optional[dict] = None, *, received_at: Optional[datetime] = None) -> dict:
    """Read one alert into the values the HMI nodes will show.

    Returns ``{"score", "text", "timestamp", "timestamp_source", "device_id", "use_case_id",
    "message", "score_key"}``.

    :raises MalformedAlertError: Not a JSON object, or no readable score. Nothing is guessed.
    """
    fields = fields or DEFAULT_FIELDS
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise MalformedAlertError(f"payload is not UTF-8 JSON: {exc}") from exc
    elif isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError as exc:
            raise MalformedAlertError(f"payload is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise MalformedAlertError(f"payload is a JSON {type(payload).__name__}, not an object")

    score_key, raw_score = _first(payload, fields["score"])
    if score_key is None:
        raise MalformedAlertError(f"payload carries no score (looked for {list(fields['score'])})")
    score = _as_score(raw_score)

    received_at = received_at or datetime.now(timezone.utc)
    timestamp, timestamp_source = received_at, "received"
    ts_key, raw_ts = _first(payload, fields["timestamp_ns"])
    if ts_key is not None:
        try:
            if isinstance(raw_ts, bool):
                raise ValueError("a boolean")
            nanos = int(raw_ts)
            timestamp = datetime.fromtimestamp(nanos / 1e9, tz=timezone.utc)
            timestamp_source = ts_key
        except (TypeError, ValueError, OverflowError, OSError) as exc:
            # Tolerated, and said so: the score is the alarm; a bad clock should not hide it.
            timestamp_source = f"received ({ts_key} {raw_ts!r} unreadable: {exc})"

    _, message = _first(payload, fields["message"])
    _, device_id = _first(payload, fields["device_id"])
    _, use_case_id = _first(payload, fields["use_case_id"])
    if isinstance(message, str) and message.strip():
        text = message
    else:
        text = f"Drift alarm: score {score:.3f}"
        if device_id is not None:
            text += f" on {device_id}"
        if use_case_id is not None:
            text += f" [{use_case_id}]"
    return {
        "score": score,
        "score_key": score_key,
        "text": text,
        "timestamp": timestamp,
        "timestamp_source": timestamp_source,
        "message": message,
        "device_id": device_id,
        "use_case_id": use_case_id,
    }


#: A write the face makes: ``(role, value)``. The server half turns it into an OPC-UA write.
NodeWrite = tuple


class HmiBridge:
    """The face's behaviour, with the OPC-UA server factored out.

    ``receive`` (an alert arrived) and ``acknowledge`` (an operator wrote Ack) compute the node
    writes, hand them to ``writer`` -- the asyncua server in a run, nothing in a unit test -- and
    record each alert and each write in the run log **after** the writer accepted it, so the log
    never claims a node value the HMI does not show.
    """

    def __init__(
        self,
        config: OpcUaFaceConfig,
        *,
        name: str = "opcua_face",
        run_log: Optional[Any] = None,
        writer: Optional[Callable[[list], None]] = None,
        node_id: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.config = config
        self.name = name
        self._run_log = run_log
        self._writer = writer
        #: Resolves a role to the node id a client reads. The server passes its own, because the
        #: namespace index is whatever it registered -- 2 on a fresh asyncua server, but assigned.
        self._node_id = node_id or config.node_id
        #: Serialises alerts against acks: an Ack landing between an alert's writes would clear an
        #: alarm the operator never saw.
        self._lock = threading.Lock()
        self.values: dict = {
            "alarm": False,
            "score": 0.0,
            "text": "",
            "last_alert_ts": _NO_TIME,
            "alert_count": 0,
            "ack": False,
        }
        self.malformed = 0

    def _log(self, kind: str, **fields: Any) -> None:
        if self._run_log is not None:
            self._run_log.append(kind, face=self.name, **fields)

    def report(self, kind: str, **fields: Any) -> None:
        """Record something that happened to this face outside an alert or an ack."""
        self._log(kind, **fields)

    def _apply(self, writes: list, *, cause: str) -> None:
        if self._writer is not None:
            self._writer(writes)
        for role, value in writes:
            self.values[role] = value
            self._log(
                "opcua_node_write",
                cause=cause,
                role=role,
                node=self.config.nodes[role],
                node_id=self._node_id(role),
                value=value.isoformat() if isinstance(value, datetime) else value,
            )

    def receive(self, topic: str, payload: Any) -> Optional[dict]:
        """One message from the broker. Returns the mapped alert, or ``None`` when malformed.

        :raises UndeclaredTopicError: The topic was never declared -- see the module docstring.
        """
        topic = str(topic)
        if topic not in self.config.topics:
            raise UndeclaredTopicError(
                f"the OPC-UA face '{self.name}' received an alert on topic '{topic}', which it does "
                f"not declare (declared: {list(self.config.topics)}). Refused rather than shown: an "
                "alert on the wrong topic reaching the HMI is exactly what a rehearsal must catch."
            )
        raw = payload.decode("utf-8", errors="replace") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            alert = map_alert(payload, self.config.fields)
        except MalformedAlertError as exc:
            with self._lock:
                self.malformed += 1
            self._log("opcua_alert_malformed", topic=topic, payload=raw, reason=str(exc))
            print(f"[opcua] warning: malformed alert on {topic}: {exc}", file=sys.stderr)
            return None
        with self._lock:
            self._log(
                "opcua_alert_received",
                topic=topic,
                payload=raw,
                mapped={**alert, "timestamp": alert["timestamp"].isoformat()},
            )
            # The alarm flag is written LAST: a client that reacts to DriftAlarm going True then
            # reads a score and text that already belong to this alert, never the previous one.
            self._apply(
                [
                    ("score", alert["score"]),
                    ("text", alert["text"]),
                    ("last_alert_ts", alert["timestamp"]),
                    ("alert_count", self.values["alert_count"] + 1),
                    ("ack", False),
                    ("alarm", True),
                ],
                cause="alert",
            )
        return alert

    def acknowledge(self, value: Any) -> bool:
        """An operator wrote the Ack node. True clears the alarm; returns whether it was active.

        False is ignored: it is also what this face writes itself on every new alert, and what the
        subscription reports on start, so treating it as an operator action would log phantom acks.
        """
        if value is not True:
            return False
        with self._lock:
            was_active = bool(self.values["alarm"])
            self.values["ack"] = True
            self._log("opcua_ack", alarm_was_active=was_active)
            if was_active:
                self._apply([("alarm", False)], cause="ack")
        return was_active


# --------------------------------------------------------------------------- #
# the OPC-UA server
# --------------------------------------------------------------------------- #


def require_asyncua(where: str = "an opcua_face") -> Any:
    """Import asyncua, or fail with the install line -- only ever called when a face is declared."""
    try:
        import asyncua  # lazy, mirroring the transports' import convention  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise RuntimeError(
            f"asyncua is required for {where} (the OPC-UA egress face) -- "
            "pip install -r agentforge_simulator/requirements.txt"
        ) from exc
    return asyncua


#: Role -> OPC-UA variant type name. Every write is typed, so a client never sees DriftScore turn
#: into an Int64 because one alert happened to carry ``1``.
_VARIANT_TYPES = {
    "alarm": "Boolean",
    "score": "Double",
    "text": "String",
    "last_alert_ts": "DateTime",
    "alert_count": "UInt32",
    "ack": "Boolean",
}


class OpcUaFace:
    """An asyncua server on its own thread and event loop, driven by an :class:`HmiBridge`.

    Its own loop because every other face is a synchronous thread server and the MQTT callback
    arrives on paho's thread: writes are marshalled onto the loop and awaited, so ``receive``
    returns only once the HMI shows the alert.
    """

    def __init__(self, config: OpcUaFaceConfig, *, name: str = "opcua_face", run_log: Optional[Any] = None) -> None:
        self.config = config
        self.name = name
        self.bridge = HmiBridge(config, name=name, run_log=run_log, writer=self._write_nodes, node_id=self.node_id)
        self._run_log = run_log
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._stopping: Optional[asyncio.Event] = None
        self._error: Optional[BaseException] = None
        self._nodes: dict = {}
        self._namespace_index = 2
        self.port: Optional[int] = None

    # -- lifecycle ------------------------------------------------------------------------------

    def start(self) -> str:
        """Bind and serve; returns the endpoint a client should dial (with the bound port)."""
        require_asyncua(f"OPC-UA face '{self.name}'")
        self._thread = threading.Thread(target=self._run, name=f"sim-opcua-{self.name}", daemon=True)
        self._thread.start()
        # A failed start releases its own thread and port before raising: the caller never got a
        # started face, so nothing else would ever stop this one (review H-1).
        if not self._ready.wait(_START_TIMEOUT_S):
            self.stop()
            raise OpcUaFaceError(f"OPC-UA face '{self.name}' did not start within {_START_TIMEOUT_S:.0f}s")
        if self._error is not None:
            self.stop()
            raise OpcUaFaceError(f"OPC-UA face '{self.name}' could not start: {self._error}") from self._error
        if self._run_log is not None:
            self._run_log.append(
                "opcua_face_started",
                face=self.name,
                endpoint=self.endpoint,
                namespace=self.config.namespace,
                topics=list(self.config.topics),
                node_ids={role: self.node_id(role) for role in self.config.nodes},
            )
        return self.endpoint

    @property
    def endpoint(self) -> str:
        """The declared endpoint with the BOUND port -- ``port 0`` in a declaration means "any"."""
        parsed = urlparse(self.config.endpoint)
        host = parsed.hostname or "127.0.0.1"
        port = self.port if self.port is not None else self.config.host_port()[1]
        return f"opc.tcp://{host}:{port}{parsed.path}"

    def node_id(self, role: str) -> str:
        """The node id a client reads a role by, with the namespace index the server registered."""
        return self.config.node_id(role, self._namespace_index)

    def stop(self) -> None:
        """Stop serving and release the port. Idempotent; never raises (the engine's _safe_close rule)."""
        loop, stopping = self._loop, self._stopping
        if loop is not None and stopping is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(stopping.set)
            except RuntimeError:
                pass  # the loop closed between the check and the call
        if self._thread is not None:
            self._thread.join(timeout=_START_TIMEOUT_S)
            self._thread = None

    def receive(self, topic: str, payload: Any) -> Optional[dict]:
        """The bridge callback target: one alert in, nodes written, run log updated."""
        return self.bridge.receive(topic, payload)

    # -- server thread --------------------------------------------------------------------------

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            loop.run_until_complete(self._serve())
        except BaseException as exc:  # noqa: BLE001 - reported to start(), which raises it
            self._error = exc
        finally:
            self._ready.set()  # never leave start() waiting on a thread that has died
            loop.close()

    async def _serve(self) -> None:
        from asyncua import Server  # pylint: disable=import-outside-toplevel
        from asyncua import ua  # pylint: disable=import-outside-toplevel

        self._stopping = asyncio.Event()
        # The face is deliberately unsecured -- a bench stand-in, documented as such in the README
        # -- so asyncua's start-up warnings about having no certificate say nothing new. Quieted
        # only when nobody has configured that logger, so a host that wants them still gets them.
        asyncua_log = logging.getLogger("asyncua")
        if asyncua_log.level == logging.NOTSET:
            asyncua_log.setLevel(logging.ERROR)
        server = Server()
        await server.init()
        server.set_endpoint(self.config.endpoint)
        # Stated rather than defaulted: asyncua would otherwise also advertise signed/encrypted
        # endpoints it has no certificate for, and a client picking one would fail to connect.
        server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        server.set_server_name(f"NeuroEdge simulated HMI ({self.name})")
        self._namespace_index = await server.register_namespace(self.config.namespace)
        idx = self._namespace_index
        hmi = await server.nodes.objects.add_object(
            ua.NodeId(self.config.object_name, idx), ua.QualifiedName(self.config.object_name, idx)
        )
        for role, browse_name in self.config.nodes.items():
            variant_type = getattr(ua.VariantType, _VARIANT_TYPES[role])
            initial = self.bridge.values[role]
            node = await hmi.add_variable(
                ua.NodeId(f"{self.config.object_name}.{browse_name}", idx),
                ua.QualifiedName(browse_name, idx),
                ua.Variant(initial, variant_type),
            )
            self._nodes[role] = (node, variant_type)
        # Only Ack is writable by a client: the rest is what the alert said, and an HMI whose alarm
        # a client could set would let a rehearsal pass on a write the gateway never made.
        await self._nodes["ack"][0].set_writable()

        async with server:
            self.port = server.bserver.port if server.bserver is not None else None
            subscription = await server.create_subscription(_ACK_SAMPLING_MS, _AckHandler(self.bridge))
            await subscription.subscribe_data_change(self._nodes["ack"][0])
            self._ready.set()
            await self._stopping.wait()

    async def _write_all(self, writes: list) -> None:
        from asyncua import ua  # pylint: disable=import-outside-toplevel

        for role, value in writes:
            node, variant_type = self._nodes[role]
            await node.write_value(ua.Variant(value, variant_type))

    def _write_nodes(self, writes: list) -> None:
        """Marshal writes onto the server loop and wait for them to land.

        Never called on the loop thread: an Ack notification is handed to an executor first (see
        :class:`_AckHandler`), because waiting here from the loop would deadlock it.
        """
        if self._loop is None or not self._nodes:
            raise OpcUaFaceError(f"OPC-UA face '{self.name}' is not started; the alert cannot reach the HMI")
        future = asyncio.run_coroutine_threadsafe(self._write_all(writes), self._loop)
        future.result(timeout=_WRITE_TIMEOUT_S)


class _AckHandler:  # pylint: disable=too-few-public-methods
    """asyncua data-change handler for the Ack node."""

    def __init__(self, bridge: HmiBridge) -> None:
        self._bridge = bridge

    def datachange_notification(self, _node: Any, val: Any, _data: Any) -> None:
        """Runs on the server loop, so the acknowledgement -- which writes a node and waits for
        it -- is handed to an executor thread rather than awaited here."""
        future = asyncio.get_running_loop().run_in_executor(None, self._bridge.acknowledge, val)
        future.add_done_callback(self._report_failure)

    def _report_failure(self, future: Any) -> None:
        """An operator's Ack that did not clear the alarm is the finding, so it is logged rather
        than left in a future nobody reads (review H-2) -- the ``on_message`` rule, for acks."""
        if future.cancelled():
            return
        exc = future.exception()
        if exc is not None:
            self._bridge.report("opcua_ack_failed", reason=str(exc))
            print(f"[opcua] warning: acknowledgement failed on '{self._bridge.name}': {exc}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# the MQTT bridge
# --------------------------------------------------------------------------- #


class MqttBridge:
    """Subscribes to a face's declared topics and feeds each message to it.

    ``connect_async`` plus paho's reconnect loop, and subscription in ``on_connect``: a broker that
    comes up after the simulator (the usual compose ordering) is picked up without a restart, and a
    reconnect re-subscribes. Queue capture's one-shot connect would leave the HMI dark for a run.
    """

    def __init__(self, face: Any, host: str, port: int, *, run_log: Optional[Any] = None) -> None:
        self.face = face
        self.host = host
        self.port = port
        self._run_log = run_log
        self._client: Any = None
        #: Subscribe message ids not yet acknowledged; touched only on paho's network thread.
        self._pending: set = set()
        self._subscribed = threading.Event()

    def _log(self, kind: str, **fields: Any) -> None:
        if self._run_log is not None:
            self._run_log.append(kind, face=self.face.name, **fields)

    def on_connect(self, client: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any = None) -> None:
        """Subscribe to every declared topic, one at a time -- never ``#`` (module docstring)."""
        if getattr(reason_code, "is_failure", False):
            self._log("opcua_bridge_connect_failed", broker=f"{self.host}:{self.port}", reason=str(reason_code))
            return
        self._subscribed.clear()
        self._pending = {client.subscribe(topic, qos=1)[1] for topic in self.face.config.topics}
        self._log("opcua_bridge_connected", broker=f"{self.host}:{self.port}", topics=list(self.face.config.topics))

    def on_subscribe(self, _client: Any, _userdata: Any, mid: int, _reason_codes: Any, _properties: Any = None) -> None:
        """Mark the bridge ready once the broker has acknowledged every declared topic."""
        self._pending.discard(mid)
        if not self._pending:
            self._subscribed.set()

    def wait_subscribed(self, timeout: float) -> bool:
        """Block until every declared topic is subscribed, or ``timeout`` passes."""
        return self._subscribed.wait(timeout)

    def on_message(self, _client: Any, _userdata: Any, message: Any) -> None:
        """Feed one message to the face, recording a refusal rather than raising it.

        Guarded for the reason ``ScenarioRunner._on_captured_message`` is: paho re-raises a callback
        exception into its network thread, which then dies and silences every topic. The refusal is
        the finding, so it is logged -- not swallowed and not thrown.
        """
        topic = getattr(message, "topic", "?")
        try:
            self.face.receive(topic, message.payload)
        except Exception as exc:  # noqa: BLE001 - one bad message must not end the bridge
            self._log("opcua_alert_refused", topic=topic, reason=str(exc))
            print(f"[opcua] warning: {exc}", file=sys.stderr)

    def start(self) -> None:
        try:
            import paho.mqtt.client as mqtt  # lazy, matching the emit path  # pylint: disable=import-outside-toplevel
        except ImportError as exc:
            raise RuntimeError(
                f"paho-mqtt is required to bridge alerts into OPC-UA face '{self.face.name}' -- "
                "pip install -r agentforge_simulator/requirements.txt"
            ) from exc
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"neuro-sim-opcua-{os.getpid()}-{self.face.name}",
        )
        client.on_connect = self.on_connect
        client.on_subscribe = self.on_subscribe
        client.on_message = self.on_message
        client.connect_async(self.host, self.port)
        client.loop_start()
        self._client = client
        self._log("opcua_bridge_started", broker=f"{self.host}:{self.port}")

    def stop(self) -> None:
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # noqa: BLE001 - teardown must not raise (engine._safe_close rule)
                pass
            self._client = None


# --------------------------------------------------------------------------- #
# scenario wiring
# --------------------------------------------------------------------------- #


class OpcUaFaces:
    """Every face one scenario process serves, with their bridges. ``stop()`` tears all down."""

    def __init__(self) -> None:
        self.faces: list = []
        self.bridges: list = []

    def endpoints(self) -> dict:
        """``{face name: endpoint}`` -- what a client dials, recorded in the run summary."""
        return {face.name: face.endpoint for face in self.faces}

    def stop(self) -> None:
        for bridge in self.bridges:
            bridge.stop()
        for face in self.faces:
            face.stop()
        self.bridges.clear()
        self.faces.clear()


def _face_sections(bundle: Any, scope: Optional[str]) -> list:
    """The sections whose face THIS process serves -- the same rule as the runner's sims.

    ``shared`` runs in its own process (``--hub shared``) or in the whole-scenario run, never once
    per hub: two processes each serving the shared HMI would race for one endpoint port.
    """
    if scope == "shared":
        return [("shared", bundle.shared)]
    if scope is None:
        return [("shared", bundle.shared)] + list(bundle.hubs.items())
    return [(scope, bundle.hubs[scope])]


def start_opcua_faces(bundle: Any, *, scope: Optional[str], run_log: Any) -> OpcUaFaces:
    """Start the faces (and their MQTT bridges) a scenario process serves.

    A declared face that cannot start is fatal, unlike queue capture: the face IS the assertion a
    run exists to make, and a run that silently skipped it would report an HMI nobody served. A
    face whose section has no broker still serves its nodes, loudly, so it can be driven by hand.
    """
    faces = OpcUaFaces()
    try:
        for section_name, adapters in _face_sections(bundle, scope):
            config = getattr(adapters, "opcua_face", None)
            if config is None:
                continue
            face = OpcUaFace(config, name=f"{section_name}.opcua", run_log=run_log)
            faces.faces.append(face)  # before start(), so the cleanup below covers a failed one
            face.start()
            if config.broker is not None:
                host, port = parse_broker(config.broker)
            else:
                decl = adapters.mqtt or bundle.shared.mqtt
                host, port = (decl.host, decl.port) if decl is not None else (None, None)
            if host is None:
                run_log.append("opcua_bridge_not_started", face=face.name, reason="no broker configured")
                print(
                    f"[scenario] warning: OPC-UA face '{face.name}' has no broker (set opcua_face.broker "
                    "or the section's mqtt:); its nodes serve but no alert will drive them",
                    file=sys.stderr,
                )
                continue
            bridge = MqttBridge(face, host, port, run_log=run_log)
            bridge.start()
            faces.bridges.append(bridge)
            if not bridge.wait_subscribed(_SUBSCRIBE_WAIT_S):
                # Carried on, loudly: paho keeps retrying, so a broker that is merely late is picked
                # up -- but alerts published before then are lost, and the log must say so.
                run_log.append("opcua_bridge_not_ready", face=face.name, broker=f"{host}:{port}", waited_s=_SUBSCRIBE_WAIT_S)
                print(
                    f"[scenario] warning: OPC-UA face '{face.name}' is not yet subscribed at {host}:{port}; "
                    "alerts published before it connects will not reach the HMI",
                    file=sys.stderr,
                )
    except BaseException:
        faces.stop()
        raise
    return faces
