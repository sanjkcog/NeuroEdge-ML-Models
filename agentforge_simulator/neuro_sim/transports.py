"""Transports — where emitted records go.

All four requested protocols plus a ``console`` sink for local testing:

  console -> print each record as a JSON line (no network)
  sse     -> host an HTTP server; connected clients receive Server-Sent Events
  mqtt    -> publish each record to a broker topic (paho-mqtt)
  webhook -> HTTP POST each record to a URL (requests)
  api     -> HTTP request with method/headers/bearer token (requests)

Every transport implements open() / send(record) / close(). Network libraries
(paho, requests) import lazily inside the transport that needs them.
"""

from __future__ import annotations

import json
import os
import queue
import threading
from abc import ABC, abstractmethod
from typing import Any

from .record import Record


class TransportError(Exception):
    """A failure attributable to the transport (connect/publish/HTTP), as opposed
    to a writer or loader I/O error. Deliberately NOT an ``OSError`` subclass so a
    caller can tell a broker-down / bad-endpoint failure apart from a disk-full or
    permission error on sim_input/ or sim_output/ — the engine raises this only for
    OSErrors that originate in a transport call."""


def _require_requests() -> Any:
    """Import requests lazily, raising a clean RuntimeError (not a bare ImportError
    traceback) when it isn't installed — mirrors MqttTransport's paho guard."""
    try:
        import requests  # lazy
    except ImportError as exc:
        raise RuntimeError(
            "requests is required for webhook/api transports — pip install -r requirements.txt"
        ) from exc
    return requests


class Transport(ABC):
    """Common lifecycle: open() once, send() per record, close() at the end."""

    name = "transport"

    def open(self) -> None:  # noqa: D401 - optional hook
        """Acquire connections / start servers. Default no-op."""

    @abstractmethod
    def send(self, record: Record) -> None:
        """Emit one record."""

    def close(self) -> None:
        """Release resources. Default no-op."""

    @staticmethod
    def _dumps(record: Record) -> str:
        return json.dumps(record.to_dict(), ensure_ascii=False, default=str)


# --------------------------------------------------------------------------- #
# console
# --------------------------------------------------------------------------- #

class ConsoleTransport(Transport):
    name = "console"

    def send(self, record: Record) -> None:
        print(self._dumps(record), flush=True)


# --------------------------------------------------------------------------- #
# webhook / api
# --------------------------------------------------------------------------- #

class WebhookTransport(Transport):
    """Fire-and-forget HTTP POST of each record's JSON body."""

    name = "webhook"

    def __init__(self, url: str, timeout: float = 10.0) -> None:
        if not url:
            raise ValueError("--webhook-url is required for transport 'webhook'")
        self.url = url
        self.timeout = timeout
        self._session: Any = None

    def open(self) -> None:
        self._session = _require_requests().Session()

    def send(self, record: Record) -> None:
        resp = self._session.post(
            self.url, json=record.to_dict(), timeout=self.timeout
        )
        resp.raise_for_status()

    def close(self) -> None:
        if self._session is not None:
            self._session.close()


