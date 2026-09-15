# /marketing-video — The one video builder (marketing · walkthrough · demo-overlay)

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /marketing-video · Skills: marketing-video-builder`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SUPPORTING-TOOLS/video/marketing-video-builder.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Your Job

This is the **single entry point for all video capability** (TD-006 consolidation) — do not fork a
second pipeline. It runs one of three **modes**, all sharing the script → storyboard → **human review
gate** → assemble → TTS → captions → ffmpeg spine:

| Mode | Flag | Base layer | Overlay | Use |
|---|---|---|---|---|
| **marketing** (default) | *(none)* | real footage (Pexels/Pixabay) | brand logo only | 3-min B2B explainer from a brief |
| **walkthrough** | `--technical-walkthrough` | screen capture | captions | technical SDLC-flow demo of AgentForge itself |
| **demo-overlay** | `--demo-overlay` | footage **or** AI-generated (`--base`) | **required**: sensor-gauge + data-flow animation (manim/remotion) | end-to-end "physical-AI" demo (e.g. sensor → edge → model → agent → action) |

**AI-imagery policy is mode-scoped, and explicit — not a silent reversal.** *marketing* mode stays
**real-footage-only** (enterprise credibility; AI base is refused there). *demo-overlay* mode permits
an **AI-generated base layer** because the value there is the **overlay** (the animated data flow),
not the base — but every base source (footage or AI-gen) still passes its own license + brand-safety
review at the human gate.

Do NOT skip the human review gate. License compliance and brand safety depend on it.

The gates are enforced in code. `fetch` refuses until `approve --stage script` has stamped the storyboard,
and `render` refuses until `approve --stage footage` has stamped the fetched selection. Run `approve` only
after the person has actually reviewed — it records their decision; it does not make one.

No portal is needed or assumed, and there is no `/demo-video`: a Studio-style recorded demo (narrated from
a recorded run of a use case and captured from a portal) needs the NeuroEdge Studio and is not part of this
command. The step-by-step offline runbook, with how to verify each step, is
`agentic-assets/docs/guides/how_to_create_marketing_video.md`.

For the demo-overlay compositing details (base + manim/remotion overlays → ffmpeg), read the
`marketing-video-builder` skill's "Demo-overlay mode" section and the `manim-video` /
`remotion-video-creation` skills it points to.

---

## Phase 0 — DETECT

Parse `$ARGUMENTS`:

| Pattern | Action |
|---|---|
| Brief text provided (≥ 20 words) | Extract product, audience, pain, CTA — proceed |
| Brief is short or vague (< 20 words) | Ask one consolidated question (see below) |
| Empty / blank | Ask: "What product or topic should the video cover? Who is the target buyer?" |
| `--draft` flag | Use OpenAI mini-tts for the VO (cheap iteration). Default for first render. |
| `--final` flag | Use ElevenLabs Multilingual v2 for the VO. Use for sign-off renders only. |
| *(aspect ratios)* | There is no `--aspects` flag. Aspects come from the storyboard's `aspect_ratios`; only `16x9` and `1x1` are rendered (`9x16` passes validation but is never produced). |
| `--technical-walkthrough` flag | Technical SDLC-flow video instead of a B2B pitch. No brief needed — content is sourced from `docs/guides/how_to_run_agentforge.md`. Switches Phase 3 to Technical Walkthrough Mode and Phase 6 to screen capture instead of stock footage (see below). Not compatible with `--draft`/`--final`'s TTS-only distinction being the only variable — everything else in this mode changes too. |
| `--demo-overlay` flag | **Demo-overlay mode.** Base video + **required** data overlays (sensor gauges, labeled flow animation). Switches Phase 6 to base-layer acquisition per `--base`, and adds an overlay-generation + composite step (see "Demo-overlay mode" in the skill). Needs a short brief describing the flow to depict (e.g. `"cooling-tower vibration+temp → edge device → CNN → agent → shutdown action"`). |
| `--base footage\|ai-gen` | **Demo-overlay only.** Chooses the base layer: `footage` (default — Pexels/Pixabay of the real scene) or `ai-gen` (an AI video generator for a scene real footage can't supply). Either way the base passes license/brand review at the gate. |

When `--technical-walkthrough` is set, skip Phase 1 EXTRACT and Phase 2 PREP's brief-based
slug (use slug `agentforge-technical-walkthrough-<YYYYMMDD>` instead) — there is no brief to
parse, the source is `docs/guides/how_to_run_agentforge.md` (EP-09, US-09-02).

When `--demo-overlay` is set, use slug `demo-overlay-<flow-slug>-<YYYYMMDD>`. The brief describes the
**flow to depict**, not a product pitch; Phase 3 writes a short narration for the flow, Phase 6
acquires the base layer per `--base`, and a new **Phase 6b** generates and composites the overlays
(see "Demo-overlay mode" in the `marketing-video-builder` skill). `--base ai-gen` is incompatible
with the marketing-mode footage-license checklist — it uses the AI-base review checklist instead.

Print scope before proceeding:

```
Product:     <name>
Audience:    <buyer>
Industry:    <vertical>
Mode:        draft | final
Aspects:     16x9, 1x1
Output dir:  data/output/marketing_videos/<slug>/
```

---

## Phase 1 — EXTRACT

From the brief, extract:

| Field | How |
|---|---|
| Product name | First proper noun, or after "for/about <product>" |
| Audience | "for business owners", "for plant managers", "for CXOs" — pick the most specific |
| Industry | Keywords: manufacturing, factory, plant → manufacturing; hospital, clinic, OR → healthcare; store, retail, POS → retail; warehouse, logistics → logistics |
| Primary pain | After "the problem is", "they struggle with", "tired of" — or infer from context |
| Proof point | Any numeric stat in the brief ("from 6 months to 2 weeks"), customer quote, or partner |
| CTA URL | First URL in brief. There is no default — if the brief has none, ask for a real one. Never invent or placeholder a URL: the outro title card prints `cta.url` |

If any of `product name`, `audience`, `industry`, `CTA URL` is missing, ask in ONE consolidated message:

```
I extracted from your brief:
  - Product:  <name or "?">
  - Audience: <buyer or "?">
  - Industry: <vertical or "?">
  - CTA URL:  <url or "?">

