"""Caption generation: from the approved script (per-scene voice), or via faster-whisper.

Re-transcribes the rendered TTS WAV (clean studio audio → near-ceiling Whisper accuracy)
and emits Advanced SubStation Alpha (.ass) for styled, burned-in captions via ffmpeg.

Why .ass not .srt: ASS allows per-line styling (background box, font, color, position)
that LinkedIn-mute captions need. ffmpeg's `subtitles=` filter handles both.
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

Position = Literal["bottom", "center"]


def transcribe_words(audio_path: Path, model_size: str = "base.en") -> list[dict]:
    """Return list of {start, end, word} dicts. Requires `faster-whisper` package."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("faster-whisper not installed. Run: pip install faster-whisper") from e

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio_path), word_timestamps=True, language="en")

    words: list[dict] = []
    for segment in segments:
        for word in segment.words or []:
            words.append({"start": word.start, "end": word.end, "word": word.word.strip()})
    logger.info("Whisper transcribed %d words from %s", len(words), audio_path)
    return words


def words_to_caption_lines(
    words: list[dict],
    *,
    max_chars_per_line: int = 38,
    max_lines: int = 2,
    max_duration_s: float = 4.0,
) -> list[dict]:
    """Group words into caption lines that fit on-screen and don't outstay welcome."""
    if not words:
        return []

    lines: list[dict] = []
    current_words: list[dict] = []
    line_start = words[0]["start"]

    def flush() -> None:
        if not current_words:
            return
        text = " ".join(w["word"] for w in current_words).strip()
        wrapped = textwrap.wrap(text, width=max_chars_per_line, break_long_words=False)
        if len(wrapped) > max_lines:
            wrapped = wrapped[:max_lines]
        lines.append(
            {
                "start": line_start,
                "end": current_words[-1]["end"],
                "text": "\\N".join(wrapped),
            }
        )

    for w in words:
        candidate = current_words + [w]
        text = " ".join(x["word"] for x in candidate)
        wrapped = textwrap.wrap(text, width=max_chars_per_line, break_long_words=False)
        duration = w["end"] - line_start
        if len(wrapped) > max_lines or duration > max_duration_s:
            flush()
            current_words = [w]
            line_start = w["start"]
        else:
            current_words = candidate

    flush()
    return lines


def write_ass(
    lines: list[dict],
    *,
    out_path: Path,
    video_width: int = 1920,
    video_height: int = 1080,
    font_name: str = "Inter",
    font_size: int = 56,
    position: Position = "bottom",
) -> Path:
    """Write Advanced SubStation Alpha subtitles with brand-styled background box."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    alignment = 2 if position == "bottom" else 5
    margin_v = int(video_height * 0.10) if position == "bottom" else 0
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginV, Encoding
Style: Caption,{font_name},{font_size},&H00FFFFFF,&H00000000,&HB3000000,1,4,2,0,{alignment},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for line in lines:
        start = _fmt_ass_time(line["start"])
        end = _fmt_ass_time(line["end"])
        text = line["text"].replace("\n", "\\N")
        events.append(f"Dialogue: 0,{start},{end},Caption,,0,0,0,,{text}")
    out_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    logger.info("Wrote %d caption events to %s", len(events), out_path)
    return out_path


def _fmt_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    return f"{h:01d}:{m:02d}:{s:05.2f}"


def generate_captions(
    audio_path: Path,
    *,
    out_path: Path,
    video_width: int = 1920,
    video_height: int = 1080,
    model_size: str = "base.en",
) -> Path:
    """End-to-end: TTS WAV → ASS caption file."""
    words = transcribe_words(audio_path, model_size=model_size)
    lines = words_to_caption_lines(words)
    return write_ass(
        lines,
        out_path=out_path,
        video_width=video_width,
        video_height=video_height,
    )


def _caption_safe(text: str) -> str:
    """Text an ASS event can hold literally: ``{`` opens an override block, ``\\`` starts an escape."""
    return " ".join(str(text or "").replace("{", "(").replace("}", ")").replace("\\", "/").split())


def script_caption_lines(
    scenes: list[dict],
    speech_s: dict[int, float],
    *,
    max_chars_per_line: int = 38,
    max_lines: int = 2,
    max_duration_s: float = 4.0,
) -> list[dict]:
    """Caption lines built from each scene's APPROVED voice-over text, never from a transcription.

    🔴 **Why not transcribe.** Re-transcribing the rendered voice-over put a small model's guesses on
    screen: in the first end-to-end render outside the Studio (2026-09-15) ``base.en`` wrote
    "rescoped" as "rescued", "faked" as "spaked", "epics" as "Epic's" and "3,870" as "3 ,870". The
    storyboard already holds the exact words a person approved, so those are what is shown -- literal
    ids included, because ``say_as`` changes only what the voice hears.

    **Timing.** Per-scene voice places each scene's audio at its ``start_s`` and measures its length,
    so a scene's speech window is exact: ``[start_s, start_s + speech]`` (``speech_s`` by scene id,
    capped at the scene's duration; the scene's duration when not measured). Within a scene, each
    word's time is its share of the scene's characters -- TTS reads at a near-constant rate, so that
    is a close proxy. Lines are grouped per scene, so a caption never spans a scene boundary.
    """
    lines: list[dict] = []
    for scene in scenes:
        tokens = _caption_safe(scene.get("voiceover") or "").split()
        if not tokens:
            continue
        start = float(scene["start_s"])
        duration = float(scene["duration_s"])
        span = min(float(speech_s.get(int(scene["id"]), duration)), duration)
        total = sum(len(token) + 1 for token in tokens)
        cumulative = 0
        words: list[dict] = []
        for token in tokens:
            word_start = start + span * cumulative / total
            cumulative += len(token) + 1
            words.append({"start": word_start, "end": start + span * cumulative / total, "word": token})
        lines.extend(
            words_to_caption_lines(
                words, max_chars_per_line=max_chars_per_line, max_lines=max_lines, max_duration_s=max_duration_s
            )
        )
    return lines
