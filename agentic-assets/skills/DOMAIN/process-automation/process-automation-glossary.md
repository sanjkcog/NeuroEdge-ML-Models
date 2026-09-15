---
name: process-automation-glossary
description: Accurate definitions of the 65 terms an agent needs to write or review process automation artefacts — safety (SIL, PFDavg, LOPA, TMR, 1oo2D), control (PID, cascade, bumpless transfer, first-out), systems (DCS, PLC, PAC, RTU, SCADA, MES), communications (HART, OPC UA, Ethernet-APL, Modbus TCP) and field installation (marshalling, loop check, hot cutover, intrinsic safety). Use it to get the vocabulary right rather than approximating it.
origin: NeuroEdge AgentForge — process automation domain pack
version: "1.0.0"
---

# Process Automation Glossary

Sixty-five terms, defined precisely. Where a definition is standardised, the standard is named.

## Safety

| Term | Definition |
|---|---|
| **BPCS** | Basic Process Control System — responds to process inputs and generates outputs to run the process as desired, and does **not** perform safety instrumented functions with a claimed SIL (IEC 61511 definition). |
| **SIS** | Safety Instrumented System — the sensors, logic solver, final elements and support systems implementing one or more SIFs, separate and independent from the BPCS to the extent that the SIS's functional integrity is not compromised. |
| **SIF** | Safety Instrumented Function — one protective function with a defined safe state, trip condition and SIL target, e.g. "on high-high level in V-101, close XV-1002 within 3 s". |
| **SIL** | Safety Integrity Level 1–4 — the band of required risk reduction assigned to a **SIF**, never to a device. |
| **PFDavg** | Average Probability of Failure on Demand — the low-demand integrity metric. SIL 1 = 10⁻² to <10⁻¹ … SIL 4 = 10⁻⁵ to <10⁻⁴. |
| **PFH** | Probability of dangerous Failure per Hour — the high-demand/continuous metric, used when demands exceed roughly twice the proof-test frequency. |
| **RRF** | Risk Reduction Factor — 1/PFDavg. SIL 1 = 10–100, SIL 2 = 100–1 000, SIL 3 = 1 000–10 000. |
| **LOPA** | Layer of Protection Analysis — semi-quantitative method counting independent protection layers against an initiating-event frequency to derive the risk-reduction gap and hence the SIL target. |
| **IPL** | Independent Protection Layer — a safeguard that is effective, auditable and independent of both the initiating cause and every other claimed layer. A non-61511 BPCS caps at RRF 10. |
| **HAZID / HAZOP** | Hazard identification; and Hazard and Operability study — a structured guideword walk of P&ID nodes (No/More/Less/Reverse/As-well-as applied to flow, pressure, temperature, level) producing causes, consequences, safeguards and actions. |
| **SRS** | Safety Requirements Specification — IEC 61511-1 **Clause 10** deliverable specifying every SIF's function and integrity requirements. |
| **TMR** | Triple Modular Redundant — three independent channels with 2oo3 hardware voting, giving both fault tolerance and a low spurious-trip rate. |
| **1oo2D** | One-out-of-two with Diagnostics — two channels, either can trip; diagnostics detect a failed channel and degrade voting to 1oo1 rather than tripping. |
| **2oo3** | Two-out-of-three — at least two of three channels must call for the trip before the final element acts. |
| **MooN** | Generic voting notation — M of N channels must function for the safety function to be performed. |
| **HFT** | Hardware Fault Tolerance — the number of dangerous faults a subsystem tolerates while still performing its function; constrained by IEC 61511-1 Cl. 11.4 with SFF and Type A/B. |
| **SFF** | Safe Failure Fraction — the proportion of a device's failure rate that is safe or dangerous-detected. |
| **Systematic capability (SC)** | The IEC 61508 attribute a *device* holds, earned through an audited development process. What a vendor certificate actually attests to. |
| **ESD** | Emergency Shutdown — the SIS instance bringing a unit or plant to a defined safe state. |
| **HIPPS** | High Integrity Pressure Protection System — a SIS used instead of mechanical relief, closing valves fast enough to protect downstream piping; typically SIL 3 with very short response times. |
| **F&G** | Fire and Gas — detection of flame, smoke and combustible/toxic gas with voting logic driving alarms, deluge and ESD. |
| **BMS** | Burner Management System — the SIS governing safe purge, light-off, flame supervision and trip of fired equipment; NFPA 85/86 in the US alongside IEC 61511. |
| **MOC** | Management of Change — the controlled procedure for any change that is not a replacement in kind. 29 CFR 1910.119(l) in the US; IEC 61511-1 Cl. 17 for the SIS. |
| **Proof test** | Periodic full-function test designed to reveal **dangerous undetected** failures diagnostics cannot see. Its interval and coverage are inputs to PFDavg, so changing either changes the achieved SIL. |

