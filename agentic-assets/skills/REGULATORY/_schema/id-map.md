# ID-map layer (FR-06)

`agentforge/src/regulatory/id_map.py` — a boundary-only, append-only symbolic-ID
translation layer. Canonical stays the working currency everywhere else (FR-01); the
map exists only so a rendered customer-facing document can show the customer's own
scheme instead of `FR-NN` / `EP-NN` / `US-NN` / `TS-NN` / `TC-NN`.

## Namespaces

One instance-map file spans all five namespaces — there is no per-namespace file to
keep in sync:

```
NAMESPACES = ("requirement", "epic", "story", "task", "testcase")
```

Namespace is inferred from the canonical ID's own prefix (`FR-` → requirement,
`EP-` → epic, `US-` → story, `TS-` → task, `TC-` → testcase) — `resolve()` and `bind()`
take the canonical ID alone; there is no separate namespace argument to keep in sync
with the ID itself.

**OQ-5 (the per-project instance-map file's canonical path/location) is TBD and
non-blocking** — this reference module accepts an explicit path at every call site
(`load(path)`); a project wires its own conventional location when it adopts this
capability. Nothing in this module hardcodes a path.

## Shape

```json
{
  "schema_version": "1.0",
  "bindings": {
    "FR-01": "QC-Req-1-v1",
    "EP-01": "QC-Epic-1",
    "US-01-02": "QC-Story-1-2",
    "TS-01-02-01": "QC-Task-1-2-1",
    "TC-01-02-01": "QC-TC-1-2-1"
  }
}
```

## API

- `resolve(canonical_id) -> str` — returns the bound customer ID, or the canonical ID
  **unchanged** on a miss or while degraded. **Never raises.** While degraded, emits
  exactly one non-fatal notice (not one per call) recorded on the `IdMap` instance —
  a fault can only ever produce "canonical IDs shown", never a dropped trace row and
  never an unhandled exception (H4).
- `bind(canonical_id, customer_id)` — **append-only**. Binding a canonical ID to the
  same customer ID again is idempotent (a no-op). Rebinding an **already-bound**
  canonical ID to a **different** customer ID raises `IdMapRenumberError` and leaves the
  existing binding untouched (AC-06.3) — the map can grow, never renumber.
- `load(path) -> IdMap` — reads one instance-map file. An **absent** path or a
  **corrupt** (unparseable/truncated/malformed-shape) file both degrade to
  `IdMap(degraded=True)` — never raises. `degraded` is a plain attribute a caller can
  check.

## Boundary-only

`resolve()` (and `bind()`) are called only inside the `reformat` use case (and, in a
future ingest path) — never by the canonical-currency engine or by any downstream
tool (`/prd-to-epics`, `/stories-to-tasks`, `/trace-matrix`). Those tools have zero
references to this module (`test_no_idmap_in_tooling.py` / `test_id_map_boundary_only.py`,
both asserting grep-count `== 0`). Canonical `FR-NN`/`TC-NN` remain the only IDs the
domain core and downstream tooling ever see or reason about.
