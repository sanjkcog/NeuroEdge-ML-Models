---
name: marketing-video-builder
description: The single video builder (TD-006) with three modes — marketing (real-footage B2B explainer), walkthrough (screen-capture technical demo), and demo-overlay (base footage OR AI-generated video with required sensor-gauge / data-flow overlays composited via manim/remotion + ffmpeg). AI voiceover, auto-captions, ffmpeg assembly, human review gate. Use for any video: marketing explainer, product demo, LinkedIn/YouTube cut, technical walkthrough, or an end-to-end physical-AI overlay demo. Reusable across Cognizant AI products.
origin: NeuroEdge AgentForge
---

# Marketing Video Builder

The one place all video is built. In its default **marketing** mode: turn a one-line product brief
into a 3-minute business-owner video (LinkedIn / YouTube / enterprise sales) from real Pexels/Pixabay
footage (license-clean, no attribution), AI voiceover, burned-in captions, branded intro/outro — no
AI-generated imagery in this mode. Two further modes (**walkthrough**, **demo-overlay**) share the
same spine; see "Video modes" below. AI-generated base video is permitted only in demo-overlay mode.

## When to Activate

- "Build a marketing video for <product>" → marketing mode
- "Create a 3-minute explainer about <topic>" → marketing mode
- "Make a LinkedIn cut showing <message>" → marketing mode
- "Produce a sales video for <buyer persona>" → marketing mode
- "Show the technical walkthrough / how AgentForge runs" → `--technical-walkthrough`
- "Build a demo of sensor → edge → model → agent, with the data overlaid on the video" → `--demo-overlay`
- `/marketing-video <brief>` (NeuroEdge command — the single video entry point)

## Video modes (this is the one video builder — TD-006)

All video capability lives here — do not fork a second pipeline. Three modes share one spine
(script → storyboard → **human review gate** → assemble → TTS → captions → ffmpeg):

| Mode | Command | Base layer | Overlay | AI base? |
|---|---|---|---|---|
| **marketing** | `/marketing-video` | real footage (Pexels/Pixabay) | brand logo | **refused** |
| **walkthrough** | `/marketing-video --technical-walkthrough` | screen capture | captions | n/a |
| **demo-overlay** | `/marketing-video --demo-overlay` | footage **or** AI-gen (`--base`) | **required** (sensor gauges, data-flow animation) | **permitted** |

**Mode-scoped AI-imagery policy (explicit, not a silent reversal).** In *marketing* mode the value is
credible real-world context, so AI-generated imagery is refused. In *demo-overlay* mode the value is
the **overlay** — the animated data flow superimposed on the scene — so an AI-generated base is
permitted when real footage can't supply the scene. Every base source, footage or AI-gen, still
passes its own license + brand-safety review at the human gate.

## Core Thesis (marketing mode)

For B2B explainers under 3 minutes, **structure beats production polish**. The 6-beat structure (hook → problem → solution → how → proof → CTA) is invariant — only the words and clips change. Automating the structure lets you iterate on message in minutes, not days.

Marketing mode uses **real footage** (not AI generation) because:
1. Identifiable industry context (factory floors, hospitals, warehouses) carries credibility AI cannot fake
2. License-clean catalogs (Pexels, Pixabay) cost $0 and require no attribution
3. AI-generated video still has the "uncanny shimmer" that signals "cheap" to enterprise buyers in 2026

(Demo-overlay mode relaxes rule 1 for the base layer only — see "Demo-overlay mode" below — because
there the credibility carrier is the accurate data overlay, not the backdrop.)

## The Pipeline

No portal, spec, or recorded run is needed — the user writes the brief, and every stage below runs offline.

```
Brief (one paragraph)                      ← the user writes it
  ↓
[marketing-script-writer agent]            → script.md   (6 beats, or Mode: step-list)
  ↓
[marketing-storyboard-planner agent]       → storyboard.json   (scenes: footage | vector | screen)
  ↓
neuroedge_marketing.cli validate           → exit 0 before a person spends time on it
  ↓
HUMAN REVIEW GATE 1 (script + storyboard)  → cli approve --stage script
  ↓
cli fetch   — Pexels/Pixabay, vision-ranked when a model key is set
            → footage/_selection.json + footage/contact_sheet.html     (refuses without gate 1)
  ↓
HUMAN REVIEW GATE 2 (footage, on the contact sheet) → cli approve --stage footage
  ↓
cli render  — per-scene TTS, re-timed → captions from the approved text → ffmpeg   (refuses without both)
  ↓
Output: video_16x9.mp4, video_1x1.mp4 (per the storyboard's aspect_ratios)
```

