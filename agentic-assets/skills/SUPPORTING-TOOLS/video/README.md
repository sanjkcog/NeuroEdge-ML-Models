# Video — the one place (TD-006)

All video capability in AgentForge lives under this folder and behind **one command**,
`/marketing-video`. There is deliberately **no second video pipeline** — new video work is a *mode*
of this one, not a fork.

## One command, three modes

| Mode | Invoke | What it makes |
|---|---|---|
| **marketing** (default) | `/marketing-video "<brief>"` | 3-min real-footage B2B explainer |
| **walkthrough** | `/marketing-video --technical-walkthrough` | screen-capture technical demo of AgentForge |
| **demo-overlay** | `/marketing-video --demo-overlay --base footage\|ai-gen "<flow>"` | base video + **required** sensor-gauge / data-flow overlays (physical-AI demo) |

**AI-imagery policy is mode-scoped:** refused in marketing mode (credibility = real footage),
permitted as the **base layer only** in demo-overlay mode (credibility = the accurate overlay). Every
base source clears license + brand review at the human gate. See `marketing-video-builder.md`.

## The skills here

| Skill | Role |
|---|---|
| `marketing-video-builder.md` | **hub** — the pipeline, all three modes, the demo-overlay compositing, the review gates |
| `manim-video.md` | programmatic animation engine — data-flow diagrams, sensor gauges (demo-overlay overlays) |
| `remotion-video-creation.md` | React-composited overlays — HTML/CSS/data-bound widgets as an alternative overlay engine |
| `video-editing.md` | raw-capture → tutorial cutting (used by walkthrough mode) |

## The rest of the video stack (same one place)

- **Command:** `commands/marketing-video.md` — the single entry point.
- **Agents:** `marketing-script-writer`, `marketing-storyboard-planner` (`agents/MARKETING/`).
- **Python:** `src/neuroedge_marketing/` — `validate`, `approve`, `fetch` (Pexels/Pixabay + contact sheet), `render` (per-scene TTS, captions, ffmpeg). Runs without Claude Code.
- **Runbook:** `agentic-assets/docs/guides/how_to_create_marketing_video.md` — every step offline, with how to verify it. No portal is needed.
- **Orchestrator:** the AgentForge **enablement** stage calls `/marketing-video --technical-walkthrough`.

## Demo-overlay in one line

Base (real footage *or* AI-generated) + a transparent manim/remotion overlay of the live data path,
composited with ffmpeg's `overlay` filter, gated on **overlay accuracy** (do the gauges and arrows
match the narrated flow?). `Higgsfield.ai` is under evaluation as an optional `--base ai-gen`
generator — spike, don't adopt blindly (license, brand-safety, clean compositing). Details in
`marketing-video-builder.md` → "Demo-overlay mode".
