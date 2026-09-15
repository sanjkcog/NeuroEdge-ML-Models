"""Input loaders — turn files in ``sim_input/`` into a stream of payload dicts.

Two families, chosen by file extension:

  timeseries : .csv .xls .xlsx .json   -> one payload per row/object
  media      : images & video          -> one payload per image / video frame

Each loader yields raw ``payload`` dicts (no seq/ts yet); the engine wraps them
in :class:`~neuro_sim.record.Record` and stamps them at emit time.

Heavy third-party imports (pandas, cv2) are done lazily inside the loader that
needs them, so a run that only touches CSV never imports OpenCV.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Iterator

# Extension -> family. Extend these sets to support more formats.
TIMESERIES_EXT = {".csv", ".xls", ".xlsx", ".json"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"}
MEDIA_EXT = IMAGE_EXT | VIDEO_EXT

SUPPORTED_EXT = TIMESERIES_EXT | MEDIA_EXT


class UnsupportedInput(ValueError):
    """A file whose extension maps to no known loader."""


def family_of(path: Path) -> str:
    """"timeseries" or "media" for ``path``; raises UnsupportedInput otherwise."""
    ext = path.suffix.lower()
    if ext in TIMESERIES_EXT:
        return "timeseries"
    if ext in MEDIA_EXT:
        return "media"
    raise UnsupportedInput(f"no loader for {path.name} (extension {ext!r})")


def discover(input_dir: Path, glob: str = "*") -> list[Path]:
    """Every supported file directly under ``input_dir`` matching ``glob``, sorted.

    Unsupported files are skipped silently so a stray README or .gitkeep in
    sim_input/ never aborts a run.
    """
    return sorted(
        p for p in input_dir.glob(glob)
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXT
    )


# --------------------------------------------------------------------------- #
# timeseries
# --------------------------------------------------------------------------- #

def load_timeseries(path: Path) -> Iterator[dict[str, Any]]:
    """Yield one payload dict per row (csv/xls) or per object (json)."""
    ext = path.suffix.lower()
    if ext == ".json":
        yield from _load_json_records(path)
    elif ext == ".csv":
        yield from _load_tabular(path, "csv")
    elif ext in (".xls", ".xlsx"):
        yield from _load_tabular(path, "excel")
    else:  # pragma: no cover - guarded by family_of upstream
        raise UnsupportedInput(path.name)


def _nan_to_none(_token: str) -> None:
    """json.loads parse_constant hook: map the non-standard NaN/Infinity/-Infinity
    tokens (which json accepts by default) to None, so payloads never carry a
    non-finite float. This keeps JSON input consistent with the pandas path (which
    already swaps NaN for None) and keeps the sim_output/ JSON spec-valid."""
    return None


def _load_json_records(path: Path) -> Iterator[dict[str, Any]]:
    """Normalise a JSON file to a stream of dicts.

    Accepts a list of objects, a single object, or a dict-of-columns
    (``{"a": [1,2], "b": [3,4]}`` -> two records). NDJSON (one JSON object per
    line) is detected and streamed too.
    """
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return
    # NDJSON: first char is not a list/JSON-doc wrapper but each line parses.
    if "\n" in text and not text.lstrip().startswith("["):
        lines = [ln for ln in text.splitlines() if ln.strip()]
        try:
            parsed = [json.loads(ln, parse_constant=_nan_to_none) for ln in lines]
            for obj in parsed:
                yield obj if isinstance(obj, dict) else {"value": obj}
            return
        except json.JSONDecodeError:
            pass  # not NDJSON — fall through to whole-document parse

    data = json.loads(text, parse_constant=_nan_to_none)
    if isinstance(data, list):
        for obj in data:
            yield obj if isinstance(obj, dict) else {"value": obj}
    elif isinstance(data, dict):
        # dict-of-columns -> row records, else a single record
        if data and all(isinstance(v, list) for v in data.values()):
            n = max(len(v) for v in data.values())
            for i in range(n):
                yield {k: (v[i] if i < len(v) else None) for k, v in data.items()}
        else:
            yield data
    else:
        yield {"value": data}


def _load_tabular(path: Path, kind: str) -> Iterator[dict[str, Any]]:
    """csv / excel via pandas, yielding NaN-free record dicts."""
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "pandas is required for CSV/Excel input — pip install -r requirements.txt"
        ) from exc

    frame = pd.read_csv(path) if kind == "csv" else pd.read_excel(path)
    # NaN is not JSON-serialisable; None is. `where(notnull)` swaps them out.
    frame = frame.where(frame.notnull(), None)
    for row in frame.to_dict(orient="records"):
        yield row


# --------------------------------------------------------------------------- #
# media
# --------------------------------------------------------------------------- #

def load_media(path: Path, media_mode: str = "ref") -> Iterator[dict[str, Any]]:
    """Yield one payload per image, or one per frame for a video.

    ``media_mode``:
      "ref" -> payload carries a file ``uri`` (small; receiver fetches bytes)
      "b64" -> payload carries ``data_b64`` (self-contained; large)
    """
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        yield _image_payload(path, media_mode)
    elif ext in VIDEO_EXT:
        yield from _video_payloads(path, media_mode)
    else:  # pragma: no cover
        raise UnsupportedInput(path.name)


def _image_payload(path: Path, media_mode: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "media_type": "image",
        "path": str(path),
        "frame_idx": 0,
        "format": path.suffix.lower().lstrip("."),
    }
    width, height = _image_dims(path)
    if width is not None:
        payload["width"], payload["height"] = width, height
    if media_mode == "b64":
        payload["data_b64"] = base64.b64encode(path.read_bytes()).decode("ascii")
    else:
        payload["uri"] = path.resolve().as_uri()
    return payload


def _image_dims(path: Path) -> tuple[int | None, int | None]:
    """Best-effort (width, height) — via cv2 if present, else unknown."""
    try:
        import cv2  # type: ignore
    except ImportError:
        return None, None
    img = cv2.imread(str(path))
    if img is None:
        return None, None
    h, w = img.shape[:2]
    return int(w), int(h)


def _video_payloads(path: Path, media_mode: str) -> Iterator[dict[str, Any]]:
    """One payload per decoded frame. Requires OpenCV."""
    try:
        import cv2  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "opencv-python is required for video input — pip install -r requirements.txt"
        ) from exc

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"could not open video {path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            payload: dict[str, Any] = {
                "media_type": "video_frame",
                "path": str(path),
                "frame_idx": idx,
                "fps": round(fps, 3) if fps else None,
                "width": width,
                "height": height,
                "format": path.suffix.lower().lstrip("."),
            }
            if media_mode == "b64":
                ok_enc, buf = cv2.imencode(".jpg", frame)
                if ok_enc:
                    payload["frame_format"] = "jpg"
                    payload["data_b64"] = base64.b64encode(buf.tobytes()).decode("ascii")
            else:
                # Reference mode: point back at the source video + frame index.
                payload["uri"] = path.resolve().as_uri()
            yield payload
            idx += 1
    finally:
        cap.release()


def iter_payloads(path: Path, media_mode: str = "ref") -> Iterator[dict[str, Any]]:
    """Dispatch ``path`` to the right loader and yield its raw payloads."""
    fam = family_of(path)
    if fam == "timeseries":
        yield from load_timeseries(path)
    else:
        yield from load_media(path, media_mode)