Both gates are enforced in code. An approval is a SHA-256 stamp of what was reviewed (`approval.json` beside
the storyboard), so editing the storyboard or fetching again voids it. `--no-gate` exists for scripted
re-renders: it skips the check, not the review.

Step-by-step runbook, with how to verify each step: `agentic-assets/docs/guides/how_to_create_marketing_video.md`.

## The 6-Beat 3-Minute Structure (180 s)

| # | Beat | Duration | Word count (at 150 wpm) | Purpose |
|---|---|---|---|---|
| 1 | **Hook** | 0–8 s | ~20 | State the pain in viewer's language. ONE striking visual. Captions carry it — LinkedIn autoplays muted. |
| 2 | **Problem** | 8–35 s | ~67 | Concrete pain: cost, time, risk, compliance. Stat or customer-language quote. |
| 3 | **Solution intro** | 35–60 s | ~62 | Name the product. ONE-sentence value prop. Don't list features yet. |
| 4 | **How it works** | 60–135 s | ~187 | 3 capability beats × ~25 s each. Each beat = one verb (Define / Benchmark / Deploy). |
| 5 | **Proof** | 135–160 s | ~62 | Logo wall, metric, customer quote. "From 6 months to 2 weeks." |
| 6 | **CTA** | 160–180 s | ~50 | Single CTA — URL + scheduled-demo link. No two-CTAs. |

**Scene count target: 8–11.** Average scene 16–22 s. Cuts faster than 10 s feel frantic; longer than 25 s feel static.

## Footage Sources

