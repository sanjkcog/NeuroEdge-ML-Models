---
name: process-automation-standards-landscape
description: Index of the standards that govern process automation products — ISA-95, IEC 61511/61508, IEC 62443, IEC 61131-3/61499, ISA-88, ISA-18.2, ISA-101, ISA-5.1, ISA-71.04, NAMUR NE/NOA, ATEX/IECEx and hazardous-area protection concepts — with current editions and what each obliges a product team to do. Use as the lookup table when a requirement needs a standards citation.
origin: NeuroEdge AgentForge — process automation domain pack
version: "1.0.0"
---

# Process Automation Standards Landscape

The lookup table. Cite the edition; do not cite a clause number you have not verified.

## When to Use

- A requirement, epic or test needs a standards citation
- Checking whether an edition reference is current
- Deciding which certification a customer will actually ask for

## Core

| Standard | Current designation | Governs / obliges |
|---|---|---|
| **ISA-95 / IEC 62264** | **ANSI/ISA-95.00.01-2025** (Part 1); 8 parts | Enterprise–control integration. If your product exchanges production data with MES/ERP, model it on ISA-95 objects (Production Schedule, Production Performance, Material, Equipment, Personnel) and state which level you occupy. Primarily addresses the **L3↔L4 interface** |
| **IEC 61511** | **61511-1:2016 Ed 2.0 + AMD1:2017**; US: ANSI/ISA-61511-1-2018 | Process-sector SIS lifecycle. See `functional-safety-iec-61511.md` |
| **IEC 61508** | **2010, Ed 2.0**, 7 parts | Generic functional safety; source of SIL 1–4 and systematic capability |
| **IEC 62443** | family; **-4-1:2018** and **-4-2:2019** bind product suppliers | See `industrial-cybersecurity-iec-62443.md` |
| **IEC 61131-3** | **2025, Ed 4.0** (superseded 2013 Ed 3.0) | PLC/DCS programming languages: LD, FBD, ST, IL (deprecated), SFC; configuration/POU/task model. Ed 4 added UTF-8 strings |
| **IEC 61499** | **61499-1:2012, Ed 2.0** | Event-driven, distribution-aware function blocks. Execution order is explicit; applications are designed system-wide then **mapped** to devices |
| **ISA-88 / IEC 61512** | **ISA-88.00.01-2010** Part 1 | Batch control. Separates **recipe** from **equipment**. Physical model enterprise→site→area→process cell→**unit**→equipment module→control module; procedural model procedure→unit procedure→operation→**phase** |
| **ISA-18.2 / IEC 62682** | ISA-18.2-2016; **IEC 62682 Ed 2.0 (2022-12)** | Alarm management. See `alarm-management-and-hmi.md` |
| **ISA-101** | **ISA-101.01-2015** | HMI design lifecycle, style guide, display hierarchy |
| **ISA-5.1** | **ANSI/ISA-5.1-2024** | P&ID symbology and tag construction. *Note: many secondary sources still cite 2009 — they are out of date* |
| **ISA-84** | published as the **ANSI/ISA-61511 series (2018)** | The historical US SIS standard; treat as identical to IEC 61511 today |
| **ISA-71.04** | **ANSI/ISA-71.04-2013** | Airborne-contaminant severity for control cabinets: **G1 Mild · G2 Moderate · G3 Harsh · GX Severe**. GX requires specially conformally coated electronics |
| **ISA-112** | **ANSI/ISA-112.00.01-2025** | SCADA systems lifecycle, diagrams and terminology — new, worth citing for SCADA products |
| **ISA-106** | **ANSI/ISA-106.00.01-2023** | Procedure automation for continuous process operations |

## 61131-3 versus 61499 — how to state the difference

61131-3 execution is **resource-scan-driven**: the runtime cycles tasks and POUs on a scan,
and execution order is implicit in task configuration and POU ordering.
61499 execution is **event-driven and explicit**: a function block executes only when an
event input fires, so execution order is a first-class design artefact and the same
application can be re-partitioned across devices without rewriting logic. An IEC 61499
interface carries **event inputs and outputs in addition to data**, bound by `WITH`
constraints; periodic behaviour is reconstructed with an `E_CYCLE` block.
61131-3 dominates the commercial installed base; 61499 is used where distribution and
reconfigurability dominate.

## NAMUR

