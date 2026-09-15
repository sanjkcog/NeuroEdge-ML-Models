# `embedded` Engineering-Discipline Manifest

This is the discipline manifest for building **embedded / firmware** products — the
ADR-0010 taxonomy's second `ENGINEERING/` pack (embedded ships first per ADR-0010's
phasing, highest reuse from the existing `cpp` reviewer/skills). It is loaded
manifest-first, exactly like `skills/ENGINEERING/ai-genai/manifest.md`: a project declares
the `embedded` discipline (`active_disciplines: [embedded]`, per
`skills/ENGINEERING/_mechanism/discipline-realization.md`) and the orchestrator reads this
file to decide which reviewers, skills, and stage realizations to bring into context for
the active stage. Non-declaring projects still receive every file on disk (the installer
copies whole-tree/flat regardless of declaration), but never load them — see `load_scope`
below.

The single fenced `yaml` block below is machine-parseable: every `path:` entry under
`reviewers` and `skills.owned` MUST resolve to an existing file in this repo (mirrors
`test_ai_genai_manifest.py`'s TC-01-01-04 pattern; here realized as
`tests/test_embedded_manifest.py`). `artifacts:` entries are all `status: backlog` and
carry no `path:` — they are declared scope, not yet-authored files, and are deliberately
excluded from the resolve check.

```yaml
discipline: embedded
kind: discipline        # ADR-0018 D-1
install: default        # ADR-0018: discipline packs always install; gating is runtime
adr: [ADR-0010]
version: 0.1.0
status: phase-1
reviewers:
  - {name: embedded-c-reviewer,      path: packs/embedded/agents/embedded-c-reviewer.md}
  - {name: embedded-build-resolver,  path: packs/embedded/agents/embedded-build-resolver.md}
skills:
  owned:
    - {path: packs/embedded/skills/misra-cert.md}
    - {path: packs/embedded/skills/linker-and-startup.md}
    - {path: packs/embedded/skills/rtos-isr-safety.md}
    - {path: packs/embedded/skills/hil-testing.md}
stage_realizations:
  build:
    realization: cross-compile
    resolver: embedded-build-resolver
    builds_on: [linker-and-startup, rtos-isr-safety]
  test:
    realization: HIL-ladder
    builds_on: [hil-testing]
    note: "host-unit -> SIL -> HIL; the HIL rung is a dependency-wait
           (skills/ENGINEERING/_mechanism/dependent-activities.md)"
artifacts:
  - {name: deviation-record,       status: backlog}   # FR-05/FR-14 — recorded-Deviation trail
  - {name: memory-size-report,     status: backlog}   # FR-06/FR-14 — size-ceiling/--print-memory-usage output
  - {name: hil-test-report,        status: backlog}   # FR-10/FR-14 — HIL-rung test evidence
load_scope:
  declared_by: active_disciplines   # mirrors requires_subjects; see discipline-realization.md
  note: "pack loads only when a project declares discipline embedded; non-declaring
         projects have files on disk (whole-tree install) but never load them"
```

## Reading this manifest

- **`reviewers`** — both discipline agents (the code reviewer and the build-port
  adapter). Installed flat via the existing `_AGENT_SUBDIRS` `ENGINEERING` entry (added by
  `ai-genai`/ADR-0011, no further `install.py` edit needed); declared here so a stage that
  names either agent can load it by path.
- **`skills.owned`** — the four embedded-discipline skills, consolidated under this pack
  since a non-embedded project never needs MISRA/CERT/linker/RTOS/HIL knowledge.
- **`stage_realizations`** — how the ADR-0008 canonical SDLC's generic `build`/`test`
  stages realize for the embedded discipline: `build` = arm-none-eabi cross-compile
  (`embedded-build-resolver`); `test` = the host→SIL→HIL ladder
  (`skills/ENGINEERING/embedded/hil-testing.md`), whose HIL rung is a dependency-wait per
  `skills/ENGINEERING/_mechanism/dependent-activities.md`. Both are live (not
  phase-3-stubbed, unlike `ai-genai`'s current `test` entry) because the embedded build/
  test realizations are fully specified this run.
- **`artifacts`** — discipline-owned outputs this pack will eventually produce; all
  `status: backlog` this run, listed here so they are visible and traceable (feeds
  ADR-0009 format-adaptation) rather than silently dropped.
- **`load_scope`** — the negative + positive context-scope contract: a project that does
  not declare `embedded` loads none of this pack's assets; one that does loads only the
  assets its active stage names.