| Source | Role | Why |
|---|---|---|
| **Pexels Video API** | Video clips | Large commercial-use catalog, REST API, no attribution. Returns no tags, so without a vision pass its clips rank `unscored`. [pexels.com/api/documentation](https://www.pexels.com/api/documentation/) |
| **Pixabay Video + Image API** | Video clips, and vectors/illustrations for `vector` scenes | Distinct creator pool from Pexels. [pixabay.com/api/docs](https://pixabay.com/api/docs/) |
| Coverr | Manual hero shots only | No public API |
| Vecteezy | Skip | Free tier requires attribution |

Neither provider is primary. `fetch --providers` (default `pexels,pixabay`) names which to query, and its order
is a preference: earlier providers get a small tie-breaking bonus (0.05 at most), so a clearly better clip from
either still wins. Either key alone works; `vector` scenes need Pixabay. Candidates are merged and deduped by
provider + id.

**License gate — non-negotiable:**
- Pexels and Pixabay licenses prohibit using identifiable people in ways implying endorsement
- Every storyboard MUST pass a human-review step before render
- Downloaded candidates go straight to `footage/scene_NN/` — there is no staging folder. What holds them back
  is `render` refusing to run until `approve --stage footage` has stamped the `_selection.json` a person reviewed

**Caching requirement:** Pixabay terms require caching responses for 24 hours and not making redundant requests. The pipeline hashes `(provider, query, page, orientation)` and writes to `data/cache/footage/` under the folder you run from.

## Voiceover (TTS)

| Provider | Use | Cost (per 1M chars) |
|---|---|---|
| **OpenAI `gpt-4o-mini-tts`** | Drafts — iterate on script in seconds | ~$0.60/M tokens |
| **ElevenLabs Multilingual v2** | Final render — corporate quality | ~$99/M (Pro) |
| **Chatterbox** (local, MIT) | Drafts or sign-off, optionally in a recorded voice | $0 — runs on your machine |
| Azure Neural HD | Enterprise compliance alt (BAA) — **not implemented**: `tts.py` has no Azure adapter | $30/M |

Voice selection:
- B2B narration: low-pitched, measured pace, no upspeak
- ElevenLabs voices to consider: `Brian` (calm authority), `Daniel` (warm), `Adam` (default)
- OpenAI: `onyx` (deep), `nova` (neutral)

**Per scene, re-timed — the default.** `render` synthesizes one WAV per scene, measures it, and sets each
scene's duration to its audio plus `--pad-s`, so cuts land after sentences rather than through them. The
re-timed storyboard goes to `_work/storyboard.timed.json`; the approved `storyboard.json` is never
rewritten. `--single-pass-voice` restores whole-script synthesis.

| `--tts-provider` | Key | Notes |
|---|---|---|
| `openai` | `OPENAI_API_KEY` | drafts |
| `elevenlabs` | `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID` | sign-off renders |
| `chatterbox` | none — runs locally (MIT) | `requirements-voice.txt`. `--voice-reference me.wav` speaks in a recorded voice; `--exaggeration` sets expressiveness. Long text is chunked at sentence ends, because one long generation garbles. A voice reference is a biometric — keep it out of git |

**Pronunciation.** `--say-as say_as.json` maps ids to how they are spoken, e.g.
`{"CNC-PWT-014": "the CNC machine on line 14"}`. Only the voice hears it; captions keep the literal id.

## Captions

Always burned in for LinkedIn (autoplays muted). **The words are the approved script, not a transcription.**

1. Per-scene TTS measures each scene's speech (see *Voiceover*)
2. Each scene's approved `voiceover` text is split into lines and timed across that scene's measured speech —
   words placed by their share of the scene's characters, so a caption never spans two scenes
3. Format as `.ass` (Advanced SubStation Alpha) with brand styling — `_work/captions_16x9.ass`, plus
   `_work/captions_1x1.ass` when the storyboard asks for a 1:1 cut
4. Burn via ffmpeg `subtitles=` filter

Why not transcribe: re-transcribing the voice-over with `faster-whisper base.en` put the model's guesses on
screen — "rescoped" as "rescued", "faked" as "spaked" (first end-to-end render outside the Studio,
2026-09-15). `--captions transcribe` remains, and is the only option with `--single-pass-voice`, which has no
per-scene timing. If the voice says a word differently from the caption, fix the voice (`--say-as`), not the
caption.

Style:
- Position: bottom-third, centered
- Font: Inter or system sans-serif, 56px @ 1080p
- Color: white on a translucent black box (`BorderStyle=4`, `BackColour=&HB3000000` — about 30 % opaque)
- Per-line: 2 lines max, 38 chars/line, 4 s max per caption

## Background Music

No music ships with the package and nothing fetches it — there is no music provider. `render --music <file.mp3>`
takes one track you supply (license it yourself) for the whole video; a path that does not exist renders voice
only, without a warning. The storyboard's `music_mood` / `music_mood_primary` fields are labels for choosing that
track by hand — the assembler does not read them. Useful labels:
- `corporate-inspiring` — for hook/solution
- `tech-cinematic` — for how-it-works
- `uplifting-resolution` — for proof/CTA

With a track, `assembler.mix_audio` ducks it under the voice with `sidechaincompress`, then loudness-normalizes
the mix (without one, it only normalizes the voice):

```bash
ffmpeg -i music.mp3 -i vo.wav -filter_complex "
  [1:a]asplit=2[sc][mix];
  [0:a][sc]sidechaincompress=threshold=0.05:ratio=8:attack=20:release=250[duck];
  [duck][mix]amix=inputs=2:duration=longest:normalize=0[mixed];
  [mixed]loudnorm=I=-16:TP=-1.5:LRA=11[out]" -map "[out]" -ar 48000 -ac 2 audio.aac
```

## Assembly — ffmpeg filtergraph

**Why ffmpeg via Python `subprocess` and not MoviePy:**
- Windows reliability (no ImageMagick/font discovery pain)
- Every filter we need (concat, overlay, subtitles, sidechaincompress, scale+crop) is one line
- Zero dependency risk; ffmpeg is a system binary

**Concat pattern.** Every scene is first trimmed and scaled to its re-timed duration (`_work/scene_NN.mp4`), so
the manifest carries no `duration` lines. Entries are absolute, single-quoted POSIX paths: the concat demuxer
resolves a relative entry against the list file's own folder (`_work/`), not the working directory.

```text
# _work/_concat.txt — written by assembler.concat_clips
file '/abs/path/to/out/_work/scene_01.mp4'
file '/abs/path/to/out/_work/scene_02.mp4'
```

```bash
# Concat with re-encode (uniform codec parameters); audio is added later
ffmpeg -y -f concat -safe 0 -i _work/_concat.txt \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p -an _work/concat.mp4
```

**Brand overlay — only when `brand.logo_path` exists** (windows from `intro_logo_duration_s` / `outro_logo_duration_s`):

```bash
ffmpeg -i concat.mp4 -i logo.png -filter_complex \
  "[1:v]format=rgba,fade=in:st=0:d=0.5:alpha=1,fade=out:st=4.5:d=0.5:alpha=1[lg]; \
   [0:v][lg]overlay=W-w-40:40:enable='between(t,0,5)+between(t,175,180)'" branded.mp4
```

With no logo file (the usual case), nothing is overlaid; instead the captioned 16:9 body is bookended by an intro
title card (`brand.title` / `brand.subtitle`) and an outro card (`cta.display_text` over `cta.url`), joined with a
second concat list, `_work/_cards_concat.txt`.

**Burn captions (16:9):**

```bash
ffmpeg -i muxed.mp4 -vf "subtitles=captions_16x9.ass" captioned_16x9.mp4
```

**Render 1:1** — from the muxed body, *before* captions and title cards, so the 1:1 cut has no cards:

```bash
ffmpeg -i muxed.mp4 -vf "crop=ih:ih,scale=1080:1080,subtitles=captions_1x1.ass" video_1x1.mp4
```

## Demo-overlay mode

The flagship "physical-AI" demo: a **base video** with **data overlays composited on top** — sensor
gauges (vibration, temperature) superimposed on the scene, plus a labeled **flow animation**
(e.g. `sensor → edge device → ML model → agent → action`). The overlay is the point; the base is
context.

### Pipeline (extends the shared spine)

```
brief (the flow to depict)
  ↓  Phase 3: narration for the flow (not a sales pitch)
  ↓  Phase 6: acquire BASE layer per --base
  │     footage → existing Pexels/Pixabay fetch (real scene: plant, cooling tower, line)
  │     ai-gen  → an AI video generator for a scene footage can't supply (see Higgsfield note)
  ↓  Phase 6b: generate OVERLAY layer  (transparent, alpha)
  │     manim  → programmatic gauges + data-flow diagram animation  (skill: manim-video)
  │     remotion → React-composited overlays if you need HTML/CSS/data-bound widgets (skill: remotion-video-creation)
  │     Export overlays as a PNG sequence or a transparent (yuva420p) .mov
  ↓  Phase 7: COMPOSITE base + overlay + captions via ffmpeg, then TTS/music as usual
  ↓  HUMAN REVIEW GATE (base license/brand + overlay accuracy)
```

### Compositing (ffmpeg — same `overlay` filter as the brand logo, generalized)

```bash
# Base video + a transparent overlay clip (alpha-premultiplied), timed to the narration
ffmpeg -i base.mp4 -i overlay_alpha.mov -filter_complex \
  "[1:v]format=yuva420p[ov]; [0:v][ov]overlay=0:0:format=auto:enable='between(t,0,180)'" \
  -c:v libx264 -crf 20 composited.mp4
# then burn captions exactly as marketing mode does (subtitles=captions.ass)
```

For a PNG sequence instead of a transparent clip, feed it as an input
(`-framerate 30 -i overlay_%04d.png`) and overlay the same way.

### Overlay accuracy is the review criterion

The demo-overlay human gate checks the **overlay**, not stock-footage licensing: do the gauge values
and the flow arrows match the story being narrated? A wrong sensor reading or a mislabeled hop is the
failure mode here (the equivalent of a wrong CTA in marketing mode). Never fabricate a specific
telemetry number on screen — use clearly illustrative values and say so, or bind to real sample data.

### `--base ai-gen`: AI video generators (evaluate — Higgsfield.ai spike)

When real footage can't supply the scene, an AI video generator can produce the base layer.
**Higgsfield.ai** (AI image-to-video / VFX) is the current candidate — treat it as a **time-boxed
spike**, not an adopted dependency:
- Verify: commercial-use **license** terms, **brand-safety** (no unintended logos/people), and that its
  output **composites cleanly** under manim/remotion overlays (stable framing, no shimmer that fights
  the gauges).
- Keep it to the **base layer only** — the overlay (the credible part) is always manim/remotion.
- Record the decision; until it clears review, `--base ai-gen` documents the intent and the operator
  supplies the base clip manually.

## Required Environment Variables

| Variable | Required? | Purpose | Where to get |
|---|---|---|---|
| `PEXELS_API_KEY` | One of the two footage keys | Pexels video search | Free at [pexels.com/api](https://www.pexels.com/api/) |
| `PIXABAY_API_KEY` | One of the two footage keys; needed for `vector` scenes | Pixabay video + vector/illustration search | Free at [pixabay.com/api/docs](https://pixabay.com/api/docs/) |
| `OPENAI_API_KEY` | For `--tts-provider openai` | OpenAI TTS; also the vision-ranking fallback | [platform.openai.com](https://platform.openai.com) |
| `ELEVENLABS_API_KEY` | For `--tts-provider elevenlabs` | ElevenLabs TTS | [elevenlabs.io](https://elevenlabs.io) |
| `ELEVENLABS_VOICE_ID` | For `--tts-provider elevenlabs` | Voice selection (`--voice` overrides) | ElevenLabs voice library |
| `ANTHROPIC_API_KEY` | Optional | Vision ranking of clip thumbnails during `fetch` (preferred over `OPENAI_API_KEY`); `--no-vision` skips it | [console.anthropic.com](https://console.anthropic.com) |
| `NEUROEDGE_VISION_MODEL` | Optional | Overrides the vision model (defaults `claude-haiku-4-5-20251001` / `gpt-4o-mini`) | — |

`--tts-provider chatterbox` needs no key. Export the keys as environment variables in the shell that runs the
pipeline, and never commit them. The package reads the process environment only — it does not load `.env` and
does not read `.claude/settings.local.json`.

## Aspect Ratios

`render` produces exactly the aspects listed in the storyboard's `aspect_ratios` (default `["16x9", "1x1"]`);
neither is required on its own.

| `aspect_ratios` value | Output | Platform | What render does |
|---|---|---|---|
| `16x9` | `video_16x9.mp4`, 1920×1080 | YouTube, sales deck embed, internal portal | captions burned in; intro/outro title cards when there is no logo file |
| `1x1` | `video_1x1.mp4`, 1080×1080 | LinkedIn feed | center crop + scale of the muxed 16:9 body, its own captions; no title cards |
| `9x16` | *(nothing)* | — | passes validation, never rendered — `validate` warns |

## Human Review Gate

Two gates, both enforced by `neuroedge_marketing.cli`:

| Gate | The person reviews | Record it with | Unblocks |
|---|---|---|---|
| **1 — script** | `script.md`, and `storyboard.json` once `validate` passes | `approve --stage script --storyboard <path>` | `fetch` |
| **2 — footage** | `footage/contact_sheet.html`: each scene's choice, alternates, scores | `approve --stage footage --storyboard <path> --footage-dir <dir>` | `render` |

```text
REVIEW CHECKLIST — gate 1
[ ] Script reads cleanly aloud, in the target length
[ ] Captions read cleanly on mute (LinkedIn check)
[ ] Every number and claim is one the business can defend
[ ] CTA URL is correct and live
[ ] No competitor names

REVIEW CHECKLIST — gate 2
[ ] No identifiable people in endorsement positions
[ ] No competitor logos visible in any clip
[ ] No off-brand color/style in any clip
[ ] License terms permit the use
```

To use an alternate clip, set `pick` (`"<provider>:<id>"`) on that scene in `storyboard.json`. It needs no
re-fetch and no re-approval: `render` chooses among the clips already fetched, all of which gate 2 covered.
Editing anything else in the storyboard voids gate 1; fetching again voids gate 2.

Without both approvals, no render. This is the license + brand-safety guarantee, and it holds even when
nobody is watching the terminal.

## Output Structure

```
data/output/marketing_videos/<slug>/
  ├── brief.md                     # original input
  ├── script.md                    # approved script
  ├── storyboard.json              # approved scene plan — never rewritten by render
  ├── approval.json                # the two review stamps
  ├── footage/
  │     ├── _selection.json        # chosen + alternate clips per scene
  │     ├── contact_sheet.html     # the gate-2 review page
  │     ├── scene_01/ …            # downloaded candidates
  │     └── scene_03.webm          # a screen scene's recording, supplied by the user
  ├── _work/
  │     ├── voice/scene_NN.wav     # per-scene voice-over
  │     ├── storyboard.timed.json  # durations re-timed to the measured audio
  │     └── …                      # captions and other intermediates
  ├── video_16x9.mp4               # primary deliverable (if 16x9 is in aspect_ratios)
  └── video_1x1.mp4                # LinkedIn deliverable (if 1x1 is in aspect_ratios)
```

Keep the media out of git. The pipeline never edits `.gitignore` — that is the project's decision. A typical
rule set:

```gitignore
data/output/marketing_videos/*/footage/
data/output/marketing_videos/*/_work/
data/output/marketing_videos/*/*.mp4
```

## Iteration Workflow

1. **First draft (10 min):** Use OpenAI mini-tts. Render once. Watch on phone + laptop.
2. **Iterate script:** Edit `script.md` and carry the words into the storyboard's `voiceover` (captions and voice
   come from there), `validate`, re-approve gate 1, re-render. No re-fetch needed while `_selection.json` is unchanged.
3. **Iterate footage:** Set `pick` to another clip already on the contact sheet and re-render. There is no
   per-scene re-search: to change what a scene searches for, edit its `footage_queries`, re-approve gate 1, and
   re-run `fetch` — it fetches every scene again (cached searches and downloaded clips are reused) — then
   re-approve gate 2.
4. **Final pass (20 min):** Switch TTS to ElevenLabs, re-render. Diff against draft on key beats.

Total time from brief → first draft: ~15 minutes. From brief → final: ~45 minutes.

## Related Skills

- `video-editing` — broader video workflow (Screen Studio, Remotion, Descript) — different scope
- `cognizant-ppt` — brand-compliant PowerPoint — sister skill for slide-based content
- `deep-research` — used by `marketing-script-writer` to source customer pains
- `market-research` — used to identify the target buyer persona

## Related Commands

- `/marketing-video <brief>` — the single entry point for all three modes (`--technical-walkthrough`, `--demo-overlay`)

## Anti-patterns

- ❌ **Generating clips with Pika / Runway / Sora.** AI video has an uncanny shimmer that signals "cheap" to enterprise buyers in 2026. Real footage carries credibility AI cannot fake.
- ❌ **Skipping the human-review gate.** License violations (identifiable people, brand collisions) are legal risk. Non-negotiable.
- ❌ **Using MoviePy on Windows.** ImageMagick + font discovery + alpha quirks burn hours. Use ffmpeg subprocess.
- ❌ **Single CTA per video, period.** "Visit our site AND book a demo AND download the whitepaper" → 0 conversions. One CTA.
- ❌ **Hook longer than 8 seconds.** LinkedIn autoplay drops off a cliff after 8 s if the viewer hasn't unmuted.
- ❌ **AI-generated voice that sounds like AI.** Use ElevenLabs Multilingual v2 for finals; mini-tts for drafts only.

## References

- [Pexels API documentation](https://www.pexels.com/api/documentation/)
- [Pixabay API documentation](https://pixabay.com/api/docs/)
- [ElevenLabs TTS guide](https://elevenlabs.io/docs/api-reference/text-to-speech)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [ffmpeg filters reference](https://ffmpeg.org/ffmpeg-filters.html)
- [LinkedIn native video best practices](https://business.linkedin.com/marketing-solutions/native-video)
- Research backing this skill: `agentic-assets/docs/research/marketing-video-automation-2026-06-05.md`
