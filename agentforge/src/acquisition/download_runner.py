"""Drive a fetch plan to completion (ADR-0024 D-3, D-7).

The other four modules are primitives: index, fetch, plan, extract. This is the loop that
uses them, and it exists because leaving it to be re-derived per run is how a session ends up
with sixteen throwaway scripts. The loop is small but every part of it was learned the hard
way:

* **A pass is not the run.** A span can fail (a rate limit outlasting its retries, a dropped
  connection) without the run failing; the entries in it stay pending and the next pass picks
  them up. Failing the whole transfer because one span timed out throws away hours of work.
* **Resume is the normal case.** A large transfer outlives its session. Progress lives on disk
  -- files present at their declared size -- not in a transcript, so a restart costs one span.
* **Making no progress is a stop condition.** A pass that fetches nothing new will fetch
  nothing new next time either; looping on it burns the rate limit and hides the real error.
* **Nothing wrong is written.** `archive_extract` verifies before writing, so a failure leaves
  an entry absent and pending rather than present and wrong.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from .archive_extract import ExtractError, Extracted, extract_span, is_complete
from .archive_index import Entry
from .fetch_plan import Plan, Selector, build_plan, pending
from .ranged_fetch import BudgetExceeded, RangeRefused, RangedFetcher

# (message) -> None. Default is silent; the command passes something that surfaces progress.
Reporter = Callable[[str], None]


@dataclass
class PassReport:
    """What one pass over the plan achieved."""

    spans_attempted: int = 0
    spans_failed: int = 0
    files_written: int = 0
    bytes_fetched: int = 0
    budget_exhausted: bool = False
    failures: list[str] = field(default_factory=list)

    @property
    def made_progress(self) -> bool:
        return self.files_written > 0


@dataclass
class RunReport:
    """The whole transfer, across however many passes it took."""

    passes: list[PassReport] = field(default_factory=list)
    remaining: list[Entry] = field(default_factory=list)
    stopped_because: str = ""

    @property
    def complete(self) -> bool:
        return not self.remaining

    @property
    def files_written(self) -> int:
        return sum(p.files_written for p in self.passes)

    @property
    def bytes_fetched(self) -> int:
        return sum(p.bytes_fetched for p in self.passes)

    def summary(self) -> str:
        state = "complete" if self.complete else f"incomplete — {len(self.remaining)} entries left"
        return (
            f"{state}: {self.files_written} files, {self.bytes_fetched / 1e9:.2f} GB fetched "
            f"over {len(self.passes)} pass(es){'; ' + self.stopped_because if self.stopped_because else ''}"
        )


def run_pass(
    plan: Plan,
    fetcher: RangedFetcher,
    dest_root: str,
    *,
    strip_prefix: str = "",
    base: int = 0,
    report: Reporter | None = None,
) -> PassReport:
    """Fetch and extract every span in `plan` once. A failed span is recorded, not raised."""
    say = report or (lambda _m: None)
    result = PassReport()

    for i, span in enumerate(plan.spans, 1):
        result.spans_attempted += 1
        try:
            blob = fetcher.fetch(span.start, span.end)
        except BudgetExceeded as exc:
            # The approved scope is a limit, not a suggestion: stop the pass, keep what landed.
            result.failures.append(f"budget: {exc}")
            result.budget_exhausted = True
            say(f"stopping — {exc}")
            break
        except RangeRefused as exc:
            result.spans_failed += 1
            result.failures.append(f"span {i}: {exc}")
            say(f"span {i}/{len(plan.spans)} refused ({exc}) — left for the next pass")
            continue

        result.bytes_fetched += len(blob)
        try:
            written: list[Extracted] = extract_span(
                blob, span.start, span.entries, dest_root, strip_prefix, base
            )
        except ExtractError as exc:
            # No individual file is ever partial — archive_extract verifies before it writes —
            # but a SPAN can be, so credit the entries that did land. Discarding them would
            # let a pass that genuinely wrote files report no progress, which stops the loop
            # early and reports a reason that is simply untrue.
            landed: list[Extracted] = getattr(exc, "written", [])
            result.files_written += len(landed)
            result.spans_failed += 1
            result.failures.append(f"span {i}: {exc}")
            say(
                f"span {i}/{len(plan.spans)} failed after {len(landed)} file(s) ({exc}) "
                "— the rest left for the next pass"
            )
            continue

        result.files_written += len(written)
        say(
            f"span {i}/{len(plan.spans)}: {len(blob) / 1e6:.0f} MB, {len(written)} files "
            f"| {fetcher.observed.rate_bytes_per_s / 1e6:.2f} MB/s"
        )
    return result


def run_to_completion(
    entries: Sequence[Entry],
    select: Selector,
    fetcher: RangedFetcher,
    dest_root: str,
    *,
    rate_bytes_per_s: float,
    per_request_penalty_s: float,
    strip_prefix: str = "",
    base: int = 0,
    limit: int | None = None,
    max_passes: int = 20,
    report: Reporter | None = None,
) -> RunReport:
    """Run passes until everything selected is on disk, or nothing more can be fetched.

    Each pass re-derives what is outstanding from the filesystem, so this is the resume path
    as well as the first-run path — calling it again after an interruption is correct and
    costs only what is genuinely missing.
    """
    say = report or (lambda _m: None)
    run = RunReport()

    for attempt in range(1, max_passes + 1):
        todo = pending(entries, lambda e: is_complete(dest_root, e, strip_prefix))
        todo = [e for e in todo if select(e)]
        if not todo:
            run.stopped_because = ""
            say("nothing outstanding")
            return run

        say(f"pass {attempt}: {len(todo)} entries outstanding")
        plan = build_plan(
            todo,
            lambda _e: True,          # already filtered; the plan just groups what is left
            rate_bytes_per_s=rate_bytes_per_s,
            per_request_penalty_s=per_request_penalty_s,
            base=base,
            limit=limit,
        )
        result = run_pass(
            plan, fetcher, dest_root, strip_prefix=strip_prefix, base=base, report=report
        )
        run.passes.append(result)

        if result.budget_exhausted and not result.made_progress:
            # The budget cannot recover within this run: another pass would refuse its first
            # span for the same reason. Name the cause rather than reporting it as a stall.
            run.stopped_because = "the approved budget is exhausted"
            break

        if not result.made_progress:
            # Another identical pass would fail identically; stop and surface the reason
            # rather than burning the rate limit against it.
            run.stopped_because = "a pass fetched nothing new — not retrying"
            break

    run.remaining = [
        e for e in pending(entries, lambda e: is_complete(dest_root, e, strip_prefix)) if select(e)
    ]
    if run.remaining and not run.stopped_because:
        run.stopped_because = f"stopped after {max_passes} passes"
    say(run.summary())
    return run


def verify_on_disk(
    entries: Iterable[Entry], dest_root: str, strip_prefix: str = ""
) -> list[Entry]:
    """Entries that should be present but are missing or the wrong size.

    Run this before declaring a transfer done. Size is checked against what the index
    declared, which catches a truncated write; it cannot catch corruption that preserves the
    byte count, and the manifest's CRC is the stronger check where a caller wants one.
    """
    return [e for e in entries if not e.is_dir and not is_complete(dest_root, e, strip_prefix)]
