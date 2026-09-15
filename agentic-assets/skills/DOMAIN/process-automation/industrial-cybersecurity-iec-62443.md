---
name: industrial-cybersecurity-iec-62443
description: IEC 62443 for product suppliers — the family structure, the -4-1 secure development lifecycle and -4-2 component requirements, how zones and conduits actually relate to the Purdue model (they are not the same thing), SL-T vs SL-C vs SL-A, and the EU Cyber Resilience Act obligations that now bind manufacturers. Read before writing any security requirement for an industrial product.
origin: NeuroEdge AgentForge — process automation domain pack
version: "1.0.0"
---

# Industrial Cybersecurity — IEC 62443 and product-cyber regulation

What a *product supplier* is actually obliged to do, and the conflation that ruins most
generated security requirements.

## When to Use

- Writing any security requirement, epic or test for an industrial control product
- Reviewing a claim about "62443 compliance" — always ask *which part*, and *4-1 or 4-2*
- Planning evidence for a customer's procurement security review
- Anything involving SBOM, vulnerability disclosure, support periods or CE marking

## Which part applies to whom

| Part | Edition | Aimed at |
|---|---|---|
| 62443-2-1 | **Ed 2.0, 2024-08** — security programme requirements, restructured into security programme elements with a maturity model | asset owner |
| 62443-2-4 | service-provider / integrator security capabilities | integrators |
| 62443-3-2 | **Ed 1.0, 2020-06** — security risk assessment for system design; the zones-and-conduits process | asset owner |
| 62443-3-3 | **2013** — system security requirements and security levels | system supplier |
| **62443-4-1** | **Ed 1.0, 2018-01** — secure product **development lifecycle** | **product supplier** |
| **62443-4-2** | **Ed 1.0, 2019-02** — technical security requirements for **components** | **product supplier** |

**If you are building a product, -4-1 and -4-2 are yours.** -3-3 belongs to whoever
integrates a system; -2-1 and -3-2 belong to the operator.

### 62443-4-1: the eight practices

| Practice | Clause |
|---|---|
| SM — Security Management | 5 |
| SR — Specification of Security Requirements | 6 |
| SD — Secure by Design | 7 |
| SI — Secure Implementation | 8 |
| SVV — Security Verification and Validation Testing | 9 |
| DM — Management of Security-Related Issues | 10 |
| SUM — Security Update Management | 11 |
| SG — Security Guidelines | 12 |

A maturity model applies (Table 1). Note: **there is no mandated relationship between
maturity level and security level** — a mature process does not confer an SL.

### 62443-4-2: component types and structure

Component types: **embedded device, host device, network device, software application**.
Requirements are **CRs** organised under the seven **Foundational Requirements**:

> FR1 Identification & Authentication Control · FR2 Use Control · FR3 System Integrity ·
> FR4 Data Confidentiality · FR5 Restricted Data Flow · FR6 Timely Response to Events ·
> FR7 Resource Availability

with device-type extensions **EDR / HDR / NDR / SAR**.

**Security levels by adversary model:** SL1 casual or accidental · SL2 simple means, low
resources, generic skills, low motivation · SL3 sophisticated means, moderate resources,
IACS-specific skills · SL4 sophisticated means, extended resources, high motivation.

**SL-T / SL-C / SL-A — keep these distinct:**

- **SL-T (Target)** is assigned to a **zone or conduit** by the asset owner's risk assessment.
- **SL-C (Capability)** is what a system (-3-3) or component (-4-2) can deliver natively. This is what a *product* can claim.
- **SL-A (Achieved)** is what is demonstrated in the as-built installation.

## Zones and conduits versus Purdue — get this right

**The Purdue model is not part of IEC 62443.** They answer different questions.

- **Purdue asks:** what does this system *do* in the functional hierarchy?
- **A zone asks:** what security requirement do these assets *share*? A zone is *"the grouping of cyber assets that share the same cybersecurity requirements"*; a conduit is the equivalent grouping for communications. The organising principle is **shared security requirement derived from risk**, not hierarchy level.

62443-3-2's normative content is **Clause 4, ZCR 1–7**:

