# Incident Response Guide

**Version:** 1.0 — 2026-06-04
**Audience:** On-call engineers, project leads, anyone responding to production issues for a project that uses the NeuroEdge AgentForge toolkit.

This guide defines the severity matrix, the triage flow, the comms templates, and the post-incident review structure. It is the source of truth for the (future) `incident-respond` and `post-mortem` skills on the toolkit's roadmap. Until those skills ship, use this guide as a manual checklist.

---

## 1. Severity matrix

Severity is determined by **what the user can do**, not by how the alert looks in a dashboard. Pick the highest applicable severity.

| Severity | Definition | Examples | Response time | Comms cadence |
|---|---|---|---|---|
| **P1** | Operation can't run. Service is down or core path is broken. Users blocked. | Production outage; data pipeline fully halted; auth completely broken; pricing engine returns zero | < 15 min ack, work until resolved | Every 30 min until mitigated |
| **P2** | Can run with config change or infra restart, but needs a code change to permanently resolve. Functional workaround exists. | Memory leak triggering daily restart; a feature flag must be toggled to recover; degraded mode running | < 1 hr ack, fix within 24 hr | Every 4 hr during business hours |
| **P3** | Minor fix. Functionality works; one path or edge case fails. | A button mis-aligned on tablet; a non-blocking validation message; intermittent slowness on a non-critical screen | < 1 business day ack | At triage + at resolution |
| **P4** | Cosmetic. No functional impact. | Typo; spacing; copy improvement; deprecated icon | Sprint planning queue | Resolution only |

### 1.1 Escalation chain

| Trigger | Escalate to |
|---|---|
| P1 unmitigated after 30 minutes | Engineering manager + on-call lead |
| P1 unmitigated after 2 hours | Director / VP Engineering + customer comms lead |
| P2 unmitigated after 24 hours | Engineering manager |
| Any incident touching regulated data (PHI, payment, PII) | Compliance / legal + security lead — immediately |
| Customer-visible outage > 30 min | Customer success / external comms — immediately |

Define the actual names/channels for each role in your project's runbook. This table is the **trigger** schema; identities are project-specific.

> **Default to higher severity** when in doubt. Downgrading is cheap; upgrading mid-incident is expensive.

---

## 2. Triage flow

When a potential incident is reported (alert, customer ticket, internal observation):

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. ACKNOWLEDGE     —  Within SLA per severity                   │
│                      Reply: "Acked. Investigating. Sev: ?"       │
├─────────────────────────────────────────────────────────────────┤
│ 2. ASSESS          —  Walk the matrix. Confirm severity.        │
│                      Identify scope: who is affected, since when │
├─────────────────────────────────────────────────────────────────┤
│ 3. ANNOUNCE        —  Open incident channel; post initial msg   │
│                      (templates in §3)                           │
├─────────────────────────────────────────────────────────────────┤
│ 4. MITIGATE        —  Stop the bleeding before fixing the cause │
│                      Acceptable mitigations: rollback, feature  │
│                      flag, traffic shift, scale up, restart      │
├─────────────────────────────────────────────────────────────────┤
│ 5. STABILIZE       —  Confirm mitigation works; monitor 30 min  │
├─────────────────────────────────────────────────────────────────┤
│ 6. RESOLVE         —  Permanent fix shipped; verify in prod     │
├─────────────────────────────────────────────────────────────────┤
│ 7. POST-MORTEM     —  Within 5 business days (§4)               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Comms templates

Post these in your incident channel (Slack, Teams, equivalent). Edit the bracketed bits.

### 3.1 Initial post (any severity)

```
INCIDENT — [P1|P2|P3|P4]
Title: [one-line description]
Status: investigating
Started: [HH:MM UTC]
Affected: [users / services / regions]
IC (incident commander): [@name]
Comms: [@name]
Updates will follow every [30 min for P1 | 4 hr for P2 | daily for P3].
```

### 3.2 Status update

```
UPDATE [HH:MM UTC] — [P1|P2|P3|P4]
Status: [investigating | mitigated | monitoring | resolved]
What we know: [1-3 bullets]
What we're doing next: [1-2 bullets]
ETA to mitigation: [time or "unknown — investigating root cause"]
```

