# `ai-ml` Engineering-Discipline Manifest

This is the discipline manifest for building **classical / deep-learning ML models** — the
ADR-0010 taxonomy's `ENGINEERING/ai-ml` pack (ADR-0014), kept **separate from `ai-genai`**
(prompt/agent products). It is loaded manifest-first, exactly like
`skills/ENGINEERING/ai-genai/manifest.md`: a project declares the `ai-ml` discipline
(`active_disciplines: [ai-ml]`, per `skills/ENGINEERING/_mechanism/discipline-realization.md`)
and the orchestrator reads this file to decide which reviewers, skills, and stage realizations
to bring into context for the active stage. Non-declaring projects still receive every file on
disk (whole-tree/flat install), but never load them — see `load_scope` below.

**The boundary this pack encodes (ADR-0014):** the user states an objective; AgentForge takes over
and produces a **training-ready package** — a suggested (or synthesized + labeled) dataset, the
**model generated as `.py` (PyTorch) or `.tf`/Keras code**, and a **training script**. Only the
**training run leaves AgentForge** — the user carries the package to a cloud GPU / build machine and
trains there. This pack builds *up to* training; it never runs training and makes no GPU assumption.

The single fenced `yaml` block below is machine-parseable: every `path:` entry under `reviewers`,
`skills.owned`, `skills.references`, `commands`, and `agents_extra` MUST resolve to an existing file
in this repo (mirrors `tests/test_ai_genai_manifest.py`'s TC-01-01-04 pattern; here realized as
`tests/test_ai_ml_manifest.py`). `artifacts:` entries are all `status: backlog` and carry no
`path:` — declared scope, not yet-authored files, deliberately excluded from the resolve check.

```yaml
discipline: ai-ml
adr: [ADR-0014, ADR-0010]
version: 0.1.0
status: phase-2                  # Phases 1-2 delivered, Phase 3 open (ADR-0014)
reviewers:
  - {name: ml-eval-reviewer, path: agents/ENGINEERING/ai-ml/ml-eval-reviewer.md}
skills:
  owned:
    - {path: skills/ENGINEERING/ai-ml/dataset-sourcing.md}
    - {path: skills/ENGINEERING/ai-ml/data-labeling.md}
    - {path: skills/ENGINEERING/ai-ml/synthetic-data.md}
    - {path: skills/ENGINEERING/ai-ml/pretrained-and-transfer.md}
    - {path: skills/ENGINEERING/ai-ml/model-architectures.md}
    - {path: skills/ENGINEERING/ai-ml/model-codegen.md}
    - {path: skills/ENGINEERING/ai-ml/time-series-ml.md}
    - {path: skills/ENGINEERING/ai-ml/ml-model-package.md}
  references:
    - {path: skills/SOFTWARE/pytorch/pytorch-patterns.md,
       reason: "REFERENCE: PyTorch training-loop / reproducibility idioms reused by model-codegen;
                broadly consumed as a SOFTWARE skill, not re-owned under this discipline"}
    - {path: skills/ENGINEERING/_mechanism/ml-artifact-destination.md,
       reason: "REFERENCE: cross-pack rule for where ai-ml/ai-genai commands write artifacts (ADR-0021)"}
commands:
  - {name: agentforge-ml, path: commands/ENGINEERING/ai-ml/agentforge-ml.md}   # orchestrator (ADR-0022)
  - {name: dataset-scout, path: commands/ENGINEERING/ai-ml/dataset-scout.md}
  - {name: dataset-verify, path: commands/ENGINEERING/ai-ml/dataset-verify.md}
  - {name: auto-label,    path: commands/ENGINEERING/ai-ml/auto-label.md}
  - {name: synth-data,    path: commands/ENGINEERING/ai-ml/synth-data.md}
  - {name: model-select,  path: commands/ENGINEERING/ai-ml/model-select.md}
  - {name: model-build,   path: commands/ENGINEERING/ai-ml/model-build.md}
  - {name: dataset-download, path: commands/ENGINEERING/ai-ml/dataset-download.md}   # ADR-0024
  - {name: data-simulator, path: commands/ENGINEERING/ai-ml/data-simulator.md}       # NeuroEdge-Web ADR-0008
  - {name: usecase-audit, path: commands/ENGINEERING/ai-ml/usecase-audit.md}         # ADR-0025 D-6
  - {name: model-fetch,   path: commands/ENGINEERING/ai-ml/model-fetch.md}           # ADR-0028 D-2
  - {name: aihub-compile, path: commands/ENGINEERING/ai-ml/aihub-compile.md}         # ADR-0028 D-10
agents_extra:
  - {path: agents/ENGINEERING/ai-ml/ml-data-engineer.md}
  - {path: agents/ENGINEERING/ai-ml/ml-modeler.md}
  - {path: agents/SOFTWARE/pytorch-build-resolver.md,
     reason: "REFERENCE: SOFTWARE agent, not re-owned; fixes crashes in the generated PyTorch
              train.py/eval.py after handoff — minimal-diff code fixes, never methodology"}
stage_realizations:
  data:
    realization: source-verify-label-synthesize-curate   # verify = acquire + profile + per-unit split + withheld test (ADR-0022 M2)
    owner: ml-data-engineer
    builds_on: [dataset-sourcing, data-labeling, synthetic-data, time-series-ml]
  build:
    realization: model-and-training-codegen      # emit .py/.tf model + training script; NOT a training run
    owner: ml-modeler
    builds_on: [model-architectures, pretrained-and-transfer, model-codegen]
    note: "ends at the training-ready handoff package; training runs externally on the user's cloud GPU"
  train:
    realization: external-cloud-gpu              # out of scope by design — dependency-wait, not an action
    status: external
    note: "/agentforge-ml suspends at this stage (waiting_external) and --resume looks for the model-package (ADR-0022 M7)"
  test:
    status: phase-2
    owner: ml-eval-reviewer
    realization: "held-out eval gate: eval.py on the withheld test split, KPIs on every path, beats_baseline only when a baseline is declared (ADR-0022 M8, ADR-0028 D-11)"
    builds_on: [model-codegen, ml-model-package]
artifacts:
  - {name: dataset-card,     status: backlog}
  - {name: label-manifest,   status: backlog}
  - {name: synthetic-recipe, status: backlog}
  - {name: model-code,       status: backlog}   # the generated .py/.tf model
  - {name: training-script,  status: backlog}
  - {name: handoff-package,  status: backlog}
  - {name: model-card,       status: backlog}
  - {name: eval-report,      status: backlog}
load_scope:
  declared_by: active_disciplines
  note: "pack loads only when a project declares discipline ai-ml; non-declaring projects have
         files on disk (whole-tree install) but never load them"
```

