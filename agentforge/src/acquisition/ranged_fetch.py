"""Rate-limit-aware HTTP byte-range client (ADR-0024 D-5, D-7, D-11).

The invariants here are not defensive programming; each one is a defect this module exists
because of:

* **206 is asserted, and 200 is refused.** `raise_for_status()` passes on 200. A server that
  ignores `Range` answers 200 with the *whole* body -- on the reference run, 44.58 GB -- and
  code that trusts `r.content` then parses full-file bytes as though they were the requested
  window, producing offsets that are wrong but entirely plausible.
* **Length is asserted.** A short body silently truncates the last entry of a span.
* **A cumulative budget hard-stops.** The scope the user approved at the gate is a limit, not
  a suggestion; without a counter, a planning error becomes an unbounded transfer.
* **Backoff is served, not raced.** The reference host rate-limits per *client*, so parallel
  connections starve each other and probing costs the real transfer (D-11).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol


class Response(Protocol):
    """The slice of a `requests.Response` this module uses — kept narrow so tests inject a fake."""

    status_code: int
    content: bytes

    def close(self) -> None: ...


class Transport(Protocol):
    """`requests.get`-shaped. Injected so the client is testable without a network."""

    def __call__(self, url: str, headers: dict[str, str], timeout: tuple[int, int]) -> Response: ...


class BudgetExceeded(RuntimeError):
    """The approved scope would be exceeded. Raised before the request is made."""


class RangeRefused(RuntimeError):
    """The server did not honour the Range request, or returned the wrong number of bytes."""


@dataclass
class RateObservation:
    """What was measured about this host — recorded once, not re-probed (D-11)."""

    bytes_fetched: int = 0
    seconds_transferring: float = 0.0
    throttle_events: int = 0
    seconds_backing_off: float = 0.0

    @property
    def rate_bytes_per_s(self) -> float:
        """Throughput excluding backoff — the figure fetch_plan's merge threshold needs."""
        return self.bytes_fetched / self.seconds_transferring if self.seconds_transferring else 0.0

    @property
    def mean_throttle_penalty_s(self) -> float:
        """Mean seconds lost per throttled request — the other half of the merge threshold."""
        return self.seconds_backing_off / self.throttle_events if self.throttle_events else 0.0


@dataclass
class RangedFetcher:
    """Fetch byte ranges from one URL under a hard cumulative budget.

    **Single-threaded by design, not by omission.** `_spent` is checked and then incremented
    without a lock, and backoff is slept in the calling thread. Both would be racy if one
    instance were shared across workers — which is deliberate: D-11 records that the hosts
    this exists for rate-limit per *client*, so concurrent connections share one budget and
    merely starve each other. Sequential use is the fast path here, not a compromise. Anything
    wanting parallelism must first establish that the host limits per connection.
    """

    url: str
    transport: Transport
    budget_bytes: int
    max_attempts: int = 10
    backoff_base_s: int = 30
    backoff_cap_s: int = 180
    timeout: tuple[int, int] = (30, 600)
    sleep = staticmethod(time.sleep)
    observed: RateObservation = field(default_factory=RateObservation)
    _spent: int = 0

    @property
    def spent_bytes(self) -> int:
        return self._spent

    @property
    def remaining_bytes(self) -> int:
        return max(self.budget_bytes - self._spent, 0)

    def fetch(self, start: int, end: int) -> bytes:
        """Fetch `[start, end)`. Raises rather than returning anything it cannot vouch for."""
        want = end - start
        if want <= 0:
            raise ValueError(f"empty range requested: [{start}, {end})")
        if self._spent + want > self.budget_bytes:
            raise BudgetExceeded(
                f"range of {want} B would take the total to {self._spent + want} B, "
                f"over the approved budget of {self.budget_bytes} B"
            )

        last_status: int | None = None
        for attempt in range(self.max_attempts):
            began = time.monotonic()
            response = self.transport(
                self.url, headers={"Range": f"bytes={start}-{end - 1}"}, timeout=self.timeout
            )
            last_status = response.status_code

            if response.status_code == 206:
                body = response.content
                if len(body) != want:
                    raise RangeRefused(
                        f"server returned {len(body)} B for a {want} B range — refusing to "
                        "treat a short body as the requested window"
                    )
                self._spent += want
                self.observed.bytes_fetched += want
                self.observed.seconds_transferring += time.monotonic() - began
                return body

            if response.status_code == 200:
                # Not a retryable condition: the host has decided to send the entire object.
                response.close()
                raise RangeRefused(
                    "server ignored the Range header and answered 200 with the full body; "
                    "refusing it — its bytes are not the requested window"
                )

            response.close()
            wait = min(self.backoff_base_s * (attempt + 1), self.backoff_cap_s)
            self.observed.throttle_events += 1
            self.observed.seconds_backing_off += wait
            self.sleep(wait)

        raise RangeRefused(
            f"range [{start}, {end}) not served after {self.max_attempts} attempts; "
            f"last status {last_status}"
        )
