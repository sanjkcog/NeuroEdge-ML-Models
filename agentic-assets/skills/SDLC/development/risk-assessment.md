---
name: risk-assessment
description: Produce a gated risk artifact for a feature before implementation — implementation, regression, and security risks, each with an ID, likelihood, impact, and mitigation, and each traceable into the test plan. Use at the S3 architecture stage alongside architecture-design, before planning and build.
origin: NeuroEdge
---

# Risk Assessment

Name what can go wrong before building, so the mitigations become work items and the test plan
covers them, instead of discovering the risk in production. The output is
`neuroedge/docs/project_related/<objective-slug>/04-development/risk-assessment.md` (`<track>` = the objective's PRD group —
`backend`, `portal`, `industries`, …), a sibling of the architecture artifact
([[architecture-design]]), approved at the same S3 hard gate.

A design says how it should work. This says how it will fail, and what is done about that.

## When to Use

- Immediately after the architecture design, before the S3 gate closes
- Any feature touching auth, data integrity, external input, money, or an existing hot path
- Before `/prp-plan` — risk mitigations are plan tasks, and risk IDs seed the test plan

## Non-Negotiable Rules

- **Every risk is falsifiable and specific.** "Might have bugs" is not a risk. "Concurrent
  writes to `run.json` corrupt gate state because writes are not atomic" is.
- **Every risk carries an ID.** `RK-NN`, permanent within the feature. The ID is what lets a
  regression risk point at a regression test and a security risk point at a security case —
  this is the traceability that makes the assessment more than a document.
- **Every risk has a mitigation or an accepted-risk note.** A risk with neither is not
  assessed; it is just named. "Accepted" is a valid mitigation if the owner signs it.
- **Rate honestly.** Likelihood and impact are Low/Med/High. Do not deflate a High to avoid
  the work it implies — that is exactly the failure this exists to prevent.
- **Do not duplicate the PRD's product risks.** Those are about the effort. These are about
  *this feature's implementation*.

## The Three Risk Classes

Assess all three. A feature with none in a class should say so explicitly, not omit it.

### Implementation risks
Ways the build itself goes wrong: a hard integration, an unproven library, a concurrency or
ordering hazard, a platform-specific pitfall, an estimate that is really a guess. Mitigation is
usually a spike, a proof, a narrowed scope, or a design change fed back to [[architecture-design]].

### Regression risks
Existing behaviour this change could break. For each: the specific behaviour at risk, why this
change endangers it, and the **characterization or regression test** that pins it. A regression
risk with no test naming it is unmitigated by definition. This is the highest-value class when
touching a hot path or shared module.

### Security risks
How the change could be abused. Walk the trust boundaries the design crosses — untrusted input,
authn/authz, secrets, injection, SSRF, path traversal, deserialization, privilege escalation. A
lightweight STRIDE pass over the sequence diagrams is enough; this is security-by-design, done
*before* code, distinct from the post-code `security-reviewer` pass at S8. For each: the abuse
case, the mitigation, and the **security test case** that proves the mitigation holds.

## The Artifact — `neuroedge/docs/project_related/<objective-slug>/04-development/risk-assessment.md`

### 1. Summary
The one or two risks that would most change the plan if they materialise. If a risk is severe
enough to reconsider the design, say so here and loop back to [[architecture-design]].

### 2. Risk register

| ID | Class | Risk (falsifiable) | Likelihood | Impact | Mitigation | Traces to |
|----|-------|--------------------|------------|--------|------------|-----------|
| RK-01 | implementation | ... | Med | High | spike X before task Y | plan task |
| RK-02 | regression | ... behaviour breaks because ... | Low | High | characterization test | TC-.. |
| RK-03 | security | ... abuse case | Med | High | validate + authz check | TC-.. (security) |

- **Class:** implementation / regression / security.
- **Traces to:** the plan task that carries the mitigation, and/or the `TC-NN` test case that
  proves it. Regression and security risks MUST reach a test case; implementation risks reach a
  plan task.

### 3. Residual and accepted risks
Anything not fully mitigated, with the owner who accepts it and why. Explicit acceptance is a
decision on the record; silent residual risk is the thing this artifact exists to prevent.

## Handoff

End with: **ready for the S3 gate**, or **design change required** (name the risk driving it,
and loop back to [[architecture-design]]). Then confirm every regression and security risk has a
`TC-NN` target so `/test-plan` can pick them up — an untested High-impact risk should block the
gate, not pass it.
