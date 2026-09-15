---
name: dependent-activities
description: Defines the dependency-wait stage-node type — a plan node that pauses on a named external input and resumes only on arrival, distinct from an approval gate. Use when a stage cannot be completed by the orchestrator alone (device-in-loop bring-up, bench/instrument availability, an external schematic or bitstream handoff).
origin: ADR-0010
---

# Dependent Activities — the dependency-wait node type

Some engineering-discipline steps **cannot be fully automated and block on an external
input**: hardware-in-the-loop (HIL) / device-in-loop bring-up, bench or instrument
availability, a PCB schematic or layout handoff from an EE, a synthesized bitstream running
on real silicon. ADR-0010 names these **dependent activities** and requires them to be
first-class plan nodes — reachable by the orchestrator, but not completable by it alone.

This spec defines that node type: the **dependency-wait**.

## Properties of a dependency-wait node

A dependency-wait node has all four of the following properties:

1. **Records a named external input.** The node states explicitly what it is waiting on —
   e.g. "DUT bring-up on bench B3", "signed bitstream from synthesis run #42", "schematic
   handoff from EE". A dependency-wait with no named input is a modeling error, not a valid
   node.
2. **Sits on the critical path.** The dependency-wait is not a side note or footnote in the
   plan — it appears in the plan's critical-path view exactly like any other stage node, so
   downstream steps that depend on it show real, non-synthetic lead time.
3. **Resumes only on arrival of the named input** — not on a timer, and not on an agent's
   decision. A dependency-wait that "times out" and proceeds anyway, or that an agent can
   wave through, is not a dependency-wait; it has silently become something else (and hidden
   the real block).
4. **Distinct from an approval gate.** An approval gate waits on a **decision** (a human or
   process choosing to proceed). A dependency-wait waits on an **artifact/input arriving**
   (a device becoming available, a file landing, a physical handoff completing). The two are
   not interchangeable: a dependency-wait cannot be satisfied by someone simply approving
   it — the named input must actually arrive.

## Why this is a distinct node type, not a flavor of gate

An approval gate models "should we proceed?" — the underlying work may already be complete;
the gate is a decision checkpoint. A dependency-wait models "we cannot proceed yet because
something outside the orchestrator's control has not happened." Conflating the two would
let an agent or human "approve past" a dependency-wait without the named input actually
existing — silently converting a genuine hardware/external block into a rubber-stamp,
which is exactly the failure mode ADR-0010 calls out (plans that "pretend the work is
synchronous").

## Worked instance — the HIL rung (FR-10)

The embedded discipline's `test` port realizes as a host→SIL→HIL ladder
(`skills/ENGINEERING/embedded/hil-testing.md`). The **HIL rung is a dependency-wait**:

- **Named external input:** the specific device-under-test (DUT) or bench becoming
  available (e.g. "Nucleo-F446RE on bench 2, flashed with build #N").
- **Critical path:** the plan shows the HIL rung as a node the `test` stage cannot pass
  without, with real (not synthetic) lead time until the DUT is available.
- **Resumes on arrival:** the lane advances only when the named DUT/bench input actually
  arrives — not when a timer expires, and not when an agent decides to mark it done.
- **Distinct from approval:** a reviewer approving the HIL test *plan* is not the same as
  the HIL rung actually executing against real hardware; approval does not substitute for
  the dependency being satisfied.

## Design posture this run

This run **design-first**: the dependency-wait node type is specified here as a documented
plan-node contract. No heavy state-machine build accompanies it — the mechanism is
declared so that a discipline pack's stage realization (like the HIL ladder) can *name* a
dependency-wait and have the plan reflect it correctly, without requiring a new runtime
execution engine in this pass.
