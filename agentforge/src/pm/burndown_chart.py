#!/usr/bin/env python3
"""burndown_chart.py — self-contained HTML burn-down/velocity chart (EP-08, US-08-06).

The existing `/sprint-report --burndown` markdown table (skills/SDLC/pm/
sprint-reporting.md) is a single-instant snapshot — committed/delivered/remaining as of
now. A real burn-down *chart* needs history, which `sprint_state.SprintState.
burndown_snapshots` now provides (appended on every PM-lane `refresh()` call). This
module renders that history as an inline SVG line chart, wrapped in a self-contained
HTML page — no external requests, no CDN, no `<link>`/remote `<script>`, mirroring the
same zero-dependency posture `neuroedge_productdoc.render` already established for
`docs/guides/*.html` and this system's own terminal-only burn-down table.

Pure functions of their inputs — no caching, so regenerating after a fresh PM-lane
refresh always reflects the latest snapshot (same "never emit a stale document"
contract `neuroedge_productdoc` already established).
"""

from __future__ import annotations

import html
from pathlib import Path

from sprint_state import BurndownSnapshot, SprintState

_WIDTH = 640
_HEIGHT = 320
_PAD_LEFT = 50
_PAD_RIGHT = 20
_PAD_TOP = 20
_PAD_BOTTOM = 40

_STYLE = """
body { font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       margin: 0; padding: 2rem; background: #0b0e14; color: #e6e6e6; }
main { max-width: 720px; margin: 0 auto; }
h1 { font-size: 1.4rem; margin: 0 0 0.25rem; }
.meta { color: #9aa4b2; font-size: 0.9rem; margin-bottom: 1.25rem; }
svg { width: 100%; height: auto; background: #11151c; border-radius: 8px; }
.axis { stroke: #3a4150; stroke-width: 1; }
.grid { stroke: #232833; stroke-width: 1; }
.ideal { stroke: #5b6472; stroke-width: 1.5; stroke-dasharray: 6 4; fill: none; }
.actual { stroke: #4da3ff; stroke-width: 2.5; fill: none; }
.point { fill: #4da3ff; }
.label { fill: #9aa4b2; font-size: 12px; }
.velocity { margin-top: 1rem; font-size: 0.95rem; }
.empty { color: #9aa4b2; font-style: italic; }
footer { margin-top: 1.5rem; font-size: 0.8rem; color: #6b7280; }
"""


def _scale(value: float, max_value: float, plot_height: float) -> float:
    """Y position (SVG coordinates, 0 at top) for `value` against `max_value`."""
    if max_value <= 0:
        return _PAD_TOP + plot_height
    fraction = max(0.0, min(1.0, value / max_value))
    return _PAD_TOP + (1.0 - fraction) * plot_height


