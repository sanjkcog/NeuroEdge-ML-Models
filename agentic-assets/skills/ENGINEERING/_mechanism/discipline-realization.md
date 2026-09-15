---
name: discipline-realization
description: Cross-pack mechanism spec for the ADR-0010 engineering-discipline layer — how a plugin declares active_disciplines, how build/test/trace dispatch to a discipline resolver, and how packs stay context-scoped. Use when wiring a new engineering-discipline pack or reasoning about which pack loads for a project.
origin: ADR-0010
---

# Discipline Realization

This is the **cross-pack contract** for the `ENGINEERING/` layer (ADR-0010). It does not
belong to any one discipline pack (`ai-genai`, `embedded`, future `fpga`/`safety`/`pcb`) —
it is the mechanism every pack plugs into. Individual packs (e.g.
`skills/ENGINEERING/embedded/manifest.md`) declare their own reviewers/skills/artifacts;
this spec declares *how* the orchestrator decides which pack to consult and which resolver
answers a given stage.

> **Source layout note (ADR-0018, 2026-08-31).** A discipline pack's SOURCE may live either
> under the classic three trees (`agents|commands|skills/ENGINEERING/<name>/`) or as a pack
> folder (`packs/<name>/{manifest.md,agents/,commands/,skills/}` — `embedded` migrated first).
> **The installed/runtime layout is identical either way**: every path in this document that a
> target reads (`agentic-assets/skills/ENGINEERING/<name>/…`, flat `.claude/agents/`) is
> unchanged, and manifests keep loading from `agentic-assets/skills/ENGINEERING/<name>/manifest.md`.
> Deliberate trade-off, documented per ADR-0018 D-3: pack agents still install flat into
> `.claude/agents/`, so discipline agents are discoverable by the harness even when the
> discipline is undeclared — runtime gating governs what *loads into context*, not what is
> *on disk*.

