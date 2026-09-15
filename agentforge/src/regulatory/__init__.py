"""agentforge.src.regulatory — ADR-0009 EP-01 keystone reference implementation.

Ports & Adapters mapping (see neuroedge/docs/project_related/regulatory-format-adaptation/
04-development/hld.md §1): canonical `FR-NN`/`EP-NN`/`US-NN`/`TS-NN`/`TC-NN` artifacts
are the untouched domain core. Everything in this package is an OUTBOUND adapter or
the one inbound use case that composes them — none of it is imported by the domain
core or by downstream tooling (`/prd-to-epics`, `/stories-to-tasks`, `/trace-matrix`).

Modules:
- `specval`           — load/validate a regime spec against the FR-02 meta-schema;
                        class-gate filter.
- `reformat`          — the FR-04 use case; the single never-synthesize enforcement
                        point (`_emit_section`).
- `conformance_gate`  — FR-05 wrapper over `agentforge.src.state.gate_state`; no
                        override path exists.
- `id_map`            — FR-06 boundary-only, append-only, degrade-to-canonical ID
                        translation layer.

This package intentionally has no `__all__` re-export surface: import the submodule
you need directly (`from agentforge.src.regulatory import specval`) so every caller's
dependency on a specific outbound adapter stays explicit and grep-able.
"""

from __future__ import annotations
