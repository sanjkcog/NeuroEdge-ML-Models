# AgentForge — src

Implementation lives here **only when it has no conventional home elsewhere in this
repo.** Commands, agents, skills, and hooks keep their existing locations so
`install.py` picks them up unchanged.

**Status: `state/` (P1-P3) and `qa/`'s adapter layer (P4) are implemented.** Runners,
oracles, and TC-ID/matrix rendering logic are still pending (P4b/P5) — see
`../docs/project_related/objectives/project_objectives.md` §12 for the phase order.

## Current layout

```
src/
  state/
    run_state.py     STAGE_SEQUENCE/STAGE_AGENTS, run.json read/write, resume/validate
    gate_state.py     gates.json — HITL approval state, ATOMIC_STATE_IO pattern
  qa/
    adapter.py        TestManagementAdapter protocol, UploadResult, NoneAdapter (D12 fallback)
    zephyr_adapter.py  ZephyrAdapter — POSTs JUnit XML to Zephyr Scale's documented
                       REST endpoint via stdlib urllib.request (first vendor, ADR-0003)
    vendor_config.py   VendorConfig/VendorChoice — D16 prompt-once persistence, JSON
                       (not YAML — disclosed deviation, see qa-traceability.plan.md)
```

## Still to build (not yet started)

```
src/qa/
  runners/      one module per framework, each implementing
                detect / select / prepare / execute / collect
                pytest · catch2_ctest · gtest · playwright · vitest
                junit5 · robot · selenium · k6 · schemathesis      (P5)
  trace.py      TC-ID parsing, coverage matrix rendering, gap detection  (P4b)
  oracles/      golden+tolerance · statistical · invariant · differential (P5)
```

A second test-management adapter (TestRail, `US-05-03`) is deferred, not stubbed —
`qa/adapter.py`'s `TestManagementAdapter` protocol is the extension point; there is no
`adapters/` subpackage, the two adapters that exist today are flat modules beside
`adapter.py`.

## Conventions

- **Python, stdlib-first.** Vendor CLIs (`trcli`) and plain HTTP beat SDK dependencies.
- **Adapters wrap vendor tooling; they do not reimplement it.** See decision D8.
- **Runners never assume a framework is present** — `detect()` decides. See D10.
- **`none` is a first-class vendor.** Everything must work with no licence and no
  vendor configured. See D12.
- Tests for this code live beside it and run under the repo's own pytest config —
  AgentForge is expected to pass its own coverage gate.