| | |
|---|---|
| ZCR 1 | Identify the system under consideration and its perimeter and access points |
| ZCR 2 | Initial cybersecurity risk assessment |
| **ZCR 3** | **Partition into zones and conduits** — including mandated separation of business vs IACS assets, **safety-related assets**, temporarily connected devices, wireless devices, and devices connected via external networks |
| ZCR 4 | Compare initial risk to tolerable risk |
| ZCR 5 | Detailed cybersecurity risk assessment |
| ZCR 6 | Document requirements, assumptions and constraints → the **CRS** |
| ZCR 7 | Attain asset owner approval |

Consequences to carry into every artefact:

- The mapping is **many-to-many**. One zone can span several Purdue levels (a packaged skid with its own L1 and L2 assets is normally *one* zone). One level can split into many zones (L2 split per unit; SIS split out from BPCS at the same level).
- **Safety separation is a security requirement, not a hierarchy requirement.** ZCR 3 requires safety-related assets in their own zone whatever level they sit at — which is how 62443 and IEC 61511 Cl. 8.2.4 interlock.
- **A conduit is not "the network."** It may be physical or logical, carry several protocols, and physically traverse a zone it does not belong to.
- **Purdue level does not determine SL.** A Level 1 controller in a high-consequence unit can carry a higher SL-T than a Level 3 historian.
- **"Level 3.5 / DMZ"** is a community convention, not a Purdue level and not a 62443 term. In 62443 language it is a zone with its own SL-T, joined by conduits.

> **The sentence to never generate:** *"The product shall reside in Purdue Level 2 and
> therefore meet SL 2."* Wrong twice.
> **The correct form:** *"The product shall be deployable within a zone whose SL-T is 2,
> and shall provide SL-C 2 per IEC 62443-4-2 for the applicable component type."*

## Product-cyber regulation now in force

### EU Cyber Resilience Act — Regulation (EU) 2024/2847

| Date | What applies |
|---|---|
| 10 Dec 2024 | Entered into force |
| 11 Jun 2026 | Chapter IV — notified bodies may be designated |
| **11 Sep 2026** | **Reporting obligations begin** — actively exploited vulnerabilities and severe incidents |
| 11 Dec 2027 | Full application — all manufacturer obligations, CE marking, conformity assessment |

**Reporting cadence:** 24 h early warning to ENISA/CSIRT → 72 h full notification with mitigations → 14 days final report once fixed.

**Manufacturer obligations:** secure by design and by default, delivered with a secure
configuration and minimised attack surface; **no known exploitable vulnerabilities at
placing on market**; documented vulnerability handling with coordinated disclosure; **free
and timely security updates for a support period of at least five years** unless the
expected lifetime is shorter; a **machine-readable SBOM**; CE marking; technical
documentation retention. Penalties up to €15 M or 2.5 % of worldwide annual turnover.

**The mismatch to confront explicitly:** a five-year CRA minimum support period against a
20-year plant asset life. Do not paper over it — make it a stated requirement decision.

### NIS2 — Directive (EU) 2022/2555

Transposition deadline 17 Oct 2024; 18 sectors; obligations for risk management, incident
reporting, **supply-chain security** and top-management accountability.

**The distinction that matters: NIS2 binds the operator, the CRA binds the manufacturer.**
NIS2 does not regulate your product — it makes your customer legally accountable for
supply-chain security, which is why their procurement questionnaire has grown. That
pressure reaches a vendor contractually, not regulatorily.

## What a customer's security review now expects

- **62443-4-1 certification** of the development process (commonly via ISASecure **SDLA**)
- **62443-4-2 component certification** (ISASecure **CSA**), with declared **SL-C** per component type
- **Machine-readable SBOM** in SPDX or CycloneDX — a legal CRA obligation, not a preference
- Documented vulnerability handling and coordinated disclosure; CVE and **CSAF** advisories; a security contact and PGP key
- Declared support period and end-of-support date
- Security hardening guide (Practice 8) and penetration/fuzz test evidence (Practice 5)
- Signed firmware, verifiable secure boot chain, documented cryptographic inventory
- Contract terms: right to audit, flow-down of security obligations to sub-suppliers, incident notification aligned to the customer's NIS2 clock, source/configuration escrow for long-life systems

## Implications for agents

- Name the **part** whenever writing a 62443 requirement. "62443 compliant" alone is not a requirement.
- Express product security capability as **SL-C**, never as an SL the installation achieves.
- Put SBOM, support period, disclosure policy and hardening guide in the requirements — they are deliverables a customer will gate the order on.
- Security work belongs **before hardware commit**. Retrofitting it after is the standard failure mode.
