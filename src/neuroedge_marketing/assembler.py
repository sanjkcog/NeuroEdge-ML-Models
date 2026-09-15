"""ffmpeg assembly — trim/scale clips, concat, mix audio, burn captions, brand overlay.

Studio ADR-0062 D-4: a scene's picture is one of three things -- a trimmed stock clip, a screen recording
held on its last frame, or a still given a slow move -- and the concat/audio/caption half does not
care which. Title cards open and close the video when no logo file exists (none ever has).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from .schema import FootageManifest
from .schema import Scene
from .schema import Storyboard

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 600

#: Where ffmpeg is, when it is not on PATH. Either the binary or its directory.
FFMPEG_BIN_ENV = "FFMPEG_BIN"

CARD_BG = "#0b1220"
CARD_FG = "#e6edf3"
CARD_ACCENT = "#2dd4bf"


class FFmpegError(RuntimeError):
    pass


#: 🔴 **Every audio stream this module writes is pinned to this shape, and that is not tidiness.**
#: The final render joins the title cards to the body with the concat DEMUXER, which copies streams
#: and requires them to be parameter-identical. `loudnorm` (in :func:`mix_audio`) resamples to
#: 192 kHz internally and, with no ``-ar``, hands that on -- the AAC encoder caps it at its own
#: 96 kHz maximum. So the body came out at 96 kHz against cards built at 48 kHz, the audio timebases
#: disagreed 2:1, and DTS went backwards at the boundary ("previous: 19485067, current: 9899648" --
#: almost exactly half). ffmpeg exited 69 after printing a full page of encoder statistics and the
#: word "Conversion failed!", naming neither the sample rate nor the file. Measured 2026-08-23.
#:
#: Stereo rather than mono because a music bed makes the mix stereo and the cards would then differ
#: in channel COUNT instead -- the same failure wearing a different hat.
AUDIO_RATE = "48000"
AUDIO_CHANNELS = "2"
#: The arguments that pin it. Spread into every call that encodes audio.
AUDIO_ARGS = ["-ar", AUDIO_RATE, "-ac", AUDIO_CHANNELS]


def resolve_ffmpeg(tool: str = "ffmpeg") -> str | None:
    """The absolute path to ``ffmpeg``/``ffprobe``, or ``None`` if it cannot be found.

    Looks at :data:`FFMPEG_BIN_ENV` first -- accepting either the binary itself or the directory
    holding it, because both are what a person means by "where ffmpeg is" -- then falls back to
    PATH. Returns ``None`` rather than raising: the caller that wants a refusal is
    :func:`ensure_ffmpeg`, and the one that wants a command name is :func:`_run`.
    """
    configured = os.environ.get(FFMPEG_BIN_ENV, "").strip().strip('"')
    if configured:
        candidate = Path(configured)
        # A directory is the more natural thing to configure; a full path to one binary still has
        # to yield the OTHER one, so the sibling is derived rather than demanded twice.
        if candidate.is_dir():
            found = shutil.which(tool, path=str(candidate))
            if found:
                return found
        else:
            sibling = candidate.parent / f"{tool}{candidate.suffix}"
            if sibling.is_file():
                return str(sibling)
            if candidate.is_file() and candidate.stem.lower() == tool:
                return str(candidate)
    return shutil.which(tool)


def _run(args: list[str], *, timeout_s: int = DEFAULT_TIMEOUT_S) -> None:
    # 🔴 argv[0] is rewritten to the RESOLVED binary. Every call site below passes the bare name
    # `"ffmpeg"`, and `ensure_ffmpeg` returned a path that nothing used -- so resolution and
    # invocation disagreed, and configuring a location could not have helped even once it was
    # possible to. Substituted in one place rather than at nine call sites.
    if args and args[0] in {"ffmpeg", "ffprobe"}:
        resolved = resolve_ffmpeg(args[0])
        if resolved:
            args = [resolved, *args[1:]]
    logger.info("ffmpeg: %s", " ".join(args))
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as e:
        raise FFmpegError(f"ffmpeg timed out after {timeout_s}s: {' '.join(args[:6])}...") from e
    if result.returncode != 0:
        raise FFmpegError(f"ffmpeg failed (exit {result.returncode}):\n{result.stderr[-2000:]}")


def _audio_shape(path: Path) -> tuple[str, str, str] | None:
    """``(codec, sample_rate, channels)`` for a file's first audio stream, or ``None``."""
    probe = resolve_ffmpeg("ffprobe")
    if not probe:
        return None
    result = subprocess.run(
        [
            probe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    parts = [f.strip() for f in result.stdout.strip().split(",") if f.strip()]
    return (parts[0], parts[1], parts[2]) if len(parts) >= 3 else None


def _refuse_mismatched_audio(paths: list[Path]) -> None:
    """Refuse a concat whose inputs do not share one audio shape, saying which one differs.

    🔴 **The concat demuxer COPIES streams, so a parameter difference is not a warning.** It
    produces a file whose timestamps go backwards at the join, and ffmpeg reports that by printing a
    page of encoder statistics ending in "Conversion failed!" -- no file name, no parameter, and no
    hint that two inputs disagreed at all. This turns that into one sentence naming the file and the
    difference. Advisory by design: an unavailable ffprobe skips the check rather than blocking a
    render that would have worked.
    """
    shapes = [(path, _audio_shape(path)) for path in paths]
    known = [(path, shape) for path, shape in shapes if shape is not None]
    if len(known) < 2:
        return
    first_path, first = known[0]
    for path, shape in known[1:]:
        if shape != first:
            raise FFmpegError(
                f"Cannot join these clips: {path.name} has audio {shape[0]} "
                f"{shape[1]}Hz/{shape[2]}ch but {first_path.name} has {first[0]} "
                f"{first[1]}Hz/{first[2]}ch. Every clip in one render must share an audio shape "
                f"({AUDIO_RATE}Hz/{AUDIO_CHANNELS}ch) -- re-run the assemble step so they are all "
                "encoded together."
            )


def _ffmpeg_filter_path(p: Path) -> str:
    """Quote and escape a path for use as a value inside an ffmpeg filtergraph.

    🔴 **The result IS single-quoted, and the docstring here used to say the opposite** — "we must
    NOT wrap the result in single quotes — quotes would be passed as literal characters into the
    filter argument and break path resolution". That was wrong, and it cost a render (2026-08-22),
    which failed with::

        Unable to parse "original_size" option value
        "/SanjeevE/NeuroEdge-.../captions_16x9.ass" as image size

    That is a Windows drive letter being read as a filter option: `subtitles=` splits its value on
    `:`, so `C:/x.ass` becomes filename `C` followed by an option named after the rest of the path.

    The quotes are consumed by ffmpeg's own **filtergraph parser**, not by a shell — argv is passed
    to `subprocess` directly, so no shell ever sees them — and they are exactly what stops that
    split. Backslash-escaping alone does not, because the value is unescaped once by the filtergraph
    and then parsed again by the filter.

    🔴 Measured rather than reasoned: six candidate forms were run against the real captions file,
    and against directories containing a space and a comma. Unquoted-and-escaped (what shipped)
    fails every time; quoted-and-escaped passes every time. The escaping is kept — harmless inside
    quotes, and it is what keeps the value safe if a caller ever concatenates it into a longer
    filtergraph, where an unescaped comma would end the filter.

    The one shape still unhandled is a directory containing an apostrophe: it needs quote-splicing
    that ffmpeg accepts only in some positions. Left alone deliberately — the failure is loud
    ("Unable to open"), and inventing a fix with no test to prove it is how the wrong claim above
    came to be written in the first place.
    """
    s = str(p).replace("\\", "/")
    s = s.replace(":", r"\:")
    s = s.replace(" ", r"\ ")
    s = s.replace("'", r"\'")
    s = s.replace(",", r"\,")
    return f"'{s}'"


def ensure_ffmpeg() -> str:
    """The ffmpeg this run will use, or a refusal naming both places that were looked at."""
    path = resolve_ffmpeg("ffmpeg")
    if not path:
        raise FFmpegError(
            "ffmpeg not found. Install it from https://ffmpeg.org, then either put its `bin` "
            f"directory on PATH or set {FFMPEG_BIN_ENV} to that directory (or to ffmpeg itself). "
            "If the Builder API is already running, restart it: it reads PATH once, at start."
        )
    return path


_VIDEO_CODEC = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p"]


def trim_clip(src: Path, *, duration_s: float, out_path: Path, width: int = 1920, height: int = 1080) -> Path:
    """Trim/scale a source clip to exactly duration_s, scaled+cropped to target aspect.

    🔴 **A clip shorter than the scene LOOPS, reversing this function's earlier hold-last-frame
    choice — and the reversal is measured, not aesthetic** (2026-09-02). The hold was chosen on
    the theory that "a frozen final frame reads as a pause, a loop reads as a glitch". Then a real
    render put a ~7s stock clip into a ~26s scene, and the clip — like much stock footage — ends
    on a fade-to-black: the held final frame was BLACK, and the video showed nineteen seconds of
    nothing with captions over it (second-by-second luma: 110 108 … 105 16 16 16 …). A loop's cut
    is a visible seam once per source length; a held fade-out is a dead screen for the whole
    remainder. When the source is at least as long as the scene, ``-stream_loop`` never wraps and
    the output is identical to before.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps=25"
    _run(
        [
            "ffmpeg",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(src),
            "-t",
            f"{duration_s:.3f}",
            "-vf",
            vf,
            "-an",
            *_VIDEO_CODEC,
            str(out_path),
        ]
    )
    return out_path


def fit_capture(src: Path, *, duration_s: float, out_path: Path, width: int = 1920, height: int = 1080) -> Path:
    """A screen recording: scaled to FIT (never cropped -- it is a UI), padded, held on its last frame."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={CARD_BG},setsar=1,fps=25,"
        f"tpad=stop_mode=clone:stop_duration={duration_s:.3f}"
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-t",
            f"{duration_s:.3f}",
            "-vf",
            vf,
            "-an",
            *_VIDEO_CODEC,
            str(out_path),
        ]
    )
    return out_path