## Control

| Term | Definition |
|---|---|
| **PID** | Proportional–Integral–Derivative — the feedback algorithm computing OP from the error between PV and SP. |
| **PV / SP / OP** | Process Variable (measured), Setpoint (target), Output (manipulated variable to the final element). |
| **Cascade control** | Two nested loops — a slow primary writes the setpoint of a fast secondary, so the inner loop rejects disturbances before they reach the outer variable. |
| **Feedforward** | Control action computed from a measured *disturbance* rather than from error, applied before the disturbance reaches PV; usually trimmed by feedback. |
| **Deadband** | The band around a threshold within which no action or state change occurs — used on alarms to stop chatter and on valves to stop hunting. |
| **Scan cycle** | In an IEC 61131-3 system, the repeating read-inputs → execute-logic → write-outputs cycle. Scan time bounds achievable loop response. |
| **Bumpless transfer** | Switching between control modes or between redundant controllers without a step change in OP, achieved by pre-loading the integral term to the current output. |
| **Hot standby** | Redundancy in which the backup runs synchronised with the primary and holds live state, so failover occurs within one or two scans with no process disturbance. |
| **First-out** | Sequence-of-events logic identifying and latching which of several simultaneous trip conditions occurred *first*, so the operator sees the cause rather than the cascade. |
| **Universal I/O** | I/O channels software-configurable as AI/AO/DI/DO (and often HART), removing the need to match wiring to card type and collapsing cross-wiring and marshalling work. Also called electronic marshalling. |

## Systems

| Term | Definition |
|---|---|
| **DCS** | Distributed Control System — an integrated control system for continuous/hybrid plant with a common engineering database, integrated operator consoles and controllers distributed near the process. Spans ISA-95 Levels 1 and 2. |
| **PLC** | Programmable Logic Controller — a ruggedised deterministic controller, historically discrete/sequential in emphasis, programmed per IEC 61131-3. |
| **PAC** | Programmable Automation Controller — marketing-origin term for a PLC-class device with expanded capability. Not a standardised class. |
| **RTU** | Remote Terminal Unit — a controller for remote, unattended, power- and bandwidth-constrained sites, with store-and-forward telemetry. |
| **SCADA** | Supervisory Control and Data Acquisition — the supervisory layer collecting data from dispersed PLCs/RTUs over telemetry and presenting it centrally. Now addressed by ANSI/ISA-112.00.01-2025. |
| **HMI** | Human–Machine Interface — the operator's display and control surface. Design per ISA-101.01-2015. A role, not a level. |
| **MES / MOM** | Manufacturing Execution System / Manufacturing Operations Management — the ISA-95 **Level 3** layer turning an ERP order into executed production. MOM is ISA-95's preferred term. |
| **ERP** | Enterprise Resource Planning — ISA-95 **Level 4**; business planning, logistics, finance. |
| **DMZ** | Demilitarised Zone — a boundary segment brokering traffic so no direct enterprise↔OT flow exists. Commonly drawn as "Purdue Level 3.5", but that is a **community convention**, not a Purdue level and not an IEC 62443 term. |
| **Historian** | Time-series database optimised for high-rate compressed storage and fast retrieval of process tags, with interpolation, aggregation and long retention. |

## Communications

