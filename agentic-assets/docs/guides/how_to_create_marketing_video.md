# How to create a marketing video — offline, no portal

**Applies to:** any project with AgentForge installed. No admin portal, no web UI, no running product —
a terminal, `ffmpeg`, and two or three API keys.

AgentForge ships a complete video builder: two agents, four skills, one `/marketing-video` command, and a
Python package (`src/neuroedge_marketing/`) with four commands — `validate`, `approve`, `fetch`, `render`.
All of it installs into every target and runs without Claude Code.

Every step has a **Verify** block. There are two human review gates, and both are **enforced in code**:
`fetch` and `render` refuse to run until a person's approval is recorded.

**Contents**

- [What ships](#what-ships)
- [The portal gap](#the-portal-gap)
- [Prerequisites](#prerequisites)
- [Step 1 — Write the script](#step-1--write-the-script)
- [Step 2 — Plan and validate the storyboard](#step-2--plan-and-validate-the-storyboard)
- [Step 3 — Review gate 1: approve the script](#step-3--review-gate-1-approve-the-script)
- [Step 4 — Fetch footage](#step-4--fetch-footage)
- [Step 5 — Review gate 2: approve the footage](#step-5--review-gate-2-approve-the-footage)
- [Step 6 — Render](#step-6--render)
- [After the first render — edit and re-render](#after-the-first-render--edit-and-re-render)
  - [Edit the script](#edit-the-script)
  - [Swap a scene's footage](#swap-a-scenes-footage)
  - [Re-record the voice-over](#re-record-the-voice-over)
- [Worked example](#worked-example--a-30-second-explainer)
- [Sample output (worked run)](#sample-output-worked-run)
- [Failure modes](#failure-modes)

---

## What ships

| Asset | Path in a target | Role |
|---|---|---|
| `/marketing-video` | `.claude/commands/marketing-video.md` | Orchestrates the steps below — three modes |
| `marketing-script-writer` | `.claude/agents/` | Brief → script (6-beat pitch, or `Mode: step-list`) |
| `marketing-storyboard-planner` | `.claude/agents/` | Script → `storyboard.json` |
| `marketing-video-builder` + 3 technique skills | `agentic-assets/skills/SUPPORTING-TOOLS/video/` | The procedure, overlays, editing |
| `neuroedge_marketing` | `src/neuroedge_marketing/` | The code that does the work |

The package's command line:

| Command | Does | Exit codes |
|---|---|---|
| `validate` | checks a storyboard and lists its scenes | 0 valid · 1 invalid or incomplete · 2 no file |
| `approve --stage script\|footage` | records a person's review as a SHA-256 stamp in `approval.json` | 0 recorded · 2 refused |
| `fetch` | finds stock footage, writes `_selection.json` and `contact_sheet.html` | 0 every scene · 1 some missing, or no provider key · 2 not approved |
| `render` | per-scene voice-over, captions, assembly → MP4 | 0 rendered · 1 a voice, key or ffmpeg error (traceback) · 2 not approved, or a bad flag |

`/marketing-video` has three modes. This guide covers the default, **marketing**. *Walkthrough*
(`--technical-walkthrough`) and *demo-overlay* (`--demo-overlay`) share the same spine; their base footage
and overlays are yours to capture or produce.

---

## The portal gap

In NeuroEdge Agentic AI Studio, a demo video is produced **through the admin portal**: the portal runs a use
case, records the run, narrates from it, captures the portal's own screens, and plays the result. None of
that exists in a target — and none of it is needed here:

| The Studio derives | Here, you write | Helped by |
|---|---|---|
| what the video is about, from the use-case spec | `brief.md` | Step 1's fields |
| the plan and narration, from a recorded run | `script.md` and `storyboard.json` | the two agents |
| the numbers, from the run | proof points in the brief | a number you can defend |
| screen clips, captured by Playwright | `scene_NN.webm`, from any screen recorder | Step 4 |
| playback in the portal | the MP4 | Step 6 |

One command is Studio-only: `recorded-demo` reads artifacts the Studio's code generator writes. In a target it
stops with a named refusal that points here:

```text
Blocked: Recorded-demo artifact(s) missing: generated/recorded_demo_script.md, ...
  recorded-demo consumes artifacts that only the NeuroEdge Studio generates. To make a video
  from content you write, see agentic-assets/docs/guides/how_to_create_marketing_video.md
  (validate -> approve -> fetch -> approve -> render).
```

Everything else — footage search and ranking, the contact sheet, per-scene voice, captions, branding,
assembly, both review gates — is the same code the Studio uses.

---

## Prerequisites

```bash
# 1. ffmpeg and ffprobe on PATH (or FFMPEG_BIN set to their folder) — the assembler shells out to them
ffmpeg -version

# 2. Python dependencies, into YOUR environment (AgentForge never edits your dependency files).
#    One file reaches every package AgentForge needs, the local Chatterbox voice included; see
#    how_to_install_agentforge.md for adding it to requirements.txt or a uv dependency group instead.
pip install -r agentic-assets/requirements-agentforge.txt

# 3. Keys: set only what you use, as environment variables. The package reads the environment and does
#    NOT load a .env file; .env.example lists the names.
```

| Need | Keys | Notes |
|---|---|---|
| Footage | `PEXELS_API_KEY`, `PIXABAY_API_KEY` | Both free. Either alone works; both rank better |
| Draft voice-over | `OPENAI_API_KEY` | `--tts-provider openai` — use for every iteration |
| Final voice-over | `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID` | `--tts-provider elevenlabs` — sign-off renders |
| Local voice-over | *(none)* | `--tts-provider chatterbox` — no key, no per-render cost, can speak in your own voice |
| Better clip ranking | `ANTHROPIC_API_KEY`, else `OPENAI_API_KEY` | Optional. A vision model scores each clip's thumbnail instead of matching tags. Defaults `claude-haiku-4-5-20251001` / `gpt-4o-mini`; `NEUROEDGE_VISION_MODEL` overrides |

> 🔴 **`OPENAI_API_KEY` does two jobs.** Set it for draft voice-overs and it also turns on vision ranking —
> one thumbnail download and one model call per candidate clip. `fetch --no-vision` switches that off.

**Verify**

```bash
ffmpeg -version | head -1
PYTHONPATH=src python -m neuroedge_marketing.cli --help
```

✅ A version banner, not "command not found". ✅ The help lists `{validate,approve,fetch,render,recorded-demo}`.

> Every command below uses `PYTHONPATH=src`, because the package installs at your project's `src/`. In
> PowerShell, set `$env:PYTHONPATH = "src"` once instead.

---

## Step 1 — Write the script

For a **pitch** — six beats, **hook → problem → solution → how → proof → cta**:

```text
Use the marketing-script-writer agent to write a six-beat script for:

  Product:   <what it is, in one sentence>
  Audience:  <who is watching and what they care about>
  Problem:   <the pain, in their language and their units — hours, defects, cost>
  Proof:     <a number or outcome you can actually stand behind>
  CTA:       <the URL and the action>
  Length:    <seconds — 30 for social, 60–90 for a site explainer, 180 max>
```

For a **step-by-step product demo** — the offline stand-in for a portal-recorded demo — list the steps
yourself:

```text
Use the marketing-script-writer agent in Mode: step-list:

  Audience: <who is watching>
  Steps:
    1. <what happens> — <the one fact that makes it matter>
    2. ...
  Output: script.md
```

**Verify**

- ✅ The script reads aloud in your target length. Read it out loud — copy written to be read runs about 20 %
  longer spoken than it looks.
- ✅ The hook works on mute; most viewers see captions before they hear anything.
- ✅ No competitor names, and every claim is one you can defend.
- ✅ Step-list scripts: nothing is marked `[CONFIRM]` that you have not confirmed, and every id under
  `## Pronunciations` has its spoken form filled in. That list becomes your `--say-as` file in Step 6.

Save it as `script.md`.

---

## Step 2 — Plan and validate the storyboard

```text
Use the marketing-storyboard-planner agent to turn script.md into storyboard.json.
Target <N> seconds. Landscape 16x9. <Name any screen recordings you will supply, and what each shows.>
```

Then check it — before a person spends time reviewing it:

```bash
PYTHONPATH=src python -m neuroedge_marketing.cli validate --storyboard storyboard.json --screen-dir footage
```

**Verify**

```text
VALID: demo-offline | 3 scenes | 30s | aspects 16x9, 1x1
   1 hook          0.0 + 10.0  footage  One stop costs a shift
   2 solution     10.0 + 12.0  footage  Drift, caught days early
   3 cta          22.0 +  8.0  footage  See it on your line
```

- ✅ Exit 0 and a scene table.
- 🔴 Exit 1 with `INVALID` names the scene and field. The two rules hand edits break most: each scene's
  `start_s` equals the running sum of earlier `duration_s` (±0.05), and the durations sum to
  `total_duration_s` (±0.5).
- 🔴 Exit 1 with `MISSING: scene N is a screen scene` — record that clip (Step 4) or change the scene's surface.
- ⚠️ `WARNING: 9x16 passes validation but is never rendered` — only `16x9` and `1x1` are produced.

Each scene's `surface` decides what it needs:

| `surface` | Picture | Requires |
|---|---|---|
| `footage` *(default)* | a stock video clip | `footage_queries` (1–5) |
| `vector` | a stock illustration with a slow move | `footage_queries` |
| `screen` | your own screen recording, `footage/scene_NN.webm` | `screen` — any short label |

Durations are provisional: `render` re-times every scene to its measured voice-over. Don't over-tune them.

**Brand and CTA.** If `brand.logo_path` names no existing file (relative to where you run `render`), the 16:9
video opens on a title card showing `brand.title` and `brand.subtitle`, and closes on one showing
`cta.display_text` over `cta.url` — so the URL must be real before a render anyone else sees. Leave `title`
empty and the card is named from the slug. Set it anyway. With a logo file there are no cards: the logo is
overlaid and no CTA text appears. The 1:1 cut never has cards.

**`caption` is not what appears on screen.** It labels the scene in the table above and on the contact sheet,
and steers clip ranking. The burned-in captions are built from `voiceover` (Step 6).

---

## Step 3 — Review gate 1: approve the script

Read `script.md` and the storyboard's `voiceover` lines (the on-screen captions), `cta`, and queries.

```text
[ ] Script reads cleanly aloud, in the target length
[ ] Captions carry the message on mute
[ ] Industry framing matches the buyer
[ ] Every number is one the business can defend
[ ] CTA URL is correct and live — the outro card prints it
[ ] Each scene's queries describe what is visible, not what is said
```

Then record the decision:

```bash
PYTHONPATH=src python -m neuroedge_marketing.cli approve --stage script --storyboard storyboard.json
```

**Verify**

- ✅ `APPROVED: script review at <time> -> approval.json`
- ✅ Editing `storyboard.json` after this voids the approval. `fetch` then stops with
  `Blocked: the script approval is stale: storyboard.json changed after it was approved.` Review, re-approve.
- 🔴 `Blocked: the storyboard is invalid, so it cannot be approved` — go back to Step 2.

---

## Step 4 — Fetch footage

```bash
PYTHONPATH=src python -m neuroedge_marketing.cli fetch \
  --storyboard storyboard.json \
  --output-dir footage \
  --providers pexels,pixabay \
  --clips-per-scene 3
```

`--providers` order is a preference — earlier providers win near-ties. The hook scene becomes a journey: one
clip per query, in the order you wrote them, cut across the scene. Search responses are cached for 24 h in
`data/cache/footage/`, under the folder you run from.

**Verify**

- ✅ `OK: 3/3 scenes selected (providers that answered: pexels, pixabay)`
- ✅ `Manifest: footage/_selection.json` and `Contact sheet: footage/contact_sheet.html`
- ✅ The log says `relevance: vision pass`, or `tags only (no model key for a vision pass)` — know which ran.
  `--no-vision` prints the second.
- 🔴 Exit 2, `Blocked: the script review has not been approved` — Step 3 first.
- 🔴 Exit 1, `No working footage providers (skipped: pexels, pixabay)` — no keys are set.

**Screen scenes:** record them now. Any recorder works (OBS, `ffmpeg`, the OS's built-in one). Save each as
`footage/scene_NN.webm`, with `NN` the scene's two-digit id, then re-run Step 2's `validate` to confirm.

---

## Step 5 — Review gate 2: approve the footage

Open `footage/contact_sheet.html`. Each scene shows its chosen clip outlined, the alternates beside it, and a
score per clip; `unscored` means no relevance signal existed for that clip.

```text
[ ] No identifiable people in what reads as an endorsement
[ ] No competitor logos or products visible
[ ] Nothing off-brand in style or color
[ ] Tone matches the beat — a "problem" scene should not look cheerful
[ ] License terms permit your use (commercial, if that is what this is)
```

To use an alternate, set `"pick": "<provider>:<id>"` on that scene in `storyboard.json`, copying the id from
the sheet. It needs no re-fetch and no re-approval: `render` chooses among clips already fetched. A pick
naming none of the sheet's clips falls back to the outlined one, with a warning. On the hook scene, a pick
replaces the journey with that one clip.

Then record the decision:

```bash
PYTHONPATH=src python -m neuroedge_marketing.cli approve --stage footage \
  --storyboard storyboard.json --footage-dir footage
```

**Verify**

- ✅ `APPROVED: footage review at <time> -> approval.json`
- 🔴 `Blocked: nothing fetched yet -- no _selection.json in footage` — Step 4 first.
- ✅ Fetching again voids this approval; review the new sheet and re-approve.

---

## Step 6 — Render

Draft first, always:

```bash
PYTHONPATH=src python -m neuroedge_marketing.cli render \
  --storyboard storyboard.json --footage-dir footage --output-dir out \
  --tts-provider openai --music assets/music/corporate.mp3
```

Each scene gets its own voice-over, measured, and the scenes are re-timed to it so cuts land after sentences.
The re-timed plan goes to `out/_work/storyboard.timed.json`; your approved `storyboard.json` is untouched.

**Captions are your approved voice-over text**, timed to each scene's measured speech — not a transcription.
A transcription model can mishear a word and burn it into the video; the storyboard already holds the words
you approved. Ids stay literal on screen, because `--say-as` changes only what the voice hears.

Lines wrap by character count alone — 38 per line, two lines and 4 s per caption — so a line can end
mid-phrase ("…flag bearing drift days / before a"). Short voice-over sentences read better.

| Flag | Does |
|---|---|
| `--tts-provider openai\|elevenlabs\|chatterbox` | who speaks (default `openai`) |
| `--voice <name>` | OpenAI voice (default `onyx`), or an ElevenLabs voice id in place of `ELEVENLABS_VOICE_ID`; Chatterbox ignores it |
| `--say-as say_as.json` | how ids and numbers are spoken — the voice hears it, captions keep the literal text. JSON, or YAML with PyYAML |
| `--voice-reference me.wav` | Chatterbox only: speak in the voice from a ~30 s recording |
| `--exaggeration 0.45` | Chatterbox only: expressiveness, 0–1 (default 0.5) |
| `--screen-dir <dir>` | where screen scenes' `scene_NN.webm` files are (default: `--footage-dir`) |
| `--pad-s 0.6` | silence after each scene's voice-over (default 0.6 s) |
| `--music <mp3>` | background bed, ducked under the voice. A path that does not exist renders with no music and no warning |
| `--single-pass-voice` | the whole script in one call, no re-timing |
| `--captions script\|transcribe` | captions from your approved text (default), or transcribed by faster-whisper (the only option with `--single-pass-voice`) |
| `--no-gate` | skip the approval check for scripted re-renders; the reviews are still yours |

A sign-off render in your own voice, locally:

```bash
PYTHONPATH=src python -m neuroedge_marketing.cli render \
  --storyboard storyboard.json --footage-dir footage --output-dir out \
  --tts-provider chatterbox --voice-reference voice/me.wav --exaggeration 0.45 \
  --say-as say_as.json --music assets/music/corporate.mp3
```

```json
{ "CNC-PWT-014": "the CNC machine on Powertrain line 14", "WO-2026-04187": "work order 4187" }
```

**Numbers.** Write them as digits in `voiceover` — that is what the captions show — and give the spoken form in
the same file: `{"214": "two hundred fourteen"}`. A key matches exactly (case-sensitive) and never inside a
longer run of letters, digits or `_`: `214` leaves `2140` alone but does rewrite the `214` of `214.5`, so give
`214.5` its own key — the longest key wins.

> 🔴 A voice recording is a biometric. Keep `voice/` out of version control.

**Verify**

```bash
ls out/ out/_work/voice/
ffprobe -v error -show_entries format=duration -of csv=p=0 out/video_16x9.mp4
```

- ✅ `OK: render complete`, listing `16x9` (and `1x1` if the storyboard asks for it).
- ✅ One `scene_NN.wav` per scene under `out/_work/voice/`.
- ✅ The 16:9 duration matches `total_duration_s` in `out/_work/storyboard.timed.json`, plus the intro and
  outro title cards (5 s each by default) when there is no logo file — to within about a second, not exactly
  (see [Sample output](#sample-output-worked-run)).
- ✅ Watch it once **muted** (do captions carry it?) and once with **sound** (does the voice match the picture?).
- ✅ Captions read exactly as your storyboard's voice-over. If the voice says a word differently, fix the
  voice — add it to `say_as.json` or rephrase — because the captions are right by design.
- 🔴 Exit 2, `Blocked: the footage review has not been approved` — Step 5.
- 🔴 `Scene N is a screen scene but <path> does not exist` — record it, or point `--screen-dir` at its folder.
- 🔴 `--voice-reference only applies to --tts-provider chatterbox` — a cloned voice is local-only.

**Keep the media out of git.** Nothing here edits your `.gitignore`; that is your call. (In the AgentForge
Assets repo itself, `data/output/` and `data/cache/` are git-ignored.) A typical set:

```gitignore
footage/
out/_work/
out/*.mp4
voice/
```

---

## After the first render — edit and re-render

Watching the first draft almost always turns up something to change. Each kind of edit costs a different amount
of work, depending on what the two approvals cover. The **script** stamp hashes `storyboard.json`, except for
`pick`. The **footage** stamp hashes `footage/_selection.json`. Nothing else is hashed: not `say_as.json`,
`script.md`, screen recordings or `render` flags.

| You change | In | Voids | Re-fetch? | Then |
|---|---|---|---|---|
| Voice-over wording, `cta`, `brand` text, `caption` | `storyboard.json` | script | no | `validate` → `approve --stage script` → `render` |
| A scene's clip, from the contact sheet | `pick` in `storyboard.json` | nothing | no | `render` |
| A scene's `footage_queries` | `storyboard.json` | script, then footage | **yes — every scene** | `validate` → `approve script` → `fetch` → review → `approve footage` → `render` |
| A stock scene becomes your own recording | `surface`/`screen` in `storyboard.json`, plus `scene_NN.webm` | script | no | `validate --screen-dir` → `approve script` → `render` |
| An existing screen recording | the `.webm` file | nothing | no | `render` |
| Scenes added, removed or reordered | `storyboard.json` | script | only if a new stock scene was added | see [Edit the script](#edit-the-script) |
| How a word is pronounced | `say_as.json` | nothing | no | `render` |
| Voice, provider, reference, expressiveness, pause, music | `render` flags | nothing | no | `render` |

> 🔴 **Render each take into its own folder.** `render` overwrites `out/video_16x9.mp4` and `out/_work/` in
> place. Use `--output-dir out/take2` to keep the earlier take and compare the two. Approvals live beside
> `storyboard.json`, not in the output folder, so a new folder needs no re-approval.

### Edit the script

🔴 **`render` never reads `script.md`.** The narration and captions come from each scene's `voiceover` in
`storyboard.json`; `script_path` is only a label. Editing `script.md` alone changes nothing in the video. Make
the change in `voiceover`, and copy it back into `script.md` so the two files agree.

1. Edit `voiceover` (and `caption`, if the scene's point changed). Leave `start_s` and `duration_s` alone:
   `render` re-times every scene to its measured speech, so the new wording sets its own length.
2. Keep each sentence under about 280 characters when the voice is Chatterbox. Chatterbox reads long text in
   chunks of whole sentences, but it cannot split one long sentence, and a long sentence can come out
   garbled or with its ending missing.
3. Re-check and re-approve. The edit voided the script stamp, and `render` needs both stamps:

   ```bash
   PYTHONPATH=src python -m neuroedge_marketing.cli validate --storyboard storyboard.json
   # --- review gate 1 again: read the changed lines ---
   PYTHONPATH=src python -m neuroedge_marketing.cli approve --stage script --storyboard storyboard.json
   PYTHONPATH=src python -m neuroedge_marketing.cli render --storyboard storyboard.json --footage-dir footage \
     --output-dir out/take2 --tts-provider openai
   ```

   No re-fetch: the footage stamp still holds, because `_selection.json` did not change. One caveat: `fetch`
   ranked the clips against the scene's old `caption` and `voiceover`. If a scene now says something quite
   different, its picture may no longer fit. Swap the clip, as described in the next section.

**Adding, removing or reordering scenes.** A scene's `id` ties it to its footage folder (`footage/scene_NN/`),
its entry in `_selection.json`, and its screen clip (`scene_NN.webm`). The order of the `scenes` list is the
playback order.

- **Reorder:** move the scene objects and **keep their ids**. Renumbering a scene separates it from the
  footage fetched for it.
- **Remove:** delete the scene. No re-fetch is needed.
- **Add:** give the new scene a new `id`. A new stock or `vector` scene has no clips yet, so `render` stops with
  `Scene N missing footage in manifest` until you run `fetch` again (see the next section).
- **After any of these:** recompute `start_s` as the running sum of the earlier scenes' `duration_s`, and make
  `total_duration_s` their total. `validate` checks both. The numbers can stay rough, because `render`
  re-times everything.

**Verify**

- ✅ `approve --stage script` prints `APPROVED`, and `render` prints `OK: render complete`.
- ✅ The captions in the new take read exactly like the edited `voiceover`.

### Swap a scene's footage

Three ways, from least work to most:

**1. Use an alternate that was already fetched.** Set `"pick": "<provider>:<id>"` on the scene, copying the id
from `footage/contact_sheet.html`, then run `render`. This needs no re-fetch and no re-approval (see Step 5).

**2. Search again with new queries.** Use this when none of the scene's clips fit. There is **no per-scene
fetch**: `fetch` searches and re-ranks every stock scene each time.

```bash
# 1. edit the scene's footage_queries in storyboard.json: describe what is visible, not what is said
PYTHONPATH=src python -m neuroedge_marketing.cli validate --storyboard storyboard.json
PYTHONPATH=src python -m neuroedge_marketing.cli approve --stage script --storyboard storyboard.json
PYTHONPATH=src python -m neuroedge_marketing.cli fetch --storyboard storyboard.json --output-dir footage \
  --clips-per-scene 5
# 2. review the WHOLE new footage/contact_sheet.html, not only the scene you changed
PYTHONPATH=src python -m neuroedge_marketing.cli approve --stage footage --storyboard storyboard.json --footage-dir footage
PYTHONPATH=src python -m neuroedge_marketing.cli render --storyboard storyboard.json --footage-dir footage \
  --output-dir out/take2 --tts-provider openai
```

What a re-fetch reuses, and what it repeats:

- ✅ **Reused:** searches from the last 24 h (`data/cache/footage/`), and every clip already downloaded
  (a file already in `footage/scene_NN/` is not downloaded again).
- 🔴 **Repeated:** the vision pass scores every candidate in every scene again, which means one thumbnail
  download and one model call per clip. Add `--no-vision` if tag matching is enough for this round.
- 🔴 **Other scenes can change.** Re-ranking can give an unchanged scene a different primary clip. A `pick`
  still works if its clip is among that scene's clips on the new sheet. Otherwise `render` warns and uses the
  outlined clip.
- 🔴 **A scene the new search fails on drops out of `_selection.json`.** `fetch` then exits 1 instead of printing
  `OK: N/N`, and `render` stops at that scene. Change its queries and fetch again.
- `--clips-per-scene 5` puts more alternates on the sheet, so the next swap can be just a `pick`. The hook scene
  still takes one clip per query, and a `pick` on it replaces that sequence of clips with the one clip you chose.

**3. Use your own clip.** Stock search can't find everything, such as a product shot or a customer's site. Turn
the scene into a screen scene and supply the file yourself:

```json
{ "id": 4, "beat": "how", "start_s": 22.0, "duration_s": 12.0,
  "voiceover": "The agent opens the work order and books the technician.",
  "caption": "Work order, booked",
  "surface": "screen", "screen": "work order booked in the portal" }
```

```bash
# render looks for exactly scene_NN.webm, so convert whatever you recorded
ffmpeg -i my_clip.mp4 -c:v libvpx-vp9 -crf 32 -b:v 0 -an footage/scene_04.webm
PYTHONPATH=src python -m neuroedge_marketing.cli validate --storyboard storyboard.json --screen-dir footage
PYTHONPATH=src python -m neuroedge_marketing.cli approve --stage script --storyboard storyboard.json
PYTHONPATH=src python -m neuroedge_marketing.cli render --storyboard storyboard.json --footage-dir footage \
  --output-dir out/take2 --tts-provider openai
```

Screen clips are handled differently from stock clips:

| | Stock clip | Screen clip |
|---|---|---|
| Framing | scaled and **cropped** to fill the frame | scaled to **fit**, never cropped, with a plain background filling the gaps |
| Shorter than the scene | **loops** | **holds its last frame** |
| Its own audio | dropped | dropped |

So record at least as long as the scene's speech. The length to aim for is that scene's `duration_s` in
`out/_work/storyboard.timed.json` from the last render. `fetch` skips screen scenes, so the footage stamp
still holds. To replace the recording later, overwrite the `.webm` and render again. No stamp covers the
file, so reviewing it is up to you.

**Verify**

- ✅ `validate` lists the scene with surface `screen` and prints no `MISSING` line.
- ✅ Watch the swapped scene in the new take. With a re-fetch, watch the whole take.

### Re-record the voice-over

🔴 **Every render re-voices every scene.** No scene audio is kept between renders and there is no seed, so
lines you didn't change can also come out differently. Render into a new `--output-dir` each time and keep
the take you like. Nothing merges scenes from two takes.

Choose the fix from what is wrong:

| What you hear | Fix | Re-approve? |
|---|---|---|
| An id, acronym or number read wrongly | Add it to `say_as.json` (see Step 6's **Numbers**) | no |
| Flat, or too theatrical | Chatterbox: `--exaggeration`, lower to calm it, higher to liven it. OpenAI: try another `--voice` | no |
| The wrong voice | `--tts-provider`, `--voice`, or a new `--voice-reference` recording | no |
| Cuts land too soon after a line | `--pad-s 0.9` | no |
| Words garbled, or the end of a line missing | Split the long sentence in `voiceover` (Chatterbox, over ~280 characters) | **yes**, the script |
| A line says the wrong thing | Edit `voiceover` ([Edit the script](#edit-the-script)) | **yes**, the script |

**Audition one line before a full render.** A render voices every scene and rebuilds the whole video. To hear a
single line, call the same voice functions `render` uses:

```bash
PYTHONPATH=src python -c "
import json
from pathlib import Path
from neuroedge_marketing.tts import get_provider
from neuroedge_marketing.voice import apply_say_as
text = 'Agents watch the signal and flag drift days early.'
say_as = json.loads(Path('say_as.json').read_text(encoding='utf-8'))
voice = get_provider('chatterbox', reference=Path('voice/me.wav'), exaggeration=0.45)
voice.synthesize(apply_say_as(text, say_as), out_path=Path('audition/scene_02.wav'))
"
```

For OpenAI, use `get_provider('openai')` and pass `voice='onyx'` to `synthesize`. Chatterbox loads its model
each time the process starts, so expect a delay before it speaks.

**Recording a new voice reference** (Chatterbox). Chatterbox copies whatever the recording sounds like, so
record about 30 s of clean speech:

- one speaker, in a quiet room, with no music;
- the same microphone and the same pace and energy you want in the video;
- saved as a WAV.

Replace the file, or point `--voice-reference` at the new one, then run `render` again. A voice recording is
a biometric: keep `voice/` out of git.

**Verify**

- ✅ Play `out/take2/_work/voice/scene_NN.wav` for the scenes you were fixing. Each scene has its own file.
- ✅ The captions still match `voiceover` word for word. `say_as.json` changes only what the voice says.
- ✅ Watch the new take all the way through, muted and with sound. Any line may have changed.

---

## Worked example — a 30-second explainer

A complete, valid storyboard, checked against the shipped schema:

```json
{
  "version": "1.0",
  "slug": "demo-offline",
  "script_path": "script.md",
  "audience": "manufacturing ops leaders",
  "total_duration_s": 30.0,
  "aspect_ratios": ["16x9", "1x1"],
  "brand": {
    "logo_path": "brand/logo.png",
    "title": "Acme Edge AI",
    "subtitle": "Catch drift before it costs you"
  },
  "cta": { "url": "https://example.com/demo", "display_text": "Book a demo" },
  "scenes": [
    { "id": 1, "beat": "hook", "start_s": 0.0, "duration_s": 10.0,
      "voiceover": "One unplanned stop costs a shift.",
      "caption": "One stop costs a shift",
      "footage_queries": ["factory floor machinery", "industrial production line"] },
    { "id": 2, "beat": "solution", "start_s": 10.0, "duration_s": 12.0,
      "voiceover": "Agents watch the signal and flag drift days early.",
      "caption": "Drift, caught days early",
      "footage_queries": ["engineer looking at dashboard", "control room monitors"] },
    { "id": 3, "beat": "cta", "start_s": 22.0, "duration_s": 8.0,
      "voiceover": "See it on your own line.",
      "caption": "See it on your line",
      "footage_queries": ["team meeting handshake"] }
  ]
}
```

The arithmetic: `0 + 10 = 10`, `10 + 12 = 22`, `22 + 8 = 30` = `total_duration_s`. `cta.url` is a placeholder —
replace it before a render anyone else sees.

The full run, with the two human reviews where they belong:

```bash
PYTHONPATH=src python -m neuroedge_marketing.cli validate --storyboard storyboard.json
# --- review gate 1: read script.md and the storyboard ---
PYTHONPATH=src python -m neuroedge_marketing.cli approve --stage script --storyboard storyboard.json
PYTHONPATH=src python -m neuroedge_marketing.cli fetch --storyboard storyboard.json --output-dir footage
# --- review gate 2: open footage/contact_sheet.html ---
PYTHONPATH=src python -m neuroedge_marketing.cli approve --stage footage --storyboard storyboard.json --footage-dir footage
PYTHONPATH=src python -m neuroedge_marketing.cli render --storyboard storyboard.json --footage-dir footage \
  --output-dir out --tts-provider openai
```

---

## Sample output (worked run)

A real end-to-end run from the AgentForge Assets repo (2026-09-15): a 9-scene explainer, Chatterbox voice,
`aspect_ratios: ["16x9"]`. That repo git-ignores `data/output/`, so the artifacts are shown inline, not linked.
Paths are relative to `data/output/marketing_videos/agentforge-sdlc-dcn-fleet-orchestration/`.

```text
brief.md  script.md  storyboard.json  say_as.json  approval.json
footage/
  _selection.json  contact_sheet.html
  scene_01/        pexels_5474324.mp4 … pixabay_14906.mp4   4 clips: the hook montage, one per query
  scene_02/ … scene_09/                                     3 clips each (--clips-per-scene 3)
_work/
  voice/scene_01.wav … scene_09.wav
  storyboard.timed.json  captions_16x9.ass  _concat.txt  _cards_concat.txt
  scene_01.mp4 … scene_09.mp4  concat.mp4  audio.aac  muxed.mp4  captioned_16x9.mp4  card_intro_a.mp4 …
video_16x9.mp4     no video_1x1.mp4 — 1x1 was not in aspect_ratios
```

Check: one `footage/scene_NN/` per footage scene, one `_work/voice/scene_NN.wav` per scene.

**`footage/_selection.json`** — scene 3, trimmed (tags cut; `local_path` and `thumbnail` omitted; the provider
URLs carry no key or token):

```json
{ "scene_id": 3,
  "primary": { "provider": "pixabay", "provider_id": "2340", "kind": "video",
    "url": "https://cdn.pixabay.com/video/2016/02/29/2340-157269921_large.mp4",
    "width": 1920, "height": 1080, "duration_s": 44.0, "tags": ["meeting", "planning", "…"],
    "relevance_score": 0.82, "unscored": false,
    "vision_note": "Shows collaborative planning and documentation work clearly" },
  "alternates": [
    { "provider": "pixabay", "provider_id": "2335", "duration_s": 87.0, "relevance_score": 0.82, "…": "…" },
    { "provider": "pixabay", "provider_id": "88", "duration_s": 13.0, "relevance_score": 0.82,
      "vision_note": "Shows agile workflow board, relevant but blurry and obstructed" } ] }
```

Check: `unscored: false` plus a `vision_note` means the vision pass looked; `unscored: true` means the score is
resolution and duration only. The reviewer set `"pick"` on five scenes in `storyboard.json` — 3 `pixabay:88`,
5 `pexels:6283061`, 6 `pixabay:120`, 7 `pixabay:1058`, 8 `pixabay:148596` — each one an alternate on the sheet.
The contact sheet shows the same data as 9 scene blocks and 28 thumbnail cards, with each scene's primary outlined.

**`approval.json`** — hashes shortened:

```json
{ "script":  { "approved_at": "2026-09-15T16:07:51+00:00", "sha256": "50ffe5e2…f6d11999" },
  "footage": { "approved_at": "2026-09-15T16:24:04+00:00", "sha256": "e9b2f1e1…5736e8a1",
               "selection": "data\\output\\marketing_videos\\…\\footage\\_selection.json" } }
```

Check: both stages are present. `script` hashes `storyboard.json` without the `pick` fields, and `footage` hashes
`_selection.json`, which is why the picks needed no re-approval.

**`_work/storyboard.timed.json`** — one scene before and after re-timing:

```text
scene 3 (how)  storyboard.json        start_s 22.0   duration_s 12.0
               storyboard.timed.json  start_s 17.04  duration_s 9.44   = 8.84 s measured speech + 0.6 s pad
whole plan     total_duration_s 102.0 → 73.68      = 68.28 s speech across 9 scenes + 9 × 0.6 s pads
```

Check: every `duration_s` is its scene's speech plus `--pad-s`, and the approved `storyboard.json` still says 102.

**Captions and voice.** `_work/captions_16x9.ass` has 24 caption events, and joined together they match the
storyboard's `voiceover` text word for word. `say_as.json` is `{"AgentForge": "Agent Forge", "QA": "Q A"}`, so
the voice says "Agent Forge" while the captions still read `AgentForge` and `QA`.

**`video_16x9.mp4`** (ffprobe):

```text
81.12 s · H.264 1920×1080 · AAC 48 kHz stereo · 32,159,320 bytes (30.7 MiB)
= 4 s intro card + 73.11 s captioned body + 4 s outro card   (this storyboard set 4 s cards)
```

Check: watch it muted and with sound. The body came out 0.57 s shorter than the 73.68 s plan, which is why
the duration check in Step 6 holds only to within about a second.

---

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `Blocked: the script review has not been approved` | `fetch` before Step 3 | Review, then `approve --stage script` |
| `Blocked: the script approval is stale` | `storyboard.json` edited after approval | Review again, re-approve |
| `Blocked: the footage review has not been approved` | `render` before Step 5 | Review the contact sheet, `approve --stage footage` |
| `Blocked: the footage approval is stale` | fetched again after approval | Review the new sheet, re-approve |
| `No working footage providers` | no `PEXELS_API_KEY` / `PIXABAY_API_KEY` in the environment | Set at least one |
| `INVALID … Scene N start_s … not contiguous` | hand-edited durations | Recompute `start_s` as the running sum |
| `Sum of scene durations does not match total_duration_s` | same | Fix one or the other |
| `MISSING: scene N is a screen scene` / `… does not exist` | no recording for a screen scene | Record `scene_NN.webm`, or `--screen-dir` |
| `--voice-reference only applies to --tts-provider chatterbox` | cloned voice with a cloud provider | Use `chatterbox` |
| `Chatterbox is not installed` | Python dependencies not installed in this environment | `pip install -r agentic-assets/requirements-agentforge.txt` |
| `ffmpeg not found` | not on `PATH` | Install `ffmpeg`, or set `FFMPEG_BIN` to its folder |
| `OPENAI_API_KEY not set` / `ELEVENLABS_VOICE_ID not set` | key not in the environment (`.env` is not read) | Export it, or `--tts-provider chatterbox` |
| `Title card has NO TEXT` in the log | `drawtext` failed — no usable font, or an ffmpeg without it; the cards render blank | Set `DEMO_FONT_FILE` to a `.ttf` |
| The video has no music | the `--music` path does not exist | Fix the path |
| `Blocked: Recorded-demo artifact(s) missing` | `recorded-demo` in a target | Studio-only — follow this guide |
| A `9x16` video never appears | not rendered | Use `16x9` or `1x1` |
| The picked clip isn't used | `pick` names a clip not on the contact sheet | Copy the id from the sheet |
| The voice says a word differently from the caption | the voice mispronounced it | Add it to `--say-as`, or rephrase; re-render |
| `--captions script needs per-scene voice` | `--single-pass-voice` has no per-scene timing | Drop it, or `--captions transcribe` |
| Edited `script.md`, the video did not change | `render` reads `voiceover` in `storyboard.json` only | Make the edit in `voiceover`, re-approve the script, re-render |
| `Scene N missing footage in manifest` | a stock scene was added, or a re-fetch found nothing for it | Fix its queries, `fetch`, `approve --stage footage` |
| An unchanged scene shows a different clip after a re-fetch | re-ranking changed its primary | Set `pick` to the clip you want, from the new sheet |
| A line you liked sounds different in the new take | every render re-voices every scene | Render takes into separate `--output-dir` folders and keep the best |
| A screen scene freezes at the end | the recording is shorter than the scene's speech | Record longer, or shorten `voiceover` |

**The summary:** the only portal-dependent part of the Studio's video is *where the script and storyboard
come from*. Write those two files yourself — with the two agents that ship — and the rest runs offline,
gated, unchanged.