def still_to_motion(src: Path, *, duration_s: float, out_path: Path, width: int = 1920, height: int = 1080) -> Path:
    """A still image with a slow push-in (Ken Burns), so a vector scene is not a frozen slide."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, int(round(duration_s * 25)))
    vf = (
        f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
        f"crop={width * 2}:{height * 2},"
        f"zoompan=z='min(zoom+0.0008,1.12)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps=25,"
        "setsar=1"
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(src),
            "-t",
            f"{duration_s:.3f}",
            "-vf",
            vf,
            "-an",
            *_VIDEO_CODEC,
            str(out_path),
        ]
    )
    return out_path


#: Where a usable font lives, per platform. 🔴 **`font=Sans` is not portable and does not fail
#: politely.** It routes through fontconfig, which Windows ffmpeg builds ship without: the filter
#: printed "Fontconfig error: Cannot load default config file" and then died with 0xC0000005 -- an
#: access violation, not an error code with a message. `title_card` caught that and rendered a BLANK
#: card, so the finished video opened and closed on empty screens and only a warning in the log said
#: why. Measured 2026-08-23. An explicit `fontfile=` needs no fontconfig anywhere.
FONT_FILE_ENV = "DEMO_FONT_FILE"
_FONT_CANDIDATES = (
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


def resolve_font() -> str | None:
    """An absolute path to a TrueType font, or ``None`` to let ffmpeg try ``font=Sans``."""
    configured = os.environ.get(FONT_FILE_ENV, "").strip().strip('"')
    if configured and Path(configured).is_file():
        return configured
    for candidate in _FONT_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def title_card(
    *,
    title: str,
    subtitle: str,
    duration_s: float,
    out_path: Path,
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """A plain branded card with text. Falls back to a blank card if this ffmpeg has no text support."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _text(value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\u2019").replace(":", "\\:").replace("%", "\\%")

    # A resolved file beats a fontconfig name everywhere; the name stays as the last resort so a
    # platform with fontconfig and no font at any path we know still gets text.
    font = resolve_font()
    # 🔴 `_ffmpeg_filter_path` returns the value ALREADY quoted. Wrapping it again produced
    # `fontfile=''C\:/...''`, which ffmpeg parsed as an empty value followed by a stray path and
    # rejected with "No option name near '/Windows/Fonts/...'" -- a message that reads like a bad
    # font path rather than a quoting bug.
    face = f"fontfile={_ffmpeg_filter_path(Path(font))}" if font else "font=Sans"
    with_text = (
        f"drawtext=text='{_text(title)}':{face}:fontsize={int(height * 0.07)}:fontcolor={CARD_FG}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-{int(height * 0.05)},"
        f"drawtext=text='{_text(subtitle)}':{face}:fontsize={int(height * 0.035)}:fontcolor={CARD_ACCENT}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2+{int(height * 0.05)},"
        f"fade=t=in:st=0:d=0.6,fade=t=out:st={max(0.0, duration_s - 0.6):.2f}:d=0.6"
    )
    base = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={CARD_BG}:s={width}x{height}:r=25:d={duration_s:.3f}"]
    try:
        _run([*base, "-vf", with_text, "-an", *_VIDEO_CODEC, str(out_path)])
    except FFmpegError as exc:
        # 🔴 The FIRST line is "ffmpeg failed (exit N):" and carries nothing usable -- which is how a
        # font-quoting bug and a genuinely text-less ffmpeg looked identical in the log while both
        # produced empty opening and closing screens. ffmpeg puts the reason last.
        detail = [line for line in str(exc).splitlines() if line.strip()]
        logger.warning(
            "Title card has NO TEXT -- drawtext failed and a blank card was rendered instead: %s",
            detail[-1] if detail else exc,
        )
        _run([*base, "-an", *_VIDEO_CODEC, str(out_path)])
    return out_path


