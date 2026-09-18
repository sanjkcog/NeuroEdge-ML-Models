# /dataset-download — Price the transfer from the manifest, gate the scope, then fetch

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /dataset-download · Skills: dataset-acquisition, time-series-ml, vision-ml, ml-artifact-destination`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/ENGINEERING/_mechanism/dataset-acquisition.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/time-series-ml.md`
> - `agentic-assets/skills/ENGINEERING/ai-ml/vision-ml.md`
> - `agentic-assets/skills/ENGINEERING/_mechanism/ml-artifact-destination.md`
<!-- neuroedge-assets-patched source-version=b5f0180 -->

## Arguments

`$ARGUMENTS` — optional: `--dest <folder>` (always passed inside an `/agentforge-ml` run;
resolved once per `ml-artifact-destination` when standalone), `--scope <name>` to re-run a
decided scope without re-asking, `--plan-only` to stop after phase 1, `--resume` to continue an
interrupted transfer.

## What this does

Stages `plan` and `download` (ADR-0024 D-3). Phase 1 prices the transfer from the archive's own
index and **transfers nothing**; a human picks the scope; phase 2 executes it under a budget.
They are one command because a human decision separates them, not a tool boundary.

`/dataset-verify` no longer transfers anything — it profiles and splits data that is already
local.

## Phase 1 — `plan` (zero payload bytes)

1. **Get the index.** If `<dest>/data/archive-manifest.tsv` exists (written by `/dataset-scout`),
   read it — this costs nothing. Otherwise capture it now:

   ```python
   from agentforge.src.acquisition import archive_index
   # a nested archive (e.g. BagIt tar wrapping a zip) needs its base offset first
   base, size = archive_index.find_tar_member(fetch, "Data.zip")   # only if nested
   entries = archive_index.read_zip_index(fetch, size, base=base)
   archive_index.write_manifest(entries, f"{dest}/data/archive-manifest.tsv")
   ```

2. **Check the source first.** Per `dataset-acquisition`, if this is Hugging Face, Kaggle,
   Roboflow or TFDS, **stop and use its client** — record that as the plan and skip to phase 2's
   equivalent. The byte-range path is for monolithic archives only.

3. **Price it.** `fetch_plan.group_sizes` by file type, then by logical unit. Name the largest
   group and say whether it is derivable from the others. Report wire bytes and disk bytes
   separately, with a wall-clock projection from a measured rate.

4. **Propose two or more scopes**, each with its cost. At minimum: everything the objective
   could need, and the minimum the objective actually needs. `fetch_plan.duplicate_groups`
   costs nothing and may remove more.

5. **Write `<dest>/data/fetch-plan.json`** — the chosen selector, the spans, both budgets, the
   projection, and the rate/penalty the merge threshold was derived from.

### The scope gate (D-3a) — hard, human

Present: total size; size by file type with any redundant group named; size by unit; the
candidate scopes with wire cost, disk cost and projected wall-clock; and a recommendation with
its reason. Record the outcome with `gate_state.py`:

- **approve** a scope → phase 2
- **narrow** it → re-plan, then re-present
- **reject** → back to `/dataset-scout` with the reason as a constraint

**A run may not enter `download` without a recorded scope decision.** An unbounded transfer is
the failure this command exists to prevent.

## Phase 2 — `download`

```python
import requests
from agentforge.src.acquisition import download_runner, ranged_fetch

fetcher = ranged_fetch.RangedFetcher(url, requests.get, budget_bytes=approved_scope_bytes)
run = download_runner.run_to_completion(
    entries, selector, fetcher, raw_dir,
    rate_bytes_per_s=rate, per_request_penalty_s=penalty,
    strip_prefix=prefix, base=base, limit=archive_size,   # limit: clamps the last span to EOF
    report=print,                                          # progress, span by span
)
print(run.summary())
assert not download_runner.verify_on_disk(entries, raw_dir, prefix), "entries missing or wrong size"
```

`run_to_completion` **is** the resume path — re-running it after an interruption re-derives what is
outstanding from the filesystem and fetches only that, so there is no separate resume branch to write.
A span that fails leaves its entries pending for the next pass rather than failing the run; a pass that
fetches nothing new stops the loop instead of burning the rate limit against the same error.

Pass `limit` whenever the archive size is known. `HEADER_MARGIN` pushes the final span past the last
byte, a server clamps that range and returns fewer bytes than asked for, and `ranged_fetch` correctly
refuses a short body — so without `limit` the last span of a non-nested archive fails every time.

- Raw data lands **outside git** — `<dest>/data/raw/`, with a `.gitignore` rule verified by
  `git check-ignore` *before* the first byte. The `pre-commit-ml-artifact` hook blocks blobs,
  but the rule is the control.
- **Resume is the norm, not the exception.** A transfer will outlive its session. Each pass
  skips entries already on disk at their declared size, so a restart costs one span, not the run.
  `--resume` reads `fetch-plan.json` and the files present; it never replays a transcript.
- **Report progress and failures**, not just completion: spans done, bytes against budget,
  observed rate, and anything refused.
- On a long transfer, set the `run.json` gate to `{pending: true, stage: download,
  reason: waiting_transfer}` and stop the session cleanly rather than polling.

## Then

`/dataset-verify --dest <dest>` — profile, split, build the upload package, present the data
gate. It reads only what is already on disk.

## Do NOT

- Do not fetch payload to discover what an archive holds.
- Do not transfer before a scope decision is recorded.
- Do not hand-roll against a source whose client already does resumable ranged transfer.
- Do not prefix-fetch without the written stationarity claim (`dataset-acquisition`).
- Do not parallelise before establishing the rate limit is per-connection, not per-client.
- Do not `git add` anything under `data/raw/`.
