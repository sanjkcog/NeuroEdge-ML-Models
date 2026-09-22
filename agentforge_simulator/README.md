# NeuroEdge Simulator (`agentforge_simulator/`)

A product-neutral **data-source simulator**. It stands in for a real data
producer — an **edge device**, a **sensor**, or an **enterprise-ops platform** —
by replaying records from `sim_input/` and streaming them over a **transport**
(Server-Sent Events, MQTT, webhook, or a generic API call). What it emits is
logged to `sim_output/` as JSON or CSV.

It has two modes:

- **Replay mode** (Steps 1–3 below) streams `sim_input/` files over a transport.
- **Scenario mode** (`--scenario`, [below](#scenario-mode)) serves the external systems a
  use case calls, from a `scenario.yaml` bundle: HTTP stubs, fixtures that answer
  differently per caller, an MCP tool-server face, canned model answers, broker capture,
  an OPC-UA machine-HMI face driven by alerts, a seeded SQLite database and a timeline of events.

This folder is installed into a project by the AgentForge installer and is
managed by `update`/`clean` like every other asset. Author it in the assets repo
under `simulator/`; never hand-edit the installed copy (`--verify` flags drift).

---

## When to use it

Reach for the simulator whenever you need a **realistic, controllable data feed**
but don't want to stand up the real producer:

| You're building… | Simulate with | Typical transport |
|---|---|---|
| An **edge/IoT ingest** pipeline | `edge_device` telemetry | MQTT |
| A **sensor analytics / anomaly** path | `sensor` channel (high-rate) | SSE or MQTT |
| An **enterprise-ops / eventing** backend | `enterprise_ops` event stream | webhook or API |
| A **dashboard / live UI** | any profile | SSE |
| A **load / soak** test | any profile, `--loop -1 --rate N` | any |

It answers: *does my consumer handle this shape, this rate, this transport, and
these anomalies* — before the real device exists.

---

## The three steps

```
  ┌─────────────┐        ┌──────────────┐        ┌───────────────┐
  │ 1. INPUT    │  ───▶  │ 2. TRANSPORT │  ───▶  │ 3. OUTPUT log │
  │ select /gen │        │ sse mqtt     │        │ sim_output/   │
  │ sim_input/  │        │ webhook api  │        │ json | csv    │
  └─────────────┘        └──────────────┘        └───────────────┘
```

### Install deps (once)

```bash
pip install -r agentforge_simulator/requirements.txt
```

Only what a run touches is needed: pandas (csv/xls), opencv (video), paho (mqtt),
requests (webhook/api), PyYAML (scenario mode), asyncua (the OPC-UA HMI face, only when
one is declared). The console transport, JSON input, and `gen_input.py` are pure stdlib.

The set is split into two groups, and `requirements.txt` above composes both, so
the standalone command is unchanged:

| Group | Contains | Who needs it |
|---|---|---|
| `requirements-transports.txt` | `paho-mqtt`, `requests` | the simulator **and** any host whose ingress layer consumes the same transports |
| `requirements-inputs.txt` | `pandas`, `openpyxl`, `xlrd`, `opencv-python`, `PyYAML`, `asyncua` | the simulator only — decoding source data, loading scenario bundles and serving the OPC-UA HMI face are producer-side |

**Host projects consuming these transports** should reference the transports
group from their own `requirements.txt` rather than copying its pins:

```
-r agentforge_simulator/requirements-transports.txt
```

That gives each shared pin one home (this asset) and skips the input decoders —
`opencv-python` alone is ~60MB for a host that never decodes a frame. Your
`requirements.txt` stays yours: add your own dependencies and tighten pins as you
like; AgentForge neither edits nor validates it. See TD-012.

---

## Step 1 — Select or generate input

### A. Select existing files

Drop files into `sim_input/`. Format decides the input **family** and how each
file becomes records:

| Family | Extensions | One record per… |
|---|---|---|
| **timeseries** | `.csv` `.xls` `.xlsx` `.json` | row (csv/xls) or object (json — plain array, NDJSON, or dict-of-columns) |
| **media** | `.png .jpg .jpeg .bmp .gif .webp .tif` · `.mp4 .avi .mov .mkv .webm .m4v` | image, or decoded video **frame** |

Media records honour `--media-mode`:
- `ref` (default) — metadata + a file `uri` (small; the receiver fetches bytes).
- `b64` — metadata + inline `data_b64` (self-contained, but large).

Unsupported files in `sim_input/` are skipped, not errored. Filter with
`--input-glob '*.csv'`. Sample files live in `examples/` — copy them in to start:

```bash
cp agentforge_simulator/examples/* agentforge_simulator/sim_input/
```

### B. Generate input (no real capture needed)

`gen_input.py` synthesizes a realistic timeseries for each persona and writes it
into `sim_input/`. Stdlib-only, seeded for reproducibility, with an injectable
anomaly rate so your consumer's alarm path gets exercised.

```bash
# device health telemetry (cpu/mem/temp/uptime/status)
python agentforge_simulator/gen_input.py --profile edge_device --rows 300

# a single high-rate sensor channel (baseline + sine + noise + spikes)
python agentforge_simulator/gen_input.py --profile sensor --rows 1000 --hz 50 --format jsonl

# ops/event stream (service, severity, latency_ms, status_code)
python agentforge_simulator/gen_input.py --profile enterprise_ops --rows 2000 \
    --anomaly-rate 0.05 --format json

# N correlated channels over repeating work cycles, with a fault that progresses
python agentforge_simulator/gen_input.py --profile cyclic_multichannel --rows 800 \
    --rows-per-cycle 80 --channel-names spindle_load,axis_err,vibration_rms \
    --drift ramp-recover --seed 20260914 --start-ts 2026-01-01T00:00:00Z --recipe
```

| Profile | Fields it emits | Models |
|---|---|---|
| `edge_device` | `device_id, ts, cpu_pct, mem_pct, temp_c, uptime_s, fw_version, status` | a fleet node reporting health; anomalies spike cpu/temp and flip `status` to warn/alarm |
| `sensor` | `sensor_id, ts, value, unit, quality` | one channel; `value` = baseline + sine + Gaussian noise; anomalies inject spikes and mark `quality: suspect` |
| `enterprise_ops` | `event_id, ts, service, severity, latency_ms, status_code, message` | a microservice event bus; anomalies raise latency and 5xx rates |
| `cyclic_multichannel` | `ts, cycle_index, row_in_cycle, <one column per channel>, severity, label` | correlated channels sharing a work-cycle envelope; the fault magnitude progresses across cycles, and rows at or above `--label-threshold` are labelled `1`. Emits whole cycles only |

Key flags: `--rows`, `--format {csv,json,jsonl}`, `--hz` (spaces the timestamps),
`--anomaly-rate 0..1`, `--seed`, `--start-ts` (pin with `--seed` for byte-identical
reruns), `--out`. `cyclic_multichannel` only: `--channel-names` (column order is the
feature order), `--rows-per-cycle` (must exceed the model's window), `--drift
{none,ramp,ramp-recover,step}`, `--label-threshold`, and `--recipe`, which also writes
`<out>.recipe.json` recording the generator, params, seed and label rule. Edit or add a
profile in [`gen_input.py`](gen_input.py) — it's a plain dict of generator functions.

---

## Step 2 — Configure the transport

Pick where records go with `--transport`, then its own flags.

| `--transport` | Key flags | Behaviour | Best for |
|---|---|---|---|
| `console` | — | print each record as a JSON line (no network) | quick checks, piping |
| `sse` | `--sse-host --sse-port --sse-path --sse-wait` | the simulator **hosts** an SSE endpoint; connected clients receive events | dashboards, live UIs, sensor streams |
| `mqtt` | `--mqtt-host --mqtt-port --mqtt-topic --mqtt-qos --mqtt-username --mqtt-password --mqtt-client-id` | publish each record to a broker topic | edge/IoT devices & sensors |
| `webhook` | `--webhook-url` | fire-and-forget HTTP POST of each record | enterprise event delivery |
| `api` | `--api-url --api-method --api-bearer --api-header 'K: V'` | configurable HTTP request with headers/auth | authenticated REST ingest |

Notes:
- **SSE** drops records emitted while no client is connected (a live source has no
  backlog). Use `--sse-wait` to hold emission until a client attaches, and
  `--loop -1` to keep streaming. Test with `curl http://127.0.0.1:8080/events`.
- **MQTT** works with paho-mqtt 1.x and 2.x. Point it at any broker (e.g. a local
  Mosquitto: `--mqtt-host 127.0.0.1 --mqtt-topic edge/telemetry`). The client id
  defaults to `neuro-sim-<pid>` so two simulators against one broker don't evict
  each other's session; override with `--mqtt-client-id`. The publish topic must
  not contain wildcards (`+`/`#`) — those are subscribe-only.
- **webhook vs api** — webhook is the simplest POST; `api` adds method, custom
  headers, and a bearer token for authenticated endpoints.
- **Failure policy is fail-fast**: a connect failure (broker down, SSE port in
  use) or a failed send (non-2xx HTTP, publish timeout) aborts the run with a
  clean `ERROR:` message — there is no per-record retry or skip-and-continue yet
  (a retry/skip policy is a candidate extension, below).

### Pacing (applies to any transport)

- `--rate` records/sec (`0` = as fast as possible)
- `--loop` passes over the inputs (`-1` = forever — natural for MQTT/SSE feeds)
- `--limit` stop after N records

---

## Step 3 — What it emits

Every emission is a **Record envelope** wrapping your data:

```json
{
  "seq": 42,                    // run-global 0-based counter
  "ts": 1785047594.33,          // EMIT time (epoch seconds)
  "source": "sensor.csv",       // input file it came from
  "kind": "timeseries",         // "timeseries" | "media"
  "payload": { ... }            // your row/object, or media frame metadata
}
```

The same envelope is what goes over SSE (`data: <json>\n\n`), MQTT (JSON message
body), and webhook/api (JSON request body).

A **sent-log** is also written to `sim_output/sent.<ext>` (override with
`--output-file`) so you have a record of exactly what left:

| `--output-format` | Shape |
|---|---|
| `jsonl` (default) | one JSON object per line — streamed, tail-safe |
| `json` | a single JSON array — easy to re-load |
| `csv` | flattened rows; payload keys hoisted (envelope ts becomes `emit_ts`, colliding payload keys get a `payload_` prefix, base64 blobs collapse to a `data_b64_len` column) |
| `none` | no file (transport is the only sink) |

---

## End-to-end recipes

```bash
# Edge device -> MQTT, forever, 1/s, generate the data first
python agentforge_simulator/gen_input.py --profile edge_device --rows 500
python agentforge_simulator/simulator.py --transport mqtt \
    --mqtt-host 127.0.0.1 --mqtt-topic edge/telemetry --rate 1 --loop -1

# Sensor -> SSE for a live dashboard, wait for the browser to connect
python agentforge_simulator/gen_input.py --profile sensor --rows 2000 --hz 20 --format jsonl
python agentforge_simulator/simulator.py --transport sse --sse-wait --rate 20 --loop -1

# Enterprise ops -> authenticated API, log what was sent as CSV
python agentforge_simulator/gen_input.py --profile enterprise_ops --rows 1000 --format json
python agentforge_simulator/simulator.py --transport api \
    --api-url https://api.example.com/ingest --api-method POST \
    --api-bearer "$TOKEN" --api-header 'X-Source: neuro-sim' \
    --rate 50 --output-format csv
```

---

## Scenario mode

Scenario mode simulates the **external systems a use case calls**, where replay mode
simulates one data feed. A bundle directory indexed by `scenario.yaml` declares hubs.
Each hub's `sim.yaml` names the systems that hub fronts, and the simulator serves them
until stopped. Start a bundle by copying [`scenarios/_base/`](scenarios/_base/README.md).

```bash
python agentforge_simulator/simulator.py --scenario path/to/scenario.yaml            # whole scenario, one process
python agentforge_simulator/simulator.py --scenario path/to/scenario.yaml --hub h1   # one hub's systems only
python agentforge_simulator/simulator.py --scenario path/to/scenario.yaml --play-once
```

| Flag | Meaning |
|---|---|
| `--scenario` | path to the bundle's `scenario.yaml`. It **must be the first argument**, because the replay flags don't apply in this mode |
| `--hub <id>` | run only that hub's systems; `--hub shared` runs the `shared:` section. Omitted, every section runs in one process |
| `--play-once` | exit once the timeline finishes. Without it the process **keeps serving** until Ctrl-C, because agents call the stubs long after the last timeline row |

On exit the process prints a JSON summary (`scenario`, `endpoints`, `events_emitted`,
`run_log`). Load errors print `ERROR: ...` and exit 2.

### Manifest

`scenario.yaml` keys: `scenario` (name, required), `seed`, `clock.compression`,
`caller_key`, `entities` (CSV), `timeline` (CSV), `hubs.<id>` and `shared`. A hub or
`shared` section may carry `port` (declared; `0` lets the OS choose), `sim` (path to its
`sim.yaml`), `env` (the endpoint overlay the hub's children see, which is how a capability
is pointed at the simulator and then back at production), `capture_topics`, `opcua_face`
([below](#opc-ua-egress-face-a-simulated-machine-hmi)), and the older `api:` / `mqtt:` adapters. Unknown keys are refused by name at load. A system `id`
declared by two hubs is also refused, because each external system is simulated exactly once.

Each `sim.yaml` `systems:` entry takes `id`, `description`, and any of `routes`,
`fixtures`, `seed`, `models` and `mcp`. Paths are relative to that `sim.yaml`.

### Faces: one port per hub, every system behind it

| Face | Declared by | Addressed as | Answers |
|---|---|---|---|
| **Route / HTTP stub** | `routes: *.routes.json` (`{"routes": [...]}`) | exact `(method, path)` | `response` (with `${seq}` / `${input.<field>}` templating), `capture` + `required` (422 if missing), `respond_from`, `feed` (cursor `{"rows", "cursor"}`), fault injection `latency_ms` / `error_rate` from the seeded RNG |
| **Role / caller fixtures** | `fixtures: *.json` (`{"fixtures": [...]}`, entries `capability`, `caller`, `returns` xor `sequence`, `faults`, `matches`) | `GET`/`POST /<system-id>/<capability>` | most specific wins: `(role, caller, capability)` + `matches` → `(role, caller, capability)` → `(role, capability)` + `matches` → `(role, capability)` → **404**. `matches` compares request arguments **as text**; omit it for a catch-all |
| **MCP tool server** | `mcp: <dir>/` holding a **generated** `servers.json` (`"source": "discovery-cache"`, otherwise refused) and an **authored** `responses.json` | JSON-RPC `POST /mcp/<server-id>` | `initialize`, `tools/list` (the derived surface), `tools/call` (from fixtures keyed `server_id` + `tool_name`) |
| **Model** | `models: responses.json` (entries `model_ref`, `prompt_fingerprint`, `returns`) | `POST /models/<model_ref>` | canned answer for `(model_ref, prompt fingerprint)`, else `(model_ref, any prompt)`, else **404** |
| **SQLite seed** | `seed: <dir>/` of CSVs | read-only DSN in the port map's `database` | one table per CSV, named after its file stem, all merged into `run/scenario.sqlite` |
| **Broker / queue capture** | hub `capture_topics: [...]` + an `mqtt:` broker | subscribes to each declared topic (wildcards refused) | records every publish per topic in the run log. A publish to an undeclared topic is logged as refused |
| **OPC-UA egress (HMI)** | hub or `shared` `opcua_face:` + an `mqtt:` broker (or `opcua_face.broker`) | an OPC-UA server at `opcua_face.endpoint`, subscribed to each declared topic (wildcards refused) | writes the HMI nodes from each alert; records every alert and every node write in the run log. See [below](#opc-ua-egress-face-a-simulated-machine-hmi) |
| **Timeline** | `timeline: events.csv` (`offset_ms, hub, adapter, target, payload`) | `adapter` is `mqtt` (topic), `webhook` (URL) or `feed` (feed name) | raw JSON payloads, played on the virtual clock (`clock.compression`). `--hub` keeps only that hub's rows |

On one hub port, an exact route match is tried first, then `/models/...` and
`/mcp/...`, then the two-segment fixture path. Nothing configured answers a **loud 404**
plus a run-log entry, never a silent 200. Every handled call logs what was `sent`
separately from what was `answered`.

### Caller identity: `X-NeuroEdge-Caller` and `caller_key`

Callers identify themselves in the `X-NeuroEdge-Caller` header as `key=value;key=value`.
The server reads the caller from the key named by the bundle's `caller_key`, and falls
back to the key `caller` when the bundle sets none:

```
X-NeuroEdge-Caller: hub_id=dealer_north;tenant=acme     # with caller_key: hub_id
```

Rules:

- `caller_key`, if present, must be a non-empty string without `=` or `;`. Either
  character is refused at load, because such a key can never be parsed out of the header.
- A missing or malformed header, or one without that key, resolves to the empty caller.
  The call then gets the **shared-fact** answer (a fixture with no `caller`) and does not fail.
- The key is carried into every `--hub` slice, and the MCP face reads the same header.
- Send the header in real environments too, so a simulated run and a real one share the
  same wire shape.

### What a run writes

| Path (relative to the bundle) | Contents |
|---|---|
| `run/ports.<scope>.json` | one per process: `ports.<hub>.json` for `--hub <hub>`, `ports.shared.json` for `--hub shared`, `ports.all.json` without `--hub`. It records `scenario`, `endpoints`, `ports` (bound, including OS-assigned), `tool_servers` and `database` |
| `run/scenario.sqlite` | the seeded database, rebuilt every run (only when a system declares `seed`) |
| `run/run.<scope>.log.jsonl` | the ordered run log (`seq`, `kind`, ...), one per process like the port map, truncated at start |

All three are generated output; gitignore them.

### OPC-UA egress face (a simulated machine HMI)

Stands in for where a business action **lands** when that is a machine HMI: an edge device
publishes an alert to MQTT, and the use case's decision is "show the alarm on the machine's HMI via
OPC-UA". With no machine on the bench, the face is an **OPC-UA server whose nodes are driven by the
alerts it receives** — a stand-in for the real MQTT→OPC-UA gateway or PLC write. The worked example
is [`scenarios/cnc_hmi_opcua/`](scenarios/cnc_hmi_opcua/scenario.yaml) (a CNC drift alarm; no real data).

```yaml
hubs:
  cnc_line:
    mqtt: { host: 127.0.0.1, port: 1883 }        # the broker the device publishes alerts to
    opcua_face:
      endpoint: opc.tcp://127.0.0.1:4840/neuroedge/cnc-hmi   # default host is loopback; 0.0.0.0 to share
      namespace: urn:neuroedge:sim:cnc-hmi
      object: CncHmi                             # node ids are ns=2;s=CncHmi.<name>
      topics: [ne-bus/cnc-drift-on-powertrain-shop-for-car-prduction/alert]
      # broker: mqtt://ne-bus:1883               # optional: bridge from a broker other than mqtt:
      # fields: / nodes:                         # optional: rename payload keys / node names
```

| Node | Type | Written from |
|---|---|---|
| `DriftAlarm` | Boolean | `true` on every accepted alert; cleared by an operator Ack |
| `DriftScore` | Double | the payload's `score` (default keys tried: `score`, then `drift_score`) |
| `AlarmText` | String | `message` verbatim, else composed from score, `device_id`, `use_case_id` |
| `LastAlertTs` | DateTime | `timestamp_ns` as UTC, else the receive time (the run log says which) |
| `AlertCount` | UInt32 | alerts accepted since start |
| `Ack` | Boolean | the **only client-writable node** — write `true` to clear `DriftAlarm`; the next alert resets it |

Rules: only the declared topics are bridged, and an alert on any other topic is refused and logged
(`opcua_alert_refused`). An alert with no readable score is logged as `opcua_alert_malformed` and
writes **no** node — it is never shown as 0. Every accepted alert logs `opcua_alert_received`, and
every node write logs `opcua_node_write` (`node`, `node_id`, `value`, `cause: alert|ack`). An operator
acknowledgement logs `opcua_ack`. So a test asserts "the alert reached the HMI" against the run log.
The face is unsecured (security policy None) — it is a bench stand-in, not a production server.

A face whose section has no broker still serves its nodes and logs `opcua_bridge_not_started`. A broker
that is down at start is retried in the background, and `opcua_bridge_not_ready` records that alerts
published before it connects are lost. Without `asyncua` installed, a scenario that declares a face
fails at start with the install line; one that declares none never imports it.

**Watch it.** Connect any OPC-UA client (UaExpert: *Add Server* → *Custom Discovery* →
`opc.tcp://127.0.0.1:4840/neuroedge/cnc-hmi`, security *None*, anonymous) and drag the nodes under
*Objects → CncHmi* into the Data Access view. The run summary's `opcua_faces` and the run log's
`opcua_face_started` give the bound endpoint (useful with port `0`).

**Trigger it** with any MQTT publish to a declared topic, for example with Mosquitto's client:

```bash
mosquitto_pub -h 127.0.0.1 -t ne-bus/cnc-drift-on-powertrain-shop-for-car-prduction/alert \
  -m '{"score": 0.91, "device_id": "sim-cnc-edge-01", "timestamp_ns": 1790000000000000000}'
```

**Without a bundle**, the same face runs from the command line (the first argument, like `--scenario`);
its run log goes to `sim_output/opcua_hmi.log.jsonl`:

```bash
python agentforge_simulator/simulator.py --opcua-hmi --mqtt-host 127.0.0.1 \
    --mqtt-topic ne-bus/cnc-drift-on-powertrain-shop-for-car-prduction/alert \
    --endpoint opc.tcp://127.0.0.1:4840/neuroedge/cnc-hmi --object CncHmi
```

In a `--play-once` run, an alert still in flight when the timeline ends is written before the process
exits, so its entries can follow `run_complete` in the log.

---

## Recommended / candidate extensions

What ships **today** covers the common edge / sensor / enterprise-ops cases. If
your scenario needs more, these are the natural next additions — ask the
`simulator-builder` agent (or `/simulator "add …"`) to wire one in. Each slots
into an existing extension point without disturbing the others.

| Area | Supported today | Strong candidates | Why you'd add it |
|---|---|---|---|
| **Input format** | csv, xls/xlsx, json, images, video | **Parquet** · line-delimited **logs** · **PCAP** · binary/**protobuf** frames | analytics captures (parquet), log replay, packet/telemetry captures |
| **Input generation** | edge_device, sensor, enterprise_ops, cyclic_multichannel profiles; scenario-mode timelines | multi-sensor **fleets** · generated ramp/drift/burst timelines · replay-with-jitter | many devices at once; scripted incident shapes |
| **Transport** | console, SSE, MQTT, webhook, API | **WebSocket** · **Kafka** · **gRPC** · **AMQP** · **CoAP** · **OPC-UA** | dashboards (WS), enterprise streaming (Kafka), industrial/IoT (CoAP/OPC-UA) |
| **Output/log** | jsonl, json, csv, none | **Parquet** · direct **DB** sink · **rotating** files | large-run analytics, persistence, long soaks |
| **Timing** | fixed `--rate`, loop, limit | **timestamp-driven** replay (honour each record's own `ts`) | reproduce real inter-arrival gaps exactly |

The most requested for realistic edge work is usually **timestamp-driven
pacing** (replay at the data's own cadence) and a **WebSocket** transport — say
the word and they go in first.

---

## Layout

```
agentforge_simulator/
├── simulator.py          # entry point — replay sim_input/ over a transport, or --scenario
├── gen_input.py          # generate sample inputs (edge_device / sensor / enterprise_ops / cyclic_multichannel)
├── requirements.txt      # composes the two groups below
├── requirements-transports.txt
├── requirements-inputs.txt
├── neuro_sim/
│   ├── cli.py            # argparse + orchestration (replay flags; --scenario short-circuit)
│   ├── engine.py         # replay loop + pacing
│   ├── loaders.py        # timeseries + media -> payloads
│   ├── transports.py     # console / sse / mqtt / webhook / api
│   ├── writers.py        # json / jsonl / csv / none
│   ├── record.py         # the Record emitted over a transport
│   ├── scenario.py       # scenario.yaml / sim.yaml bundle model + loader
│   ├── scenario_run.py   # one runtime per scenario run: start faces, play timeline, port map
│   ├── simcore.py        # EntityStore, RunLog, VirtualClock, templating
│   ├── stub_server.py    # the one HTTP server per hub: routes, fixtures, /models, /mcp
│   ├── api_stub.py       # path-addressed entry point to stub_server
│   ├── fixture_server.py # role/caller-addressed entry point to stub_server
│   ├── fixtures.py       # fixture manifest + resolution chain (caller, matches)
│   ├── mcp_face.py       # MCP tool-server face (initialize / tools/list / tools/call)
│   ├── model_face.py     # canned model answers keyed by prompt fingerprint
│   ├── opcua_face.py     # OPC-UA machine-HMI face driven by MQTT alerts (--opcua-hmi too)
│   ├── queue_capture.py  # broker capture sink for declared topics
│   └── sql_seed.py       # seed CSVs -> SQLite
├── scenarios/_base/      # the scenario bundle template (copy beside a use case)
├── scenarios/cnc_hmi_opcua/  # worked example: a CNC drift alarm reaching a simulated HMI over OPC-UA
├── examples/             # ready-made sample inputs to copy into sim_input/
├── sim_input/            # you drop / generate inputs here (git-kept, user-owned)
└── sim_output/           # sent-logs land here (git-kept, user-owned)
```

`sim_input/` and `sim_output/` are **yours** — the installer ships only a
`.gitkeep` there, so your data is never overwritten by an update nor deleted by a
clean.

## Extending it

Use the `/simulator` slash command or the `simulator-builder` agent. The design
and extension points (add a format, transport, writer, or generator profile) are
documented in the `simulator-patterns` skill
(`agentic-assets/skills/SOFTWARE/simulator/simulator-patterns.md`).