NAMUR is the German process-industry end-user association. Its recommendations (NE) are
**not standards** — they are user-community requirements that vendors adopt because major
chemical and pharma buyers write them into specifications.

| Item | Content |
|---|---|
| **NE 107** (current ed. 2025-07-15) | Device self-diagnostics mapped to **F / C / S / M** with standardised symbols and colours |
| **NE 43** | 4–20 mA fault signalling: low fault ≤ 3.6 mA, low saturation ≥ 3.8 mA, high saturation ≤ 20.5 mA, high fault ≥ 21.0 mA |
| **NE 175** (2020-07-09) | NAMUR Open Architecture concept |
| NE 176 / 177 / 178 / 179 | NOA information model · security zones and gateway · verification of request · aggregating server |

**What NOA actually proposes** — this is often misstated. NOA does **not** flatten Purdue.
It keeps the existing hierarchy intact as the **Core Process Control (CPC)** domain, and
adds a **second, parallel, strictly outbound-by-default channel** into a **Monitoring &
Optimisation (M+O)** domain where analytics and asset health live. Where a write-back is
genuinely required it must pass the **NE 178 "Verification of Request"** check. Data diodes
are a common enforcement; OPC UA is the usual carrier. The point is to unlock the data
without touching the BPCS or the SIS.

## Hazardous area

| | ATEX | IECEx | North America |
|---|---|---|---|
| Instrument | **Directive 2014/34/EU** (ATEX 114, equipment); 1999/92/EC (ATEX 153, workplace) | Voluntary global scheme on IEC 60079 | NEC/CEC Class & Division |
| Gas zones | Zone 0 / 1 / 2 | Zone 0 / 1 / 2 | Class I Div 1 ≈ Zones 0+1; Div 2 ≈ Zone 2 |
| Dust | Zone 20 / 21 / 22 | same | Class II |
| Categories | Cat 1→Zone 0/20, Cat 2→Zone 1/21, Cat 3→Zone 2/22; EPL Ga/Gb/Gc, Da/Db/Dc | same EPLs | — |
| **Self-certification** | **Permitted for Category 3 (Zone 2/22)** — module A, internal production control | **Not permitted** — an ExCB Certificate of Conformity is always required | varies |

Zones and Divisions must not be intermixed in one classification.

**Protection concepts**

| Concept | Standard | Zones | Mechanism |
|---|---|---|---|
| **Ex ia / ib / ic** intrinsic safety | IEC 60079-11 | ia 0,1,2 · ib 1,2 · ic 2 | Limits electrical and thermal energy below the minimum ignition energy. ia tolerates two faults, ib one, ic none. The only concept permitting live working and Zone 0 entry |
| **Ex d** flameproof | IEC 60079-1 | 1, 2 | Accepts ignition inside the enclosure; prevents propagation via certified flame paths |
| **Ex e** increased safety | IEC 60079-7 | 1, 2 | Eliminates the ignition source by construction — creepage, clearance, certified terminals, temperature limits |
| **Ex p** pressurisation | IEC 60079-2 | 1, 2 | Positive pressure excludes the hazardous atmosphere |
| **Ex m** encapsulation | IEC 60079-18 | ma 0 · mb 1,2 | Live parts embedded in compound |
| **Ex t** dust enclosure | IEC 60079-31 | 20, 21, 22 | Ingress protection plus surface-temperature limits |

**Ethernet-APL** is the current brownfield-relevant development: **IEEE 802.3cg 10BASE-T1L**
plus **IEC TS 60079-47 "2-WISE"**; a single shielded pair carrying power and 10 Mbit/s data,
1000 m trunk / 200 m spur, usable into Zone 0.

**Obligation:** hazardous-area certification is a **hard gate on product architecture**, not
a late add-on. Ex ia caps available energy — which caps CPU, radio, display and comms
bandwidth. Ex d imposes enclosure mass and flame-path machining tolerances. Certification is
per-variant and per-scheme, and any change touching the safety-relevant design invalidates it.

## Implications for agents

- Cite the **edition**. "IEC 61511" without an edition is weaker than "IEC 61511-1:2016 Ed 2.0".
- Do **not** invent clause numbers. Where this pack marks a clause as unverified, cite the clause *title* instead.
- Certification is per-variant. A requirement for a new variant is a requirement for a new certification campaign with its own lead time.
- NAMUR recommendations are contractual in practice even though they are not standards. Treat NE 107 and NE 43 as binding when the customer is a large chemical or pharma buyer.