def render_burndown_svg(
    snapshots: list[BurndownSnapshot], *, capacity_points: float
) -> str:
    """An inline `<svg>` burn-down line chart: actual remaining-points history plus a
    dashed ideal-trend reference from the first snapshot's value down to zero.

    A sprint with no snapshots yet (no PM-lane refresh has fired) renders an explicit
    "no data yet" message rather than a broken or empty chart — mirrors this system's
    own "state a boundary explicitly, never emit a silent blank" convention (e.g.
    US-08-06's own first-sprint-no-velocity boundary case).
    """
    if not snapshots:
        return '<p class="empty">No burn-down data yet — the PM lane records a snapshot on every stage transition; none has happened yet.</p>'

    plot_width = _WIDTH - _PAD_LEFT - _PAD_RIGHT
    plot_height = _HEIGHT - _PAD_TOP - _PAD_BOTTOM
    max_value = max(capacity_points, max(s.remaining_points for s in snapshots), 1.0)

    n = len(snapshots)
    xs = [
        _PAD_LEFT + (i * plot_width / (n - 1) if n > 1 else plot_width / 2)
        for i in range(n)
    ]
    ys = [_scale(s.remaining_points, max_value, plot_height) for s in snapshots]

    actual_path = " ".join(
        f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(zip(xs, ys))
    )
    points_markup = "\n".join(
        f'<circle class="point" cx="{x:.1f}" cy="{y:.1f}" r="3.5"/>' for x, y in zip(xs, ys)
    )

    ideal_start_y = _scale(snapshots[0].remaining_points, max_value, plot_height)
    ideal_end_y = _scale(0, max_value, plot_height)
    ideal_end_x = xs[-1] if n > 1 else xs[0]
    ideal_path = f"M{xs[0]:.1f},{ideal_start_y:.1f} L{ideal_end_x:.1f},{ideal_end_y:.1f}"

    axis_y = _PAD_TOP + plot_height
    grid_lines = "\n".join(
        f'<line class="grid" x1="{_PAD_LEFT}" y1="{_PAD_TOP + plot_height * frac:.1f}" '
        f'x2="{_WIDTH - _PAD_RIGHT}" y2="{_PAD_TOP + plot_height * frac:.1f}"/>'
        for frac in (0.25, 0.5, 0.75)
    )

    return f"""<svg viewBox="0 0 {_WIDTH} {_HEIGHT}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Burn-down chart">
{grid_lines}
<line class="axis" x1="{_PAD_LEFT}" y1="{_PAD_TOP}" x2="{_PAD_LEFT}" y2="{axis_y:.1f}"/>
<line class="axis" x1="{_PAD_LEFT}" y1="{axis_y:.1f}" x2="{_WIDTH - _PAD_RIGHT}" y2="{axis_y:.1f}"/>
<path class="ideal" d="{ideal_path}"/>
<path class="actual" d="{actual_path}"/>
{points_markup}
<text class="label" x="{_PAD_LEFT}" y="{_PAD_TOP - 4}">{max_value:.0f} pts</text>
<text class="label" x="{_PAD_LEFT}" y="{axis_y + 14:.1f}">0 pts</text>
</svg>"""


def render_burndown_html(
    sprint: SprintState, *, velocity: float | None = None, velocity_sprint_count: int = 0
) -> str:
    """Wrap `render_burndown_svg` in a self-contained HTML page — no external
    requests, matching `neuroedge_productdoc.render_html`'s own zero-dependency
    precedent for `docs/guides/*.html`."""
    chart = render_burndown_svg(sprint.burndown_snapshots, capacity_points=sprint.capacity_points)

    if velocity is None:
        velocity_line = "no historical velocity — first sprint"
    else:
        velocity_line = f"{velocity:.1f} pts/sprint (from {velocity_sprint_count} closed sprint{'s' if velocity_sprint_count != 1 else ''})"

    committed = sprint.committed_points()
    delivered = committed - sprint.undelivered_points()

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Sprint Burn-down: {html.escape(sprint.sprint_id)} | NeuroEdge AgentForge</title><style>
{_STYLE}
</style></head>
<body>
<main>
<h1>Sprint Burn-down: {html.escape(sprint.sprint_id)}</h1>
<p class="meta">Committed {committed:.0f} pts &middot; Delivered {delivered:.0f} pts &middot; Remaining {sprint.undelivered_points():.0f} pts</p>
{chart}
<p class="velocity">Velocity: {html.escape(velocity_line)}</p>
</main>
<footer>NeuroEdge AgentForge &middot; Standalone chart, no external requests. Generated by <code>/sprint-report --burndown</code> at S12.</footer>
</body></html>
"""


def write_burndown_chart(
    sprint: SprintState,
    out_path: str | Path,
    *,
    velocity: float | None = None,
    velocity_sprint_count: int = 0,
) -> Path:
    """Render and write the chart, returning the path written."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        render_burndown_html(sprint, velocity=velocity, velocity_sprint_count=velocity_sprint_count),
        encoding="utf-8",
        newline="\n",
    )
    return out_path
