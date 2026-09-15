"""The API stub server -- serves route tables, captures writes, feeds pollers.

🔴 **The implementation moved to :mod:`neuro_sim.stub_server` (ADR-0038 D-5 / FR-02).** This module
is now the path-addressed *entry point* to that one server: the simulator used to run two HTTP
servers for one job -- this one answering by path, :mod:`neuro_sim.fixture_server` answering by role
and caller -- so an author had to know in advance which of two processes a capability's call would
reach. Both names still work and behave as they did; there is one implementation underneath.

Route table entries (JSON, in the bundle's ``stubs/*.routes.json``)::

    {"method": "GET",  "path": "/battery_soh_lookup", "response": {"soh_percent": 92}}
    {"method": "POST", "path": "/create_recall_bookings", "capture": "bookings",
     "required": ["dealer_id", "vins"], "response": {"bookings_created": "${seq}"}}
    {"method": "GET",  "path": "/bookings", "respond_from": "bookings"}
    {"method": "GET",  "path": "/pm_due", "feed": "pm_due"}
    {"method": "GET",  "path": "/flaky", "response": {}, "latency_ms": 200, "error_rate": 0.5}

Rules the design pins, all preserved by the merge:

* an **unmatched** route is a loud 404 and a run-log entry -- never a silent 200 (the repo's
  vacuity lesson: "not configured" and "conforms" are different answers);
* ``required`` fields missing from a captured body are a 422 naming them;
* feed routes serve the cursor contract ``{"rows": [...], "cursor": <n>}`` over rows the
  timeline has released -- exactly what ``HttpPollTransport`` polls;
* fault injection (``latency_ms``, ``error_rate``) draws from the run's seeded RNG only, so a
  flaky route is exactly as flaky on every run with the same seed.
"""

from __future__ import annotations

import random
import threading
from typing import Optional

from .simcore import EntityStore
from .simcore import RunLog
from .stub_server import FeedBuffer
from .stub_server import StubServer

__all__ = ["ApiStubServer", "FeedBuffer"]


class ApiStubServer(StubServer):
    """One stub server instance (one hub's system, or a shared one), addressed by path.

    A :class:`~neuro_sim.stub_server.StubServer` with no fixture store: the route table is the only
    scheme it answers, which is exactly what this class meant before the merge. Construct
    :class:`StubServer` directly to serve both schemes on one port.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        name: str,
        routes: list[dict],
        entities: EntityStore,
        run_log: RunLog,
        rng: random.Random,
        feeds: Optional[dict] = None,
        port: int = 0,
        rng_lock: Optional[threading.Lock] = None,
    ) -> None:
        super().__init__(
            name,
            routes=routes,
            entities=entities,
            run_log=run_log,
            rng=rng,
            feeds=feeds,
            port=port,
            rng_lock=rng_lock,
        )
