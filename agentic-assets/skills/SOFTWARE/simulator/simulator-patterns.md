---
name: simulator-patterns
description: How the NeuroEdge data-source simulator (agentforge_simulator/) is structured and how to run or extend it — input families (timeseries vs media), transports (SSE/MQTT/webhook/API), output writers, and the pacing engine. Use when running the simulator or adding a new input format, transport, or output format.
---

# NeuroEdge Simulator Patterns

The simulator (`agentforge_simulator/`) is a **data-source emitter**: it replays
records from `sim_input/` and streams them over a transport, logging what was
sent to `sim_output/`. It is a standalone runnable tool installed at the project
root — authored in the assets repo under `simulator/`, never hand-edited in the
installed copy.

## When to Activate

- Composing a `python agentforge_simulator/simulator.py …` invocation from a
  plain-language ask ("stream the CSV over MQTT at 10/s").
- Adding a new **input format**, **transport**, or **output writer**.
- Debugging why records aren't emitted or a payload looks wrong.

## Architecture (one responsibility per module)

```
simulator.py            thin entry -> neuro_sim.cli:main (adds its dir to sys.path)
gen_input.py            standalone: synthesize sample inputs into sim_input/
neuro_sim/
  cli.py                argparse; builds ReplayConfig + transport + writer
  engine.py             ReplayEngine.run(): the loop, pacing, loop/limit, Ctrl-C flush
  loaders.py            files -> raw payload dicts (timeseries + media families)
  transports.py         console / sse / mqtt / webhook / api  (open/send/close)
  writers.py            json / jsonl / csv / none              (open/write/close)
  record.py             Record envelope emitted over the wire
```

Data flow: `loaders.iter_payloads(path) → engine wraps each in a Record (stamps
seq + emit ts) → transport.send(record) → writer.write(record)`.

## The Record envelope

Every emission is a `Record(seq, ts, source, kind, payload)`. `seq` is a
run-global 0-based counter; `ts` is the **emit** time (epoch). `payload` is the
loader's dict. JSON/JSONL output keeps `payload` nested; CSV flattens it — and
because a payload very often has its own `ts`, `flatten()` names the envelope
timestamp **`emit_ts`** and prefixes any still-colliding payload key with
`payload_`. Keep that rule if you add envelope fields.

## Generating input (`gen_input.py`)

When there's no real capture to replay, `gen_input.py` synthesizes a timeseries
for a persona — `edge_device`, `sensor`, or `enterprise_ops` — and writes it into
`sim_input/` as csv/json/jsonl. Stdlib-only, seeded, with an `--anomaly-rate` so
the consumer's alarm path is exercised. `GENERATORS` is a plain dict of profile →
generator function; add a profile by adding one function and a `PROFILES` entry.
It is independent of the replay engine: it only writes files the loaders then read.

## Two input families

`loaders.py` splits inputs by extension:

| Family | Extensions | Yields |
|---|---|---|
| `timeseries` | `.csv .xls .xlsx .json` | one payload per row / object (NDJSON and dict-of-columns handled) |
| `media` | images + `.mp4/.avi/.mov/.mkv/.webm/.m4v` | one payload per image / decoded video frame |

Media honours `--media-mode`: `ref` (metadata + file `uri`, small) or `b64`
(metadata + inline `data_b64`, large). CSV output drops the blob to a
`data_b64_len` column.

### Adding an input format

1. Add the extension to `TIMESERIES_EXT`, `IMAGE_EXT`, or `VIDEO_EXT` (this also
   updates `family_of`, `discover`, and the CLI epilog — all derive from these).
2. If it's a new *shape*, add a branch in `load_timeseries`/`load_media` that
   `yield`s payload dicts. Import heavy deps **lazily inside the loader** so an
   unrelated run never imports them (the CSV path must not import OpenCV).
3. Return plain JSON-serialisable dicts — no NaN (swap to `None`), no numpy scalars.

## Transports (`--transport`)

`console` (default, prints JSON lines), `sse`, `mqtt`, `webhook`, `api`. Each is
a `Transport` with `open()/send(record)/close()`. Network libs import lazily.

- **sse** — the simulator *hosts* an HTTP SSE endpoint; connected clients receive
  events. Records emitted with no client connected are dropped (a live source has
  no backlog) — use `--sse-wait` to hold emission until a client attaches, and
  `--loop -1` to keep streaming.
- **mqtt** — publishes to a topic; works across paho-mqtt 1.x/2.x (2.x needs the
  callback-API version, handled in `MqttTransport.open`).
- **webhook** vs **api** — webhook is a fire-and-forget POST; api adds method,
  custom `--api-header 'K: V'` (repeatable), and `--api-bearer`.

### Adding a transport

Subclass `Transport`, implement the three methods, add it to `TRANSPORT_NAMES`
and the `build_transport` factory, and add its CLI flags in its own argument
group in `cli.py`. Lazy-import any new dependency and add it to `requirements.txt`.

## Output writers (`--output-format`)

`jsonl` (streamed, tail-safe — default), `json` (buffered array, written on
close), `csv` (flattened, header grows across records), `none`. Path defaults to
`sim_output/sent.<ext>`; override with `--output-file`.

## Pacing (engine)

`--rate` records/sec (`0` = as fast as possible), `--loop` passes over the inputs
(`-1` = forever), `--limit` cap. The loop flushes the writer and closes the
transport in a `finally`, so Ctrl-C still writes a complete log.

## Gotchas

- **Run from the project root**: `python agentforge_simulator/simulator.py`. The
  entry script puts its own dir on `sys.path`, so the `neuro_sim` package
  resolves; `sim_input`/`sim_output` default to folders beside the package.
- Unsupported files in `sim_input/` are skipped by `discover`, not errored — a
  stray README never aborts a run.
- CSV/xls input needs pandas; video needs opencv-python. Both raise a clear
  `pip install -r requirements.txt` message only when that path is used.
- Don't hand-edit the installed copy; change `simulator/` in the assets repo and
  re-install (`--verify` will flag drift otherwise).