def _concat_line(clip: Path) -> str:
    """One ``file '...'`` entry for ffmpeg's concat demuxer, written as an ABSOLUTE path.

    🔴 The concat demuxer resolves a relative entry against the list file's own directory, not the
    working directory. Every list here is written into ``_work/``, so a caller passing relative paths
    -- which is exactly what ``render --output-dir out`` does -- produced ``_work/out/_work/scene.mp4``
    and failed at the first concat. Found 2026-09-15 by the first end-to-end render outside the
    Studio, whose pipeline always passes absolute paths and so never hit it. A single quote in the
    path is escaped the way the demuxer requires.
    """
    posix = Path(clip).resolve().as_posix().replace("'", "'\\''")
    return f"file '{posix}'\n"


def concat_clips(clip_paths: list[Path], *, out_path: Path) -> Path:
    """Concat with re-encode to ensure uniform codec params."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = out_path.parent / "_concat.txt"
    with open(manifest, "w", encoding="utf-8") as f:
        for clip in clip_paths:
            f.write(_concat_line(clip))
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(manifest),
            *_VIDEO_CODEC,
            "-an",
            str(out_path),
        ]
    )
    return out_path


def mix_audio(
    voiceover: Path,
    music: Path | None,
    *,
    out_path: Path,
    total_duration_s: float,
) -> Path:
    """Mix VO over ducked music. If no music supplied, just normalize VO."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if music is None or not music.exists():
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(voiceover),
                "-af",
                "loudnorm=I=-16:TP=-1.5:LRA=11",
                *AUDIO_ARGS,
                "-t",
                f"{total_duration_s:.3f}",
                str(out_path),
            ]
        )
        return out_path

    filtergraph = (
        "[1:a]asplit=2[sc][mix];"
        "[0:a][sc]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=250[duck];"
        "[duck][mix]amix=inputs=2:duration=longest:normalize=0[mixed];"
        "[mixed]loudnorm=I=-16:TP=-1.5:LRA=11[out]"
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(music),
            "-i",
            str(voiceover),
            "-filter_complex",
            filtergraph,
            "-map",
            "[out]",
            *AUDIO_ARGS,
            "-t",
            f"{total_duration_s:.3f}",
            str(out_path),
        ]
    )
    return out_path


