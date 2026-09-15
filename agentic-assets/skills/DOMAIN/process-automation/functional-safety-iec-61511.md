---
name: functional-safety-iec-61511
description: Functional safety for process-sector products — IEC 61511 and IEC 61508, the SIS lifecycle from HAZOP to proof test, the SIS/BPCS independence and risk-reduction-credit rules, and the exact wording a vendor is allowed to use about SIL. Read before writing any requirement, claim or test that touches a safety instrumented function.
origin: NeuroEdge AgentForge — process automation domain pack
version: "1.0.0"
---

# Functional Safety — IEC 61511 / IEC 61508

The rules that decide whether a product may go anywhere near a safety instrumented
function, and what a vendor is allowed to say about it.

## When to Use

- Any requirement, epic, story or test involving SIS, ESD, F&G, BMS, HIPPS or a trip
- Writing or reviewing a datasheet, UI string or marketing claim containing "SIL" or "safety"
- Deciding whether a control feature may share hardware with a safety feature
- Planning a release that touches certified firmware

## The two standards

- **IEC 61508:2010 (Ed 2.0, 7 parts)** — the generic product standard. Defines SIL 1–4 and the safety lifecycle for the *manufacturer*.
- **IEC 61511-1:2016 Edition 2.0 + AMD1:2017** — the process-sector standard, for the *end user's* SIS. US adoption is **ANSI/ISA-61511-1-2018**. "ISA-84" and "IEC 61511" are the same requirement set today.

## SIL is a property of a function, never of a device

This is the single most-abused fact in the vertical.

- A **SIL** is assigned to a **SIF** (safety instrumented function) by risk assessment, and is achieved by the whole loop — sensor + logic solver + final element + proof-test regime + mission time.
- A **device** cannot "be SIL 2". What a device can hold is:
  1. **Systematic capability (SC 1–4)** — earned by developing the product under an IEC 61508-audited management system. This is what a vendor certificate actually attests to.
  2. **Architectural constraints data** — SFF, HFT, Type A/B — which cap the SIL the device can support in a given architecture.
  3. **Random failure data** — λ_DU, λ_DD, diagnostic coverage, proof-test coverage — which the *user* feeds into the *loop's* PFDavg calculation.

**Correct claim wording:** *"Systematic capability SC 3, Type B, SFF x %, λ_DU = y FIT, PTC = z %, suitable for use in SIL 3 SIFs subject to loop verification."*
**Forbidden wording:** *"SIL 3 device", "SIL-rated", "SIL-ready", "safety capable"* before a certificate exists.

A **Safety Manual** is a normative deliverable, not marketing collateral.

### PFDavg bands (low demand)

| SIL | PFDavg | RRF |
|---|---|---|
| 1 | 10⁻² to <10⁻¹ | 10 – 100 |
| 2 | 10⁻³ to <10⁻² | 100 – 1 000 |
| 3 | 10⁻⁴ to <10⁻³ | 1 000 – 10 000 |
| 4 | 10⁻⁵ to <10⁻⁴ | 10 000 – 100 000 |

High-demand / continuous mode uses **PFH** (dangerous failures per hour) with equivalent decade bands.

For a simple 1oo1 loop, PFDavg ≈ λ_DU × TI/2 — so **doubling the proof-test interval roughly doubles PFDavg**. The proof-test interval is therefore a *safety requirement*, not a maintenance preference.

## Independence between SIS and BPCS — the load-bearing rules

**IEC 61511-1:2016 Clause 9.3, "Requirements on the basic process control system as a protection layer"** governs how much credit a BPCS may be given:

- A BPCS **not** designed *and* managed to IEC 61511 may be claimed as a protection layer, but the risk reduction claimed is **limited to a factor of 10**. Edition 2 raised the bar: to claim more than 10 the BPCS must be **designed *and* managed** to IEC 61511 — at which point it is, in effect, a SIS.
- **No more than one** BPCS protection layer may be claimed for the same sequence of events **when the BPCS is the initiating source**.
- **No more than two** BPCS protection layers may be claimed **when the BPCS is not the initiating source** — so total credit from a non-61511 BPCS is capped at roughly 100.
- Corollary: a BPCS alone cannot deliver SIL 1.

