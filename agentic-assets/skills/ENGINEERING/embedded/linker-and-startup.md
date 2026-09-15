---
name: linker-and-startup
description: Bare-metal linker script (MEMORY/SECTIONS) and startup-code conventions for arm-none-eabi cross-compilation — .data LMA to VMA copy, .bss zero-init, vector-table placement, and the size-ceiling checks that gate a build. Use when reviewing or diagnosing an embedded build/link failure.
origin: ADR-0010
---

# Linker & Startup — bare-metal build realization

This skill backs `embedded-build-resolver`'s realization of the `build` outbound port
(`skills/ENGINEERING/_mechanism/discipline-realization.md`'s ports table): for the
`embedded` discipline, "build" means arm-none-eabi cross-compile plus a linker/startup
correctness pass that a software build has no equivalent of.

## Toolchain

Cross-compilation targets a bare-metal ARM Cortex-M/A part via the `arm-none-eabi` GCC
toolchain (`arm-none-eabi-gcc`, `arm-none-eabi-ld`, `arm-none-eabi-objcopy`,
`arm-none-eabi-size`), building `no_std` / freestanding code — no hosted C library, no OS
underneath it (or an RTOS instead of a general-purpose OS; see `rtos-isr-safety.md`).

## Linker script: MEMORY and SECTIONS

A bare-metal linker script has two required top-level commands:

- **`MEMORY`** — declares the physical memory regions (typically `FLASH` and `RAM`) with
  their origin address and length. Every output section must land inside a declared
  region; a section that does not fit is a **region-overflow** build failure (see below).
- **`SECTIONS`** — maps input sections (`.text`, `.rodata`, `.data`, `.bss`, the vector
  table) to output sections, and assigns those output sections to a `MEMORY` region via
  `> REGION` (load-memory-address region) and, for `.data`, `AT> REGION` (the
  load-address region distinct from the run-address region — see LMA→VMA below).

## `.data`: load address (LMA) → run address (VMA) copy

`.data` (initialized globals/statics) is **linked** to run from RAM (its Virtual/run
Memory Address, VMA) but must be **stored** in non-volatile Flash (its Load Memory
Address, LMA), because RAM does not retain its contents across a power cycle. Startup
code, before `main()` runs, must **copy** the `.data` image from its Flash LMA to its RAM
VMA. A startup routine that omits this copy leaves every initialized global holding
whatever garbage was in RAM at reset — a **missing-`.data`-copy** build failure.

## `.bss`: zero-initialization

`.bss` (zero-initialized globals/statics) occupies no space in the Flash image — the
linker only reserves its RAM extent. Startup code must explicitly **zero** the `.bss`
region before `main()` runs, because RAM contents are undefined at reset; C's "zero-
initialized globals start at zero" guarantee is a **startup-code responsibility**, not
something the linker or hardware provides for free. Startup code that omits this zeroing
is a **missing-`.bss`-zero** build failure.

## Vector table: `KEEP(.isr_vector)` and first-two-entry contract

The interrupt/exception vector table must be linked at the address the core expects
(typically the very start of Flash) and must **not be discarded by garbage collection**
(`--gc-sections`) even though nothing in the C code appears to reference it directly — the
linker script must wrap it in `KEEP(*(.isr_vector))` (or equivalent `KEEP(...)`) so it
survives dead-code stripping. A vector table stripped by an over-eager `--gc-sections`
pass is a **stripped-vector-table** build failure — the part will not boot even though the
rest of the image compiled and linked cleanly.

The vector table's **first two entries** carry a fixed contract on Cortex-M parts: entry 0
is the **initial stack pointer** value, entry 1 is the **reset handler** address. A vector
table missing or misordering either entry is a boot-time failure indistinguishable, at the
symptom level, from a stripped vector table — `embedded-build-resolver` treats both under
the same failure class.

## Size ceilings

A bare-metal target has a fixed, small Flash/RAM budget with no virtual memory to fall
back on. `embedded-build-resolver` checks the linked image against declared size ceilings
using:

- **`arm-none-eabi-size`** — reports `.text`/`.data`/`.bss` sizes from the final ELF.
- **`--print-memory-usage`** (a linker flag surfaced through `arm-none-eabi-gcc`/`ld`) —
  reports each `MEMORY` region's used/free bytes directly from the link, so a region that
  is over-budget is visible without a separate `size` invocation.

An image that exceeds a declared ceiling is a build failure at the size-check stage, even
if the link itself succeeded mechanically.

## Failure taxonomy (all treated as build failures, not warnings)

| Failure | Cause | Symptom |
|---|---|---|
| **Region overflow** | An output section (or the whole image) does not fit the declared `MEMORY` region | Linker error at link time, or a `--print-memory-usage`/`arm-none-eabi-size` ceiling breach |
| **Missing `.data` copy** | Startup code omits the Flash-LMA → RAM-VMA copy | Initialized globals hold garbage at runtime; link succeeds, boot is silently wrong |
| **Missing `.bss` zero** | Startup code omits zero-initialization of `.bss` | Zero-initialized globals hold garbage at runtime; link succeeds, boot is silently wrong |
| **Stripped vector table** | `.isr_vector` not wrapped in `KEEP(...)` and stripped by `--gc-sections`, or first-two-entry (SP/reset-handler) ordering wrong | Part fails to boot, or jumps to garbage on reset/first interrupt |

`embedded-build-resolver` diagnoses all four as build failures — none of them are treated
as a soft warning, because each produces a part that either does not link, does not boot,
or runs with silently corrupted initial state.
