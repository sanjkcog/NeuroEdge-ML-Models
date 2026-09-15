"""CLI entry point for the marketing video pipeline.

Subcommands:
    fetch   — search Pexels + Pixabay for storyboard scenes, rank, download top N
    render  — generate VO, captions, run ffmpeg pipeline, produce final MP4s
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

from . import approval
from . import contact_sheet
from . import voice as voice_mod
from .assembler import assemble
from .captions import script_caption_lines
from .providers import FootageProvider
from .providers import PexelsProvider
from .providers import PixabayImageProvider
from .providers import PixabayProvider
from .providers import rank_and_dedupe
from .providers import vision_available
from .providers import vision_score
from .schema import FootageManifest
from .schema import SceneSelection
from .schema import Storyboard
from .tts import get_provider as get_tts_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _recorded_demo_paths(generated_dir: Path) -> tuple[Path, Path, Path]:
    script = generated_dir / "recorded_demo_script.md"
    storyboard = generated_dir / "recorded_demo_storyboard.json"
    manifest = generated_dir / "recorded_demo_manifest.json"
    missing = [str(path) for path in (script, storyboard, manifest) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Recorded-demo artifact(s) missing: {', '.join(missing)}")
    return script, storyboard, manifest


def _prepare_recorded_demo(generated_dir: Path, output_dir: Path | None = None) -> tuple[Path, Storyboard]:
    script, storyboard_path, manifest = _recorded_demo_paths(generated_dir)
    storyboard = Storyboard.from_json_file(storyboard_path)
    target_dir = output_dir or Path("data/output/marketing_videos") / storyboard.slug
    target_dir.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(script, target_dir / "script.md")
    shutil.copyfile(storyboard_path, target_dir / "storyboard.json")
    shutil.copyfile(manifest, target_dir / "recorded_demo_manifest.json")
    review = target_dir / "REVIEW.md"
    review.write_text(_recorded_demo_review_text(target_dir, storyboard), encoding="utf-8")
    return target_dir, storyboard


def _recorded_demo_review_text(output_dir: Path, storyboard: Storyboard) -> str:
    return "\n".join(
        [
            "# Recorded Demo Review Gate",
            "",
            f"Storyboard: `{output_dir / 'storyboard.json'}`",
            f"Script: `{output_dir / 'script.md'}`",
            f"Scenes: {len(storyboard.scenes)}",
            f"Duration: {storyboard.total_duration_s:.0f}s",
            "",
            "## Script + Storyboard Checklist",
            "",
            "- [ ] Script reads cleanly when read aloud",
            "- [ ] Captions read on mute",
            "- [ ] Industry context is right for the buyer",
            "- [ ] No competitor names in copy",
            "- [ ] CTA URL is correct",
            "",
            "## Footage Checklist",
            "",
            "- [ ] No identifiable people in endorsement positions",
            "- [ ] No competitor logos visible",
            "- [ ] No off-brand style or color in any clip",
            "- [ ] Footage matches scene tone",
            "",
            "Proceed only after human approval.",
            "",
        ]
    )


def cmd_recorded_demo(args: argparse.Namespace) -> int:
    generated_dir = Path(args.generated_dir)
    output_dir_arg = Path(args.output_dir) if args.output_dir else None
    try:
        output_dir, storyboard = _prepare_recorded_demo(generated_dir, output_dir_arg)
    except FileNotFoundError as exc:
        # The three artifacts are written by the NeuroEdge Studio's code-gen engine. A project without
        # that engine never has them, so this is a named refusal rather than a traceback.
        print(f"Blocked: {exc}")
        print("  recorded-demo consumes artifacts that only the NeuroEdge Studio generates. To make a video")
        print("  from content you write, see agentic-assets/docs/guides/how_to_create_marketing_video.md")
        print("  (validate -> approve -> fetch -> approve -> render).")
        return 2

    print("OK: recorded demo prepared")
    print(f"Output dir: {output_dir}")
    print(f"Script: {output_dir / 'script.md'}")
    print(f"Storyboard: {output_dir / 'storyboard.json'}")
    print(f"Scenes: {len(storyboard.scenes)}")
    print(f"Duration: {storyboard.total_duration_s:.0f}s")

    if args.stage == "prepare":
        print("\n=== READY FOR REVIEW ===")
        print("Review checklist: REVIEW.md")
        print("After approval, run this command with --stage fetch --approved.")
        return 0

    if args.stage == "fetch":
        if not args.approved:
            print("Blocked: pass --approved only after script/storyboard human review.")
            return 2
        return cmd_fetch(
            SimpleNamespace(
                storyboard=str(output_dir / "storyboard.json"),
                output_dir=str(output_dir / "footage"),
                providers=args.providers,
                clips_per_scene=args.clips_per_scene,
            )
        )

    if not args.approved:
        print("Blocked: pass --approved only after footage human review.")
        return 2
    return cmd_render(
        SimpleNamespace(
            storyboard=str(output_dir / "storyboard.json"),
            footage_dir=str(output_dir / "footage"),
            output_dir=str(output_dir),
            tts_provider=args.tts_provider,
            voice=args.voice,
            music=args.music,
        )
    )


def _journey_top(queries: list[str], by_query: dict[str, list]) -> list:
    """One best candidate PER QUERY, in query order — the hook scene's establishing journey.

    Selection happens within each query's own candidates (never the pooled ranking, which lets one
    strong theme crowd out the others), and a clip already chosen for an earlier query is skipped
    so the journey never shows the same shot twice. A query with no candidates simply contributes
    no cut — the journey shortens rather than failing the scene.

    🔴 **Reads the scores the pooled `rank_and_dedupe` pass already computed, never re-ranks**
    (review HIGH, 2026-09-02). `by_query` holds the same candidate objects that pass scored, and a
    second `rank_and_dedupe` per query would re-invoke the vision scorer — a thumbnail fetch plus
    an LLM call per candidate — doubling real API cost on exactly the scene with the most
    candidates. The sort key restates the pooled pass's own final ordering (score, then
    scored-over-unscored).
    """
    picks: list = []
    seen: set[tuple[str, str]] = set()
    for query in queries:
        candidates = sorted(by_query.get(query) or [], key=lambda c: (-c.relevance_score, c.unscored))
        chosen = next((c for c in candidates if (c.provider, c.provider_id) not in seen), None)
        if chosen is not None:
            seen.add((chosen.provider, chosen.provider_id))
            picks.append(chosen)
    return picks


def _build_providers(names: str) -> tuple[list[FootageProvider], list[FootageProvider], list[str]]:
    """Video providers, image providers, and the names that could NOT be constructed (no key)."""
    videos: list[FootageProvider] = []
    images: list[FootageProvider] = []
    skipped: list[str] = []
    for raw in names.split(","):
        name = raw.strip().lower()
        if not name:
            continue
        try:
            if name == "pexels":
                videos.append(PexelsProvider())
            elif name == "pixabay":
                videos.append(PixabayProvider())
                images.append(PixabayImageProvider(image_type="vector"))
                images.append(PixabayImageProvider(image_type="illustration"))
            else:
                logger.warning("Unknown provider: %s", name)
        except RuntimeError as exc:
            # 🔴 Visible in the result, not only in a log line: the first DC fetch skipped Pixabay
            # for want of a key and the only trace was a WARNING nobody read (Studio ADR-0062 F-3).
            logger.warning("Skipping %s: %s", name, exc)
            skipped.append(name)
    return videos, images, skipped


def cmd_fetch(args: argparse.Namespace) -> int:
    storyboard = Storyboard.from_json_file(args.storyboard)
    videos, images, skipped = _build_providers(args.providers)
    # The --providers list read as PREFERENCE order for ranking (owner, 2026-09-02): earlier-listed
    # providers get a small tie-tilting bonus in `rank_and_dedupe`.
    provider_order = [name.strip().lower() for name in args.providers.split(",") if name.strip()]
    use_vision = getattr(args, "vision", True) and vision_available()
    scorer = vision_score if use_vision else None
    logger.info("relevance: %s", "vision pass" if use_vision else "tags only (no model key for a vision pass)")

    wanted = [scene for scene in storyboard.scenes if scene.surface != "screen"]
    if wanted and not videos and not images:
        logger.error("No working footage providers (skipped: %s)", ", ".join(skipped) or "none")
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    selections: list[SceneSelection] = []
    answered: set[str] = set()

    for scene in wanted:
        providers = images if scene.surface == "vector" else videos
        if not providers:
            logger.error("Scene %d needs a %s provider and none is configured", scene.id, scene.surface)
            continue
        scene_dir = output_dir / f"scene_{scene.id:02d}"
        scene_dir.mkdir(parents=True, exist_ok=True)
        pool = []
        by_query: dict[str, list] = {}
        for query in scene.footage_queries:
            for provider in providers:
                try:
                    found = provider.search(query, n=8, orientation=scene.preferred_orientation)
                except Exception as e:
                    logger.warning("Provider %s query '%s' failed: %s", provider.name, query, e)
                    continue
                if found:
                    answered.add(provider.name)
                pool.extend(found)
                by_query.setdefault(query, []).extend(found)

        if not pool:
            logger.error("Scene %d: no candidates from any query", scene.id)
            continue

        intent = f"{scene.caption}. {scene.voiceover[:160]}"
        # The duration a clip actually has to fill (2026-09-02): the scene's slot — or one cut of
        # it for the hook's journey montage. A ~7s clip in a ~26s scene ranked "duration ok"
        # against the flat 4s floor, and its held fade-out tail rendered 19s of black. Provisional
        # durations (pre-retime) are a good-enough proxy; 0.6 leaves room for the pad and retime.
        cuts = len(scene.footage_queries) if scene.beat == "hook" and len(scene.footage_queries) > 1 else 1
        needed_s = max(4.0, float(scene.duration_s) * 0.6 / cuts)
        ranked = rank_and_dedupe(
            pool,
            query=" ".join(scene.footage_queries),
            scorer=scorer,
            intent=intent,
            provider_order=provider_order,
            min_duration_s=needed_s,
        )
        top = ranked[: args.clips_per_scene]
        # The hook is a JOURNEY, not a held shot (2026-09-02): its queries are authored in story
        # order (stamping -> body -> powertrain), so its selection is the best candidate PER
        # QUERY, in that order -- the assembler cuts the hook across them. Pooled ranking would
        # happily pick three stamping clips. A human `pick` collapses back to one clip.
        if scene.beat == "hook" and len(scene.footage_queries) > 1 and not scene.pick:
            journey = _journey_top(scene.footage_queries, by_query)
            if len(journey) > 1:
                top = journey
                logger.info(
                    "Scene %d (hook): journey montage of %d clips, one per query -- clips_per_scene "
                    "does not bound this scene's downloads.",
                    scene.id,
                    len(journey),
                )
        if not top:
            logger.error("Scene %d: no usable candidates after ranking", scene.id)
            continue

        primary = top[0]
        for candidate in top:
            provider = next((p for p in providers if p.name == candidate.provider), None)
            if provider is None:
                continue
            try:
                provider.download(candidate, scene_dir)
            except Exception as e:  # noqa: BLE001 -- one failed alternate must not lose the scene
                logger.warning(
                    "Scene %d: could not download %s/%s: %s", scene.id, candidate.provider, candidate.provider_id, e
                )
        if not primary.local_path:
            logger.error("Scene %d: the primary candidate could not be downloaded", scene.id)
            continue

        selections.append(
            SceneSelection(scene_id=scene.id, primary=primary, alternates=[c for c in top[1:] if c.local_path])
        )
        logger.info(
            "Scene %d: selected %s/%s (score=%.2f%s, %dx%d)",
            scene.id,
            primary.provider,
            primary.provider_id,
            primary.relevance_score,
            " unscored" if primary.unscored else "",
            primary.width,
            primary.height,
        )

    manifest = FootageManifest(slug=storyboard.slug, selections=selections, providers_answered=sorted(answered))
    manifest_path = output_dir / "_selection.json"
    manifest.to_json_file(manifest_path)
    sheet = contact_sheet.write(
        storyboard.model_dump(mode="json"),
        manifest.model_dump(mode="json"),
        output_dir / contact_sheet.CONTACT_SHEET_NAME,
    )
    print(
        f"OK: {len(selections)}/{len(wanted)} scenes selected "
        f"(providers that answered: {', '.join(sorted(answered)) or 'none'})"
    )
    print(f"Manifest: {manifest_path}")
    print(f"Contact sheet: {sheet}")
    return 0 if (len(selections) == len(wanted)) else 1


def cmd_render(args: argparse.Namespace) -> int:
    storyboard = Storyboard.from_json_file(args.storyboard)
    footage = FootageManifest.from_json_file(Path(args.footage_dir) / "_selection.json")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = output_dir / "_work"

    per_scene = getattr(args, "per_scene_voice", False)
    captions = getattr(args, "captions", None) or ("script" if per_scene else "transcribe")
    if captions == "script" and not per_scene:
        print("Blocked: --captions script needs per-scene voice. Drop --single-pass-voice, or use --captions transcribe.")
        return 2
    reference = getattr(args, "voice_reference", None)
    if reference and args.tts_provider != "chatterbox":
        print("Blocked: --voice-reference only applies to --tts-provider chatterbox.")
        return 2
    tts = get_tts_provider(
        args.tts_provider,
        reference=Path(reference) if reference else None,
        exaggeration=getattr(args, "exaggeration", 0.5),
    )

    # Per-scene voice is the CLI default. Programmatic callers that do not ask for it -- the Studio
    # pipeline, which runs its own voice stage, and `recorded-demo` -- keep the single-pass
    # behaviour they were built against.
    speech_s: dict[int, float] = {}
    if per_scene:
        voiceover, storyboard, speech_s = _per_scene_voiceover(
            storyboard,
            tts,
            voice=args.voice,
            say_as=_load_say_as(getattr(args, "say_as", None)),
            pad_s=getattr(args, "pad_s", 0.6),
            work_dir=work_dir,
        )
    else:
        voiceover = tts.synthesize(
            _vo_text_from_storyboard(storyboard),
            out_path=work_dir / f"voiceover_{tts.name}.wav",
            voice=args.voice,
        )

    screen_dir = getattr(args, "screen_dir", None)
    music = Path(args.music) if args.music else None
    outputs = assemble(
        storyboard,
        footage,
        voiceover=voiceover,
        music=music,
        output_dir=output_dir,
        screen_dir=Path(screen_dir) if screen_dir else None,
        caption_lines=(
            script_caption_lines([scene.model_dump(mode="json") for scene in storyboard.scenes], speech_s)
            if captions == "script"
            else None
        ),
    )

    print("OK: render complete")
    for aspect, path in outputs.items():
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"  {aspect}: {path} ({size_mb:.1f} MB)")
    return 0
def _vo_text_from_storyboard(storyboard: Storyboard) -> str:
    return "\n\n".join(scene.voiceover for scene in storyboard.scenes if scene.voiceover)


class CliUsageError(ValueError):
    """Input the user can fix. `main` prints it as a named refusal instead of a traceback."""


def _load_say_as(path: str | None) -> dict[str, str]:
    """The pronunciation map: JSON, or YAML when PyYAML is installed. No file, no substitutions."""
    if not path:
        return {}
    file = Path(path)
    if not file.is_file():
        raise CliUsageError(f"--say-as {file}: no such file")
    text = file.read_text(encoding="utf-8")
    if file.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # noqa: PLC0415 -- optional; JSON needs nothing
        except ImportError as exc:
            raise CliUsageError(f"--say-as {file.name}: YAML needs PyYAML (pip install pyyaml), or use .json") from exc
        data = yaml.safe_load(text) or {}
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CliUsageError(f"--say-as {file.name}: not valid JSON ({exc})") from exc
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise CliUsageError(f"--say-as {file.name}: expected a flat mapping of id -> spoken phrase")
    return data


def _per_scene_voiceover(
    storyboard: Storyboard,
    tts,
    *,
    voice: str | None,
    say_as: dict[str, str],
    pad_s: float,
    work_dir: Path,
) -> tuple[Path, Storyboard, dict[int, float]]:
    """One WAV per scene, and the storyboard re-timed to the measured audio (see ``voice.py``).

    The re-timed storyboard goes to ``_work/storyboard.timed.json``, never over the authored file:
    the authored file is what the script review approved, and a render must not rewrite it.
    ``say_as`` changes only what the voice hears -- captions keep the literal text.
    """
    timed = storyboard.model_dump(mode="json")
    spoken = [dict(scene, voiceover=voice_mod.apply_say_as(scene.get("voiceover") or "", say_as)) for scene in timed["scenes"]]

    def synth(text: str, out_path: Path) -> Path:
        return tts.synthesize(text, out_path=out_path, voice=voice)

    audio = voice_mod.synthesize_scenes(spoken, synth, work_dir / "voice")
    voice_mod.retime(timed, audio, pad_s)
    joined = voice_mod.join_with_pads(audio, timed, work_dir / f"voiceover_{tts.name}_per_scene.wav")
    result = Storyboard.model_validate(timed)
    result.to_json_file(work_dir / "storyboard.timed.json")
    return joined, result, {item.scene_id: item.duration_s for item in audio}


def cmd_validate(args: argparse.Namespace) -> int:
    """Check a storyboard before anything is spent on it: 0 valid, 1 invalid or incomplete, 2 missing."""
    path = Path(args.storyboard)
    if not path.is_file():
        print(f"Blocked: no storyboard at {path}")
        return 2
    try:
        storyboard = Storyboard.from_json_file(path)
    except ValueError as exc:  # pydantic's ValidationError and JSONDecodeError are both ValueErrors
        print(f"INVALID: {path}")
        print(str(exc))
        return 1
    print(
        f"VALID: {storyboard.slug} | {len(storyboard.scenes)} scenes | {storyboard.total_duration_s:g}s"
        f" | aspects {', '.join(storyboard.aspect_ratios)}"
    )
    for scene in storyboard.scenes:
        print(
            f"  {scene.id:>2} {scene.beat:<9} {scene.start_s:7.1f} +{scene.duration_s:5.1f}"
            f"  {scene.surface:<8} {scene.caption[:48]}"
        )
    problems = 0
    if "9x16" in storyboard.aspect_ratios:
        print("  WARNING: 9x16 passes validation but is never rendered; only 16x9 and 1x1 are produced.")
    screen_dir = Path(args.screen_dir) if getattr(args, "screen_dir", None) else None
    if screen_dir is not None:
        for scene in storyboard.scenes:
            clip = screen_dir / f"scene_{scene.id:02d}.webm"
            if scene.surface == "screen" and not clip.is_file():
                print(f"  MISSING: scene {scene.id} is a screen scene; record it and save it as {clip}")
                problems += 1
    return 1 if problems else 0


def cmd_approve(args: argparse.Namespace) -> int:
    """Record a person's approval: the script review (gates fetch) or the footage review (gates render)."""
    storyboard_path = Path(args.storyboard)
    if not storyboard_path.is_file():
        print(f"Blocked: no storyboard at {storyboard_path}")
        return 2
    try:
        Storyboard.from_json_file(storyboard_path)
    except ValueError as exc:
        print("Blocked: the storyboard is invalid, so it cannot be approved. Run validate first.")
        print(str(exc))
        return 2
    footage_dir = Path(args.footage_dir) if args.footage_dir else None
    if args.stage == "footage":
        if footage_dir is None:
            print("Blocked: --stage footage needs --footage-dir")
            return 2
        if not (footage_dir / approval.SELECTION_NAME).is_file():
            print(f"Blocked: nothing fetched yet -- no {approval.SELECTION_NAME} in {footage_dir}")
            return 2
    entry = approval.approve(args.stage, storyboard_path, footage_dir)
    print(f"APPROVED: {args.stage} review at {entry['approved_at']} -> {approval.stamp_path(storyboard_path)}")
    return 0



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="neuroedge_marketing")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser("validate", help="Check a storyboard before spending anything on it")
    p_validate.add_argument("--storyboard", required=True)
    p_validate.add_argument(
        "--screen-dir", default=None, help="Also check that each screen scene's scene_NN.webm is in this folder"
    )
    p_validate.set_defaults(func=cmd_validate)

    p_approve = sub.add_parser(
        "approve", help="Record a human review: --stage script (gates fetch) or --stage footage (gates render)"
    )
    p_approve.add_argument("--storyboard", required=True)
    p_approve.add_argument("--stage", choices=list(approval.GATES), required=True)
    p_approve.add_argument("--footage-dir", default=None, help="Required for --stage footage")
    p_approve.set_defaults(func=cmd_approve)

    p_fetch = sub.add_parser("fetch", help="Fetch footage for an approved storyboard")
    p_fetch.add_argument("--storyboard", required=True)
    p_fetch.add_argument("--output-dir", required=True)
    p_fetch.add_argument("--providers", default="pexels,pixabay")
    p_fetch.add_argument("--clips-per-scene", type=int, default=3)
    p_fetch.add_argument(
        "--no-vision", dest="vision", action="store_false", help="Rank by tags only; skip the vision pass"
    )
    p_fetch.add_argument(
        "--no-gate", dest="gate", action="store_false", help="Skip the script-approval check (the review is still yours)"
    )
    p_fetch.set_defaults(func=cmd_fetch, vision=True, gate=True)

    p_render = sub.add_parser("render", help="Render the final video from approved footage")
    p_render.add_argument("--storyboard", required=True)
    p_render.add_argument("--footage-dir", required=True)
    p_render.add_argument("--output-dir", required=True)
    p_render.add_argument("--tts-provider", choices=["openai", "elevenlabs", "chatterbox"], default="openai")
    p_render.add_argument("--voice", default=None)
    p_render.add_argument("--music", default=None, help="Path to MP3 background music")
    p_render.add_argument(
        "--screen-dir", default=None, help="Folder holding screen scenes' scene_NN.webm (default: --footage-dir)"
    )
    p_render.add_argument(
        "--single-pass-voice",
        dest="per_scene_voice",
        action="store_false",
        help="Synthesize the whole script in one call instead of per scene (no re-timing)",
    )
    p_render.add_argument("--voice-reference", default=None, help="Chatterbox only: a ~30 s WAV of the voice to speak in")
    p_render.add_argument("--exaggeration", type=float, default=0.5, help="Chatterbox only: expressiveness, 0-1")
    p_render.add_argument("--say-as", default=None, help="JSON (or YAML) map of id -> how the voice should say it")
    p_render.add_argument("--pad-s", type=float, default=0.6, help="Silence after each scene's voice-over, seconds")
    p_render.add_argument(
        "--captions",
        choices=["script", "transcribe"],
        default=None,
        help="script: the approved voice-over text (default with per-scene voice); transcribe: faster-whisper",
    )
    p_render.add_argument(
        "--no-gate", dest="gate", action="store_false", help="Skip the approval checks (the reviews are still yours)"
    )
    p_render.set_defaults(func=cmd_render, per_scene_voice=True, gate=True)

    p_recorded = sub.add_parser(
        "recorded-demo",
        help="NeuroEdge Studio only: review-gated steps over artifacts the Studio's code-gen engine writes",
    )
    p_recorded.add_argument("--generated-dir", required=True)
    p_recorded.add_argument("--output-dir", default=None)
    p_recorded.add_argument("--stage", choices=["prepare", "fetch", "render"], default="prepare")
    p_recorded.add_argument("--approved", action="store_true", help="Assert the required human review gate passed")
    p_recorded.add_argument("--providers", default="pexels,pixabay")
    p_recorded.add_argument("--clips-per-scene", type=int, default=3)
    p_recorded.add_argument("--tts-provider", choices=["openai", "elevenlabs", "chatterbox"], default="openai")
    p_recorded.add_argument("--voice", default=None)
    p_recorded.add_argument("--music", default=None, help="Path to MP3 background music")
    p_recorded.set_defaults(func=cmd_recorded_demo)

    args = parser.parse_args(argv)
    if getattr(args, "gate", False):
        footage_dir = Path(args.footage_dir) if args.cmd == "render" else None
        reason = approval.check(args.cmd, Path(args.storyboard), footage_dir)
        if reason:
            print(f"Blocked: {reason}")
            print("  (--no-gate skips this check; the review is still yours to do.)")
            return 2
    if args.cmd == "render" and not args.screen_dir:
        args.screen_dir = args.footage_dir
    try:
        return args.func(args)
    except CliUsageError as exc:
        print(f"Blocked: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