| Term | Definition |
|---|---|
| **OPC UA** | Open Platform Communications Unified Architecture (IEC 62541) — platform-independent, service-oriented, with a rich address space, information model, built-in security and companion specifications. The default vendor-neutral integration layer above the controller. |
| **HART** | Highway Addressable Remote Transducer — an FSK digital signal superimposed on a 4–20 mA loop carrying configuration, diagnostics and secondary variables without disturbing the analogue primary value. The largest installed base of smart field devices. |
| **Foundation Fieldbus** | H1 (31.25 kbit/s, two-wire, bus-powered, IS-capable) digital fieldbus supporting **control in the field** — function blocks executing in the transmitter and positioner rather than the controller. |
| **PROFIBUS PA** | The process-automation profile of PROFIBUS on the same MBP two-wire bus-powered IS-capable physical layer as FF H1, bridged to PROFIBUS DP. |
| **PROFINET** | Ethernet-based industrial protocol from PI, within the IEC 61158/61784 family; real-time (RT) and isochronous (IRT) classes. |
| **Modbus TCP** | Modbus application protocol over TCP/IP port 502 — register-based, no built-in authentication or encryption, trivially simple, universally implemented. IEC 61784 CPF 15. |
| **EtherNet/IP** | CIP over standard Ethernet/TCP-UDP, from ODVA; dominant in discrete and hybrid North American installations. |
| **IO-Link** | Point-to-point serial digital link over standard unshielded three-wire sensor cable (IEC 61131-9), bringing parameterisation and diagnostics to simple sensors without a fieldbus. |
| **Ethernet-APL** | Two-wire Ethernet for process plants — IEEE 802.3cg 10BASE-T1L plus IEC TS 60079-47 "2-WISE"; power and 10 Mbit/s on one shielded pair, 1000 m trunk / 200 m spur, usable into Zone 0. |
| **4–20 mA live zero** | The convention that the lowest *valid* signal is 4 mA, not 0 mA, so a broken wire or dead transmitter reads 0 mA and is unambiguously distinguishable from a genuine zero measurement. NAMUR **NE 43** extends this into fault bands (≤3.6 mA, ≥21.0 mA). |
| **NE 107** | NAMUR recommendation standardising field-device diagnostics into four operator-actionable signals — **F** Failure, **C** Function check, **S** Out of specification, **M** Maintenance required. |

## Field and installation

| Term | Definition |
|---|---|
| **Intrinsic safety (Ex i)** | Protection by energy limitation — the circuit cannot store or release enough electrical or thermal energy to ignite the atmosphere, even under fault. The only concept permitting live working and Zone 0 entry. |
| **Marshalling** | The interposing stage where multi-core field cables are broken out and cross-wired signal-by-signal onto terminals arranged to match the controller's I/O card layout. |
| **Junction box** | The field enclosure where individual instrument cables from a local area are gathered onto a multi-core home-run cable back to the marshalling cabinet. |
| **Loop check** | Commissioning activity proving one signal end to end — apply a real input at the field element, confirm the value on the HMI faceplate and in the historian, confirm the output drives the final element. Every loop, individually, signed off. |
| **Hot cutover** | Migrating a control system loop by loop while the plant continues to run, as opposed to a cold cutover during a shutdown. |
| **P&ID** | Piping and Instrumentation Diagram — the master engineering drawing of equipment, piping, instruments and control loops; symbology per ANSI/ISA-5.1-2024. Freezing the P&ID is the precondition for a meaningful HAZOP. |
| **Tag** | The unique plant-wide identifier of an instrument, loop or signal (e.g. `PIC-101`), constructed per ISA-5.1: first letter = measured variable, succeeding letters = function. The tag, not a database key, is the plant's real primary key. |
| **Cabinet footprint** | The floor area and rack space a control system occupies including door swing, cooling clearance and cable entry. A genuine commercial differentiator in brownfield projects where the room is fixed and new cabinets must sit alongside the old system during a phased cutover. |
| **FAT / SAT** | Factory Acceptance Test (staged, simulated I/O, before shipment — IEC 61511-1 Cl. 13 for SIS) and Site Acceptance Test (repeated on site on the real installation). |
| **FEED** | Front-End Engineering Design — the phase between concept and FID that matures the design to AACE Class 2–3 estimate accuracy and freezes the control and safety philosophy. |
| **PSSR** | Pre-Startup Safety Review — 29 CFR 1910.119(i); confirms construction matches specification and PHA recommendations are resolved before hazardous chemicals are introduced. |
| **Turnaround (TAR)** | Planned plant shutdown, typically on a multi-year cycle, during which intrusive control-system work is done. The scope is frozen months ahead and competed for by every discipline. |
