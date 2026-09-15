"""One stub server, both addressing schemes (ADR-0038 D-5 / FR-02).

The simulator grew two HTTP servers for one job. :mod:`neuro_sim.api_stub` answers by **path**, from
a route table, and owns capture, feeds and templated responses. :mod:`neuro_sim.fixture_server`
answers by **role and caller**, from a :class:`~neuro_sim.fixtures.FixtureStore`, and owns the one
axis a multi-party scenario needs: *who is asking*. Both were right; having two of them was not.
An author configuring a capability had to know, in advance, which of two processes their call would
reach -- and the two answered on different ports, with different 404s and different run logs.

This module is the merge. **One process, one port, both schemes**, in a fixed order:

1. an exact ``(method, path)`` match in the route table wins;
2. else a two-segment path ``/<role>/<capability>`` resolves through the fixture store,
   ``(role, caller, capability)`` -> ``(role, capability)`` -> nothing;
3. else a **loud 404** naming what was tried and what is live.

Nothing about either scheme's behaviour changes -- that is the point of a merge, and the tests that
pinned each of them separately still pin them here. What changes is that one address serves both.

🔴 **A loud 404 in both schemes, never a silent 200.** "No route is configured for this" and "this
capability returns an empty object" are different answers, and a sim that collapses them teaches a
green run to mean nothing. That rule was already in both servers; it survives the merge verbatim.

🔴 **Both directions are recorded.** Every handled call logs what was ``sent`` (a write's body, a
read's query) apart from what was ``answered``. One ``payload`` key for both would turn "the write
carried plant_a" into an assertion about the sim's own reply.
"""

from __future__ import annotations

import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from typing import Any
from typing import Optional
from urllib.parse import parse_qs
from urllib.parse import urlparse

from .fixtures import FixtureStore
from .mcp_face import MCP_PATH_PREFIX
from .mcp_face import McpFace
from .model_face import ModelResponses
from .model_face import prompt_fingerprint
from .simcore import EntityStore
from .simcore import RunLog
from .simcore import render

#: The header a caller identity is expected under, unless the host names another. Chosen to be
#: vendor-neutral and unlikely to collide with a proxy's own headers.
DEFAULT_CALLER_HEADER = "X-NeuroEdge-Caller"

#: The reserved first path segment for the canned-model face. A name rather than a bare literal so
#: the reservation is greppable from both the server and the bundle that points at it.
MODEL_PATH_PREFIX = "models"

#: Which key inside that header names the caller, unless the host names another. A host whose
#: identity is spelled differently (``hub_id``, ``tenant``, ``branch``) passes its own.
DEFAULT_CALLER_KEY = "caller"


def parse_caller_header(raw: str) -> dict:
    """Decode the caller header's ``key=value;key=value`` form.

    Tolerant by design: this value arrives over the wire, and a malformed one must degrade to "no
    caller identity" -- which then misses caller-scoped fixtures and falls back to the shared-fact
    answer -- rather than failing the call. A *wrong* answer would be worse than a *general* one
    here, and the fallback is the general one.
    """
    caller: dict = {}
    for part in raw.split(";"):
        key, separator, value = part.partition("=")
        if separator and key.strip():
            caller[key.strip()] = value.strip()
    return caller


class FeedBuffer:
    """Rows released to a named feed, served with cursor semantics (exactly-once per cursor)."""

    def __init__(self) -> None:
        self._rows: list[dict] = []
        self._lock = threading.Lock()

    def release(self, row: dict) -> None:
        with self._lock:
            self._rows.append(dict(row))

    def page(self, cursor: int) -> dict:
        with self._lock:
            return {"rows": [dict(row) for row in self._rows[cursor:]], "cursor": len(self._rows)}


