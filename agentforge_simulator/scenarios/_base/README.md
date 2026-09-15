# `_base` — the scenario bundle every project starts from

This directory is the generic template for a simulated world. A host copies it beside a use case
and fills it in; the simulator ships it so that a project's first simulated run is a **command**
rather than an authoring project.

## What a filled-in bundle looks like

```text
<use-case>/simulation/
  scenario.yaml            # THE index: seed, hubs, ports, per-hub endpoint overlay
  timeline/                # events.csv, entities.csv — what arrives during a run
  shared/
    sim.yaml               # systems more than one hub calls
    routes/ fixtures/ seed/ models/ mcp/
  hubs/<hub>/
    sim.yaml               # the systems THIS hub fronts
    routes/*.routes.json   # answers addressed by path
    fixtures/*.json        # answers addressed by (role, caller, capability)
    seed/*.csv             # tables seeded into the scenario database
    models/responses.json  # canned model answers
    mcp/servers.json       # tool servers + their tools (GENERATED from discovery)
    mcp/responses.json     # what each of those tools answers (authored)
  run/                     # generated, gitignored: ports.<scope>.json, run.<scope>.log.jsonl, scenario.sqlite
```

## The three rules worth knowing before you edit anything

1. **The address is the switch.** A capability has one binding. Pointing it at this simulator means
   putting a loopback address in `scenario.yaml`'s `env:` overlay; going real means putting the
   production address back in the same field. Same code path, same request, different value.

2. **Each external system is simulated exactly once.** In the sim of the hub that fronts it; else
   in the single caller's; else in `shared/`. The loader refuses two hubs configuring the same
   system id, because two copies are free to disagree.

3. **Nothing configured answers 404, loudly.** "No fixture is configured for this" and "this
   returns an empty object" are different facts. A simulator that collapses them teaches a green
   run to mean nothing.

## Editing

`sim.yaml` and `scenario.yaml` are the two files you edit. Everything else is data they point at.
Ports are **declared**, not assigned — the workflow this exists to serve is a person typing an
address into a config, and an address that changes every run cannot be typed. Use `port: 0` when
you want the OS to choose (CI, parallel runs); the resolved map is always written to
`run/ports.<scope>.json` — one file per simulator process, so per-hub processes never overwrite
each other's: `run/ports.<hub>.json` for `--hub <hub>`, `run/ports.shared.json` for `--hub shared`,
and `run/ports.all.json` for a whole-scenario run with no `--hub`. Each map carries `endpoints`,
`ports`, `tool_servers` (the MCP face URLs) and `database` (the seeded SQLite path, or `null`).

The ordered run log is written beside the port map, one per process: `run/run.<scope>.log.jsonl`
(`run.all.log.jsonl` without `--hub`), truncated when that process starts.

`run/` is generated; the host truncates it at the start of each run. Nothing you author belongs in
it.
