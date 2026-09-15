# Conformance gate (FR-05)

`agentforge/src/regulatory/conformance_gate.py` — a thin wrapper over the existing
`agentforge/src/state/gate_state.py`. It adds regulatory semantics only; it does not
re-implement gate mechanics.

## Rule

A gapful `conformance_result` (any required section absent, or any `fillable:false`
section) opens a **hard** gate:

```
evaluate(conformance_result, artifact, *, gates_path, stage="S-conformance", opened_by="reformatter") -> "BLOCKED" | "PASS"
```

- `conformance_result["status"] == "gaps"` → `GateState.open_gate(artifact, stage=stage, gate_type="hard", opened_by=opened_by)`, save, return `BLOCKED`.
- Otherwise → return `PASS`. No gate is opened when nothing is required-but-absent.

## No override — by construction, not by convention

`evaluate` exposes **no** override / force / flag / bypass parameter. There is no
argument name, config key, or environment variable this module reads that changes a
gapful result into anything other than `BLOCKED`. This is a structural absence, not a
documented-but-ignorable rule: read the function signature — the parameter simply does
not exist. A caller cannot pass a bypass because there is nothing to pass it to.

## Clearing

The **only** way out of `BLOCKED` is the existing, unmodified
`GateState.record_decision(artifact, "approved", identity=<reviewer>)`:

```
is_cleared(artifact, *, gates_path) -> bool   # True iff gate status == "approved"
```

- `identity` must be a distinct reviewer from `opened_by` — `record_decision` already
  raises `SelfApprovalError` if the identity that opened the gate is the same one trying
  to approve it (ADR-0012 self-approval guard, reused unchanged here).
- `changes_requested` / `rejected` outcomes leave the gate **not** approved —
  `is_cleared` stays `False`; `reopen_gate` can re-arm it for another pass, preserving
  the decision history.
- Approving writes an auditable `Decision` (identity, timestamp, outcome) into
  `gates.json` via the same atomic temp-file + `os.replace` write `gate_state.py` already
  uses for every other gate.

## Composition with ADR-0008

This module reuses `gate_state.py` verbatim — same `gates.json`, same `type` enum, same
`status` semantics that `stop-hitl-gate.js` / `pre-write-hitl-gate.js` already read. It
adds a boundary (a new kind of artifact that can be gated); it does not relax, patch, or
special-case any existing ADR-0008 gate behavior. The existing hard-gate suite runs
unchanged with this module present (TS-01-01-04 / AC-05.4).