class StubServer:  # pylint: disable=too-many-instance-attributes
    """One stub process answering by path **and** by ``(role, caller, capability)``.

    Both halves are optional and independent: a server with only ``routes`` behaves exactly as the
    old ``ApiStubServer``, one with only ``store`` exactly as the old ``FixtureRoleServer``, and one
    with both serves them in the documented order. That is what lets the two former entry points
    keep working while there is only one implementation underneath.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        name: str = "stub",
        *,
        routes: Optional[list[dict]] = None,
        store: Optional[FixtureStore] = None,
        models: Optional[ModelResponses] = None,
        mcp: Optional[McpFace] = None,
        entities: Optional[EntityStore] = None,
        run_log: Optional[RunLog] = None,
        log: Optional[list] = None,
        rng: Optional[random.Random] = None,
        feeds: Optional[dict[str, FeedBuffer]] = None,
        port: int = 0,
        rng_lock: Optional[threading.Lock] = None,
        caller_header: str = DEFAULT_CALLER_HEADER,
        caller_key: str = DEFAULT_CALLER_KEY,
    ) -> None:
        self.name = name
        self._routes = list(routes or [])
        self._store = store
        #: Canned model answers (ADR-0038 D-5 / FR-09), served under `/models/<model_ref>`.
        self._models = models
        #: The tool-server protocol face (FR-10), served under `/mcp/<server_id>`. It speaks
        #: JSON-RPC rather than the route table, so it gets its own reserved prefix for the same
        #: reason the model face does -- a protocol is not an address.
        self._mcp = mcp
        self._entities = entities if entities is not None else EntityStore()
        self._run_log = run_log
        #: Every call, in order, as plain dicts. The in-memory sibling of ``run_log`` -- kept
        #: because a caller that only wants to assert on a list should not have to own a file.
        self.log: list = log if log is not None else []
        # Seeded so a flaky route is exactly as flaky on every run with the same seed: the property
        # that makes fault injection usable in a regression suite and not only in a demo.
        self._rng = rng if rng is not None else random.Random(0)  # nosec B311 - fixtures, not crypto
        # Shared with every stub that shares `rng`: `random.Random` is not thread-safe, and
        # ThreadingHTTPServer serves each connection on its own thread.
        self._rng_lock = rng_lock if rng_lock is not None else threading.Lock()
        self._feeds = feeds if feeds is not None else {}
        self._caller_header = caller_header
        self._caller_key = caller_key
        self._requested_port = port
        self._server: Optional[ThreadingHTTPServer] = None
        self._call_seq = 0
        self._seq_lock = threading.Lock()

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> int:
        """Bind and serve on a daemon thread; returns the bound port."""
        stub = self

        class Handler(BaseHTTPRequestHandler):
            """Closure-bound handler so the server object carries no public routing state."""

            def log_message(self, *_args):
                """The run log is the record; stderr chatter is noise."""

            # pylint: disable=invalid-name  # `do_GET`/`do_POST` are BaseHTTPRequestHandler's names
            def do_GET(self):  # noqa: N802
                """Route a read."""
                stub.handle(self, "GET")

            def do_POST(self):  # noqa: N802
                """Route a write."""
                stub.handle(self, "POST")

            def do_PUT(self):  # noqa: N802
                """Route an update."""
                stub.handle(self, "PUT")

        self._server = ThreadingHTTPServer(("127.0.0.1", self._requested_port), Handler)
        threading.Thread(target=self._server.serve_forever, name=f"sim-stub-{self.name}", daemon=True).start()
        return self.port

    @property
    def port(self) -> int:
        """The bound port. Raises if never started -- a port of 0 would read as "not listening" and
        be dialled anyway."""
        if self._server is None:
            raise RuntimeError(f"stub server '{self.name}' is not started")
        return self._server.server_address[1]

    @property
    def base_url(self) -> str:
        """What a host should point its simulated endpoints at."""
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        """Shut down and release the port. Idempotent."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self) -> StubServer:
        """Start on entry so a caller can scope the process to a `with` block."""
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        """Stop on exit, however the block ended."""
        self.stop()

    # ------------------------------------------------------------------ plumbing

    def _emit(self, kind: str, **fields: Any) -> None:
        """Record one event in whichever sinks this server was given.

        The two sinks spell the event key differently (``kind`` in the JSONL :class:`RunLog`,
        ``event`` in the in-memory list) because each was already read that way by existing
        assertions. Renaming either during a merge would break a test for a reason that has nothing
        to do with the merge.
        """
        if self._run_log is not None:
            self._run_log.append(kind, **fields)
        self.log.append({"event": kind, **fields})

    def _next_seq(self) -> int:
        with self._seq_lock:
            self._call_seq += 1
            return self._call_seq

    def _match(self, method: str, path: str) -> Optional[dict]:
        for route in self._routes:
            if route.get("method", "GET").upper() == method and route.get("path") == path:
                return route
        return None

    @staticmethod
    def _read_body(handler: BaseHTTPRequestHandler) -> dict:
        """The JSON object a request sent, or ``{}``.

        🔴 Read unconditionally, before any routing decision: the body must be drained either way,
        and a connection left with unread bytes stalls the next keep-alive request on it. Reading it
        up front is also what lets one server dispatch to either scheme -- the fixture path needs the
        body, and by then the route table has already been consulted.
        """
        try:
            length = int(handler.headers.get("content-length", 0) or 0)
        except ValueError:
            return {}
        if length <= 0:
            return {}
        try:
            parsed = json.loads(handler.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _reply(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        handler.send_response(status)
        handler.send_header("content-type", "application/json")
        handler.send_header("content-length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _roll_fault(self, error_rate: float) -> bool:
        """One atomic draw against the run's seeded RNG.

        Honest limit, stated: with overlapping requests the *order* of draws is arrival order, so
        seed-determinism holds exactly for sequential request patterns.
        """
        if not error_rate:
            return False
        with self._rng_lock:
            return self._rng.random() < error_rate

    # ------------------------------------------------------------------ request handling

    def handle(self, handler: BaseHTTPRequestHandler, method: str) -> None:
        """Route one request. Public so the closure-handler stays four lines."""
        parsed = urlparse(handler.path)
        query = {key: values[0] for key, values in parse_qs(parsed.query).items() if values}
        sent = self._read_body(handler)

        route = self._match(method, parsed.path)
        if route is not None:
            self._serve_route(handler, method, parsed.path, route, {**query, **sent})
            return

        segments = [segment for segment in parsed.path.split("/") if segment]
        # 🔴 Checked BEFORE the fixture scheme, because `/models/<ref>` is also two segments and
        # would otherwise be read as role `models`, capability `<ref>` -- answering 404 for a model
        # the face has canned. The prefix is reserved for exactly that reason, and a role actually
        # named `models` would be shadowed, which is why the 404 below names both schemes.
        if self._models is not None and len(segments) == 2 and segments[0] == MODEL_PATH_PREFIX:
            self._serve_model(handler, segments[1], {**query, **sent})
            return

        # Checked before the fixture scheme for the same reason, and with the same reservation:
        # `/mcp/<server_id>` is two segments and would otherwise resolve as role `mcp`.
        if self._mcp is not None and len(segments) == 2 and segments[0] == MCP_PATH_PREFIX:
            self._serve_mcp(handler, method, segments[1], handler.headers, sent)
            return

        if self._store is not None and len(segments) == 2:
            self._serve_fixture(handler, method, segments, handler.headers, query, sent)
            return

        self._not_found(handler, method, parsed.path)

    def _serve_mcp(
        self,
        handler: BaseHTTPRequestHandler,
        method: str,
        server_id: str,
        headers: Any,
        sent: dict,
    ) -> None:
        """One protocol message for one simulated tool server.

        🔴 **The face decides; this method only carries.** Routing, refusals and wire shapes all
        live in :mod:`neuro_sim.mcp_face`, so the protocol can be driven from a test without a
        socket -- and so a second carrier could serve it without reimplementing any of it.

        The caller identity rides the same header every other face reads, so a tool server can
        answer two hubs differently exactly as an HTTP role can.
        """
        if method != "POST":
            # The protocol's other verbs (a server-initiated stream, a session teardown) exist for
            # features this face does not offer. Said plainly rather than 404'd, so a client that
            # tries one reads "not offered" instead of "wrong address".
            self._emit("mcp_unsupported", stub=self.name, server=server_id, method=method)
            self._reply(handler, 405, {"error": f"this tool-server face answers POST only, not {method}"})
            return
        if not sent:
            self._emit("mcp_unreadable", stub=self.name, server=server_id)
            self._reply(handler, 400, {"error": "request body is not a JSON-RPC object"})
            return
        identity = parse_caller_header(headers.get(self._caller_header, "") or "")
        caller = identity.get(self._caller_key, "")
        status, payload = self._mcp.handle(server_id, sent, caller)
        # 🔴 A refusal is recorded under its OWN event name. Logging a miss and a served call
        # identically is how "nothing was configured for that tool" becomes invisible in a run log
        # full of successful-looking lines -- the same reason the model face emits `model_miss`.
        refused = isinstance(payload, dict) and (
            "error" in payload or (payload.get("result") or {}).get("isError") is True
        )
        self._emit(
            "mcp_miss" if refused else "mcp_call",
            stub=self.name,
            server=server_id,
            rpc_method=sent.get("method"),
            caller=identity,
            sent=sent,
            answered=payload,
        )
        if payload is None:
            # A notification. Answered with a status and no body, because the protocol forbids a
            # response to something that did not ask one.
            handler.send_response(status)
            handler.send_header("content-length", "0")
            handler.end_headers()
            return
        self._reply(handler, status, payload)

    def _serve_model(self, handler: BaseHTTPRequestHandler, model_ref: str, payload: dict) -> None:
        """One canned model answer, or a loud miss naming both halves of the key.

        🔴 A miss is a 404, never a passthrough. The whole reason this face exists is that a
        simulated run must not reach a real provider -- so "nothing canned for this" has to stop the
        call, not fall back to the thing it was built to avoid.
        """
        answer = self._models.answer(model_ref, payload)
        if answer is None:
            fingerprint = prompt_fingerprint(payload)
            self._emit(
                "model_miss", stub=self.name, model_ref=model_ref, prompt_fingerprint=fingerprint, sent=payload
            )
            self._reply(
                handler,
                404,
                {
                    "error": f"no canned response for model '{model_ref}' with prompt fingerprint {fingerprint}",
                    "model_refs": list(self._models.model_refs()),
                },
            )
            return
        self._emit("model_call", stub=self.name, model_ref=model_ref, sent=payload, answered=answer)
        self._reply(handler, 200, answer)

    def _not_found(self, handler: BaseHTTPRequestHandler, method: str, path: str) -> None:
        """The loud 404, naming what was tried and what is live.

        Which of the two schemes is named depends on which are configured, because naming a scheme
        this server does not serve would send the reader looking for a file that should not exist.
        """
        payload: dict = {"error": f"no route configured for {method} {path}", "stub": self.name}
        if self._store is not None:
            payload["error"] = (
                f"no route configured for {method} {path}, and it is not a "
                "two-segment /<role>/<capability> path the fixture store could resolve"
            )
            payload["roles"] = list(self._store.roles())
        if self._models is not None:
            payload["model_refs"] = list(self._models.model_refs())
        if self._mcp is not None:
            payload["tool_servers"] = list(self._mcp.server_ids())
        self._emit("unmatched", stub=self.name, method=method, path=path, note="no route configured")
        self._reply(handler, 404, payload)

    def _serve_route(  # pylint: disable=too-many-return-statements
        self,
        handler: BaseHTTPRequestHandler,
        method: str,
        path: str,
        route: dict,
        inputs: dict,
    ) -> None:
        """The route-table scheme: templated responses, capture, feeds, seeded faults."""
        seq = self._next_seq()

        latency_ms = float(route.get("latency_ms", 0))
        if latency_ms:
            time.sleep(latency_ms / 1000.0)
        if self._roll_fault(float(route.get("error_rate", 0))):
            self._emit("fault", stub=self.name, method=method, path=path, injected=True)
            self._reply(handler, 500, {"error": "injected fault", "stub": self.name})
            return

        if "feed" in route:
            feed = self._feeds.setdefault(str(route["feed"]), FeedBuffer())
            cursor = int(inputs.get("cursor", 0) or 0)
            page = feed.page(cursor)
            self._emit("feed_poll", stub=self.name, feed=route["feed"], cursor=cursor, returned=len(page["rows"]))
            self._reply(handler, 200, page)
            return

        if "capture" in route:
            missing = [key for key in route.get("required", []) if key not in inputs]
            if missing:
                self._emit("capture_rejected", stub=self.name, path=path, missing=missing)
                self._reply(handler, 422, {"error": "missing required fields", "missing": missing})
                return
            record = dict(inputs)
            self._entities.add(str(route["capture"]), record)
            self._emit(
                "capture",
                stub=self.name,
                method=method,
                path=path,
                collection=route["capture"],
                record=record,
            )
            response = render(route.get("response", {"captured": True}), seq=seq, inputs=inputs)
            self._reply(handler, int(route.get("status", 200)), response)
            return

        if "respond_from" in route:
            rows = self._entities.get(str(route["respond_from"]))
            self._emit("call", stub=self.name, method=method, path=path, rows=len(rows))
            self._reply(handler, 200, {"rows": rows, "count": len(rows)})
            return

        response = render(route.get("response", {}), seq=seq, inputs=inputs)
        self._emit("call", stub=self.name, method=method, path=path, sent=inputs, answered=response)
        self._reply(handler, int(route.get("status", 200)), response)

    def _serve_fixture(  # pylint: disable=too-many-arguments
        self,
        handler: BaseHTTPRequestHandler,
        method: str,
        segments: list,
        headers: Any,
        query: dict,
        sent: dict,
    ) -> None:
        """The ``(role, caller, capability)`` scheme, with the store's own resolution chain."""
        role, capability = segments
        identity = parse_caller_header(headers.get(self._caller_header, "") or "")
        caller = identity.get(self._caller_key, "")
        # 🔴 The call's arguments reach resolution, so a fixture can answer *about* what was asked.
        # They arrived here all along and were used only for logging -- which is why a per-SKU
        # capability answered identically for every SKU. Merged the same way the route scheme
        # merges them (`handle`), so one request shape means one thing across both schemes: a read
        # carries them on the query string, a write in the body.
        inputs = {**query, **sent}
        answered = self._store.answer(role, capability, caller, inputs)
        if answered is None:
            # 🔴 Loud, and it names the facts a person needs to fix it: which key missed, what was
            # asked, and which roles exist. A 404 saying only "not found" would be
            # indistinguishable from the sim not running at all -- and now that a fixture can be
            # scoped by argument, "no fixture for THIS sku" is a distinct miss from "no fixture for
            # this capability at all", so the arguments are named too.
            self._emit("unconfigured", role=role, capability=capability, caller=identity, sent=sent, inputs=inputs)
            self._reply(
                handler,
                404,
                {
                    "error": f"no fixture configured for role '{role}', capability '{capability}'",
                    "caller": caller,
                    "asked_with": inputs,
                    "roles": list(self._store.roles()),
                },
            )
            return

        payload, faults = answered
        if faults.delay_seconds:
            time.sleep(faults.delay_seconds)
        if self._roll_fault(faults.error_rate):
            self._emit("fault", role=role, capability=capability, injected=500)
            self._reply(handler, 500, {"error": "injected fault", "role": role})
            return
        if faults.malformed:
            # Deliberately not the declared shape: a string where an object is expected, which is
            # what a misbehaving upstream actually sends.
            self._emit("fault", role=role, capability=capability, injected="malformed")
            self._reply(handler, 200, "this is not the declared object shape")
            return

        self._emit(
            "call",
            method=method,
            role=role,
            capability=capability,
            caller=identity,
            # 🔴 Both directions, named apart. `sent` is what the caller asked with -- the body of a
            # write, or a read's query string; `answered` is the fixture.
            sent={**query, **sent},
            answered=payload,
        )
        self._reply(handler, 200, payload)
