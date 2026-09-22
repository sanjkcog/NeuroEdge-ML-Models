"""Command-line interface for the NeuroEdge simulator.

    python simulator.py --transport console
    python simulator.py --transport sse --sse-port 8080 --rate 5
    python simulator.py --transport mqtt --mqtt-host localhost --mqtt-topic edge/telemetry
    python simulator.py --transport webhook --webhook-url https://example.com/hook
    python simulator.py --transport api --api-url https://api.example.com/ingest \
        --api-method POST --api-bearer $TOKEN --api-header 'X-Source: sim'
    python simulator.py --scenario path/to/scenario.yaml
    python simulator.py --opcua-hmi --mqtt-topic plant/line1/alert

Inputs are read from ``sim_input/`` (csv, xls/xlsx, json, images, video) and a
log of what was sent is written to ``sim_output/`` as json/jsonl/csv.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

from .engine import ReplayConfig, ReplayEngine
from .loaders import IMAGE_EXT, VIDEO_EXT, TIMESERIES_EXT
from .transports import TRANSPORT_NAMES, TransportError, build_transport
from .writers import build_writer, default_output_path

# Default I/O folders live next to the simulator, i.e. agentforge_simulator/.
_ROOT = Path(__file__).resolve().parent.parent


def _force_utf8_stdio() -> None:
    """Make stdout/stderr UTF-8 so non-ASCII payloads (console transport prints
    JSON with ensure_ascii=False), error messages, and --help don't raise
    UnicodeEncodeError on a legacy console (e.g. Windows cp1252). No-op on streams
    without reconfigure(). Mirrors install.py's helper of the same name."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="simulator",
        description="NeuroEdge data-source simulator — replay sim_input/ over a transport.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog=(
            "input families: timeseries "
            + "/".join(sorted(e.lstrip(".") for e in TIMESERIES_EXT))
            + " | media "
            + "/".join(sorted(e.lstrip(".") for e in (IMAGE_EXT | VIDEO_EXT)))
        ),
    )

    io = p.add_argument_group("input / output")
    io.add_argument("--input-dir", type=Path, default=_ROOT / "sim_input", help="folder to read input files from")
    io.add_argument("--input-glob", default="*", help="glob within --input-dir (e.g. '*.csv')")
    io.add_argument(
        "--media-mode",
        choices=("ref", "b64"),
        default="ref",
        help="media payload: file reference (ref) or inline base64 (b64)",
    )
    io.add_argument(
        "--output-format",
        choices=("json", "jsonl", "csv", "none"),
        default="jsonl",
        help="format of the sent-log written to --output-dir",
    )
    io.add_argument("--output-dir", type=Path, default=_ROOT / "sim_output", help="folder to write the sent-log into")
    io.add_argument(
        "--output-file",
        type=Path,
        default=None,
        help="explicit sent-log path (overrides --output-dir/--output-format naming)",
    )

    pace = p.add_argument_group("pacing")
    pace.add_argument("--rate", type=float, default=1.0, help="records per second (0 = as fast as possible)")
    pace.add_argument("--loop", type=int, default=1, help="number of passes over the inputs (-1 = forever)")
    pace.add_argument("--limit", type=int, default=0, help="stop after N records (0 = no cap)")

    tr = p.add_argument_group("transport")
    tr.add_argument("--transport", choices=TRANSPORT_NAMES, default="console", help="where to emit records")
    tr.add_argument("--http-timeout", type=float, default=10.0, help="timeout (s) for webhook/api requests")

    sse = p.add_argument_group("sse (transport=sse)")
    sse.add_argument("--sse-host", default="127.0.0.1")
    sse.add_argument("--sse-port", type=int, default=8080)
    sse.add_argument("--sse-path", default="/events")
    sse.add_argument("--sse-wait", action="store_true", help="hold emission until at least one client connects")

    mqtt = p.add_argument_group("mqtt (transport=mqtt)")
    mqtt.add_argument("--mqtt-host", default="127.0.0.1")
    mqtt.add_argument("--mqtt-port", type=int, default=1883)
    mqtt.add_argument("--mqtt-topic", default="neuroedge/sim")
    mqtt.add_argument("--mqtt-qos", type=int, choices=(0, 1, 2), default=0)
    mqtt.add_argument("--mqtt-username", default=None)
    mqtt.add_argument("--mqtt-password", default=None)
    mqtt.add_argument(
        "--mqtt-client-id",
        default=None,
        help="MQTT client id; when unset, a per-run unique neuro-sim-<pid> "
        "is used so concurrent simulators don't evict each other's "
        "broker session",
    )

    web = p.add_argument_group("webhook (transport=webhook)")
    web.add_argument("--webhook-url", default=None)

    api = p.add_argument_group("api (transport=api)")
    api.add_argument("--api-url", default=None)
    api.add_argument("--api-method", default="POST")
    api.add_argument("--api-bearer", default=None, help="bearer token for Authorization header")
    api.add_argument("--api-header", action="append", default=None, help="extra header 'Key: Value' (repeatable)")

    return p


