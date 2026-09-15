# SUBJECTS — subject-matter expertise skills

Reusable **domain-of-knowledge** skills, product-neutral and client-neutral, on the same
footing as `SDLC/`, `SOFTWARE/`, `DOMAIN/`, and `DEPLOY-TARGETS/`.

A **SUBJECT** is a body of expertise a project needs but that is *not* software craft and
*not* tied to any one product — e.g. medical physics, structural engineering, actuarial
science, RF engineering. It answers "what does an expert in this field know?" so that a
role agent (PM, architect, QA) can reason correctly about the problem domain.

## SUBJECTS vs DOMAIN vs a custom plugin

| Layer | Example | Reusable? | Where |
|---|---|---|---|
| **SUBJECT** (this folder) | Radiotherapy QA physics, TG-142/TG-218 | Yes — any radiation-oncology project | `skills/SUBJECTS/<Subject>/` |
| **DOMAIN** | Healthcare PHI patterns, retail inventory | Yes — any project in that vertical | `skills/DOMAIN/<vertical>/` |
| **Custom plugin** | Mirion SunCHECK product specifics | No — one product/client | `agentforge_custom_plugin/<Product>/` |

Rule of thumb: if the knowledge would still be true for a *different vendor's* product in
the same field, it is a SUBJECT (or DOMAIN) skill and belongs here. If it is specific to
one product's file formats, APIs, or a client's workflow, it belongs in a custom plugin.

## Contents

- `Physics/` — medical physics for radiotherapy & diagnostic imaging QA.