Please fill in any "?" so I can write the script:

1. Product name?
2. Target buyer (CXO / VP Eng / Plant Manager / etc.)?
3. Industry / vertical?
4. CTA URL (where viewers should click)?
5. (Optional) Proof point or stat to feature?

Reply with answers in order.
```

---

## Phase 2 — PREP

0. **Domain plugins (auto-discovered, brief-based mode only — skip entirely when
   `--technical-walkthrough` is set, since that mode documents AgentForge itself, not a
   client product).** Product/client-specific context lives in custom plugins under
   `agentforge_custom_plugin/<Name>/`. Self-discover: run
   `python agentforge_custom_plugin/discover_plugins.py --stage enablement` (or find
   `agentforge_custom_plugin/*/plugin.json` directly and read any plugin whose
   `wiring.auto_load` is not `false`), and if the brief's product matches an active
   plugin, prefer its real `context/DOMAIN.md`/proof-point/persona content over a
   generic or placeholder proof point in Phase 1 EXTRACT. Absence of plugins is normal —
   never a blocker.

1. Compute slug: `<product>-<audience>-<YYYYMMDD>` (lowercase, hyphens). e.g. `neuroedge-businessowners-20260605`.

2. Create output directory:
   ```bash
   mkdir -p "data/output/marketing_videos/<slug>"
   ```

3. Save the brief as `data/output/marketing_videos/<slug>/brief.md`.

4. Check env vars (silently — print SET/MISSING, never a value):
   ```bash
   python -X utf8 -c "
   import os
   keys = ['PEXELS_API_KEY', 'PIXABAY_API_KEY', 'OPENAI_API_KEY', 'ELEVENLABS_API_KEY', 'ELEVENLABS_VOICE_ID', 'ANTHROPIC_API_KEY']
   for k in keys:
       print(k, 'SET' if os.getenv(k) else 'MISSING')
   "
   ```
   If **both** `PEXELS_API_KEY` and `PIXABAY_API_KEY` are MISSING → block: `fetch` has no provider and exits 1
   (`No working footage providers`). Either key alone works. `vector` scenes need `PIXABAY_API_KEY` — Pexels
   has no illustrations — so with Pexels alone those scenes get no selection.
   If `OPENAI_API_KEY` is MISSING and mode=draft → block, or offer `--tts-provider chatterbox` (local, no key).
   If `ELEVENLABS_API_KEY` or `ELEVENLABS_VOICE_ID` is MISSING and mode=final → fall back to draft mode and warn.
   `ANTHROPIC_API_KEY` (else `OPENAI_API_KEY`) turns on vision ranking of clips during fetch — optional;
   tell the user which applies, and that it costs one model call per candidate (`--no-vision` skips it).
   Tell the user to export missing keys as environment variables in the shell that runs the pipeline. The
   package reads the process environment only: it does not load `.env` and does not read
   `.claude/settings.local.json`.

5. Check dependencies and report what is missing — do not install into the user's environment unasked:
   `ffmpeg -version`, and `pip install -r agentic-assets/requirements-agentforge.txt` (every
   AgentForge Python package, the local Chatterbox voice included).

---

## Phase 3 — SCRIPT

**If `--technical-walkthrough` is set**, spawn `marketing-script-writer` in Technical
Walkthrough Mode instead (skips the brief-based inputs entirely):

```
Mode: technical-walkthrough
Source narration: docs/guides/how_to_run_agentforge.md
Stages to cover: invocation, auto-spawn, gate stop/approval, --status, --resume, sprint/budget report
Output: data/output/marketing_videos/<slug>/script.md
```

Otherwise, spawn the `marketing-script-writer` agent with:

```
Brief: <data/output/marketing_videos/<slug>/brief.md>
Product: <name>
Audience: <buyer>
Industry: <vertical>
Pain: <pain>
Proof: <proof or placeholder>
CTA URL: <url>
Tone: calm-authoritative
Output: data/output/marketing_videos/<slug>/script.md
```

Wait for the agent to return the script summary (path + word count + estimated VO duration).

---

## Phase 4 — STORYBOARD

Spawn the `marketing-storyboard-planner` agent with:

```
Script: data/output/marketing_videos/<slug>/script.md
Industry: <vertical>
Brand assets: assets/brand/  (if exists, else placeholder)
Output: data/output/marketing_videos/<slug>/storyboard.json
```

Wait for the agent to return the storyboard summary (scene count + total duration + query count).

Then validate it before a person spends time reviewing it:

```bash
PYTHONPATH=src python -X utf8 -m neuroedge_marketing.cli validate \
  --storyboard data/output/marketing_videos/<slug>/storyboard.json \
  --screen-dir data/output/marketing_videos/<slug>/footage
```

Exit 0 is valid. Exit 1 names the broken scene and field, or a screen scene whose recording is missing —
send storyboard problems back to the planner, and ask the user for missing recordings.

---

## Phase 5 — HUMAN REVIEW GATE (REQUIRED — DO NOT SKIP)

Print to the user:

```
=== READY FOR REVIEW ===

Script:     data/output/marketing_videos/<slug>/script.md
Storyboard: data/output/marketing_videos/<slug>/storyboard.json

REVIEW CHECKLIST:
[ ] Script reads cleanly when read aloud
[ ] CTA URL is correct and live
[ ] Captions read on mute (LinkedIn check)
[ ] Industry context is right for the buyer
[ ] No competitor names in copy

Reply "approve" to proceed to footage fetch + render.
Reply "edit script" / "edit storyboard" to iterate.
Reply "abort" to stop.
```

Wait for explicit "approve". Do NOT proceed without it.

When the person approves, record it — this is what unblocks `fetch`:

```bash
PYTHONPATH=src python -X utf8 -m neuroedge_marketing.cli approve --stage script \
  --storyboard data/output/marketing_videos/<slug>/storyboard.json
```

Editing `storyboard.json` afterwards voids the approval: review again, then re-approve.

---

## Phase 6 — FOOTAGE FETCH

**If `--technical-walkthrough` is set**, skip the Pexels/Pixabay pipeline below entirely
— a technical SDLC walkthrough needs a real screen recording, not stock footage. Follow
`skills/SUPPORTING-TOOLS/video/video-editing.md`'s raw-capture-to-tutorial guidance:

1. Print the capture checklist to the user. `docs/guides/how_to_run_agentforge.md` has no
   capture checklist of its own; this one is derived from that guide's S17 row (table
   "Canonical stage → code stage → owner → gate"), its "S17 walkthrough needs a human"
   note, the `--status` / `--resume` flags under "Running Agentic Automated mode", and the
   sprint-mechanics row under "Running Agentic Manual mode":
   ```
   === SCREEN CAPTURE CHECKLIST (technical walkthrough) ===

   [ ] Clean checkout, terminal + editor visible, 1920x1080
   [ ] Record: python install.py --project .
   [ ] Record: /agentforge "<a real objective>" through at least one gate approval
   [ ] Record: --status
   [ ] Record: closing the session, then --resume
   [ ] Record: /sprint-report --burndown or /budget-report
   [ ] Save raw capture to data/output/marketing_videos/<slug>/footage/raw_capture.mp4

   This is a live, human-run capture — not something this command can generate on
   your behalf. Reply "captured" once footage/raw_capture.mp4 exists.
   ```
2. Wait for "captured". Do NOT proceed without the raw capture file present.
3. Hand `raw_capture.mp4` + `script.md` to the `video-editing` skill's cut/structure
   workflow to segment the raw capture into the 7 beats from the script's Stage-by-Stage
   table, instead of running `neuroedge_marketing.cli fetch`.
4. Skip the REVIEW CHECKLIST below (it's Pexels/Pixabay-license-specific) — use a
   footage-specific checklist instead: no visible API keys/credentials on screen, no
   real client data in any use-case example shown, terminal font size legible at 1080p.

Otherwise, once approved, run the Python pipeline:

```bash
PYTHONPATH=src python -X utf8 -m neuroedge_marketing.cli fetch \
  --storyboard data/output/marketing_videos/<slug>/storyboard.json \
  --output-dir data/output/marketing_videos/<slug>/footage \
  --providers pexels,pixabay \
  --clips-per-scene 3
```

The pipeline:
1. For each non-screen scene, runs every query through each provider named in `--providers` — neither is
   primary (videos from Pexels/Pixabay; `vector` scenes use Pixabay vectors and illustrations). A provider
   with no key is skipped and named in the result line
2. Merges the candidates and dedupes by provider + id (the same clip returned by two queries counts once)
3. Ranks by relevance — a vision model scores thumbnails when `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is set, else tag match — plus resolution + duration fit; `--providers` order breaks near-ties; the hook scene becomes a one-clip-per-query journey montage
4. Downloads the top `--clips-per-scene` (default 3) to `footage/scene_NN/`. A hook scene with more than one
   query is the exception: one clip per query, not bounded by `--clips-per-scene`
5. Caches search responses in `data/cache/footage/` for 24 h (Pixabay's terms), keyed by provider, query,
   page and orientation; a clip already on disk is not downloaded again
6. Writes `footage/_selection.json`: per scene, a `primary` and the other downloaded clips as `alternates`
7. Writes `footage/contact_sheet.html` — every scene's choice and alternates, with thumbnails and scores

`fetch` exits 1 if any scene got no selection.

Print the candidate manifest to the user:

```
=== FOOTAGE FETCHED ===
Contact sheet: data/output/marketing_videos/<slug>/footage/contact_sheet.html

Scene 1 (hook):    factory_aerial_wide.mp4    [Pexels #12345, 1920x1080]
                   Alternates: <n> more (see _selection.json)
Scene 2 (problem): warehouse_busy.mp4         [Pixabay #67890, 1920x1080]
...

REVIEW CHECKLIST:
[ ] No identifiable people in endorsement positions
[ ] No competitor logos visible
[ ] No off-brand style/color in any clip
[ ] Footage matches scene tone

Reply "approve" to render. Reply "use <provider:id> for scene <N>" to pick an alternate from the contact sheet.
```

Wait for "approve". To use an alternate, set `"pick": "<provider>:<id>"` on that scene in
`storyboard.json` — no re-fetch and no re-approval needed: `render` chooses among the clips already
fetched, which this review covered. Then record the footage approval, which unblocks `render`:

```bash
PYTHONPATH=src python -X utf8 -m neuroedge_marketing.cli approve --stage footage \
  --storyboard data/output/marketing_videos/<slug>/storyboard.json \
  --footage-dir data/output/marketing_videos/<slug>/footage
```

Fetching again after this voids the footage approval.

---

## Phase 7 — RENDER

Once footage is approved **and** `approve --stage footage` has run, run:

```bash
PYTHONPATH=src python -X utf8 -m neuroedge_marketing.cli render \
  --storyboard data/output/marketing_videos/<slug>/storyboard.json \
  --footage-dir data/output/marketing_videos/<slug>/footage \
  --output-dir data/output/marketing_videos/<slug>/ \
  --tts-provider <openai|elevenlabs|chatterbox>
```

The pipeline:
1. Synthesizes one WAV per scene (OpenAI for drafts, ElevenLabs for finals, Chatterbox locally), measures
   each, and re-times the scenes so cuts land after sentences. The re-timed storyboard is written to
   `_work/storyboard.timed.json`; the approved `storyboard.json` is never rewritten
2. Writes captions from the approved voice-over text, timed to each scene's measured speech →
   `_work/captions_16x9.ass`, plus `_work/captions_1x1.ass` when `1x1` is in `aspect_ratios`.
   `--captions transcribe` uses faster-whisper instead
3. Trims each scene's clip (or the `pick`) to its re-timed duration and concats them (`_work/_concat.txt`)
4. If `brand.logo_path` exists, overlays the logo in the intro/outro windows; otherwise overlays nothing
5. Mixes the voice-over (with `--music` ducked under it, when given) and muxes it onto the picture
6. `16x9`: burns `captions_16x9.ass`; then, when there is no logo file, adds an intro title card
   (`brand.title` / `brand.subtitle`) and an outro card (`cta.display_text` over `cta.url`) → `video_16x9.mp4`
7. `1x1`: crops + scales the muxed body — before captions and title cards — to 1080×1080 and burns
   `captions_1x1.ass`. It has no title cards → `video_1x1.mp4`
8. Produces only the aspects in the storyboard's `aspect_ratios` (`9x16` is never rendered)

Optional `render` flags: `--voice <name>` (OpenAI voice, default `onyx`, or an ElevenLabs voice id; Chatterbox
ignores it) · `--say-as say_as.json` (how the voice pronounces ids; captions keep the literal
text) · `--voice-reference me.wav` and `--exaggeration 0.5` (Chatterbox only: speak in a recorded voice) ·
`--screen-dir <dir>` (where screen scenes' `scene_NN.webm` recordings are; default `--footage-dir`) ·
`--pad-s 0.6` · `--single-pass-voice` (whole script in one call, no re-timing) · `--captions transcribe`
(whisper captions instead of the approved text) · `--music <mp3>` (a path that does not exist renders without
music) · `--no-gate` (skip the approval check for scripted re-renders).
`render` exits 2 when either approval is missing or stale, naming which.

Render is expected to take 2–4 minutes on a developer laptop.

---

## Phase 8 — OUTPUT

Report to the user:

```
✓ Marketing video built — data/output/marketing_videos/<slug>/

  Product:      <name>
  Audience:     <buyer>
  Duration:     <video_16x9.mp4 length from ffprobe — the re-timed plan plus any title cards>
  Word count:   <words>
  Scenes:       <count>
  TTS:          <openai gpt-4o-mini-tts | elevenlabs eleven_multilingual_v2 | chatterbox (local)>
  Aspect ratios: <the aspects that rendered, from the storyboard's aspect_ratios>

  Deliverables:
  → video_16x9.mp4   (1920x1080, <size>)  — YouTube, sales deck
  → video_1x1.mp4    (1080x1080, <size>)  — LinkedIn feed (only if 1x1 is in aspect_ratios)
  → script.md                              — for handoff to brand team
  → storyboard.json                        — for re-render with edits

  Next steps:
  → Watch on phone and laptop before sharing
  → /marketing-video --final <brief>       — re-render with ElevenLabs for sign-off
```

---

## Iteration Loop

If the user wants to iterate after watching:

| User says | Do this |
|---|---|
| "rewrite the hook" / "change the CTA" | Re-spawn `marketing-script-writer` with the edits and carry them into `storyboard.json` (`voiceover`, `cta`) — captions come from `voiceover`, not `script.md`. `validate`, review, `approve --stage script` (the edit voided it), `render`. No re-fetch: the footage approval holds while `_selection.json` is unchanged |
| "swap scene 4" | Set `"pick": "<provider>:<id>"` on scene 4 to one of its clips on the contact sheet, then `render` — no re-fetch, no re-approval. If none fit: edit scene 4's `footage_queries`, `validate`, `approve --stage script`, re-run `fetch` — there is no per-scene fetch, so every scene is fetched and re-ranked again (cached searches and clips on disk are reused; the vision pass runs again, and other scenes' primaries can change). Review the new contact sheet, `approve --stage footage`, `render` |
| "shorter" | Ask `marketing-script-writer` for fewer words — `render` re-times every scene to its measured speech, so length follows the words, not `total_duration_s`. Update the storyboard, `validate`, re-approve, re-run `fetch` if scenes or queries changed, `render` |
| "different voice" | Re-render with `--voice <name>` (OpenAI voice, or an ElevenLabs voice id); for Chatterbox use `--voice-reference <wav>` — it ignores `--voice` |
| "make it final" | Re-render with `--tts-provider elevenlabs` (needs `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID`), or `chatterbox` locally |

---

## Notes

- Never fabricate proof points or customer names — use placeholders and flag for human fill-in
- AI-generated imagery is **refused in marketing mode** (real footage only, for credibility) but
  **permitted as the base layer in demo-overlay mode** via `--base ai-gen` — each base source still
  clears license + brand review at the human gate (mode-scoped policy, see "Your Job")
- Always honor the two human-review gates (script+storyboard, then footage)
- Captions burned in by default — LinkedIn autoplay is muted
- The skill file is the source of truth for structure rules — read it if unsure
- Brief writers should target ONE buyer persona, not two — multi-persona videos test worse in A/B
