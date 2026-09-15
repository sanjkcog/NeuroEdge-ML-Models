---
name: plant-and-project-lifecycle
description: How industrial control products are actually specified, tested and deployed — FEED, FID, FAT, SAT, commissioning, PSSR, turnaround cycles, brownfield migration and hot cutover, and why Management of Change makes continuous deployment structurally impossible in a covered process. Read before proposing any release, update or migration capability.
origin: NeuroEdge AgentForge — process automation domain pack
version: "1.0.0"
---

# Plant and Project Lifecycle

The cadence a real plant runs at. It is not the software release cadence, and requirements
that ignore the difference get built and then never deployed.

## When to Use

- Proposing any firmware/software update, patch or release mechanism
- Writing migration, commissioning, or acceptance-test requirements
- Estimating when a capability can actually reach a customer's live plant
- Any requirement that assumes the customer can restart the process

## The project lifecycle

| Phase | What it is | Who owns it |
|---|---|---|
| Concept / pre-FEED | Feasibility, technology selection, order-of-magnitude estimate | Owner-operator |
| **FEED** | Front-End Engineering Design — matures the estimate to AACE Class 2–3. Freezes P&IDs, control philosophy, I/O count, SIS architecture, room and cabinet layout. Deliverables: scope definition, cost estimate, baseline schedule, QRA (P50/P80), risk register, contracting strategy | Owner or FEED contractor; the owner's engineer holds the pen on the specification |
| **FID** | Final Investment Decision — the sanction gate FEED exists to make defensible | Owner's board |
| Detailed design / EPC | Loop drawings, wiring and termination schedules, cabinet GAs, application software, alarm rationalisation, cause & effect matrices, SRS. **Vendors are locked in here** | EPC contractor; MAC for the control scope |
| **FAT** | Factory Acceptance Test — staged off-site with simulated I/O, witnessed by the customer before shipment. Normative for SIS: **IEC 61511-1 Cl. 13** | Integrator executes; owner and often an independent assessor witness |
| **SAT** | Site Acceptance Test — repeated on real cabinets, real power, real network, usually still without live process | Integrator, witnessed by owner |
| Installation & commissioning | Cabinet installation, field termination, **loop checks** (every loop proven end-to-end, individually, signed off), energisation. **Cl. 14** for SIS | Construction contractor; commissioning team |
| Validation | Proving the SIS achieves the SRS — **Cl. 15** | Owner's functional safety engineer + independent FSA |
| **PSSR** | Pre-Startup Safety Review — **29 CFR 1910.119(i)** in the US. Confirms construction matches specification, procedures adequate, PHA recommendations resolved, personnel trained, before hazardous chemicals are introduced | Owner |
| Handover | As-built documentation, spares, licences, training, warranty | EPC → operations |
| **Turnaround (TAR)** | Planned shutdown during which anything needing a de-energised or de-pressured plant is done. **The only routine window for intrusive control-system work.** Scope is frozen months ahead and competed for by every discipline | Owner's TAR manager |

**The load-bearing consequence:** *the turnaround cycle, not the software release cycle,
sets the cadence at which an automation product can be changed in a live plant.* A
capability that requires a plant outage is on a multi-year release train. Anything that can
be delivered **without** an outage is worth disproportionately more than its engineering
cost suggests.

## Brownfield migration

Most of this market is replacement, not greenfield.

- **Cold cutover** — the control system is replaced while the process is not running.
- **Hot cutover** — replacement *"loop by loop and point by point"* while the plant is in operation. Chosen on **total cost of ownership, not upgrade cost**: it looks more expensive until lost production, startup risk and outage duration are counted.
- **Phased migration** spreads cost and reduces per-phase risk, but lengthens total cutover time.
- Four strategic axes of any migration: **hot vs cold · rip-and-replace vs phased · horizontal vs vertical · replication vs innovation.**

**Why re-termination dominates.** Field cables arrive from junction boxes at a **marshalling
cabinet**, where they are broken out and **cross-wired one signal at a time** onto terminals
matching the controller's I/O card layout. Disconnecting, re-landing and re-proving
thousands of terminations — plus a loop check for each — is the largest labour item, and it
is the one item better software cannot compress.

**Universal / configurable I/O** (electronic marshalling) is the specific engineering answer:
each channel is software-configurable as AI/AO/DI/DO, so field wiring can be landed in any
order and the cross-wiring step collapses.

> **Numbers discipline.** The *dominance* of re-termination cost and of lost-production cost
> is settled practitioner consensus. A published percentage, or a $/hour outage figure, is
> **not** verifiable and is wildly sector-dependent. State the dominance; refuse to invent
> the number. If a requirement needs a figure, it must come from the customer's own model.

## Management of Change — why continuous deployment is impossible here

**29 CFR 1910.119(l)(1):** *"The employer shall establish and implement written procedures
to manage changes (except for 'replacements in kind') to process chemicals, technology,
equipment, and procedures; and, changes to facilities that affect a covered process."*
The procedure must address technical basis, safety and health impact, changes to operating
procedures, required time period, and **authorisation requirements**. Under **(l)(3)**,
affected employees *"shall be informed of, and trained in, the change **prior to start-up**."*
The EU analogue is Seveso III (Directive 2012/18/EU). For the SIS specifically, MOC is
**IEC 61511-1 Cl. 17**.

Four mechanics that constrain product design:

1. **"Replacement in kind" is the whole game.** A like-for-like replacement escapes MOC. Anything that alters behaviour does not. A firmware update that changes a diagnostic threshold, an alarm limit, a scan rate or a comms timeout is **not** a replacement in kind.
2. **Training must precede startup.** A change altering operator-visible behaviour cannot be pushed; it must be scheduled around a training event.
3. **Authorisation is a named human**, not a CI pipeline. There is no MOC-compliant path to continuous deployment into a covered process.
4. **Therefore:** rolling releases, forced auto-updates, silent behaviour changes and feature flags that alter control behaviour are structurally incompatible with a PSM-covered plant.

**What works instead** — and what a good requirement should ask for:

- Long-term-support branches with published end dates
- **Security-only patch streams separated from feature streams** (the CRA also pushes this)
- Machine-readable change manifests a customer can paste into an MOC form
- An explicit, per-release statement of which changes are behaviour-affecting
- Configuration and firmware versions readable and exportable from the product for audit

## Implications for agents

- Never write a requirement for automatic, unattended or silent update into a live process.
- Any update mechanism must state whether it requires an outage. That single attribute usually decides the requirement's commercial value.
- Acceptance criteria for control products should reference FAT/SAT and loop check, not just unit tests.
- Migration requirements should name the cutover mode (hot/cold, phased/rip-and-replace) and the rollback point.
- Treat "customer data quality" as a real risk on any tooling that consumes existing I/O schedules — flag what could not be interpreted rather than inferring it.
