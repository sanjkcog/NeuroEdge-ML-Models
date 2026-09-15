# IEC 62304 — Medical device software life cycle processes (ADR-0009 keystone)

`spec.json` is a data instance of the FR-02 meta-schema
(`skills/REGULATORY/_schema/format-spec.schema.json`), read by
`agentforge/src/regulatory/specval.py`. This document is the human-readable companion
to that data — it does not itself carry any regulatory content.

**Edition pinned:** `2006+A1:2015` (IEC 62304:2006 plus Amendment 1:2015).
**Authority:** IEC. **Classification axis:** Class A / B / C (per §4.3 software safety
classification — increasing rigor A → B → C).

## Non-certification notice

This spec instance and the reformatter that renders against it produce a **draft for
expert review**, never a certification or compliance attestation. `conformance_result`
is present/absent-only (no "certified" / "compliant" wording anywhere in this
pipeline, C-2) — an authorized reviewer, not this tooling, makes any conformance
determination.

## Class-gated required-sections table

| Section id (never literal `"DHF"`) | §ref | Required for classes | `fillable` |
|---|---|---|---|
| `software-development-plan` | §5.1 | A, B, C | true |
| `software-requirements` | §5.2 | A, B, C | true |
| `software-architecture` | §5.3 | **B, C** (exempt A) | true |
| `detailed-design` | §5.4 | **C only** | true |
| `unit-implementation-verification` | §5.5 | A, B, C | true |
| `software-integration-testing` | §5.6 | **B, C** (exempt A) | true |
| `software-system-testing` | §5.7 | A, B, C | true |
| `software-release` | §5.8 | A, B, C | true |
| `soup-identification` | §5.3.3/§8.1.2 | A, B, C | true |
| `soup-anomaly-evaluation` | §7.1.3 | A, B, C | **false** |
| `risk-management-iso14971` | §7 | A, B, C | **false** |
| `software-configuration-management` | §8 | A, B, C | true |
| `software-problem-resolution` | §9 | A, B, C | true |
| `design-development-record-set` | §5 (QMSR-harmonized) | A, B, C | true |

Class A drops the architecture (§5.3) and integration-testing (§5.6) sections; class C
adds detailed design (§5.4) on top of everything class B requires. This is expressed
purely as data (`required_for_classes` per section) — there is no separate schema fork
per class (AC-02.4/AC-03.1).

## Why two sections are `fillable: false`

`soup-anomaly-evaluation` (§7.1.3) and `risk-management-iso14971` (§7) are the two
sections where a model-generated "best guess" would itself be a safety event — a
fabricated SOUP anomaly evaluation or a fabricated risk statement is worse than an
honest gap. Both cross-reference **ISO 14971:2019** (Application of risk management to
medical devices); their content is authored by a human risk-management process outside
this tooling and only ever surfaces here as a gap requiring expert input
(`agentforge/src/regulatory/reformat.py`'s single write path, `_emit_section`, refuses
to populate either regardless of what the source document contains — AC-03.3, AC-04.4,
RK-01/RK-02).

## Why the record set is `design-development-record-set`, never `"DHF"`

FDA's historical "Design History File" (DHF) requirement is being harmonized into the
Quality Management System Regulation (QMSR, effective **2026-02-02**) which aligns FDA
device-software recordkeeping with **ISO 13485:2016**. Hardcoding the literal token
`"DHF"` as a section id would bake a single jurisdiction's legacy term into a
product-neutral spec instance that other regimes/authorities also read. This spec
instead encodes the underlying **requirement** — a design-and-development record set —
as `design-development-record-set` (§5, QMSR-harmonized), cross-referencing both
`21-CFR-820.30(j)` (historical DHF clause) and `ISO-13485:2016` (§4.2.3-equivalent
technical file expectations) so downstream authors can map to whichever term their own
regulatory context uses.

**OQ-1 (the precise QMSR/ISO-13485:2016 clause-level mapping beyond the two
cross-references above) is TBD** — noted here rather than silently assumed; it does not
block this EP-01 keystone slice, which only needs the record-set concept represented as
a requirement, not asserted as a fully worked jurisdictional crosswalk.