### 3.3 Mitigation announcement

```
MITIGATED [HH:MM UTC] — [P1|P2|P3|P4]
Action taken: [rollback to v1.2.3 | toggled feature_X to off | scaled to 8 replicas]
Current state: [users can now ... | error rate back to baseline]
Permanent fix: [tracking issue link]
Monitoring for: [30 min] then resolving.
```

### 3.4 Resolution

```
RESOLVED [HH:MM UTC] — [P1|P2|P3|P4]
Duration: [start time → resolved time]
User impact: [scope and magnitude]
Permanent fix: [PR link]
Post-mortem: [link or "scheduled by YYYY-MM-DD"]
```

---

## 4. Post-mortem (P1 + P2 mandatory, P3 by judgment)

Run within 5 business days of resolution. Blameless — focus on systems, not people.

### 4.1 Required sections

| Section | Content |
|---|---|
| **Summary** | 3 sentences: what happened, who was affected, how long |
| **Timeline** | UTC-stamped events from first signal through resolution |
| **Root cause** | The actual cause, found via 5-whys (§4.2) — not the symptom |
| **Contributing factors** | Things that made it worse or harder to detect (monitoring gap, runbook missing, single point of failure) |
| **What went well** | Specific actions/decisions that helped — preserve these |
| **What went poorly** | Specific things that hurt — avoid blaming individuals |
| **Action items** | Concrete tasks with owners and dates. Categorized: Prevent (won't happen again), Detect (faster next time), Mitigate (faster recovery) |
| **Customer impact statement** | What you tell affected users (if anything) |

### 4.2 Five-whys template

```
Symptom: [what users saw]

Why 1: Why did [symptom] happen?
  → [direct cause]

Why 2: Why did [direct cause] happen?
  → [next layer]

Why 3: ...
Why 4: ...
Why 5: ...

Root cause: [the deepest "why" that's still actionable]
```

Stop when the next "why" becomes "because that's how the world is" — earlier whys are usually more actionable.

### 4.3 Action item discipline

Every action item must have:
1. **Owner** — a single name (not a team)
2. **Date** — realistic, not aspirational
3. **Done state** — binary, verifiable (e.g. "alert rule deployed to prod", not "improve monitoring")
4. **Category** — Prevent / Detect / Mitigate

Track action items in `docs/decisions/post-mortems/<YYYY-MM-DD>-<slug>.md` (one file per incident) and in your project board. Create the folder on first use: `mkdir -p docs/decisions/post-mortems`.

---

## 5. Integration with the AgentForge toolkit

### Today (manual)

- This guide is the source of truth.
- Use the `chief-of-staff` agent for multi-channel incident comms triage.
- Use `silent-failure-hunter` agent to investigate code that swallowed errors during the incident.
- Use `code-explorer` to map the blast radius of changes that may have caused the incident.

### Future (audit P0)

- `incident-respond` skill — generates the §3 templates, walks you through §2 triage, escalates per matrix.
- `post-mortem` skill — facilitates the §4 format, drives the 5-whys, produces the action item list.

---

## 6. Quick reference — severity decision tree

```
Is anyone blocked from a core workflow?
  ├─ YES → P1
  └─ NO
     │
     Does a workaround (config / restart) exist while we fix code?
       ├─ YES → P2
       └─ NO
          │
          Is functionality impaired (slow, ugly, edge-case)?
            ├─ YES → P3
            └─ NO → P4 (cosmetic)
```

---

## 7. What this guide does NOT cover

- **Customer-facing status page updates** — project-specific; document in your runbook.
- **Pager rotations and on-call schedules** — use your team's chosen tool (PagerDuty, Opsgenie, etc.).
- **SLO / error-budget breach handling** — see future `slo-define` skill on the audit P1 backlog.
- **Regulatory disclosure** (data breach notifications, etc.) — get legal involved per your jurisdiction.

---

*End of guide. Update this file when severity definitions change. If you find a useful pattern in a real incident, capture it as an instinct with `/learn-eval` so future sessions benefit.*
