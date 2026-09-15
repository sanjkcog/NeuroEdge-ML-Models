---
name: rtos-isr-safety
description: RTOS/bare-metal ISR-safety patterns — FreeRTOS FromISR API discipline, Zephyr k_mutex_lock-in-ISR hazard, priority inversion, and word-vs-byte stack-depth sizing across FreeRTOS/Zephyr/no_std. Use when reviewing interrupt-context code or task/stack configuration.
origin: ADR-0010
---

# RTOS / Bare-Metal ISR Safety

This skill backs `embedded-c-reviewer`'s RTOS/ISR-awareness checks. It recognizes three
target shapes — **FreeRTOS**, **Zephyr**, and **bare-metal `no_std`** (no RTOS at all) —
and applies the ISR-safety rules that shape implies.

## FromISR API discipline (FreeRTOS)

FreeRTOS provides two parallel API families: the normal task-context API
(`xQueueSend`, `xSemaphoreGive`, `xTaskNotify`, ...) and an **ISR-safe** `...FromISR`
variant of each (`xQueueSendFromISR`, `xSemaphoreGiveFromISR`, `xTaskNotifyFromISR`, ...).
The non-`FromISR` variants may block or trigger a context switch in ways that are only
valid from task context; calling one from an interrupt service routine is undefined
behavior on the kernel's internal state (corrupted ready-list, missed context switch, or a
hard fault depending on port).

**Rule applied:** any FreeRTOS API call inside an ISR body that is **not** the `FromISR`
variant (e.g. `xQueueSend` instead of `xQueueSendFromISR`) is flagged as an ISR-safety
violation. This is the concrete instance the reviewer's manual walkthrough exercises
(TC-02-04-02): an ISR calling non-`FromISR` `xQueueSend` must be flagged, not passed.

## `k_mutex_lock` in ISR context (Zephyr)

Zephyr's `k_mutex_lock()` is a **blocking** call — it can suspend the calling context
waiting for the mutex to become available. Interrupt service routines must never block:
an ISR that calls `k_mutex_lock()` (with anything but a zero/no-wait timeout that it is
prepared to fail immediately) risks stalling the interrupt controller or deadlocking
against the very task it preempted. Zephyr's ISR-safe primitives (spinlocks,
`k_sem_give`/`k_sem_take` with `K_NO_WAIT`, or deferring the mutex-protected work to a
work-queue/thread) are the correct pattern instead.

**Rule applied:** `k_mutex_lock()` called from ISR context (rather than deferred to a
thread/work-queue) is flagged.

## Priority inversion

Priority inversion occurs when a low-priority task holds a resource (mutex) a
high-priority task needs, and an unrelated medium-priority task preempts the low-priority
holder — indefinitely delaying the high-priority task despite it "winning" priority on
paper. The standard mitigation is a **priority-inheritance mutex** (the low-priority
holder temporarily inherits the blocked high-priority task's priority for the duration it
holds the resource), which both FreeRTOS (`xSemaphoreCreateMutex`, not
`xSemaphoreCreateBinary`, for a resource lock) and Zephyr (`k_mutex_lock`, which is
priority-inheriting by default) provide as the mutex-flavored primitive rather than the
raw binary-semaphore flavor.

**Rule applied:** a resource-protection lock implemented with a non-inheriting primitive
(e.g. a binary semaphore used as a mutex) where a real priority spread exists across
tasks is flagged as a priority-inversion risk.

## Word-vs-byte stack-depth sizing

Task stack depth is configured in **different units** depending on the RTOS/port:
FreeRTOS's `configSTACK_DEPTH_TYPE` (commonly `uint16_t`) sizes a task's stack in
**words**, not bytes, on most ports (`xTaskCreate(..., usStackDepth, ...)` — the value is
a word count that the port multiplies by `sizeof(StackType_t)`); Zephyr's
`K_THREAD_STACK_DEFINE` sizes a stack in **bytes**. Porting a stack-depth constant between
RTOSes (or between FreeRTOS ports with different `StackType_t` widths) without converting
units silently under- or over-allocates a task's stack — an under-allocation is a
stack-overflow risk with no compile-time signal.

**Rule applied:** a stack-depth value carried across a port/RTOS boundary (or into a
different `StackType_t` width) without an explicit unit conversion is flagged.

## Target-shape recognition

`embedded-c-reviewer` and `embedded-build-resolver` recognize three target shapes and
apply the rules above accordingly:

- **FreeRTOS** — `FromISR` discipline, priority-inheriting mutex vs. binary semaphore,
  word-based stack-depth sizing.
- **Zephyr** — `k_mutex_lock`-in-ISR hazard, `K_NO_WAIT`/spinlock ISR-safe alternatives,
  byte-based stack-depth sizing.
- **Bare-metal `no_std`** — no RTOS primitives at all; ISR-safety concerns instead center
  on `volatile` correctness and minimal, non-blocking ISR bodies (see `misra-cert.md`'s
  unpinned `volatile`/ISR-entry concepts).

## Relationship to the trace port

A flagged ISR-safety violation (non-`FromISR` call, blocking-lock-in-ISR, priority
inversion, unit-mismatched stack depth) is recorded the same way a MISRA/CERT violation
is — through the recorded-Deviation model in `misra-cert.md` — since these are safety-
relevant defects a project may need to formally accept-with-justification rather than
silently ignore.