## Reading this manifest

- **`reviewers`** — `ml-eval-reviewer` complements (never replaces) the generic `code-reviewer`:
  it reviews eval methodology, train/test leakage, and the generated model/training code. Installed
  flat via the existing `_AGENT_SUBDIRS` `ENGINEERING` entry (no `install.py` change).
- **`skills.owned`** — the seven `ai-ml` skills (`time-series-ml` added by ADR-0015). A non-ML project never needs dataset-sourcing /
  labeling / synthetic-data / model codegen, so they live here rather than in `skills/SDLC/`.
- **`agents_extra`** — `ml-data-engineer` and `ml-modeler` are owned. `pytorch-build-resolver` is
  REFERENCE-in-place: it lives under `agents/SOFTWARE/` and installs flat to `.claude/agents/` via
  the `SOFTWARE` entry. It is the route when the generated PyTorch training/eval code crashes on the
  user's GPU box after handoff (shape, device, gradient, DataLoader, AMP errors). It does not review
  methodology, so an `ml-eval-reviewer` pass follows its fix. PyTorch only — no TF/Keras counterpart.
- **`skills.references`** — `pytorch-patterns` is deliberately NOT moved (REFERENCE-in-place): it is
  a broadly-consumed SOFTWARE skill; `model-codegen` builds on it rather than re-owning it.
- **`stage_realizations`** — how the ADR-0008 canonical stages realize for `ai-ml`: `data` =
  source→label→synthesize→curate; `build` = generate the `.py`/`.tf` model + training script and
  assemble the handoff package; `train` = **external** (cloud GPU, out of scope); `test` = the eval
  gate (`ml-eval-reviewer`) that reviews metrics returned from that external run.
- **`artifacts`** — discipline-owned outputs this pack will eventually produce; all `status: backlog`
  this phase, listed so they are visible and traceable (feeds ADR-0009 format-adaptation) rather than
  silently dropped.
- **`load_scope`** — a project that does not declare `ai-ml` loads none of this pack's assets; one
  that does loads only the assets its active stage names.
