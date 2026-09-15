---
name: radiotherapy-qa-physics
description: Medical-physics subject expertise for radiotherapy and diagnostic-imaging QA. Covers the machine-QA vs patient-QA distinction, LINAC output/geometry checks (TG-142), patient-specific IMRT/VMAT QA and the gamma index (TG-218), and the vocabulary a PM/architect/QA agent needs to reason correctly about a radiotherapy-QA product. Product-neutral.
origin: NeuroEdge SUBJECTS — medical physics
version: "0.1.0"
subject: Physics
anchors:
  - "AAPM Report (docid=125): https://www.aapm.org/pubs/reports/detail.asp?docid=125"
  - "AAPM TG-142 — QA of medical accelerators (machine QA)"
  - "AAPM TG-218 — patient-specific IMRT/VMAT QA & gamma tolerances"
---

# Radiotherapy QA Physics (subject expertise)

Product-neutral medical-physics knowledge for building or integrating software that
performs **quality assurance (QA)** in radiation oncology and diagnostic imaging. This is
the "what an expert knows" layer — it does **not** describe any one vendor's product.
Vendor/product specifics (e.g. Mirion SunCHECK file formats and APIs) live in a custom
plugin, not here.

> Populate exact tolerance numbers from the AAPM report tables the project designates
> (see `anchors`). This skill gives the framework and vocabulary; mark any specific
> numeric tolerance as **verify-against-report** rather than asserting it from memory.

## The core distinction: Machine QA vs Patient QA

A radiotherapy QA product almost always spans **two different jobs**. Conflating them is
the most common domain error in requirements and test design.

| | **Machine QA** | **Patient QA** |
|---|---|---|
| Question answered | "Is the delivery machine itself performing within tolerance?" | "Will *this patient's* planned treatment be delivered accurately?" |
| Subject under test | The LINAC / imaging device | An individual treatment plan before it is delivered |
| Cadence | Daily / monthly / annual schedules | Per-plan, before first treatment |
| Reference standard | AAPM **TG-142** (accelerators) | AAPM **TG-218** (IMRT/VMAT patient-specific QA) |
| Typical checks | Output constancy, flatness/symmetry, beam energy, MLC position, gantry/collimator angle, imaging (kV/MV, CBCT) alignment | Measured vs planned dose agreement, **gamma index** pass rate, point-dose checks, independent MU/dose recalculation |
| Owner | Medical Physicist (with RTT for daily checks) | Medical Physicist |

Both feed the same safety goal but have different data, different pass/fail logic, and
different regulatory weight. A PRD, architecture, and test matrix must treat them as
**two capabilities**, not one.

## Machine QA (TG-142 framework)

TG-142 defines QA for medical linear accelerators across **daily / monthly / annual**
schedules, with tolerances that tighten for more complex delivery (non-IMRT < IMRT <
SRS/SBRT). Categories:

- **Dosimetry** — output (dose) constancy, beam quality/energy, flatness & symmetry,
  output factors.
- **Mechanical / geometric** — gantry, collimator and couch angle accuracy; jaw and
  **MLC (multi-leaf collimator)** position; light/radiation field coincidence; isocenter.
- **Imaging** — planar kV/MV and **CBCT** (cone-beam CT) spatial accuracy, contrast,
  and registration to the treatment isocenter.
- **Safety** — interlocks, door/beam-on indicators, audio-visual monitoring.

Each check has a **tolerance** (action-if-exceeded) and a **schedule**. Software's job is
typically: capture the measurement, compare to baseline/tolerance, trend it over time,
flag out-of-tolerance results, and hold an auditable record.

## Patient QA (TG-218 framework) and the gamma index

Patient-specific QA verifies that a *planned* dose distribution can actually be delivered.
The dominant metric is the **gamma index (γ)**, which combines two tolerances into one
pass/fail per measurement point:

- **Dose Difference (DD)** — e.g. 3% (absolute or global-normalized).
- **Distance-to-Agreement (DTA)** — e.g. 3 mm.

A point **passes** (γ ≤ 1) if the measured dose agrees with the planned dose within
*either* the dose tolerance *or* the distance tolerance. Common criteria: **3%/3mm**,
tightening to **2%/2mm** for more demanding plans. Results are reported as a **gamma pass
rate** (% of points with γ ≤ 1) against an action/tolerance limit, plus a **low-dose
threshold** (points below X% of max dose are excluded). TG-218 gives recommended action
and tolerance limits and stresses stating the *exact* gamma configuration — normalization,
threshold, global vs local — because a pass rate is meaningless without it.

Independent **MU (monitor unit) / dose recalculation** is a complementary patient-QA check:
a second dose engine recomputes the plan and the difference to the TPS is compared to a
tolerance.

## Diagnostic imaging QA (adjacent scope)

Some products (and the Mirion portfolio) also cover **diagnostic imaging** QA — CT, MRI,
mammography, fluoroscopy — with its own constancy and image-quality metrics and its own
regulatory regime. Treat it as a **third capability** if in scope; do not assume the
radiotherapy QA data model transfers to it.

## Key data objects (product-neutral)

- **Baseline** — the reference value a check is measured against (commissioning or last
  calibration).
- **Tolerance / Action limit** — two-tier: a *tolerance* warns, an *action limit* stops
  clinical use.
- **Measurement / result** — one captured value with timestamp, device, operator, and
  pass/fail.
- **Trend** — results over time for one check; drift detection matters as much as any
  single pass/fail.
- **Plan** (patient QA) — the treatment plan under verification, from the **TPS**
  (Treatment Planning System), usually exchanged as **DICOM-RT**.
- **Report** — the auditable, sign-off-bearing record a physicist approves.

## Where clinical safety lives (for PM/architect/QA agents)

- A **false pass** (saying an out-of-tolerance machine or plan is fine) is a patient-safety
  event; a false fail is merely rework. Design and test asymmetrically — a missed
  out-of-tolerance result is the worst outcome.
- QA results carry **sign-off** by a qualified Medical Physicist; records are **immutable
  after approval** (addendum, not edit) and fully **audit-trailed**.
- Tolerances and schedules are **configurable per machine and per plan class** — never
  hard-code them.
- Units, normalization, and gamma configuration must be **explicit and stored with every
  result**; an unlabeled number is a defect.

## Glossary anchor

Term definitions (LINAC, MLC, CBCT, TPS, MU, DTA, gamma index, flatness/symmetry, etc.)
should be sourced from the designated AAPM report and kept in the project's glossary. See
`anchors` in the frontmatter for the report the project standardizes on.
