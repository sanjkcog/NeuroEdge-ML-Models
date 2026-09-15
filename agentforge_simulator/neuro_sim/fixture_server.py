"""The sim's role-addressed face: one process, many roles, fixtures served at run time.

🔴 **The implementation moved to :mod:`neuro_sim.stub_server` (ADR-0038 D-5 / FR-02).** This module
is now the role-addressed *entry point* to that one server. It existed as a sibling of
:mod:`neuro_sim.api_stub` because that module answers by path alone and a multi-party scenario needs
one more axis -- **who is asking**. Three branches of one organisation calling ``/check_capacity``
are indistinguishable to a route table, so "find the branch with room" could not be simulated. Both
axes now live in one server, on one port; both names still work and behave as they did.

Addressing::

    GET  /<role>/<capability>          # reads
    POST /<role>/<capability>          # writes; the body is the caller's arguments

The caller identity arrives in a header (:data:`DEFAULT_CALLER_HEADER`) as ``key=value;key=value``,
and the server is told which of those keys names the caller. A host that has no such notion simply
sends no header and gets the shared-fact answer.

🔴 **The header is expected in every environment the host runs, not only the simulated one.** That is
the property that makes a simulated run *evidence*: if a request carries different metadata when it
is real, the two runs are exercising different wire shapes and the simulated one proves nothing
about the other. In a real deployment the same header is audit context.

🔴 **An unconfigured route is a loud 404 and a log line, never a silent 200.** "No fixture is
configured for this" and "this capability returns an empty object" are different answers, and a sim
that collapses them teaches a green run to mean nothing.

**One 404 difference the merge introduces, stated rather than hidden:** a path that is not two
segments used to answer "expected /<role>/<capability>". It now answers "no route configured … and it
is not a two-segment /<role>/<capability> path", because one server cannot know which scheme the
caller *meant*. Both name the same two facts; the merged one also names the route table it checked.
"""

from __future__ import annotations

import random
from typing import Optional

from .fixtures import FixtureStore
from .stub_server import DEFAULT_CALLER_HEADER
from .stub_server import DEFAULT_CALLER_KEY
from .stub_server import StubServer
from .stub_server import parse_caller_header

__all__ = [
    "DEFAULT_CALLER_HEADER",
    "DEFAULT_CALLER_KEY",
    "FixtureRoleServer",
    "parse_caller_header",
]


class FixtureRoleServer(StubServer):
    """One process playing every role in a scenario's fixture manifest.

    A :class:`~neuro_sim.stub_server.StubServer` with no route table: ``(role, caller, capability)``
    is the only scheme it answers. Construct :class:`StubServer` directly to serve both schemes on
    one port.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        store: FixtureStore,
        port: int = 0,
        rng: Optional[random.Random] = None,
        log: Optional[list] = None,
        caller_header: str = DEFAULT_CALLER_HEADER,
        caller_key: str = DEFAULT_CALLER_KEY,
    ) -> None:
        super().__init__(
            "fixtures",
            store=store,
            port=port,
            rng=rng,
            log=log,
            caller_header=caller_header,
            caller_key=caller_key,
        )
