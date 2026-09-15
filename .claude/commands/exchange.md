# Exchange

Push the current `/agentforge` run-state manifest and gate status to the Git exchange
substrate (ADR-0012 POC), and pull/apply inbound drive intents through the hard-gate
fence — so an external agentic app can **monitor and drive** a run without AgentForge
shipping a UI.

This is the CLI wrapper (`agentforge/src/exchange/exchange_cli.py`) around the exchange
package built in EP-01/EP-02: `exchange_record` (the manifest), `git_adapter` (push to a
repo-local file + GitHub Issues, pull intents from Issues), and `drive.apply_intent`
(the safety-critical hard-gate fence — an inbound intent **never** clears a pending hard
gate; only a recorded human decision via `gate_state.py decide`, D1, does that).

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /exchange · Skills: agentic-engineering, coding-standards, tdd-workflow`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/development/agentic-engineering.md`
> - `agentic-assets/skills/SDLC/development/coding-standards.md`
> - `agentic-assets/skills/SDLC/tdd/tdd-workflow.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Domain plugins (auto-discovered)

Product/client-specific context lives in custom plugins under
`agentforge_custom_plugin/<Name>/`. Before running, self-discover: find
`agentforge_custom_plugin/*/plugin.json` and read any plugin whose `wiring.auto_load` is
not `false` — honor any named safety constraint (a regulatory hard gate is never
overridable by an external drive intent, regardless of plugin content). Absence of
plugins is normal — never a blocker.

## Usage

```
/exchange export
/exchange import-intents
/exchange apply
```

Flags (all subcommands): `--run-path`, `--gates-path`, `--record-path`,
`--config-path` — default to `run.json`, `gates.json`, `exchange.json`,
`exchange_config.json` in the current directory.

Subcommands:
- **`export`** — build the exchange record from `run.json`/`gates.json`, save it, and
  push it via the configured adapter (`exchange/config.py`; unset falls back to the
  D12 `NoneExchangeAdapter`, repo-local only). Exit 0.
- **`import-intents`** — pull inbound drive intents from the substrate and print them
  (raw_id, action, target, identity). Exit 0, or 1 if the pull itself failed
  (never a crash — D12 result-object-never-raise).
- **`apply`** — pull inbound drive intents and apply each through
  `exchange.drive.apply_intent`. Persists `run.json`/`gates.json` afterward. Exit 0 if
  every intent that touched state was applied cleanly; exit **`BLOCKED` (3)** — the
  same convention as `run_state.py resume`'s `RESUME_BLOCKED_BY_GATE` — if any intent
  was refused because it targeted a pending hard gate. A refused intent is reported,
  never silently dropped, and the authoritative gate state is provably unchanged
  (`gates.json` stays `pending`, zero decisions recorded).

## Phase 0 — CONFIGURE (first run only)

Check `exchange/config.py`'s persisted choice at `--config-path`. If unset, prompt
(`AskUserQuestion`, main session only, D1) among Git (GitHub Issues) / none (repo-local
only) / decide later, and persist the answer. `export`/`import-intents`/`apply` all run
fully with no substrate configured at all (D12) — `NoneExchangeAdapter` makes the
run-state manifest still save locally and reports "not projected," never a failure.

## Phase 1 — EXPORT

Run `export` after any stage transition you want reflected outbound. The manifest never
mutates `run.json`/`gates.json` — it is a read-only projection
(`exchange_record.build`).

## Phase 2 — IMPORT / APPLY

Run `import-intents` to see what's pending without mutating anything, or `apply` to
actually drive the run from inbound intents. **The fence is load-bearing and has no
override**: an `approve_gate` (or any other action) targeting a pending hard gate is
always refused — clearing a hard gate is exclusively a human act via
`gate_state.py decide` in the main session (ADR-0009).

## Report

```
## Exchange

- Config: <unset (NoneExchangeAdapter) | git | none>
- Command: <export | import-intents | apply>
- Result: <exported/pushed | N intent(s) printed | N applied, M refused>
- Exit: <0 | 1 | BLOCKED(3)>

> Next: if BLOCKED, resolve the named hard gate via
> `gate_state.py --path <gates.json> decide <artifact> <approved|changes_requested|rejected> --identity <who>`,
> then re-run `/exchange apply`.
```

## Standalone vs. orchestrated

- **Standalone (this command):** the only entry point today — the Git exchange
  substrate (ADR-0012) is a POC layered on top of an existing `/agentforge` run, not a
  stage in `run_state.STAGE_SEQUENCE`. You run it yourself, whenever you want the run
  projected outbound or want to pull/apply inbound drive intents.
- **Inside `/agentforge`:** not yet wired as an orchestrator-driven stage (EP-03,
  orchestrator-side automatic drive, is deferred per `sprint-01.json`/`sprint-02.json`).
  The artifact this command produces/consumes (`exchange.json`, and the state it
  reads/writes) is the same `run.json`/`gates.json` the orchestrator already owns —
  running `/exchange` alongside `/agentforge` never conflicts with it, since every
  mutation still goes through the same `run_state`/`gate_state` primitives and the same
  hard-gate fence.