**Clause 11.2.10** governs shared devices, verbatim:

> "A device used to perform part of a safety instrumented function shall not be used for basic process control purposes, where a failure of that device results in a failure of the basic process control function which causes a demand on the safety instrumented function, unless an analysis has been carried out to confirm that the overall risk is acceptable."

**Clause 9.4** — *Requirements for preventing common cause, common mode and dependent failures* — is where independence between claimed layers is governed. **Clause 8.2.1 NOTE** requires common cause between demand-creating and protecting systems to be accounted for.

> **Precision note.** Cite **"IEC 61511-1:2016 Clause 9.3"** for the credit rule. The exact
> subclause (9.3.2 / 9.3.3 / 9.3.4) is not verified here — do not invent one. Edition 1's
> equivalent clauses were 9.4.2 and 9.4.3.

**Clause 8.2.4** (new in Edition 2) requires *"a cybersecurity risk assessment shall be performed to identify security vulnerabilities of the SIS"* — this is the clause that makes IEC 62443 work mandatory on SIS projects.

## The safety lifecycle — what each stage produces

| Stage | Produces | Anchor |
|---|---|---|
| HAZID | Register of major accident scenarios | pre-FEED |
| HAZOP | Node-by-node guideword analysis against **frozen P&IDs** — causes, consequences, safeguards, actions | FEED, repeated on as-builts |
| LOPA | Independent protection layers counted against initiating-event frequency → risk-reduction gap → **SIL target** per SIF. This is where the Clause 9.3 cap bites |  |
| **SRS** | Safety Requirements Specification: per SIF — safe state, trip points, SIL target, response time, HFT, spurious-trip tolerance, bypass rules, reset philosophy, proof-test interval and coverage, mission time | **IEC 61511-1 Cl. 10** |
| SIL verification | PFDavg (or PFH) for the whole loop + architectural-constraint check | **Cl. 11.4** (HFT), **Cl. 11.9** (quantification) |
| FAT | Staged off-site test with simulated I/O, witnessed | **Cl. 13** |
| Installation & commissioning | Loop checks, energisation | **Cl. 14** |
| Validation | End-to-end proof against the SRS on the installed system | **Cl. 15** |
| Proof testing | Reveals **dangerous undetected** failures; confirms the assumed interval and coverage still hold | Cl. 16 |
| Modification | Any change re-enters the lifecycle at the appropriate phase | **Cl. 17** |

## Voting architectures

- **1oo1** — single channel, no fault tolerance.
- **1oo2** — either channel trips; higher integrity, higher spurious trip rate.
- **2oo2** — both must agree; lower spurious trips, lower integrity.
- **1oo2D** — two channels with diagnostics; a detected failed channel degrades voting to 1oo1 rather than tripping. Trades a little integrity for a large spurious-trip reduction.
- **2oo3 / TMR** — three channels, hardware majority vote; fault-tolerant *and* low spurious-trip. The classic process-SIS architecture.

## Implications for agents

- **Never** generate a requirement, story, UI string or datasheet line claiming a SIL for a device. Use the systematic-capability wording above.
- **Never** design an architecture in which the BPCS can command, inhibit, bypass or reset a safety function. A status path to the control system is read-only, always.
- Any requirement that shares a sensor, cable, card, logic solver or power supply between control and safety **must** cite Clause 11.2.10 and require a documented analysis.
- Every safety-related requirement should name its SRS attribute (trip point, response time, proof-test interval) rather than describing behaviour loosely.
- Redundancy underwrites **availability**, not safety. Never present a redundant control pair as a contribution to a SIL claim.
- Treat certification schedule as the critical path. A safety variant's certificate, not its code, is what gates its release.
