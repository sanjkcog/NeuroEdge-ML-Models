---
name: alarm-management-and-hmi
description: Alarm management and operator interface design for process plants — ISA-18.2 / IEC 62682 lifecycle and rationalisation, the published EEMUA 191 and ISA-18.2 performance benchmarks, alarm flood definitions, and ISA-101 HMI design conventions. Read before writing any requirement that creates, displays or prioritises an alarm.
origin: NeuroEdge AgentForge — process automation domain pack
version: "1.0.0"
---

# Alarm Management and HMI Design

More alarms does not mean a safer plant. Flooded alarm lists have caused major incidents,
not prevented them — which is why this is a standardised discipline with measurable targets.

## When to Use

- Any requirement that generates, routes, prioritises or displays an alarm
- Designing an operator-facing screen, faceplate or notification
- Reviewing a feature that adds diagnostics visible to an operator
- Writing acceptance criteria involving operator response

## The standards

- **ANSI/ISA-18.2-2016** and **IEC 62682 Ed 2.0 (2022-12)** — mandate a documented **alarm philosophy**, a **ten-stage lifecycle**, rationalisation, and monitoring against measurable KPIs.
- **EEMUA 191, 3rd edition** — a UK industry guide (not a standard), the origin of the operator-loading benchmarks.
- **ISA-101.01-2015** — HMI design lifecycle, style guide, display hierarchy.

### The ISA-18.2 lifecycle (Table 1)

A Philosophy → B Identification → C **Rationalization** → D Detailed Design →
E Implementation → F Operation → G Maintenance → H Monitoring & Assessment →
I **Management of Change** → J Audit.

**Alarm (ISA-18.2 3.1.7):** *"audible and/or visible means of indicating to the operator an
equipment malfunction, process deviation, or abnormal condition requiring a timely response."*

**Rationalization (3.1.73):** *"process to review potential alarms using the principles of
the alarm philosophy, to select alarms for design, and to document the rationale for each
alarm."*

In practice every candidate alarm is challenged against four tests:

1. Is there a **defined operator response**?
2. Is there **enough time to act**?
3. Are the **consequences of inaction** meaningful?
4. Is it **unique** — not a duplicate of another alarm on the same event?

Alarms that fail become events, or are deleted. The output is the **master alarm database**,
itself a controlled document under stage I.

## Published performance benchmarks

**ISA-18.2 / IEC 62682 targets**

| Metric | Target | Maximum |
|---|---|---|
| Annunciated alarms per hour per operating position | 6 (average) | 12 |
| Annunciated alarms per 10 minutes per operating position | 1 (average) | 2 |
| Percentage of 10-minute periods containing >10 alarms | < 1 % | |
| Stale alarms (annunciated > 24 h) | < 5 per day, with an action plan | |
| Priority distribution, 3-priority scheme | ~80 % low / ~15 % medium / ~5 % high | |

**Alarm flood** — ISA-18.2-2016's own text: *"alarm flood condition during which the alarm
rate is greater than the operator can effectively manage (e.g., **more than 10 alarms per 10
minutes**)"*. EEMUA's convention adds a hysteresis exit: the flood continues through
subsequent 10-minute intervals until one contains fewer than five new alarms.

**EEMUA 191 3rd edition, steady state (p. 96)**

| Rating | Rate |
|---|---|
| Acceptable | fewer than one alarm per ten minutes |
| Manageable | one per five minutes |
| Over-demanding | one per two minutes |
| Unacceptable | more than one per minute |

**EEMUA 191 3rd edition, first ten minutes after a major upset (p. 97)**

| Rating | Alarms per operator |
|---|---|
| Manageable | under 10 |
| Difficult | 20 – 100 |
| Excessive | more than 100 |

> **Caveat to carry.** Per-*day* averages (the widely quoted ~150/day) are secondary: one
> credible reading is that they were deliberately de-emphasised in the 2016 revision because
> averaging over a day masks floods. Prefer the per-hour and per-10-minute figures, and the
> page-attributed EEMUA numbers.

## Field device diagnostics — NAMUR NE 107

NE 107 standardises device self-diagnostics into four operator-actionable status signals,
with standardised symbols and colours:

| Signal | Meaning |
|---|---|
| **F** | Failure |
| **C** | Function check |
| **S** | Out of specification |
| **M** | Maintenance required |

The current edition (2025-07-15) aligns diagnostic transmission with the NOA information
model. Any product that surfaces device health to an operator should map its internal
diagnostics onto these four categories rather than inventing its own taxonomy.

**NE 43** is the related 4–20 mA fault-signalling convention: low fault ≤ 3.6 mA, low
saturation ≥ 3.8 mA, high saturation ≤ 20.5 mA, high fault ≥ 21.0 mA, with the gaps as
forbidden differentiation zones. NE 43 gives **ranges, not a single mandated alarm value** —
vendor defaults differ and must be configurable.

## ISA-101 HMI conventions

- **Display hierarchy**: Level 1 plant/area overview → Level 2 unit → Level 3 detail → Level 4 diagnostic/support.
- **Grey-scale, low-saturation base**, with **colour reserved for abnormal condition**. A screen where everything is coloured conveys nothing.
- Consistent style guide across all displays; deviations are a design defect, not a preference.
- Alarm indication is distinguishable without relying on colour alone.

## Implications for agents

- A new alarm is a **requirement with a cost**. Any story that adds one must state the operator response, the time available and the consequence of inaction — or make it an event instead.
- Never write acceptance criteria that measure alarm *coverage*. Measure alarm *rate against the benchmarks above*.
- A diagnostic that no operator can act on belongs in the historian and the service tool, not on the alarm list.
- Map device health to NE 107 F/C/S/M.
- Do not specify a fixed fault current value; specify configurability within the NE 43 bands.
