# /simulator — Run or extend the NeuroEdge data-source simulator

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /simulator · Skills: simulator-patterns`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SOFTWARE/simulator/simulator-patterns.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Arguments

`$ARGUMENTS` — a plain-language ask, either to **run** or to **extend** the
simulator. Examples:
- `"stream sim_input over MQTT to localhost topic edge/telemetry at 10/s"`
- `"replay the CSV over SSE, wait for a client, loop forever"`
- `"POST each record to https://api.example.com/ingest with a bearer token"`
- `"add support for .parquet inputs"` · `"add a Kafka transport"`

## What this does

Drives `agentforge_simulator/` — the standalone tool that replays `sim_input/`
files (csv, xls/xlsx, json, images, video) over a transport (SSE, MQTT, webhook,
or API) and logs what was sent to `sim_output/` as json/csv. It also has a
**scenario mode** that serves a whole simulated world of external systems from a
`scenario.yaml` bundle (see *Scenario mode* below).

Two modes, inferred from the ask:

### Run mode — compose and execute an invocation

1. Read `agentic-assets/skills/SOFTWARE/simulator/simulator-patterns.md`.
2. Confirm deps are installed once: `pip install -r agentforge_simulator/requirements.txt`
   (only needed for csv/xls → pandas, video → opencv, mqtt → paho, http → requests).
3. Map the ask to flags and run:
   ```
   python agentforge_simulator/simulator.py \
     --transport <console|sse|mqtt|webhook|api> \
     --rate <n/s> [--loop -1] [--limit N] \
     --media-mode <ref|b64> --output-format <jsonl|json|csv|none> \
     <transport-specific flags>
   ```
   For SSE, prefer `--sse-wait --loop -1` so a late client still receives the stream.
4. Report where the sent-log landed (`sim_output/sent.<ext>`).

### Scenario mode — serve a simulated world from a bundle

When the ask is to stand in for the **external systems a use case calls**
(rather than to replay a data file), run a scenario bundle. Start a new bundle by
copying `agentforge_simulator/scenarios/_base/`; its README explains the layout.

```
python agentforge_simulator/simulator.py --scenario <bundle>/scenario.yaml \
  [--hub <hub-id>] [--play-once]
```

- `--scenario` must be the **first** argument. It needs PyYAML, which is in
  `requirements-inputs.txt`.
- `--hub <id>` runs only that hub's systems (`--hub shared` runs the shared
  ones). With no `--hub`, every section runs in one process.
- By default the process **keeps serving** after the timeline ends. `--play-once`
  exits when the timeline finishes, for batch runs and tests.
- Each hub gets **one port** with every face behind it: route tables (path),
  fixtures (`/<system-id>/<capability>`, answered per caller via the
  `X-NeuroEdge-Caller: key=value;...` header and optional `matches`), the MCP
  tool-server face (`/mcp/<server-id>`), and canned model answers
  (`/models/<model_ref>`). A hub can also capture broker publishes on declared
  `capture_topics`, seed CSVs into SQLite, and play a timeline.
- Report where things landed: the port map at `<bundle>/run/ports.<hub|shared|all>.json`
  and the run log at `<bundle>/run/run.<hub|shared|all>.log.jsonl`.
- Anything that isn't configured returns a loud 404. Treat that as an authoring
  gap, never as success.

### Extend mode — add a format, transport, or writer

Delegate to the **`simulator-builder`** agent. It preserves the module boundaries
(`loaders` / `transports` / `writers` / `engine`), lazy-imports optional deps, and
smoke-tests via `--transport console` before wiring the real path. In this assets
repo it edits `simulator/`; in a consuming project, `agentforge_simulator/`.

## Notes

- **Author upstream, not the installed copy.** Changes belong in the assets repo's
  `simulator/`; `python install.py --project <path> --verify` flags drift in an
  installed copy.
- `sim_input/` and `sim_output/` are yours — the installer ships only a `.gitkeep`
  there, so your data is never overwritten by an update nor deleted by a clean.
- Sample inputs live in `agentforge_simulator/examples/` — copy them into
  `sim_input/` to try it immediately.

## Related

- `simulator-builder` agent — the extension worker.
- `agentforge_simulator/README.md` — full flag reference, scenario mode and layout.
- `agentforge_simulator/scenarios/_base/README.md` — the scenario bundle template.