def _run_scenario(manifest: Path, hub: str | None, serve: bool) -> dict:
    """One scenario run, with the OPC-UA faces it declares served beside it (ADR-0029).

    🔴 **Composed here, not inside ``ScenarioRunner``, on purpose.** Installed projects keep a local
    ``scenario_run.py`` that an update must not overwrite, so a face wired into the runner would
    reach none of them. Composed around the runner's public surface (``bundle``, ``scope``,
    ``run_log``, ``run``) it works unchanged over any runner that keeps that surface.

    The faces start first so an alert the timeline publishes at offset 0 already has an HMI, and
    they stop in ``finally`` so Ctrl-C releases the OPC-UA port as it does the stub ports.
    """
    from .opcua_face import start_opcua_faces  # pylint: disable=import-outside-toplevel
    from .scenario import load_scenario  # pylint: disable=import-outside-toplevel
    from .scenario_run import ScenarioRunner  # pylint: disable=import-outside-toplevel

    runner = ScenarioRunner(load_scenario(Path(manifest)), hub=hub)
    faces = start_opcua_faces(runner.bundle, scope=runner.scope, run_log=runner.run_log)
    endpoints = faces.endpoints()
    try:
        summary = runner.run(serve=serve)
    finally:
        faces.stop()
    if endpoints:
        # Only when a face exists, so a scenario without one prints exactly the summary it always did.
        summary["opcua_faces"] = endpoints
    return summary


