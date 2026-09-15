"""Per-scene voice-over: one WAV per scene, measured, and the storyboard re-timed from it.

Ported from the NeuroEdge Studio's ``voice`` stage (Studio ADR-0062 D-3), where it was measured on
real renders. Nothing in it is Studio-specific: it works on a storyboard dict and WAV files.

🔴 **Per scene, not per video.** Synthesising the whole storyboard as one string and cutting the
picture on the authored durations lets sentences straddle cuts. Here each scene's text becomes its
own WAV, the scene's duration becomes that audio's measured length plus a pad, and the cuts land
after the sentences because the sentences decide the cuts. The scene WAVs are then joined, each
starting at its scene's ``start_s``, into the single voice-over the assembler and the caption
transcriber already expect -- so everything downstream is unchanged.

Measurement goes through ``ffprobe`` when it is available (every format) and the ``wave`` module
otherwise (PCM only), and a file neither can read is a named refusal rather than a guessed length.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from typing import Mapping

logger = logging.getLogger(__name__)

SILENCE_SAMPLE_RATE = 24000


def apply_say_as(text: str, say_as: Mapping[str, str]) -> str:
    """The authored pronunciation map (the ``--say-as`` file), applied to spoken text only.

    A TTS engine reads "CNC-PWT-014" as seven syllables of alphabet; the author maps it to "the
    CNC machine on Powertrain line 14" and this function substitutes it in the text a voice
    provider receives -- captions and the storyboard keep the literal id, so the screen stays the
    audit surface while the ear gets a sentence.

    🔴 ONE pass, all keys as a longest-first alternation, boundary-guarded on both sides. The
    alternation order resolves overlap ("PWT-LINE-30" wins over "PWT-LINE-3"); the lookarounds
    stop "PWT-LINE-3" matching INSIDE "PWT-LINE-30" even when only the short key is declared (an
    id continues in letters or digits, never in prose); and a single pass is what stops a
    replacement VALUE being rescanned -- key-by-key substitution let a value like
    "successor to PWT-LINE-3" be mangled by the next key's turn (Studio review HIGH, 2026-09-02).
    """
    result = str(text or "")
    keys = sorted((key for key in say_as if key), key=len, reverse=True)
    if not keys:
        return result
    alternation = "|".join(re.escape(key) for key in keys)
    # Underscore in the boundary class too: snake_case ids like "line_operations" are say_as keys
    # in practice, and without it the key matched INSIDE a longer compound
    # ("sop_line_operations_signal") — an id's edge is any non-identifier character.
    pattern = re.compile(rf"(?<![A-Za-z0-9_])(?:{alternation})(?![A-Za-z0-9_])")
    return pattern.sub(lambda match: str(say_as[match.group(0)]), result)


class VoiceError(RuntimeError):
    """The voice could not be made, and the message names what was missing."""


@dataclass
class SceneAudio:
    scene_id: int
    path: Path
    duration_s: float


def measure_s(path: Path) -> float:
    """The audio's length in seconds, by ffprobe first and the wave module second."""
    # pylint: disable=import-outside-toplevel
    from .assembler import resolve_ffmpeg

    probe = resolve_ffmpeg("ffprobe")
    if probe:
        try:
            out = subprocess.run(
                [probe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            duration = float(json.loads(out.stdout)["format"]["duration"])
            if duration > 0:
                return duration
        except (subprocess.SubprocessError, ValueError, KeyError) as exc:
            logger.warning("ffprobe could not measure %s: %s", path, exc)
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() / float(handle.getframerate())
    except (wave.Error, OSError) as exc:
        raise VoiceError(f"Could not measure {path.name}: {exc}. Is ffprobe installed?") from exc


def synthesize_scenes(
    scenes: list[dict],
    synth: Callable[[str, Path], Path],
    work_dir: Path,
) -> list[SceneAudio]:
    """Run ``synth(text, out_path)`` once per scene and measure each result."""
    work_dir.mkdir(parents=True, exist_ok=True)
    audio: list[SceneAudio] = []
    for scene in scenes:
        text = str(scene.get("voiceover") or "").strip()
        target = work_dir / f"scene_{int(scene['id']):02d}.wav"
        if not text:
            raise VoiceError(f"Scene {scene['id']} has no voiceover text; add it in storyboard.json.")
        synth(text, target)
        if not target.is_file() or target.stat().st_size == 0:
            raise VoiceError(f"The voice provider wrote nothing for scene {scene['id']}.")
        audio.append(SceneAudio(int(scene["id"]), target, measure_s(target)))
    return audio


def retime(storyboard: dict, audio: list[SceneAudio], pad_s: float, *, minimum_s: float = 3.0) -> dict:
    """Replace every scene's provisional duration with its measured audio plus the pad."""
    by_id = {item.scene_id: item for item in audio}
    start = 0.0
    for scene in storyboard["scenes"]:
        measured = by_id[int(scene["id"])].duration_s
        duration = round(max(minimum_s, measured + pad_s), 3)
        scene["start_s"] = round(start, 3)
        scene["duration_s"] = duration
        start = round(start + duration, 3)
    storyboard["total_duration_s"] = round(start, 3)
    return storyboard


def join_with_pads(audio: list[SceneAudio], storyboard: dict, out_path: Path) -> Path:
    """Concatenate the scene WAVs so each starts exactly at its scene's ``start_s``.

    Uses ffmpeg when present (handles any codec the provider wrote); otherwise the ``wave`` module
    for PCM input. Either way the result is PCM WAV the assembler's loudnorm accepts.
    """
    # pylint: disable=import-outside-toplevel
    from .assembler import resolve_ffmpeg

    starts = {int(scene["id"]): float(scene["start_s"]) for scene in storyboard["scenes"]}
    ffmpeg = resolve_ffmpeg("ffmpeg")
    if ffmpeg:
        args = [ffmpeg, "-y"]
        for item in audio:
            args += ["-i", str(item.path)]
        delays = []
        for index, item in enumerate(audio):
            delay_ms = int(round(starts[item.scene_id] * 1000))
            delays.append(
                f"[{index}:a]aresample={SILENCE_SAMPLE_RATE},aformat=channel_layouts=mono,adelay={delay_ms}|{delay_ms}[a{index}]"
            )
        mix = (
            "".join(f"[a{i}]" for i in range(len(audio)))
            + f"amix=inputs={len(audio)}:normalize=0:dropout_transition=0[out]"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        args += ["-filter_complex", ";".join(delays) + ";" + mix, "-map", "[out]", "-c:a", "pcm_s16le", str(out_path)]
        result = subprocess.run(args, capture_output=True, text=True, timeout=600, check=False)
        if result.returncode != 0:
            raise VoiceError(f"ffmpeg could not join the scene audio: {result.stderr[-800:]}")
        return out_path

    if shutil.which("ffmpeg") is None:
        logger.warning("ffmpeg not found; joining scene audio with the wave module (PCM only)")
    return _join_pcm(audio, starts, out_path)


def _join_pcm(audio: list[SceneAudio], starts: dict[int, float], out_path: Path) -> Path:
    params = None
    frames: list[bytes] = []
    cursor_frames = 0
    for item in audio:
        with wave.open(str(item.path), "rb") as handle:
            if params is None:
                params = handle.getparams()
            elif (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) != (
                params.nchannels,
                params.sampwidth,
                params.framerate,
            ):
                raise VoiceError("Scene WAVs differ in format; install ffmpeg to join them.")
            target_frame = int(starts[item.scene_id] * params.framerate)
            gap = max(0, target_frame - cursor_frames)
            frames.append(b"\x00" * gap * params.nchannels * params.sampwidth)
            data = handle.readframes(handle.getnframes())
            frames.append(data)
            cursor_frames = target_frame + handle.getnframes()
    if params is None:
        raise VoiceError("No scene audio to join.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(params.nchannels)
        out.setsampwidth(params.sampwidth)
        out.setframerate(params.framerate)
        out.writeframes(b"".join(frames))
    return out_path
