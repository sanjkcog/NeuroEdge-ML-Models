---
name: hil-testing
description: The embedded discipline's test-port realization — a host-unit to SIL to HIL ladder, where the HIL rung is modeled as a dependency-wait on a named device/bench. Use when planning or reviewing embedded test strategy.
origin: ADR-0010
---

# HIL Testing — the embedded `test` port realization

Per `skills/ENGINEERING/_mechanism/discipline-realization.md`'s ports table, the embedded
discipline realizes the `test` outbound port as a **host-unit → SIL → HIL** ladder. This
is the pack's `stage_realizations.test` entry (`skills/ENGINEERING/embedded/manifest.md`).

## The three rungs

1. **Host-unit** — ordinary unit tests compiled and run on the development host (x86/
   ARM64 workstation or CI runner), exercising pure logic with the hardware-facing layer
   mocked/faked out. Fastest feedback, no target hardware or simulator required.
2. **SIL (Software-in-the-Loop)** — the embedded target code (or a cross-compiled build
   of it) runs against a **simulated** environment/peripheral model rather than real
   silicon — e.g. a register/peripheral simulator, or the cross-compiled binary executed
   under an instruction-set simulator (QEMU or similar). Exercises target-specific code
   paths (bit-widths, endianness, alignment) without needing physical hardware access.
3. **HIL (Hardware-in-the-Loop)** — the actual compiled firmware runs on **real target
   hardware** (or a hardware-accurate bench), exercised against real or bench-simulated
   peripherals/signals. This is the only rung that validates real timing, real interrupt
   latency, and real electrical/peripheral behavior — nothing before it can substitute for
   it.

## The HIL rung is a dependency-wait

The HIL rung is not just "slower" than host-unit/SIL — it is qualitatively different
because it depends on something the orchestrator cannot itself produce: **a real device
under test (DUT) or bench being available**. Per
`skills/ENGINEERING/_mechanism/dependent-activities.md`, the HIL rung is modeled as a
**dependency-wait** node:

- **Named external input:** the specific DUT/bench (e.g. "Nucleo-F446RE on bench 2,
  flashed with build #N") the HIL run requires.
- **On the critical path:** the plan shows the HIL rung as a real node the `test` stage
  cannot pass without, with genuine (not synthetic) lead time until the DUT/bench is
  available.
- **Resumes only on arrival** of that named DUT/bench input — not on a timer, and not on
  an agent's decision to mark it done (see the dependency-wait vs. approval-gate
  distinction in `dependent-activities.md`).

## Wired as `stage_realizations.test`

`skills/ENGINEERING/embedded/manifest.md` names this ladder — with the HIL rung explicitly
flagged as a dependency-wait — as the concrete value of its `stage_realizations.test`
field, mirroring the shape `skills/ENGINEERING/ai-genai/manifest.md` uses for its own
`test` realization (evals + guardrails). The `test` outbound port
(`discipline-realization.md`'s ports table) dispatches to this ladder whenever a project
declares the `embedded` discipline.

## Practical ordering

A change should climb the ladder rung by rung: fix host-unit failures before attempting
SIL, and reach SIL green before scheduling a HIL slot — since HIL time on real hardware is
the scarcest resource in the ladder (bench availability, DUT flash-cycle time, one DUT
serving multiple in-flight changes), burning it on a defect host-unit/SIL would already
have caught is the failure mode this ordering avoids.