def mux_audio_video(video: Path, audio: Path, *, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            *AUDIO_ARGS,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
    )
    return out_path


def overlay_logo(
    src: Path,
    logo: Path,
    *,
    out_path: Path,
    intro_duration_s: float,
    outro_start_s: float,
    outro_duration_s: float,
) -> Path:
    """Overlay logo top-right during intro and outro windows."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    intro_end = intro_duration_s
    outro_end = outro_start_s + outro_duration_s
    enable_expr = f"between(t,0,{intro_end:.2f})+between(t,{outro_start_s:.2f},{outro_end:.2f})"
    filtergraph = (
        f"[1:v]format=rgba,fade=in:st=0:d=0.5:alpha=1,"
        f"fade=out:st={intro_end - 0.5:.2f}:d=0.5:alpha=1[lg];"
        f"[0:v][lg]overlay=W-w-40:40:enable='{enable_expr}'"
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-i",
            str(logo),
            "-filter_complex",
            filtergraph,
            *_VIDEO_CODEC,
            "-an",
            str(out_path),
        ]
    )
    return out_path


def burn_captions(src: Path, captions: Path, *, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            f"subtitles={_ffmpeg_filter_path(captions)}",
            *_VIDEO_CODEC,
            "-c:a",
            "copy",
            str(out_path),
        ]
    )
    return out_path


def render_square(src: Path, captions: Path | None, *, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = "crop=ih:ih,scale=1080:1080"
    if captions is not None:
        vf += f",subtitles={_ffmpeg_filter_path(captions)}"
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            vf,
            *_VIDEO_CODEC,
            "-c:a",
            "copy",
            str(out_path),
        ]
    )
    return out_path


# --- per-scene source resolution (Studio ADR-0062 D-4/D-5) -----------------------------------------


def pick_candidate(scene: Scene, footage: FootageManifest):
    """The media for a scene: the human's ``pick`` when it names a fetched candidate, else the primary."""
    selection = next((s for s in footage.selections if s.scene_id == scene.id), None)
    if selection is None:
        return None
    if scene.pick:
        wanted = scene.pick.strip()
        for candidate in (selection.primary, *selection.alternates):
            if f"{candidate.provider}:{candidate.provider_id}" == wanted:
                return candidate
        logger.warning("Scene %d pick '%s' is not among the fetched candidates; using the primary", scene.id, wanted)
    return selection.primary


