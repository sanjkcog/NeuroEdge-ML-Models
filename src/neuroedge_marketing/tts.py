"""TTS adapters — Chatterbox (local, cloned voice), OpenAI (steerable), ElevenLabs (hosted clone).

Each writes one WAV/MP3 to disk. Provider word-timestamps are never trusted: with per-scene voice
(the default) each scene's audio is measured and captions are the approved script timed across it
(``captions.script_caption_lines``); ``--single-pass-voice`` transcribes with faster-whisper instead.

Studio ADR-0062 D-3: a ``style`` direction is accepted by every provider and applied where the engine can
honour it -- ``gpt-4o-mini-tts``'s ``instructions`` field, Chatterbox's exaggeration knob. The
first shipped render sent no direction at all, and a flat read was the result (Studio ADR-0062 F-5).
"""

from __future__ import annotations

import logging
import os
from abc import ABC
from abc import abstractmethod
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class TTSProvider(ABC):
    name: str

    @abstractmethod
    def synthesize(self, text: str, *, out_path: Path, voice: str | None = None, style: str | None = None) -> Path: ...


class OpenAITTSProvider(TTSProvider):
    name = "openai"
    DEFAULT_VOICE = "onyx"
    DEFAULT_MODEL = "gpt-4o-mini-tts"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set")
        self.api_key = key
        self.model = model or self.DEFAULT_MODEL

    def synthesize(self, text: str, *, out_path: Path, voice: str | None = None, style: str | None = None) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        body: dict = {
            "model": self.model,
            "voice": voice or self.DEFAULT_VOICE,
            "input": text,
            "response_format": "wav",
        }
        # The direction is what separates a read from a delivery. Only the steerable model takes it.
        if style and self.model.startswith("gpt-4o"):
            body["instructions"] = style
        resp = requests.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=120,
        )
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(resp.content)
        logger.info("OpenAI TTS wrote %s (%d bytes)", out_path, out_path.stat().st_size)
        return out_path


class ElevenLabsTTSProvider(TTSProvider):
    name = "elevenlabs"
    DEFAULT_MODEL = "eleven_multilingual_v2"

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model: str | None = None,
    ) -> None:
        key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not key:
            raise RuntimeError("ELEVENLABS_API_KEY not set")
        voice = voice_id or os.getenv("ELEVENLABS_VOICE_ID")
        if not voice:
            raise RuntimeError("ELEVENLABS_VOICE_ID not set")
        self.api_key = key
        self.voice_id = voice
        self.model = model or self.DEFAULT_MODEL

    def synthesize(self, text: str, *, out_path: Path, voice: str | None = None, style: str | None = None) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice or self.voice_id}"
        resp = requests.post(
            url,
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text,
                "model_id": self.model,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=180,
        )
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(resp.content)
        logger.info("ElevenLabs TTS wrote %s (%d bytes)", out_path, out_path.stat().st_size)
        return out_path


class ChatterboxTTSProvider(TTSProvider):
    """Resemble AI's Chatterbox, run locally (MIT licence) -- Studio ADR-0062 D-3's default.

    Zero-shot voice cloning from a short reference recording, with an ``exaggeration`` knob for
    expressiveness. The model loads once per process (first use downloads ~1-2 GB into the Hugging
    Face cache, outside the repo) and runs on CUDA when available, else CPU -- slowly, but it runs.

    🔴 The reference recording is a biometric. This class reads it from wherever the caller points
    and never copies it anywhere. Keep it out of version control.
    """

    name = "chatterbox"

    def __init__(self, reference: Path | None = None, *, exaggeration: float = 0.5, device: str | None = None) -> None:
        if reference is not None and not Path(reference).is_file():
            raise RuntimeError(f"Chatterbox voice reference not found: {reference}")
        self.reference = Path(reference) if reference else None
        self.exaggeration = exaggeration
        self.device = device
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            import torch  # noqa: F401  (Chatterbox needs it; a missing torch is the common failure)
            from chatterbox.tts import ChatterboxTTS
        except ImportError as exc:
            raise RuntimeError(
                "Chatterbox is not installed. Run `pip install chatterbox-tts` (it pulls torch; a CUDA "
                "build of torch is strongly recommended on a machine with a GPU)."
            ) from exc
        device = self.device
        if device is None:
            import torch as _torch

            device = "cuda" if _torch.cuda.is_available() else "cpu"
        logger.info("Loading Chatterbox on %s", device)
        self._model = ChatterboxTTS.from_pretrained(device=device)
        return self._model

    #: 🔴 Chatterbox degrades past roughly this many characters in ONE generation call — words get
    #: garbled and the tail can vanish entirely. Measured live (2026-09-02): a ~980-char hook lost
    #: its closing sentences, mangled "every tool issue was caught" into "every tool is cheap",
    #: and read "line_operations" as "Money Operations". Sentences are grouped up to this budget
    #: and generated separately, then concatenated with a short breath of silence.
    MAX_CHUNK_CHARS = 280

    #: The pause between generated chunks, seconds. A chunk boundary is a sentence boundary, so
    #: this reads as an ordinary breath, not an edit.
    CHUNK_GAP_S = 0.25

    @classmethod
    def _chunks(cls, text: str) -> list[str]:
        """Sentence groups within the stability budget. A single over-long sentence stays whole —
        splitting mid-sentence sounds worse than one risky generation."""
        import re

        flat = " ".join(str(text or "").split())
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", flat) if part.strip()]
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > cls.MAX_CHUNK_CHARS:
                chunks.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks or [flat]

    def synthesize(self, text: str, *, out_path: Path, voice: str | None = None, style: str | None = None) -> Path:
        model = self._load()
        import torch
        import torchaudio

        out_path.parent.mkdir(parents=True, exist_ok=True)
        kwargs: dict = {"exaggeration": self.exaggeration}
        if self.reference is not None:
            kwargs["audio_prompt_path"] = str(self.reference)
        chunks = self._chunks(text)
        if len(chunks) > 1:
            logger.info("Chatterbox: %d chars split into %d chunks for stability", len(text), len(chunks))
        waves = [model.generate(chunk, **kwargs) for chunk in chunks]
        if len(waves) == 1:
            wav = waves[0]
        else:
            gap = torch.zeros(
                (waves[0].shape[0], int(model.sr * self.CHUNK_GAP_S)),
                dtype=waves[0].dtype,
                device=waves[0].device,
            )
            pieces: list = []
            for index, piece in enumerate(waves):
                pieces.append(piece)
                if index < len(waves) - 1:
                    pieces.append(gap)
            wav = torch.cat(pieces, dim=1)
        torchaudio.save(str(out_path), wav, model.sr)
        logger.info("Chatterbox wrote %s (%d bytes)", out_path, out_path.stat().st_size)
        return out_path


def get_provider(
    name: str,
    *,
    reference: Path | None = None,
    exaggeration: float = 0.5,
) -> TTSProvider:
    name = name.lower()
    if name == "openai":
        return OpenAITTSProvider()
    if name == "elevenlabs":
        return ElevenLabsTTSProvider()
    if name == "chatterbox":
        return ChatterboxTTSProvider(reference, exaggeration=exaggeration)
    raise ValueError(f"Unknown TTS provider: {name}")