def _run_opcua_hmi(argv: list[str]) -> int:
    """``--opcua-hmi``: the OPC-UA egress face alone, bridged from one broker -- no bundle needed.

    The quickest way to put a simulated HMI in front of a device that already publishes alerts.
    Same face, same run-log entries as scenario mode; the log goes to ``sim_output/``.
    """
    # pylint: disable=import-outside-toplevel  # asyncua/paho stay lazy for every other mode
    from .opcua_face import DEFAULT_ENDPOINT
    from .opcua_face import DEFAULT_NAMESPACE
    from .opcua_face import DEFAULT_OBJECT
    from .opcua_face import MqttBridge
    from .opcua_face import OpcUaFace
    from .opcua_face import load_opcua_face_config
    from .simcore import RunLog

    parser = argparse.ArgumentParser(
        prog="simulator --opcua-hmi",
        description="Serve a simulated machine HMI over OPC-UA, driven by alerts from an MQTT broker.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--opcua-hmi", action="store_true", required=True, help=argparse.SUPPRESS)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="OPC-UA endpoint the HMI serves on")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help="namespace URI of the HMI nodes")
    parser.add_argument("--object", default=DEFAULT_OBJECT, help="object the nodes hang under (node id prefix)")
    parser.add_argument("--mqtt-host", default="127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument(
        "--mqtt-topic", action="append", required=True, help="alert topic to bridge (repeatable; no wildcards)"
    )
    parser.add_argument(
        "--run-log", type=Path, default=_ROOT / "sim_output" / "opcua_hmi.log.jsonl", help="run log (truncated)"
    )
    args = parser.parse_args(argv)
    try:
        config = load_opcua_face_config(
            {"endpoint": args.endpoint, "namespace": args.namespace, "object": args.object, "topics": args.mqtt_topic},
            where="--opcua-hmi",
        )
        run_log = RunLog(args.run_log)
        face = OpcUaFace(config, name="opcua_hmi", run_log=run_log)
        endpoint = face.start()
    except Exception as exc:  # noqa: BLE001 - the CLI boundary reports, it does not trace
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    bridge = MqttBridge(face, args.mqtt_host, args.mqtt_port, run_log=run_log)
    try:
        bridge.start()
        print(f"[opcua] HMI at {endpoint}  (Ctrl-C to stop)")
        for role in config.nodes:
            print(f"[opcua]   {face.node_id(role)}")
        print(f"[opcua] bridging {list(config.topics)} from mqtt://{args.mqtt_host}:{args.mqtt_port}")
        print(f"[opcua] run log: {args.run_log}")
        threading.Event().wait()
    except KeyboardInterrupt:
        print("opcua hmi stopped", file=sys.stderr)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    finally:
        bridge.stop()
        face.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    # `--scenario` short-circuits the replay engine entirely (simulator-mvp Group B, design D-2):
    # a scenario run is one runtime hosting the bundle's declared adapters, not a file replay.
    # Handled before the replay parser so the two argument sets never entangle.
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "--scenario":
        scenario_parser = argparse.ArgumentParser(prog="simulator --scenario")
        scenario_parser.add_argument(
            "--scenario", type=Path, required=True, help="path to a scenario.yaml bundle manifest"
        )
        scenario_parser.add_argument(
            "--hub", default=None, help="run only this hub's adapters (plus shared) -- debug mode"
        )
        scenario_parser.add_argument(
            "--play-once",
            action="store_true",
            help="exit when the timeline finishes instead of serving until stopped (batch/test mode)",
        )
        scenario_args = scenario_parser.parse_args(argv)

        try:
            # Serve-until-stopped is the DEFAULT (review C-2): the orchestrator launches this
            # process for the life of a simulated run, and agents call the stubs long after the
            # timeline's last row has played. Ctrl-C (or the orchestrator's terminate) ends it.
            summary = _run_scenario(scenario_args.scenario, hub=scenario_args.hub, serve=not scenario_args.play_once)
        except KeyboardInterrupt:
            print("scenario stopped", file=sys.stderr)
            return 0
        except Exception as exc:  # noqa: BLE001 - the CLI boundary reports, it does not trace
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(summary, indent=2))
        return 0
    # `--opcua-hmi` short-circuits the same way, and for the same reason: it serves, it does not replay.
    if argv and argv[0] == "--opcua-hmi":
        return _run_opcua_hmi(argv)

    args = build_parser().parse_args(argv)

    if args.limit < 0:
        print("ERROR: --limit must be >= 0 (0 = no cap)", file=sys.stderr)
        return 2
    if args.loop == 0 or args.loop < -1:
        # -1 is the only valid non-positive value (forever); 0 and other negatives
        # would otherwise slip through and behave like a single pass.
        print("ERROR: --loop must be a positive count, or -1 for forever", file=sys.stderr)
        return 2
    # json/csv writers buffer the whole run in memory and only flush on close;
    # pairing them with an unbounded run would grow memory without ever writing.
    if args.loop == -1 and args.output_format in ("json", "csv"):
        print(
            f"WARNING: --output-format {args.output_format} buffers all records "
            "in memory and only writes on exit; with --loop -1 (forever) that grows "
            "unbounded. Use --output-format jsonl (streamed) for endless runs.",
            file=sys.stderr,
        )

    if args.output_file is not None:
        out_path = args.output_file
    else:
        out_path = default_output_path(args.output_dir, args.output_format)

    config = ReplayConfig(
        input_dir=args.input_dir,
        input_glob=args.input_glob,
        media_mode=args.media_mode,
        rate=args.rate,
        loop=args.loop,
        limit=args.limit,
    )

    try:
        transport = build_transport(args)
        writer = build_writer(args.output_format, out_path)
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        f"[sim] input={config.input_dir} glob={config.input_glob!r} "
        f"transport={args.transport} output={args.output_format} "
        f"rate={config.rate}/s loop={config.loop}"
    )

    engine = ReplayEngine(config, transport, writer)
    try:
        sent = engine.run()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except TransportError as exc:
        # Broker unreachable / SSE port in use / webhook/api HTTP error — the engine
        # already labelled it with the transport name, so print it as-is.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        # A non-transport I/O error (writer/loader): disk full or bad permissions on
        # sim_output/ or sim_input/. Point at the paths, not the transport.
        print(f"ERROR: I/O error (check --input-dir / --output-dir): {exc}", file=sys.stderr)
        return 1

    if args.output_format != "none":
        print(f"[sim] {sent} record(s) sent - log written to {out_path}")
    else:
        print(f"[sim] {sent} record(s) sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
