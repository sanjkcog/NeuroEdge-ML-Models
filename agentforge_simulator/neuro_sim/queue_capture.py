"""The broker-side capture sink: what a *tool* published (ADR-0038 D-5 / FR-08).

The simulator has always been able to **produce** to a broker — that is how a timeline drives an
ingress adapter. What it could not do is **observe**: a capability bound to ``queue_publish`` sent a
message into the broker and nothing recorded it, so a flow whose whole outcome is "the containment
notice was published" had no evidence it ever happened. A write you cannot see is a write you cannot
test.

This is the other half. It subscribes to the topics a scenario declares and records every message
per topic, in order, into the run log.

🔴 **A publish to a topic the scenario does not declare is a loud failure, not a silent drop.** The
tempting alternative — subscribe to ``#`` and record whatever arrives — sounds more useful and is
worse: it makes a capability that published to the wrong topic indistinguishable from one that
published correctly, which is exactly the class of defect a rehearsal exists to catch. Declaring the
topics is what turns the capture into an assertion.

🔴 **Ordering is per topic, not global.** Two topics have no ordering relationship anyone could rely
on — the broker makes no such promise and neither does this. Within one topic the order is the
order the sink received them, which is the property a consumer actually depends on.
"""

from __future__ import annotations

import json
import threading
from typing import Any
from typing import Optional


class UndeclaredTopicError(ValueError):
    """A message arrived on a topic the scenario never declared.

    Loud by construction: the sink only subscribes to declared topics, so this can only be reached
    by a caller feeding it directly -- which the runner does when a wildcard subscription is in use
    for diagnostics. Named rather than swallowed so the diagnostic mode cannot quietly become the
    permissive one.
    """


class QueueCapture:
    """Records what was published, per topic, in arrival order.

    Deliberately transport-agnostic: :meth:`record` takes a topic and a payload, so the sink can be
    unit-tested without a broker and driven by one in an integration run. The broker-shaped half is
    the subscription, which lives in the runner -- keeping it out of here is what makes the
    behaviour above testable at all.
    """

    def __init__(self, topics: Optional[list] = None, run_log: Optional[Any] = None) -> None:
        #: Topics the scenario declared. Empty means "declare nothing, capture nothing" -- a
        #: scenario that publishes to no queue is the common case and must not need configuration.
        self._declared = tuple(str(topic) for topic in (topics or []))
        self._run_log = run_log
        self._lock = threading.Lock()
        self._by_topic: dict = {topic: [] for topic in self._declared}

    @property
    def declared_topics(self) -> tuple:
        """What this sink will accept. Named in the refusal so a typo is one line from its fix."""
        return self._declared

    def record(self, topic: str, payload: Any) -> None:
        """Record one published message.

        :raises UndeclaredTopicError: The topic was never declared.
        """
        topic = str(topic)
        if topic not in self._by_topic:
            raise UndeclaredTopicError(
                f"a tool published to topic '{topic}', which this scenario does not declare "
                f"(declared: {list(self._declared)}). A capability publishing to the wrong topic "
                "is exactly what a rehearsal exists to catch, so this is refused rather than "
                "recorded under a topic nobody asked for."
            )
        decoded = payload
        if isinstance(payload, (bytes, bytearray)):
            try:
                decoded = json.loads(payload.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                # Kept as text rather than dropped: a malformed publish is a finding, and a sink
                # that discarded it would hide the one message worth looking at.
                decoded = payload.decode("utf-8", errors="replace")
        with self._lock:
            self._by_topic[topic].append(decoded)
        if self._run_log is not None:
            self._run_log.append("queue_published", topic=topic, payload=decoded)

    def published(self, topic: str) -> list:
        """Everything recorded on one topic, in arrival order. A snapshot -- callers cannot mutate
        the capture through a read."""
        with self._lock:
            return list(self._by_topic.get(str(topic), []))

    def counts(self) -> dict:
        """``{topic: message_count}`` for every declared topic, including the empty ones.

        🔴 The empty ones are the point. A topic declared and never published to is a *fact* a test
        should be able to assert; omitting it would make "nothing was published" indistinguishable
        from "that topic was never configured".
        """
        with self._lock:
            return {topic: len(messages) for topic, messages in self._by_topic.items()}