class ApiTransport(Transport):
    """Configurable HTTP request: method, custom headers, optional bearer token."""

    name = "api"

    def __init__(
        self,
        url: str,
        method: str = "POST",
        headers: dict[str, str] | None = None,
        bearer: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not url:
            raise ValueError("--api-url is required for transport 'api'")
        self.url = url
        self.method = method.upper()
        self.headers = dict(headers or {})
        if bearer:
            self.headers.setdefault("Authorization", f"Bearer {bearer}")
        self.timeout = timeout
        self._session: Any = None

    def open(self) -> None:
        self._session = _require_requests().Session()

    def send(self, record: Record) -> None:
        resp = self._session.request(
            self.method,
            self.url,
            json=record.to_dict(),
            headers=self.headers or None,
            timeout=self.timeout,
        )
        resp.raise_for_status()

    def close(self) -> None:
        if self._session is not None:
            self._session.close()


# --------------------------------------------------------------------------- #
# mqtt
# --------------------------------------------------------------------------- #

class MqttTransport(Transport):
    """Publish each record to an MQTT topic via paho-mqtt."""

    name = "mqtt"

    def __init__(
        self,
        host: str,
        port: int = 1883,
        topic: str = "neuroedge/sim",
        qos: int = 0,
        username: str | None = None,
        password: str | None = None,
        client_id: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.topic = topic
        self.qos = qos
        self.username = username
        self.password = password
        # A per-process-unique default: a fixed client id would make a broker kick
        # an earlier still-connected session when a second simulator connects with
        # the same id — silent data loss for the first run. Concurrent "devices"
        # against one broker is a normal use of this tool. Override with --mqtt-client-id.
        self.client_id = client_id or f"neuro-sim-{os.getpid()}"
        self._client: Any = None

    def open(self) -> None:
        try:
            import paho.mqtt.client as mqtt  # lazy
        except ImportError as exc:
            raise RuntimeError(
                "paho-mqtt is required for transport 'mqtt' — pip install -r requirements.txt"
            ) from exc
        # Works across paho-mqtt 1.x and 2.x (2.x needs the callback-API version).
        try:
            client = mqtt.Client(
                client_id=self.client_id,
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            )
        except (AttributeError, TypeError):
            client = mqtt.Client(client_id=self.client_id)
        if self.username:
            client.username_pw_set(self.username, self.password)
        client.connect(self.host, self.port)
        client.loop_start()
        self._client = client

    def send(self, record: Record) -> None:
        # paho's publish() raises ValueError (not OSError) for an operator mistake
        # like a wildcard publish topic (--mqtt-topic 'a/+/b'), a bad QoS, or an
        # oversized payload, and RuntimeError on a failed publish — neither is an
        # OSError, so the engine's OSError->TransportError wrapper would miss them
        # and they'd escape as a raw traceback. Re-raise as TransportError here so
        # MQTT honours the same "clean, transport-labelled error" contract as the
        # HTTP transports (whose requests exceptions already subclass OSError).
        try:
            info = self._client.publish(self.topic, self._dumps(record), qos=self.qos)
            info.wait_for_publish(timeout=10)
        except (ValueError, RuntimeError) as exc:
            raise TransportError(f"mqtt publish failed at seq={record.seq}: {exc}") from exc

    def close(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()


# --------------------------------------------------------------------------- #
# sse
# --------------------------------------------------------------------------- #

class SseTransport(Transport):
    """Host an HTTP Server-Sent-Events endpoint and push records to subscribers.

    The simulator becomes the server: clients connect to
    ``http://<host>:<port><path>`` and receive each record as an SSE ``data:``
    frame. Records emitted while no client is connected are dropped (a live data
    source has no backlog); use ``wait_for_client`` to hold emission until at
    least one subscriber is present.
    """

    name = "sse"

    # Per-client queue cap. A client that connects but stops reading (paused tab,
    # slow link, half-dead socket) must not accumulate every subsequent record in
    # memory — at high --rate or --loop -1 that is unbounded growth. Once full we
    # drop the OLDEST record for that client (freshest data wins for a live feed).
    _MAX_QUEUE = 1000

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        path: str = "/events",
        wait_for_client: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.path = path if path.startswith("/") else "/" + path
        self.wait_for_client = wait_for_client
        self._server: Any = None
        self._thread: threading.Thread | None = None
        self._clients: set[queue.Queue] = set()
        self._lock = threading.Lock()

    def open(self) -> None:
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        transport = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:  # silence access logs
                pass

            def do_GET(self) -> None:  # noqa: N802 - required name
                if self.path.rstrip("/") != transport.path.rstrip("/"):
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                client_q: queue.Queue = queue.Queue(maxsize=transport._MAX_QUEUE)
                transport._add_client(client_q)
                try:
                    while True:
                        data = client_q.get()
                        if data is None:  # shutdown sentinel
                            break
                        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass  # client disconnected
                finally:
                    transport._remove_client(client_q)

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        url = f"http://{self.host}:{self.port}{self.path}"
        print(f"[sse] serving events at {url}  (Ctrl-C to stop)")
        if self.wait_for_client:
            print("[sse] waiting for a client to connect ...")
            # If the wait is interrupted (Ctrl-C) the server + thread are already
            # bound; open() raising before the engine's try-block means the engine
            # won't close them, so clean up here. BaseException catches KeyboardInterrupt.
            try:
                self._wait_for_client()
            except BaseException:
                self.close()
                raise

    def _add_client(self, q: queue.Queue) -> None:
        with self._lock:
            self._clients.add(q)
        print(f"[sse] client connected ({len(self._clients)} total)")

    def _remove_client(self, q: queue.Queue) -> None:
        with self._lock:
            self._clients.discard(q)

    def _wait_for_client(self) -> None:
        import time
        while True:
            with self._lock:
                if self._clients:
                    return
            time.sleep(0.1)

    def send(self, record: Record) -> None:
        data = self._dumps(record)
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            self._offer(q, data)

    @staticmethod
    def _offer(q: queue.Queue, item: Any) -> None:
        """Non-blocking enqueue with drop-oldest on a full (stalled) client queue.

        A slow/stalled consumer never blocks the emit loop and never grows without
        bound: when its queue is full we discard its oldest pending record and
        enqueue the newest, so a live feed stays current rather than stale.
        """
        try:
            q.put_nowait(item)
        except queue.Full:
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(item)
            except queue.Full:
                pass  # lost a race with the consumer; the next record will catch up

    def close(self) -> None:
        # Unblock every streaming handler with the shutdown sentinel, then stop the
        # server. Use the same drop-oldest offer so a full queue still receives it.
        # A client that registers in the tiny window after this snapshot won't get a
        # sentinel and stays blocked on get(); harmless because the handler threads
        # are daemon (ThreadingHTTPServer.daemon_threads), so process exit reclaims it.
        with self._lock:
            clients = list(self._clients)
        for q in clients:
            self._offer(q, None)
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()


# --------------------------------------------------------------------------- #
# factory
# --------------------------------------------------------------------------- #

TRANSPORT_NAMES = ("console", "sse", "mqtt", "webhook", "api")


def build_transport(args: Any) -> Transport:
    """Construct the transport named by ``args.transport`` from parsed CLI args."""
    name = args.transport
    if name == "console":
        return ConsoleTransport()
    if name == "webhook":
        return WebhookTransport(url=args.webhook_url, timeout=args.http_timeout)
    if name == "api":
        headers = _parse_headers(args.api_header)
        return ApiTransport(
            url=args.api_url,
            method=args.api_method,
            headers=headers,
            bearer=args.api_bearer,
            timeout=args.http_timeout,
        )
    if name == "mqtt":
        return MqttTransport(
            host=args.mqtt_host,
            port=args.mqtt_port,
            topic=args.mqtt_topic,
            qos=args.mqtt_qos,
            username=args.mqtt_username,
            password=args.mqtt_password,
            client_id=args.mqtt_client_id,
        )
    if name == "sse":
        return SseTransport(
            host=args.sse_host,
            port=args.sse_port,
            path=args.sse_path,
            wait_for_client=args.sse_wait,
        )
    raise ValueError(f"unknown transport {name!r}")


def _parse_headers(pairs: list[str] | None) -> dict[str, str]:
    """Turn ``--api-header 'K: V'`` repeats into a dict."""
    headers: dict[str, str] = {}
    for item in pairs or []:
        if ":" not in item:
            raise ValueError(f"--api-header must be 'Key: Value', got {item!r}")
        key, value = item.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers
