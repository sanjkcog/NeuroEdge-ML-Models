---
name: process-automation-fundamentals
description: The layered architecture of a process plant — ISA-95/Purdue Levels 0-4, what a DCS, PLC, SCADA, HMI, RTU and SIS each are, where each sits, and how a single field measurement travels from a tapping point to the ERP. Read this before writing any requirement, architecture or test artefact for an industrial control product.
origin: NeuroEdge AgentForge — process automation domain pack
version: "1.0.0"
---

# Process Automation Fundamentals

The layered model of a process plant, and the vocabulary that goes with it. Most confusion
in this vertical is really a question of **which layer am I standing on**.

## When to Use

- Writing requirements, architecture or test plans for any control-system product
- Deciding where a capability belongs (controller? supervisory? MES?)
- Reviewing a claim that a product "integrates with the DCS" — ask at which level
- Any time BPCS and SIS appear in the same sentence

## The layer model

The hierarchy comes from the **Purdue Enterprise Reference Architecture (PERA)**, developed
in the early 1990s by the Industry–Purdue University Consortium for CIM. Its Level 0–4
hierarchy was absorbed into **ISA-95 / IEC 62264**'s functional hierarchy model, which is
where practitioners actually meet it. ANSI/ISA-95.00.01-**2025** is the current Part 1.

| Level | Name | What lives there | Time scale |
|---|---|---|---|
| **L4** | Enterprise | ERP, order books, procurement, finance | days – months |
| **L3** | Operations (MOM/MES) | Scheduling, batch, quality/LIMS, plant historian, maintenance | minutes – shifts |
| *3.5* | *DMZ* | *Historian replicas, patch servers, data diodes* | *—* |
| **L2** | Supervisory | Operator stations, SCADA, alarm system, area historian | ~1 second |
| **L1** | Basic control | DCS controllers, PLCs, RTUs — **and, separately, the SIS logic solver** | 10–500 ms |
| **L0** | Process | Transmitters, valves, drives, motor starters, the process itself | continuous |

Two facts that are commonly stated wrongly and must not be repeated in generated artefacts:

- **ISA-95 primarily addresses the Level 3 ↔ Level 4 interface.** It is not a wiring model
  or a security model.
- **"Level 3.5 / the DMZ" is a community convention.** It is not part of PERA, not part of
  ISA-95, and not an IEC 62443 term. See `industrial-cybersecurity-iec-62443.md`.

## Where each system actually sits

| Thing | Level | Note |
|---|---|---|
| Transmitter, valve, drive | L0 | A "smart" HART transmitter has a processor and is still L0 |
| **PLC** | L1 | A *platform*, not a role. A standard PLC serves the BPCS; a certified safety PLC serves the SIS |
| **DCS** | **L1 + L2** | One integrated system spanning two levels — its controllers are L1, its operator stations, alarms and historian are L2. This is the single most common beginner error |
| **SCADA** | L2 | Supervisory over geographically dispersed L1 controllers/RTUs. SCADA does not perform the control. Now formally addressed by ANSI/ISA-112.00.01-2025 |
| **HMI** | a role, not a level | A panel HMI on a skid and a control-room console are both HMIs at different levels. Design governed by ISA-101.01-2015 |
| **RTU** | L1 | Remote, unattended, power- and bandwidth-constrained sites |
| **SIS logic solver** | L1, separate lane | At Level 1 but *not part of* the BPCS at Level 1 |
| Historian | L2 and L3 | Often the same product deployed twice |
| MES / MOM | L3 | Sends recipes and targets down; never closes a control loop |
| Engineering workstation | L2, reaches L1 | The highest-privilege machine in the plant |

## BPCS and SIS — the two systems at Level 1

| | BPCS | SIS |
|---|---|---|
| Job | Hold the process at setpoint | Take the process to a safe state when it has left the envelope |
| Mode | Continuous, every scan | Dormant; acts on demand |
| Failure philosophy | Fail-operational (availability first) | Fail-safe, de-energise to trip |
| Rating | None | SIL target, proven by calculation and proof test |
| Change control | Routine | Formal MOC, revalidation, key-switch |

**The rule that follows from this:** the demand rate on the SIS *is* the failure rate of the
BPCS. Protecting yourself with the system that just failed you is not protection. The
independence requirements in `functional-safety-iec-61511.md` exist for exactly this reason
and must be reflected in any requirement that touches a safety path.

## Tracing one signal — the worked mental model

A level transmitter `LT-101` on vessel `V-101`, calibrated 0–2000 mm as 0–100 %, reading 62 %:

1. **L0** — the DP cell outputs 4 + (0.62 × 16) = **13.92 mA**. The *live zero* means 0 mA is a broken wire, not an empty vessel (see NAMUR NE 43).
2. **L0 → L1** — field junction box, multicore, marshalling cabinet, terminal block, analog input card. Unglamorous; the source of most real faults.
3. **L1** — the card scales to **62.0 %** and range-checks it: below ~3.6 mA or above 21 mA it flags *bad quality* rather than passing on a lie.
4. **L1** — the PID block compares PV 62.0 % to SP 50.0 % and computes a new output, every 500 ms, for twenty years.
5. **L1 → L0** — the analog output card drives the valve positioner; the valve strokes; the level falls.
6. **L1 → L2** — the value publishes to the operator station: bargraph, trend, faceplate, and a HI alarm at 80 %.
7. **L2 → L3 → L4** — historian, then MES aggregation, then ERP, through the DMZ, never on a direct route to a controller.

Meanwhile, on hardware that shares nothing with any of the above, a **separate** transmitter
on a **separate** nozzle feeds the safety logic solver, which votes, waits out a confirmation
delay, and de-energises a shutdown valve. Status flows to the operator's screen **read-only**;
the BPCS cannot command, inhibit or reset the SIS.

## Implications for agents

- Always ask **which level** a capability belongs to before writing a requirement for it.
- Never write a requirement that has the BPCS commanding, inhibiting or resetting a SIS function.
- Never place a direct path from L4 to L1 in an architecture.
- A product that spans levels (a DCS does) must say so explicitly rather than being described as sitting at one.
- Instrument tags follow **ANSI/ISA-5.1-2024** (first letter = measured variable, succeeding letters = function). The tag, not a database key, is the plant's real primary key — it appears on the P&ID, the loop drawing, the terminal, the faceplate, the historian, the alarm database and the work order.
