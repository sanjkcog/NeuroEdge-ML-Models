"""The replay engine — the loop that ties loaders, transport, and writer together.

For each input file it streams raw payloads from the loader, wraps them in a
:class:`Record`, stamps ``seq``/``ts``, sends over the transport, logs via the
writer, and paces the loop to the requested rate.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from . import loaders
from .record import Record
from .transports import Transport, TransportError
from .writers import Writer


def _safe_close(closer: Callable[[], None], label: str) -> None:
    """Run a teardown callable, downgrading any failure to a warning.

    Called from run()'s finally for both writer and transport close: a teardown
    error must not replace an exception already unwinding (Python's finally would
    otherwise discard the original) nor fail an otherwise-successful run.
    """
    try:
        closer()
    except Exception as exc:  # noqa: BLE001 - deliberately broad; teardown must not raise
        print(f"[engine] warning: {label} close failed: {exc}", file=sys.stderr)


@dataclass
class ReplayConfig:
    input_dir: Path
    input_glob: str = "*"
    media_mode: str = "ref"      # ref | b64
    rate: float = 1.0            # records per second (0 = as fast as possible)
    loop: int = 1               # number of passes over the inputs; -1 = forever
    limit: int = 0              # 0 = no cap, else stop after N records

    @property
    def interval(self) -> float:
        return 0.0 if self.rate <= 0 else 1.0 / self.rate


class ReplayEngine:
    def __init__(self, config: ReplayConfig, transport: Transport, writer: Writer) -> None:
        self.config = config
        self.transport = transport
        self.writer = writer

    def _raw_payloads(self) -> Iterator[tuple[str, dict]]:
        """(source_name, payload) across every discovered file, in filename order."""
        files = loaders.discover(self.config.input_dir, self.config.input_glob)
        if not files:
            raise FileNotFoundError(
                f"no supported input files in {self.config.input_dir} "
                f"(glob {self.config.input_glob!r})"
            )
        for path in files:
            for payload in loaders.iter_payloads(path, self.config.media_mode):
                yield path.name, payload

    def run(self) -> int:
        """Emit records until inputs are exhausted (respecting loop/limit).

        Returns the number of records sent. open()/close() on transport and
        writer are handled here so a KeyboardInterrupt still flushes and cleans
        up.
        """
        cfg = self.config
        interval = cfg.interval
        sent = 0
        passes_done = 0
        # transport.open() first; if it raises there is nothing to clean up on the
        # writer side yet. Everything after is guarded by the finally so a failure
        # in writer.open() (or anywhere in the loop) still closes the transport —
        # otherwise a bound SSE socket / open MQTT connection would leak.
        #
        # OSError from a transport call is re-raised as TransportError so the CLI can
        # label it correctly. A writer/loader OSError (disk full, bad permissions on
        # sim_output/ or sim_input/) is left as a plain OSError — mislabelling those
        # as "transport failed" sent debuggers to the wrong subsystem.
        try:
            self.transport.open()
        except OSError as exc:
            raise TransportError(f"could not open {self.transport.name} transport: {exc}") from exc
        # Fail-safe default: assume an error is unwinding, flipped to False only at a
        # clean return. A LOCAL flag, not sys.exc_info() — the latter is ambient
        # (reflects any exception being handled anywhere up the call stack), so a
        # caller invoking run() from inside its own `except` block would read it as
        # in-flight and wrongly swallow a real writer output-loss error.
        run_failed = True
        try:
            self.writer.open()
            try:
                while True:
                    for source, payload in self._raw_payloads():
                        record = Record(
                            seq=sent,
                            ts=time.time(),
                            source=source,
                            kind=loaders.family_of(Path(source)),
                            payload=payload,
                        )
                        try:
                            self.transport.send(record)
                        except OSError as exc:
                            raise TransportError(
                                f"{self.transport.name} send failed at seq={sent}: {exc}"
                            ) from exc
                        self.writer.write(record)
                        sent += 1
                        if cfg.limit and sent >= cfg.limit:
                            run_failed = False
                            return sent
                        if interval:
                            time.sleep(interval)
                    passes_done += 1
                    if cfg.loop == -1:
                        continue  # forever
                    if passes_done >= cfg.loop:  # loop=N -> exactly N passes (default 1)
                        break
            except KeyboardInterrupt:
                print(f"\n[engine] interrupted after {sent} record(s)")
            run_failed = False
            return sent
        finally:
            # writer.close() is NOT pure teardown for the buffered formats: json and
            # csv do the real file write here, so a failure is genuine output loss and
            # must surface (discarding the return, so the CLI reports it) — UNLESS the
            # run is already failing, in which case swallowing would only hide the more
            # useful primary error. transport.close() IS pure teardown (records already
            # went out), so it is always best-effort. The inner finally guarantees the
            # transport is closed even if writer.close() raises.
            try:
                if run_failed:
                    _safe_close(self.writer.close, "writer")
                else:
                    self.writer.close()  # may raise -> becomes the run's failure
            finally:
                _safe_close(self.transport.close, "transport")
