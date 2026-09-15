"""The contact sheet: every scene's chosen and alternate media, with scores, for a person to review.

Ported from the NeuroEdge Studio (Studio ADR-0062 D-5). ``fetch`` writes it beside
``_selection.json`` as a static HTML file. It links provider thumbnails rather than embedding them,
so it weighs nothing and needs no asset copying. It is the evidence for the footage review: to
use another card for a scene, set ``pick`` on that scene in ``storyboard.json`` and render. The
pick must name one of the cards shown -- ``render`` chooses among clips already fetched, and falls
back to the outlined one otherwise. This module writes nothing authored.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

CONTACT_SHEET_NAME = "contact_sheet.html"


def render(storyboard: dict[str, Any], selection: dict[str, Any]) -> str:
    by_scene = {int(item["scene_id"]): item for item in selection.get("selections", [])}
    answered = ", ".join(selection.get("providers_answered") or []) or "none"
    parts = [
        "<!doctype html><meta charset='utf-8'><title>Contact sheet</title>",
        "<style>body{font:14px/1.4 system-ui;margin:24px;background:#0b1220;color:#e6edf3}"
        ".scene{margin:0 0 28px;padding:16px;border:1px solid #233;border-radius:8px}"
        ".row{display:flex;gap:12px;flex-wrap:wrap}.card{width:240px}"
        ".card img{width:100%;border-radius:4px;background:#000}"
        ".primary{outline:3px solid #2dd4bf}.meta{font-size:12px;color:#9fb0c0}"
        ".warn{color:#f7b955}code{color:#9fd}</style>",
        f"<h1>Contact sheet · {html.escape(str(storyboard.get('slug', '')))}</h1>",
        f"<p class='meta'>Providers that answered: {html.escape(answered)}. The outlined card is each "
        "scene's current choice. To use another card, set <code>pick: provider:id</code> on that scene in "
        "storyboard.json and render -- no need to fetch again. A pick naming none of these cards falls "
        "back to the outlined one.</p>",
    ]
    for scene in storyboard.get("scenes", []):
        sid = int(scene["id"])
        parts.append(f"<div class='scene'><h2>Scene {sid} · {html.escape(str(scene.get('caption', '')))}</h2>")
        parts.append(
            f"<p class='meta'>surface: {html.escape(str(scene.get('surface', 'footage')))}"
            + (f" · screen: {html.escape(str(scene.get('screen')))}" if scene.get("screen") else "")
            + (f" · pick: <code>{html.escape(str(scene.get('pick')))}</code>" if scene.get("pick") else "")
            + "</p>"
        )
        if scene.get("surface") == "screen":
            parts.append(
                f"<p class='meta'>A screen scene uses your own recording, scene_{sid:02d}.webm; "
                "nothing to choose here.</p></div>"
            )
            continue
        chosen = by_scene.get(sid)
        if not chosen:
            parts.append("<p class='warn'>No media was selected for this scene.</p></div>")
            continue
        parts.append("<div class='row'>")
        for index, candidate in enumerate([chosen["primary"], *chosen.get("alternates", [])]):
            klass = "card primary" if index == 0 else "card"
            thumb = html.escape(str(candidate.get("thumbnail") or ""))
            label = f"{candidate.get('provider')}:{candidate.get('provider_id')}"
            score = float(candidate.get("relevance_score") or 0.0)
            flag = " <span class='warn'>unscored</span>" if candidate.get("unscored") else ""
            note = html.escape(str(candidate.get("vision_note") or ""))
            parts.append(
                f"<div class='{klass}'>"
                + (f"<img src='{thumb}' alt=''>" if thumb else "<div class='meta'>(no thumbnail)</div>")
                + f"<div class='meta'><code>{html.escape(label)}</code> · {html.escape(str(candidate.get('kind', 'video')))} · "
                f"{html.escape(str(candidate.get('width')))}×{html.escape(str(candidate.get('height')))} · score {score:.2f}{flag}</div>"
                + (f"<div class='meta'>{note}</div>" if note else "")
                + "</div>"
            )
        parts.append("</div></div>")
    return "\n".join(parts) + "\n"


def write(storyboard: dict[str, Any], selection: dict[str, Any], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(storyboard, selection), encoding="utf-8")
    return out_path