def scene_clip(
    scene: Scene,
    footage: FootageManifest,
    *,
    screen_dir: Path | None,
    workdir: Path,
    width: int,
    height: int,
) -> Path:
    """Render one scene's picture to a uniform clip, whatever its surface."""
    out = workdir / f"scene_{scene.id:02d}.mp4"
    if scene.surface == "screen":
        capture = (screen_dir or workdir) / f"scene_{scene.id:02d}.webm"
        if not capture.is_file():
            raise FFmpegError(
                f"Scene {scene.id} is a screen scene but {capture} does not exist. Record the screen and save it there (render --screen-dir sets the folder)"
            )
        return fit_capture(capture, duration_s=scene.duration_s, out_path=out, width=width, height=height)

    candidate = pick_candidate(scene, footage)
    if candidate is None or not candidate.local_path:
        raise FFmpegError(f"Scene {scene.id} missing footage in manifest")
    # The hook's establishing journey (2026-09-02): its selection is one clip per authored query,
    # in story order (cmd_fetch's `_journey_top`), and the montage walks them across the hook's
    # measured duration. A human `pick` means one deliberately chosen shot -- honoured as such.
    if scene.beat == "hook" and not scene.pick:
        selection = next((s for s in footage.selections if s.scene_id == scene.id), None)
        segments = [
            c for c in ((selection.primary, *selection.alternates) if selection else ()) if c.local_path
        ]
        if len(segments) > 1:
            return _hook_montage(segments, scene=scene, out_path=out, workdir=workdir, width=width, height=height)
    source = Path(candidate.local_path)
    if candidate.kind == "image":
        return still_to_motion(source, duration_s=scene.duration_s, out_path=out, width=width, height=height)
    return trim_clip(source, duration_s=scene.duration_s, out_path=out, width=width, height=height)


