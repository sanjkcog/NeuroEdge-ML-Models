---
name: dataset-acquisition
description: Cross-pack rule for acquiring a dataset — read the source's index before any payload, price and scope the transfer from it, then fetch under a budget. Covers the ordering that makes acquisition cheap, the per-modality rule for what is a valid subset, and when NOT to hand-roll a transfer. Use at /dataset-scout (capture the index), /dataset-download (plan and fetch), and whenever a source is a monolithic archive.
origin: ADR-0024
---

# Dataset Acquisition

A dataset is **planned before it is fetched**. The index of an archive costs kilobytes and
prices the whole thing; the payload costs hours. Doing those in the wrong order is what makes
acquisition expensive, and it is the default mistake.

On the reference run (KIT CNC milling, 44.58 GB) the plan that emerged from 64 KB of index was
4.31 GB and ~2.3 h. The same data fetched without planning was heading for 44.58 GB and 13.2 h,
and an earlier attempt landed **2 files in one hour**. Nothing clever separates those outcomes —
only the order the steps were done in.

## The ladder — in this order, and the order is the point

1. **Read the index. Persist it.** Never fetch a payload byte to learn what is in an archive.
   Write it to `<dest>/data/archive-manifest.tsv`; every later question is then free.
2. **Group by file type.** The largest group is often derivable from the others and need not be
   fetched at all. This one step found 88% of the reference archive to be a redundant
   upsampled merge of data present in two other formats.
3. **Group by logical unit** — experiment, machine, class, episode. Scope to the units the
   objective needs. A further 56% on the reference run.
4. **Merge what remains into spans**, tolerating a gap only while it is cheaper than another
   request: `gap_threshold = measured_rate x per_request_penalty`.
5. **Fetch prefixes rather than whole units** — but only under the stationarity rule below.
6. **Stop when the model has enough**, not when the archive is exhausted.

Skipping to step 4 is the trap. Optimising a transfer of data you did not need to fetch is the
most expensive kind of efficiency.

## First: do not hand-roll this

The machinery below exists for **monolithic archives with no client library and no per-file
API**. That is the hard case, not the common one.

| Source | Do this instead |
|---|---|
| Hugging Face | `huggingface_hub` / `datasets` — resumable, ranged, Parquet-native |
| Kaggle | the `kaggle` CLI |
| Roboflow | the API export |
| TFDS | `tfds` |
| COCO-style | served per split — selection means choosing a URL |
| D4RL / Minari | served per task — same |

**Storage format decides what is possible.** CSV is row-oriented: fetching 3 of 61 columns means
fetching all 61. Parquet has a footer with per-column, per-row-group offsets, so the same
selection costs ~95% less. Where a source offers both, Parquet is categorically cheaper.

## Sizing: two budgets, never one

Wire bytes and disk bytes differ by the compression ratio (1.9:1 overall on the reference
archive, 4.7:1 for its CSVs). Report both — they are different constraints and a single figure
hides which one binds. Add a wall-clock projection from a **measured** rate; rate varies enough
(0.44–1.31 MB/s observed on one host in one session) that a byte budget alone bounds nothing.

## What counts as a valid subset — per modality

The transport is modality-agnostic. **Selection is not**, and it is where correctness lives.

| Modality | Unit | Valid | Invalid |
|---|---|---|---|
| Time series | experiment · machine · cutter | whole units; prefix under the rule below | prefix when the anomaly is localised in time |
| Vision | source image · capture session | stratified by class; class-scoped fetch | prefix of a file listing — archives sort by class, so a prefix is one class; splitting augmented variants of one source image across splits |
| Offline RL | episode · trajectory | whole episodes; stratified by task and quality | prefix of a replay buffer — biased toward early-policy behaviour |

Online RL has **no acquisition stage**: there is no dataset to scout or split (ADR-0023).

### The prefix rule

Fetching the first *n*% of a sequentially-compressed entry yields *n*% of its records. It is the
largest remaining saving and the **only** optimisation that changes *which* data you hold rather
than merely what it costs.

Permitted only when the run records, in writing, that the labelled condition holds across the
whole unit. The reference dataset contains its own counter-example: three experiments fitted a
pre-worn tool (constant — prefix-safe), while two others seeded blowholes at a stated depth
(localised in the toolpath — prefix-unsafe). No metric would reveal the difference afterwards.

## Transport safety — each rule is a defect that happened

- **Assert HTTP 206.** `raise_for_status()` passes on 200, and a host ignoring `Range` returns
  the entire object; parsing it as the requested window yields offsets that are wrong but
  entirely plausible. Refuse 200 — it is not a retryable condition.
- **Assert the response length** against the request. A short body truncates the last entry of
  a span while every other entry extracts perfectly.
- **Allow for the local header.** An archive index records where an entry's *header* starts, not
  its data. A span ending at `offset + compressed` is short by the filename and extra field.
- **Decode GNU base-256 tar sizes.** An octal-only parser silently returns 0 for a member over
  8 GB instead of failing.
- **Budget before the request**, cumulatively, and hard-stop.
- **Resume from what is on disk**, verified against the index's declared size — not from a
  transcript.
- **Measure the rate limit's scope once and record it.** Per-client and per-connection limits
  demand opposite strategies; under a per-client limit, parallel connections starve each other
  and every exploratory request slows the real transfer.

## Free wins people miss

- **Checksums are in the index.** ZIP carries a CRC32 per entry, so duplicate members are
  detectable with zero payload fetched. Most valuable where duplicates are endemic — vision.
- **The persisted manifest makes re-scoping free.** Every re-scope on the reference run was
  answered from the file on disk with no further requests.

## Do NOT

- Do not fetch payload to find out what an archive contains.
- Do not plan a transfer before scoping it — optimising the fetch of data you did not need is
  the most expensive efficiency there is.
- Do not hand-roll against a source whose client already does this.
- Do not prefix-fetch without a written stationarity claim.
- Do not report one byte figure — wire and disk are different budgets.
- Do not parallelise before establishing that the host limits per connection.