The process layer (`skills/SDLC/development/hexagonal-architecture.md` +
ADR-0008's canonical stages) is **unchanged** by this mechanism. What changes is a single
indirection: each process stage's *realization* — the concrete thing that happens when
"build" or "test" runs — is resolved per active discipline instead of assumed to be a
software toolchain.

## 1. `active_disciplines` — manifest-declared, mirrors `requires_subjects`

A plugin declares which engineering disciplines its project needs, exactly the way
`plugin.json` already declares `requires_subjects` for `skills/SUBJECTS/<Subject>`
knowledge (see `agentforge_custom_plugin/*/plugin.json`):

```json
{
  "requires_subjects": ["Physics"],
  "active_disciplines": ["embedded"]
}
```

- `requires_subjects` mirror: same declare-to-load shape — a field on the plugin manifest
  that names the packs a project actually needs, so the orchestrator never guesses.
- **Declared → loads.** A project declaring `active_disciplines: [embedded]` causes the
  orchestrator to read `skills/ENGINEERING/embedded/manifest.md` and load the reviewers,
  skills, and stage realizations it names.
- **Undeclared → loads nothing.** A project that declares no disciplines (or omits the
  field) loads **zero** `ENGINEERING/<discipline>/` assets. The files are on disk (the
  installer copies the whole tree, same as `ai-genai` — see that pack's manifest note) but
  never read into context unless declared.

**Worked example:**

| Project | `active_disciplines` | What loads |
|---|---|---|
| Software-only web app | `[]` (or absent) | Nothing under `ENGINEERING/embedded/`; build/test/trace use the software default realization. |
| Firmware project (e.g. Paragon-style embedded target) | `["embedded"]` | `agents/ENGINEERING/embedded/{embedded-c-reviewer,embedded-build-resolver}.md`, the 4 `skills/ENGINEERING/embedded/*.md` files, and `manifest.md`'s `stage_realizations`. |

## 2. Build / test / trace — outbound ports, resolver-per-discipline

Per the hexagonal-architecture skill, an outbound port models a *capability*, not a
technology. This mechanism declares three outbound ports every discipline binds an adapter
(resolver) to:

| Port | Software adapter (default) | Embedded adapter (this run) |
|---|---|---|
| `build` | compile + package manager | cross-compile arm-none-eabi + linker/size-ceiling checks |
| `test` | host unit/integration | host-unit → SIL → HIL/device-in-loop (dependency-wait) |
| `trace` | code↔requirement | + MISRA/CERT recorded deviations, safety-req |

Each discipline pack's manifest declares its `stage_realizations` for the ports it
realizes (see `skills/ENGINEERING/embedded/manifest.md` for the embedded pack's `build`
and `test` realizations; `skills/ENGINEERING/ai-genai/manifest.md` for `ai-genai`'s `test`
realization).

## 3. Dispatch rule

- **`active_disciplines` names `embedded`** → the `build`, `test`, and `trace` ports
  dispatch to the embedded pack's resolver/reviewer (`embedded-build-resolver` for build,
  the host→SIL→HIL ladder for test, `embedded-c-reviewer`'s recorded-deviation model for
  trace).
- **No discipline declared** → all three ports dispatch to the **software default**
  realization (compile + package manager for build, host unit/integration for test, plain
  code↔requirement linkage for trace) — the behavior every non-declaring project already
  has today.
- **`test` and `trace` dispatch the same way as `build`** — same declared-discipline →
  discipline-resolver rule, no special-casing per port.
- **ADR-0008's process layer is unchanged.** Stage names, gates, and canonical artifacts
  stay exactly as ADR-0008 defines them; only the *realization* behind a stage name is
  discipline-dispatched. `ai-genai`'s `test` realization (evals + guardrails) already
  exercises this same dispatch mechanism — embedded is the second pack to use it, not a
  new mechanism.

### Invariant C-07 — no toolchain leak into the orchestrator

Discipline toolchain literals (`arm-none-eabi`, a synthesis tool name, etc.) never appear
in the orchestrator/composition-root layer (`commands/agentforge.md`, `agentforge/src/`).
They live **only** inside the resolver/adapter asset that owns them
(`agents/ENGINEERING/embedded/embedded-build-resolver.md`). The orchestrator only knows
"dispatch build to the active discipline's resolver" — it never hardcodes which compiler
that resolver invokes.

## 4. `load_scope` — context-scoped pack loading

- **Software-only project → zero engineering packs loaded.** A project with no
  `active_disciplines` (or only disciplines other than the packs present) loads **ZERO**
  `ENGINEERING/<discipline>/` packs into context. This keeps context lean (M3) — the
  software default realization requires no discipline-specific asset at all.
- **Embedded project → only its pack + stage-named assets.** A project declaring
  `embedded` loads only `skills/ENGINEERING/embedded/` + `agents/ENGINEERING/embedded/`
  assets, and within that pack only the files the active stage's realization names (e.g.
  a `build` stage loads `embedded-build-resolver.md` + `linker-and-startup.md`; it does not
  also load `hil-testing.md` unless the stage is `test`).
- **Software-only behavior is byte-identical (M5).** Declaring zero disciplines changes
  nothing about the existing software-pack behavior — no file this mechanism adds is ever
  read by a project that does not opt in. Backward compatibility is the default, not an
  exception.

## Reuse notes

- Ports/adapters vocabulary and the composition-root wiring pattern are borrowed directly
  from `skills/SDLC/development/hexagonal-architecture.md` — read that skill for the full
  Ports & Adapters model this mechanism specializes.
- The `stage_realizations` field name and its "declared, not yet a live loader" phase-1
  posture mirror `skills/ENGINEERING/ai-genai/manifest.md`'s `stage_realizations.test`
  entry — the same field, a second discipline.
- The dependency-wait stage-node type this mechanism's `test` port dispatches through for
  embedded (the HIL rung) is specified separately in
  `skills/ENGINEERING/_mechanism/dependent-activities.md`.