def _hook_montage(segments, *, scene: Scene, out_path: Path, workdir: Path, width: int, height: int) -> Path:
    """Equal cuts across the journey's clips, summing EXACTLY to the scene's measured duration.

    The last segment absorbs the rounding remainder: the joined voice-over places every scene at
    its ``start_s``, so a montage a few frames short would slide every later scene against its own
    audio.
    """
    share = round(scene.duration_s / len(segments), 3)
    parts: list[Path] = []
    for index, candidate in enumerate(segments):
        duration = share if index < len(segments) - 1 else round(scene.duration_s - share * (len(segments) - 1), 3)
        seg_out = workdir / f"scene_{scene.id:02d}_hook_{index}.mp4"
        source = Path(candidate.local_path)
        if candidate.kind == "image":
            parts.append(still_to_motion(source, duration_s=duration, out_path=seg_out, width=width, height=height))
        else:
            parts.append(trim_clip(source, duration_s=duration, out_path=seg_out, width=width, height=height))
    return concat_clips(parts, out_path=out_path)


def _write_captions(
    voiceover: Path, caption_lines: list[dict] | None, *, out_path: Path, video_width: int, video_height: int
) -> Path:
    """The render's caption file: the approved script's lines when given, else a transcription.

    ``caption_lines`` comes from ``captions.script_caption_lines`` -- the storyboard's own voice-over
    text, timed by each scene's measured audio -- so the words on screen are the words a person
    approved. Callers that pass nothing (the Studio pipeline, single-pass voice) keep transcribing.
    """
    from .captions import generate_captions
    from .captions import write_ass

    if caption_lines is not None:
        return write_ass(caption_lines, out_path=out_path, video_width=video_width, video_height=video_height)
    return generate_captions(voiceover, out_path=out_path, video_width=video_width, video_height=video_height)


