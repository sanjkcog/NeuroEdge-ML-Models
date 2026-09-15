"""Footage providers — Pexels and Pixabay videos, Pixabay vectors/illustrations — and the ranking.

Both support free commercial use without attribution. License gate (no identifiable
people in endorsement positions, no competitor brands) is enforced by the human-review
step in the orchestrating command, not here.

Studio ADR-0062 D-5: relevance is judged by LOOKING when a vision-capable model key is configured, and
the contact sheet shows a person what was chosen either way. The tag-overlap score that preceded
it was blind to Pexels -- which returns no tags, so every Pexels clip tied and resolution decided --
and that blindness is now a visible ``unscored`` flag rather than a silent tie.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
from abc import ABC
from abc import abstractmethod
from pathlib import Path
from typing import Any
from typing import Callable

import requests

from .schema import FootageCandidate
from .schema import Orientation

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache/footage")
CACHE_TTL_S = 24 * 60 * 60  # Pixabay terms require 24h caching


def _cache_key(provider: str, query: str, page: int, orientation: str) -> Path:
    digest = hashlib.sha1(f"{provider}|{query}|{page}|{orientation}".encode()).hexdigest()
    return CACHE_DIR / f"{provider}_{digest}.json"


def _read_cache(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > CACHE_TTL_S:
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


class FootageProvider(ABC):
    name: str

    @abstractmethod
    def search(self, query: str, *, n: int = 10, orientation: Orientation = "landscape") -> list[FootageCandidate]: ...

    def download(self, candidate: FootageCandidate, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".mp4" if candidate.kind == "video" else _image_suffix(candidate.url)
        filename = f"{candidate.provider}_{candidate.provider_id}{suffix}"
        path = dest_dir / filename
        if path.exists() and path.stat().st_size > 0:
            candidate.local_path = str(path)
            return path
        logger.info("Downloading %s → %s", candidate.url, path)
        resp = requests.get(candidate.url, stream=True, timeout=60)
        resp.raise_for_status()
        with open(path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)
        candidate.local_path = str(path)
        return path


def _image_suffix(url: str) -> str:
    match = re.search(r"\.(png|jpe?g|webp)(?:\?|$)", url.lower())
    return f".{match.group(1)}" if match else ".jpg"


class PexelsProvider(FootageProvider):
    name = "pexels"
    BASE = "https://api.pexels.com/videos/search"

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.getenv("PEXELS_API_KEY")
        if not key:
            raise RuntimeError("PEXELS_API_KEY not set")
        self.api_key = key

    def search(self, query: str, *, n: int = 10, orientation: Orientation = "landscape") -> list[FootageCandidate]:
        cache = _cache_key("pexels", query, 1, orientation)
        payload = _read_cache(cache)
        if payload is None:
            params = {
                "query": query,
                "per_page": min(n, 30),
                "orientation": orientation,
                "size": "large",
            }
            headers = {"Authorization": self.api_key}
            resp = requests.get(self.BASE, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            _write_cache(cache, payload)
        results: list[FootageCandidate] = []
        for video in payload.get("videos", []):
            candidate = self._to_candidate(video, query)
            if candidate is not None:
                results.append(candidate)
        return results[:n]

    @staticmethod
    def _to_candidate(video: dict[str, Any], query: str) -> FootageCandidate | None:
        best = _best_pexels_rendition(video.get("video_files", []))
        if best is None:
            logger.debug("Pexels video %s has no usable renditions", video.get("id"))
            return None
        # 🔴 Pexels returns NO tags. The title used to be photographer + query, which made every
        # candidate match its own query perfectly; it is now the photographer only, so the tag score
        # is honestly zero and the candidate is flagged `unscored` unless the vision pass looks.
        return FootageCandidate(
            provider="pexels",
            provider_id=str(video.get("id", "")),
            url=best["link"],
            width=best.get("width", 0),
            height=best.get("height", 0),
            duration_s=float(video.get("duration", 0)),
            title=str(video.get("user", {}).get("name", "")),
            tags=[],
            thumbnail=str(video.get("image") or ""),
        )


def _best_pexels_rendition(files: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not files:
        return None
    mp4s = [f for f in files if f.get("file_type") == "video/mp4"]
    candidates = mp4s or files
    sized = [f for f in candidates if 1280 <= (f.get("width") or 0) <= 2560]
    candidates = sized or candidates
    if not candidates:
        return None
    return max(candidates, key=lambda f: (f.get("width") or 0) * (f.get("height") or 0))


class PixabayProvider(FootageProvider):
    name = "pixabay"
    BASE = "https://pixabay.com/api/videos/"

    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.getenv("PIXABAY_API_KEY")
        if not key:
            raise RuntimeError("PIXABAY_API_KEY not set")
        self.api_key = key

    def search(self, query: str, *, n: int = 10, orientation: Orientation = "landscape") -> list[FootageCandidate]:
        cache = _cache_key("pixabay", query, 1, orientation)
        payload = _read_cache(cache)
        if payload is None:
            # Pixabay requires the API key in the query string (no header auth supported).
            # The Cognizant Zscaler proxy logs full URLs — treat the key as moderately
            # exposed and rotate periodically. The cache filename hashes (provider,
            # query, page, orientation) only, never the key itself.
            params = {
                "key": self.api_key,
                "q": query,
                "per_page": max(3, min(n, 50)),
                "video_type": "film",
                "safesearch": "true",
                "min_width": 1280,
            }
            resp = requests.get(self.BASE, params=params, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            _write_cache(cache, payload)
        results: list[FootageCandidate] = []
        for hit in payload.get("hits", []):
            candidate = self._to_candidate(hit, query)
            if candidate is not None:
                results.append(candidate)
        return results[:n]

    @staticmethod
    def _to_candidate(hit: dict[str, Any], query: str) -> FootageCandidate | None:
        videos = hit.get("videos", {})
        rendition = videos.get("large") or videos.get("medium") or videos.get("small") or {}
        if not rendition.get("url"):
            logger.debug("Pixabay hit %s has no usable rendition", hit.get("id"))
            return None
        tags = [t.strip() for t in (hit.get("tags") or "").split(",") if t.strip()]
        return FootageCandidate(
            provider="pixabay",
            provider_id=str(hit.get("id", "")),
            url=rendition["url"],
            width=rendition.get("width", 0),
            height=rendition.get("height", 0),
            duration_s=float(hit.get("duration", 0)),
            title=" ".join(tags[:3]),
            tags=tags,
            thumbnail=str(rendition.get("thumbnail") or ""),
        )


class PixabayImageProvider(FootageProvider):
    """Pixabay vectors and illustrations -- the ``vector`` surface (Studio ADR-0062 D-4).

    Same key, same licence, a different endpoint. Returned as ``kind="image"`` candidates the
    assembler renders to motion; ``duration_s`` is 0 because a still has none.
    """

    name = "pixabay"
    BASE = "https://pixabay.com/api/"

    def __init__(self, api_key: str | None = None, image_type: str = "vector") -> None:
        key = api_key or os.getenv("PIXABAY_API_KEY")
        if not key:
            raise RuntimeError("PIXABAY_API_KEY not set")
        self.api_key = key
        self.image_type = image_type

    def search(self, query: str, *, n: int = 10, orientation: Orientation = "landscape") -> list[FootageCandidate]:
        cache = _cache_key(f"pixabay-{self.image_type}", query, 1, orientation)
        payload = _read_cache(cache)
        if payload is None:
            params = {
                "key": self.api_key,
                "q": query,
                "image_type": self.image_type,
                "orientation": "horizontal" if orientation == "landscape" else "vertical",
                "per_page": max(3, min(n, 50)),
                "safesearch": "true",
                "min_width": 1280,
            }
            resp = requests.get(self.BASE, params=params, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            _write_cache(cache, payload)
        results: list[FootageCandidate] = []
        for hit in payload.get("hits", []):
            url = hit.get("largeImageURL") or hit.get("webformatURL")
            if not url:
                continue
            tags = [t.strip() for t in (hit.get("tags") or "").split(",") if t.strip()]
            results.append(
                FootageCandidate(
                    provider="pixabay",
                    provider_id=str(hit.get("id", "")),
                    url=url,
                    width=int(hit.get("imageWidth") or 0),
                    height=int(hit.get("imageHeight") or 0),
                    duration_s=0.0,
                    title=" ".join(tags[:3]),
                    tags=tags,
                    kind="image",
                    thumbnail=str(hit.get("previewURL") or hit.get("webformatURL") or ""),
                )
            )
        return results[:n]


# --- ranking -------------------------------------------------------------------------------

VisionScorer = Callable[[FootageCandidate, str], tuple[float, str] | None]


#: Cheap, vision-capable defaults for the plain-key path. Override with NEUROEDGE_VISION_MODEL.
_DEFAULT_VISION_MODELS = {"anthropic": "claude-haiku-4-5-20251001", "openai": "gpt-4o-mini"}
_VISION_TIMEOUT_S = 30


def _vision_prompt(intent: str) -> str:
    return (
        "You are choosing B-roll for a corporate product video. Score 0-10 how well this image "
        f'shows: "{intent}". Penalise text overlays, watermarks, faces in close-up, and anything '
        'off-topic. Reply with ONLY a JSON object: {"score": <0-10>, "why": "<eight words>"}.'
    )


def _parse_vision_reply(reply: str) -> tuple[float, str] | None:
    match = re.search(r"\{.*\}", reply or "", re.DOTALL)
    if not match:
        return None
    parsed = json.loads(match.group(0))
    score = float(parsed.get("score", 0))
    return max(0.0, min(10.0, score)) / 10.0, str(parsed.get("why") or "")


def _fetch_thumbnail(url: str) -> tuple[str, str]:
    """The thumbnail as base64 plus its media type, so it can be sent inline to any provider."""
    image = requests.get(url, timeout=20)
    image.raise_for_status()
    encoded = base64.b64encode(image.content).decode("ascii")
    mime = image.headers.get("content-type", "image/jpeg").split(";")[0]
    return encoded, mime


def generic_vision_config() -> tuple[str, str, str] | None:
    """``(provider, api_key, model)`` from plain environment variables, or ``None``.

    The path for any project without the Studio's Builder-API LLM adapter -- which is every
    installed target. ``ANTHROPIC_API_KEY`` is preferred, then ``OPENAI_API_KEY``.

    🔴 ``OPENAI_API_KEY`` is also the draft-voiceover key, so a project that sets it for TTS gets
    this pass too: one thumbnail download and one model call per candidate. ``fetch --no-vision``
    turns it off.
    """
    override = os.getenv("NEUROEDGE_VISION_MODEL", "").strip()
    for provider, env in (("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY")):
        key = os.getenv(env, "").strip()
        if key:
            return provider, key, override or _DEFAULT_VISION_MODELS[provider]
    return None


def _generic_chat(provider: str, api_key: str, model: str, prompt: str, encoded: str, mime: str) -> str:
    """One vision call over plain HTTPS -- no SDK, so the package adds no dependency for it."""
    if provider == "anthropic":
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": model,
                "max_tokens": 150,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": mime, "data": encoded}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            },
            timeout=_VISION_TIMEOUT_S,
        )
        response.raise_for_status()
        return "".join(
            block.get("text", "") for block in response.json().get("content", []) if block.get("type") == "text"
        )
    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
        json={
            "model": model,
            "max_tokens": 150,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                    ],
                }
            ],
        },
        timeout=_VISION_TIMEOUT_S,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"] or ""


def vision_score(candidate: FootageCandidate, intent: str) -> tuple[float, str] | None:
    """Ask a vision-capable model how well the thumbnail shows ``intent``, 0-10. ``None`` = could not.

    Inside the NeuroEdge Studio this goes through ``neuroedge.backend.api.llm.chat``, so the
    BYOK/provider rules are the Builder API's own. Everywhere else -- every installed target -- that
    module does not exist, and the call goes to Anthropic or OpenAI directly with a plain key (see
    :func:`generic_vision_config`). Any failure returns ``None``: the caller then keeps the
    candidate ``unscored`` rather than pretending a number.
    """
    if not candidate.thumbnail:
        return None
    try:
        from neuroedge.backend.api.llm import LlmNotConfiguredError  # noqa: PLC0415
        from neuroedge.backend.api.llm import chat  # noqa: PLC0415
    except ImportError:
        return _generic_vision_score(candidate, intent)
    try:
        encoded, mime = _fetch_thumbnail(candidate.thumbnail)
        reply = chat(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _vision_prompt(intent)},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                    ],
                }
            ],
            None,
        )
        return _parse_vision_reply(reply)
    except (LlmNotConfiguredError, requests.RequestException, ValueError, TypeError) as exc:
        logger.debug("vision score unavailable for %s: %s", candidate.provider_id, exc)
        return None
    except Exception as exc:  # noqa: BLE001 -- a scorer outage must degrade to unscored, never abort a fetch
        logger.warning("vision score failed for %s/%s: %s", candidate.provider, candidate.provider_id, exc)
        return None


def _generic_vision_score(candidate: FootageCandidate, intent: str) -> tuple[float, str] | None:
    config = generic_vision_config()
    if config is None:
        return None
    provider, api_key, model = config
    try:
        encoded, mime = _fetch_thumbnail(candidate.thumbnail)
        return _parse_vision_reply(_generic_chat(provider, api_key, model, _vision_prompt(intent), encoded, mime))
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError) as exc:
        logger.debug("vision score unavailable for %s: %s", candidate.provider_id, exc)
        return None
    except Exception as exc:  # noqa: BLE001 -- a scorer outage must degrade to unscored, never abort a fetch
        logger.warning("vision score failed for %s/%s: %s", candidate.provider, candidate.provider_id, exc)
        return None


def vision_available() -> bool:
    """Whether a model key the vision pass can use is configured."""
    try:
        from neuroedge.backend.api.llm import _resolve_config  # noqa: PLC0415
    except ImportError:
        return generic_vision_config() is not None
    try:
        return bool(_resolve_config(None).get("api_key"))
    except Exception:  # noqa: BLE001
        return False


def rank_and_dedupe(
    candidates: list[FootageCandidate],
    *,
    query: str,
    min_duration_s: float = 4.0,
    target_width: int = 1920,
    scorer: VisionScorer | None = None,
    intent: str | None = None,
    provider_order: list[str] | None = None,
) -> list[FootageCandidate]:
    """Rank by relevance + resolution fit + duration adequacy. Dedupe by provider+id.

    Relevance is the vision score when ``scorer`` returns one, else tag overlap when tags exist,
    else nothing -- and a candidate with nothing is marked ``unscored`` so the contact sheet can say
    so. Stills (``kind="image"``) are not penalised for having no duration.

    ``provider_order`` makes the ``--providers`` list a PREFERENCE, not only a construction order:
    the first-listed provider's candidates get a small additive bonus (0.05 at most -- half a
    resolution-fit's weight), decreasing down the list. It tilts ties and near-ties toward the
    preferred library while a clearly better clip from anywhere still wins. ``None`` ranks exactly
    as before.
    """
    seen: set[tuple[str, str]] = set()
    deduped: list[FootageCandidate] = []
    for c in candidates:
        key = (c.provider, c.provider_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)

    query_terms = {t.lower() for t in query.split() if len(t) > 2}

    for c in deduped:
        relevance: float | None = None
        if scorer is not None:
            scored = scorer(c, intent or query)
            if scored is not None:
                relevance, c.vision_note = scored
        if relevance is None and c.tags:
            text = (c.title + " " + " ".join(c.tags)).lower()
            relevance = sum(1 for t in query_terms if t in text) / max(len(query_terms), 1)
        c.unscored = relevance is None
        res_fit = 1.0 - min(abs(c.width - target_width) / target_width, 1.0)
        duration_ok = 1.0 if (c.kind == "image" or c.duration_s >= min_duration_s) else 0.3
        preference = 0.0
        if provider_order and c.provider in provider_order:
            span = max(len(provider_order) - 1, 1)
            preference = 0.05 * (len(provider_order) - 1 - provider_order.index(c.provider)) / span
        c.relevance_score = 0.6 * (relevance or 0.0) + 0.3 * res_fit + 0.1 * duration_ok + preference

    # Scored candidates rank above unscored ones at equal numbers: a known fit beats an unknown one.
    return sorted(deduped, key=lambda c: (-c.relevance_score, c.unscored))
