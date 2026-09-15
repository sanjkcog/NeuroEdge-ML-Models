"""Storyboard schema — Pydantic models matching marketing-storyboard-planner agent output.

Studio ADR-0062 D-4 adds a *surface* per scene. ``footage`` is a stock clip (the only kind before);
``screen`` is a screen recording you supply; ``vector`` is a stock illustration rendered with a slow move.
Every field added here defaults, so a storyboard written before D-4 still validates unchanged.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator

Beat = Literal["hook", "problem", "solution", "how", "proof", "cta"]
Orientation = Literal["landscape", "portrait", "square"]
Transition = Literal["cut", "fade", "dissolve"]
AspectRatio = Literal["16x9", "1x1", "9x16"]
Surface = Literal["footage", "screen", "vector"]
MediaKind = Literal["video", "image"]


class Brand(BaseModel):
    logo_path: str
    intro_logo_duration_s: float = 5.0
    outro_logo_duration_s: float = 5.0
    primary_color_hex: str = "#0066CC"
    caption_font: str = "Inter"
    #: Rendered on the intro/outro title cards when no logo file exists. Empty falls back to a
    #: title made from the slug, so an untitled video is never branded as another product.
    title: str = ""
    subtitle: str = ""


class Scene(BaseModel):
    id: int
    beat: Beat
    start_s: float
    duration_s: float = Field(gt=0)
    voiceover: str
    caption: str
    #: Required for ``footage`` and ``vector``; empty for ``screen`` (there is nothing to search).
    footage_queries: list[str] = Field(default_factory=list, max_length=5)
    preferred_orientation: Orientation = "landscape"
    music_mood: str = "corporate-inspiring"
    transition_in: Transition = "cut"
    transition_out: Transition = "cut"
    surface: Surface = "footage"
    #: A free label for a ``screen`` scene -- any non-empty string. The picture is your own screen
    #: recording, saved as ``scene_NN.webm`` where ``render`` looks for screen clips.
    screen: str | None = None
    #: ``<provider>:<id>`` -- a human's choice from the contact sheet, honoured over the ranking.
    pick: str | None = None
    #: Optional. Ids of the steps this scene narrates, for traceability; rendering never reads it.
    node_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_surface(self) -> Scene:
        if self.surface in ("footage", "vector") and not self.footage_queries:
            raise ValueError(f"Scene {self.id} has surface '{self.surface}' but no footage_queries")
        if self.surface == "screen" and not self.screen:
            raise ValueError(f"Scene {self.id} has surface 'screen' but names no screen")
        return self


class CTA(BaseModel):
    url: str
    display_text: str
    logo_lockup_at_end: bool = True


class Storyboard(BaseModel):
    version: str = "1.0"
    slug: str
    script_path: str
    audience: str
    total_duration_s: float = 180.0
    aspect_ratios: list[AspectRatio] = ["16x9", "1x1"]
    music_mood_primary: str = "corporate-inspiring"
    brand: Brand
    scenes: list[Scene]
    cta: CTA

    @model_validator(mode="after")
    def check_contiguity(self) -> Storyboard:
        total = 0.0
        for scene in self.scenes:
            if not math.isclose(scene.start_s, total, abs_tol=0.05):
                raise ValueError(f"Scene {scene.id} start_s={scene.start_s} not contiguous (expected {total:.3f})")
            total = round(total + scene.duration_s, 6)
        if not math.isclose(total, self.total_duration_s, abs_tol=0.5):
            raise ValueError(
                f"Sum of scene durations ({total}s) does not match total_duration_s ({self.total_duration_s}s)"
            )
        return self

    @classmethod
    def from_json_file(cls, path: str | Path) -> Storyboard:
        import json

        with open(path, encoding="utf-8") as f:
            return cls.model_validate(json.load(f))

    def to_json_file(self, path: str | Path) -> None:
        import json

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2)
            f.write("\n")


class FootageCandidate(BaseModel):
    provider: Literal["pexels", "pixabay"]
    provider_id: str
    url: str
    width: int
    height: int
    duration_s: float
    title: str = ""
    tags: list[str] = []
    local_path: str | None = None
    relevance_score: float = 0.0
    #: A stock clip, or a stock image (Studio ADR-0062 D-4 ``vector``). Images are rendered to motion.
    kind: MediaKind = "video"
    #: A preview image URL both providers return, and what the vision pass looks at (D-5).
    thumbnail: str = ""
    #: ``True`` when no relevance signal existed for this candidate -- no tags and no vision pass --
    #: so the score beside it is resolution and duration only. Shown rather than hidden (D-5).
    unscored: bool = False
    #: What the vision pass said, when it ran. Kept for the contact sheet.
    vision_note: str = ""


class SceneSelection(BaseModel):
    scene_id: int
    primary: FootageCandidate
    alternates: list[FootageCandidate] = []


class FootageManifest(BaseModel):
    slug: str
    selections: list[SceneSelection]
    #: Which providers actually answered, so "fetched from Pexels only" is visible (D-5).
    providers_answered: list[str] = []

    @classmethod
    def from_json_file(cls, path: str | Path) -> FootageManifest:
        import json

        with open(path, encoding="utf-8") as f:
            return cls.model_validate(json.load(f))

    def to_json_file(self, path: str | Path) -> None:
        import json

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2)