def assemble(
    storyboard: Storyboard,
    footage: FootageManifest,
    *,
    voiceover: Path,
    music: Path | None,
    output_dir: Path,
    width: int = 1920,
    height: int = 1080,
    screen_dir: Path | None = None,
    caption_lines: list[dict] | None = None,
) -> dict[str, Path]:
    """End-to-end: storyboard + footage manifest + VO → rendered MP4 (16:9, optional 1:1)."""
    ensure_ffmpeg()
    workdir = output_dir / "_work"
    workdir.mkdir(parents=True, exist_ok=True)

    clips: list[Path] = []
    for scene in storyboard.scenes:
        clips.append(scene_clip(scene, footage, screen_dir=screen_dir, workdir=workdir, width=width, height=height))

    concat = concat_clips(clips, out_path=workdir / "concat.mp4")

    logo_path = Path(storyboard.brand.logo_path)
    if logo_path.exists():
        outro_start = storyboard.total_duration_s - storyboard.brand.outro_logo_duration_s
        branded = overlay_logo(
            concat,
            logo_path,
            out_path=workdir / "branded.mp4",
            intro_duration_s=storyboard.brand.intro_logo_duration_s,
            outro_start_s=outro_start,
            outro_duration_s=storyboard.brand.outro_logo_duration_s,
        )
    else:
        # No logo has ever existed at that path; the brand is carried by title cards instead, and
        # their time is EXTRA -- the storyboard's clock (and the voice-over) starts after the intro.
        logger.info("No logo at %s — using title cards", logo_path)
        branded = concat

    audio = mix_audio(
        voiceover,
        music,
        out_path=workdir / "audio.aac",
        total_duration_s=storyboard.total_duration_s,
    )
    muxed = mux_audio_video(branded, audio, out_path=workdir / "muxed.mp4")

    outputs: dict[str, Path] = {}

    captions_16x9 = workdir / "captions_16x9.ass"
    _write_captions(voiceover, caption_lines, out_path=captions_16x9, video_width=width, video_height=height)

    if "16x9" in storyboard.aspect_ratios:
        captioned = burn_captions(muxed, captions_16x9, out_path=workdir / "captioned_16x9.mp4")
        outputs["16x9"] = _with_cards(
            storyboard, captioned, out_path=output_dir / "video_16x9.mp4", width=width, height=height, workdir=workdir
        )

    if "1x1" in storyboard.aspect_ratios:
        captions_1x1 = workdir / "captions_1x1.ass"
        _write_captions(voiceover, caption_lines, out_path=captions_1x1, video_width=1080, video_height=1080)
        outputs["1x1"] = render_square(muxed, captions_1x1, out_path=output_dir / "video_1x1.mp4")

    return outputs


def _card_title(storyboard: Storyboard) -> str:
    """The title card's text: the authored title, else one made from the slug.

    The schema's default title is empty rather than a product name, so a project that never sets
    one gets its own name on the card instead of someone else's. A trailing date stamp in the slug
    (``...-20260915``) is dropped; it is a filename convention, not a title.
    """
    if storyboard.brand.title.strip():
        return storyboard.brand.title
    words = [part for part in re.split(r"[-_\s]+", storyboard.slug) if part and not (part.isdigit() and len(part) >= 6)]
    return " ".join(word.capitalize() for word in words) or storyboard.slug


def _with_cards(storyboard: Storyboard, body: Path, *, out_path: Path, width: int, height: int, workdir: Path) -> Path:
    """Bookend the body with intro/outro title cards when no logo overlay was applied."""
    if Path(storyboard.brand.logo_path).exists():
        shutil.copyfile(body, out_path)
        return out_path
    intro = title_card(
        title=_card_title(storyboard),
        subtitle=storyboard.brand.subtitle,
        duration_s=storyboard.brand.intro_logo_duration_s,
        out_path=workdir / "card_intro.mp4",
        width=width,
        height=height,
    )
    outro = title_card(
        title=storyboard.cta.display_text,
        subtitle=storyboard.cta.url,
        duration_s=storyboard.brand.outro_logo_duration_s,
        out_path=workdir / "card_outro.mp4",
        width=width,
        height=height,
    )
    # Cards are silent; the body carries audio. Concat with the audio stream padded so the
    # container stays in sync: give the cards a silent track first.
    for card in (intro, outro):
        silent = card.with_name(card.stem + "_a.mp4")
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(card),
                "-f",
                "lavfi",
                "-i",
                f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_RATE}",
                "-shortest",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                *AUDIO_ARGS,
                str(silent),
            ]
        )
    manifest = workdir / "_cards_concat.txt"
    ordered = [intro.with_name(intro.stem + "_a.mp4"), body, outro.with_name(outro.stem + "_a.mp4")]
    _refuse_mismatched_audio(ordered)
    with open(manifest, "w", encoding="utf-8") as f:
        for clip in ordered:
            f.write(_concat_line(clip))
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(manifest),
            *_VIDEO_CODEC,
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
    )
    return out_path
