---
name: misra-cert
description: MISRA C:2023 taxonomy, the two hard-pinned rules (21.3 no dynamic memory, 18.1 pointer-in-array-bounds), the recorded-Deviation model, and the MISRA C:2023 Addendum 3 correspondence to CERT C 2016. Use when reviewing embedded C for standards conformance or recording a deviation.
origin: ADR-0010
---

# MISRA C:2023 & CERT C 2016 — standards fidelity

This skill is the reference standard behind `embedded-c-reviewer`. It is deliberately
conservative about which rule numbers it cites: **only the two attested rule IDs (21.3,
18.1) are numeric.** Every other rule this skill or the reviewer discusses is named by
**concept** with a `TBD — pin from MISRA C:2023` marker — see "Unpinned rule concepts"
below. Shipping a guessed rule ID is a doc-accuracy safety event (false authority); this
skill's numeric surface is intentionally narrow until each concept is verified against the
actual standard text.

## MISRA C:2023 taxonomy

MISRA C:2023 classifies every rule along two independent axes:

- **Directive vs Rule** — a **Directive** cannot be fully checked by static analysis alone
  (it requires broader process/design context); a **Rule** is fully decidable by a
  conforming static-analysis tool.
- **Mandatory / Required / Advisory** — the enforcement category:
  - **Mandatory** — no deviation is ever permitted. A Mandatory violation is a defect, full
    stop.
  - **Required** — must be followed, but a **recorded Deviation** (see below) may
    permissibly relax it for a specific, justified instance.
  - **Advisory** — best-practice guidance; violations are flagged but do not block on
    their own.

Every rule this skill or the reviewer cites carries both classifications (e.g. "Rule 21.3
— Required").

## The two hard-pinned rules

### Rule 21.3 — no dynamic memory allocation

**Category:** Required, Rule (not Directive).

The standard `<stdlib.h>` dynamic memory functions (`malloc`, `calloc`, `realloc`, `free`)
must not be used on a freestanding/bare-metal target. Dynamic allocation on a target with
no heap, or with an unmanaged heap, produces unbounded fragmentation and non-deterministic
allocation latency — both unacceptable on a resource-constrained or real-time embedded
target. `embedded-c-reviewer` flags any `malloc`/`calloc`/`realloc`/`free` call on a
bare-metal or `no_std`-class target as a Rule 21.3 violation.

### Rule 18.1 — pointer arithmetic must stay within the bounds of the array object

**Category:** Required, Rule.

Pointer arithmetic (increment, addition, subtraction, indexing) on a pointer into an array
must not produce a pointer value outside the bounds of that array object (except the
one-past-the-end value, which itself must not be dereferenced). Walking a pointer past the
end of its backing array and dereferencing it is undefined behavior and a common source of
out-of-bounds reads/writes on embedded targets with no memory-protection unit to catch it
at runtime. `embedded-c-reviewer` flags pointer arithmetic that walks past an array's
declared bound as a Rule 18.1 violation.

## The recorded-Deviation model

- A **Required**-rule violation **with a recorded Deviation** (a documented justification:
  who, why, scope, compensating control) is **accepted** — the deviation record is the
  evidence trail, not a bypass.
- A **Required**-rule violation **without a recorded Deviation** is **flagged** — Required
  means "follow it, or document exactly why not," not "ignore it silently."
- A **Mandatory**-rule violation is **never waivable** — no Deviation record, however
  well-justified, permits a Mandatory violation to pass.

This model is the trace-port realization referenced by
`skills/ENGINEERING/_mechanism/discipline-realization.md`'s ports table ("trace: + MISRA/
CERT recorded deviations, safety-req").

## Unpinned rule concepts — `TBD — pin from MISRA C:2023`

The following embedded-safety concepts are real, named MISRA C:2023 concerns that
`embedded-c-reviewer` and `rtos-isr-safety.md` reason about, but whose exact rule number is
**not yet pinned** in this pack. Each is named by concept only, with the explicit marker
below, rather than guessing a number:

- **`volatile`-qualified access correctness** (reading/writing memory-mapped registers
  without the qualifier, or relying on compiler-visible side effects without it) —
  `TBD — pin from MISRA C:2023`.
- **ISR entry/exit discipline** (what a rule requires of interrupt service routine
  signature, reentrancy, and side effects) — `TBD — pin from MISRA C:2023`.
- **Register-map / memory-mapped I/O access patterns** (bit-field vs. masked-write access
  to a hardware register) — `TBD — pin from MISRA C:2023`.
- **DMA buffer coherency** (cache/compiler visibility of a buffer a DMA engine writes
  without CPU involvement) — `TBD — pin from MISRA C:2023`.

Do not promote any of these to a numeric ID without verifying the exact rule text against
the published MISRA C:2023 standard.

## MISRA ↔ CERT C 2016 correspondence — via MISRA C:2023 Addendum 3

MISRA C:2023 ships **Addendum 3**, the official cross-reference mapping MISRA C rules to
CERT C 2016 (SEI CERT C Coding Standard) rules. Every MISRA↔CERT correspondence this pack
draws is cited **through Addendum 3** — never inferred by topical similarity.

- Rule 21.3 (no dynamic memory) corresponds, per Addendum 3, to the CERT C 2016 memory-
  management rule family (dynamic-allocation-on-constrained-targets concerns) — cited via
  Addendum 3, not independently derived.
- Rule 18.1 (pointer-in-array-bounds) corresponds, per Addendum 3, to the CERT C 2016
  pointer-arithmetic/array-bounds rule family — cited via Addendum 3, not independently
  derived.

**No-inferred-overlap note:** this skill does not assert any MISRA↔CERT correspondence
that is not backed by an Addendum 3 entry. A topical resemblance between a MISRA rule and a
CERT C rule is not, on its own, sufficient grounds to claim a correspondence — only
Addendum 3's own mapping is authoritative here.

## Reading order

1. `embedded-c-reviewer` (agent) applies this skill's taxonomy and the two pinned rules.
2. `rtos-isr-safety.md` builds on the ISR-entry/exit and `volatile` concepts named here.
3. `linker-and-startup.md` and `hil-testing.md` are independent (build/test realizations),
   not standards-fidelity documents.
