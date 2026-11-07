---
name: video-edit
description: Director workflow for editing real footage (talking heads, interviews, screencasts, podcasts, shorts) from raw files to a finished MP4. Use whenever someone wants to cut, tighten, trim, clean up, caption, reformat (9:16 / 1:1), recut, or "edit this video", remove pauses/ums/retakes, or turn a long recording into clips. Plans with a transcript-first cut list, gets approval, renders with ffmpeg via video-studio/vs, QA-checks, then iterates on notes.
---

# Video edit (director workflow)

You are the director and editor. You never "watch" video frame-by-frame: you
read the word-level transcript (cheap, exact), and you look at contact sheets
only at decision points. Every edit is an EDL (`work/edl.json`) rendered by
ffmpeg, so it is deterministic and easy to revise.

All tools: `video-studio/vs <cmd>` (run from the repo root; `vs help` lists them).
Brand, moves and persistent notes: `video-studio/style/{brand,moves,notes}.md`.

## 0. Start
1. `video-studio/vs doctor`. If anything is ✗, use `/video-setup`.
2. Project: `video-studio/vs new <name>` → put footage in `projects/<name>/raw/`.
   Work inside `video-studio/projects/<name>/`; keep `project.md` current (it is your memory).
3. Read `style/notes.md`, `style/brand.md`, `style/moves.md` and `project.md` before planning.
4. If the brief is missing platform, length or caption style, ask ONE short question with
   sensible defaults ("Reels 9:16, ≤60 s, bold-pop captions, OK?"). A loose idea gets a proposal, not a render.

## 1. Understand the footage
```bash
P=video-studio/projects/<name>
video-studio/vs probe $P/raw/<file>
video-studio/vs transcribe $P/raw/<file> -o $P/work/transcript --prompt "Nexa IT Solution, <names, jargon>"
```
- `--model small` for planning; re-run with `--model large-v3` (or `turbo`) before a final if words look wrong.
- Read `work/transcript.md` (packed: phrases, pauses ⏸, fillers `{um}`, low-confidence `word?`).
- No speech / music only: `vs silences <in> -o work/silences.json --edl work/edl.json`.
- Need to see something (framing, gestures, slides, b-roll content)? `vs filmstrip <in> -o work/strip.png --every 10` and Read the PNG. Never extract hundreds of frames.

## 2. Plan → GATE 1 (cut list)
1. Mechanical draft: `vs cuts $P/work/transcript.json -o $P/work/edl.json --max-pause 0.45`
   (shorts 0.3–0.45, long-form 0.5–0.7).
2. Editorial pass: edit `edl.json` yourself:
   - Retakes: when a sentence is restarted, keep the LAST complete take unless an earlier one is clearly better; delete the others.
   - Remove false starts, tangents, "let me redo that", housekeeping talk.
   - Hook: for shorts, consider opening on the strongest line (segments may be reordered).
   - Cut only on word boundaries using `words[i].s/.e` from the json. Keep ≥ 60 ms before the first word, ≥ 80 ms after the last.
   - Multi-file: segments can carry `"src": "path"`; b-roll goes in as its own segment or as an overlay.
3. Show the person a cut list, not JSON:
   ```
   #  source time        out time     keep
   1  00:00.42–00:03.08  00:00–00:02  "Hello and welcome to Nexa."
   ✂  removed 00:03.08–00:04.42 (1.3 s pause)
   ...
   Result: 7.5 s from 12.0 s (−38%). Captions: bold-pop. Aspect 9:16.
   ```
   For anything > 60 s or with graphics, add a short storyboard (beats, what's on screen, graphics).
   **Stop and wait for approval** unless they said "no stops" / "just do it".

## 3. Draft render → self-QA (before showing anything)
```bash
video-studio/vs captions $P/work/transcript.json $P/work/edl.json -o $P/work/captions --style bold-pop --aspect 9:16
video-studio/vs render $P/work/edl.json -o $P/out/draft.mp4 --preview --aspect 9:16 --captions $P/work/captions.ass --loudnorm -14
video-studio/vs qa $P/out/draft.mp4 --edl $P/work/edl.json --transcript $P/work/transcript.json --lufs -14
video-studio/vs filmstrip $P/out/draft.mp4 -o $P/work/cuts.png --cuts $P/work/edl.json
```
- Fix every FAIL; weigh every WARN. Read `cuts.png`: look for jarring jump cuts (same framing, head jump → suggest punch-in or b-roll), caption collisions with faces/UI, flashes.
- Self-correct up to 3 times before showing. Then tell the person what you checked.
- Use the `video-qa-reviewer` subagent for an independent pass on longer edits.

## 4. Graphics (only where they explain)
Motion graphics, titles, lower thirds, animated charts, end cards: `/motion-graphics`.
They come back as transparent renders placed via the EDL `overlays` array (output-timeline seconds).
Spawn the `motion-designer` subagent per graphic when there are several; they can run in parallel.

## 5. Iterate → GATE 2 (draft approval)
- Map each note to a concrete EDL / caption / overlay change; re-render only what changed (preview).
- A note that applies to future videos ("never cut my breaths", "captions smaller") → one line in `style/notes.md`.
- Log decisions in `project.md`.

## 6. Final
```bash
video-studio/vs render $P/work/edl.json -o $P/out/final.mp4 --aspect 9:16 --captions $P/work/captions.ass --loudnorm -14
video-studio/vs qa $P/out/final.mp4 --edl $P/work/edl.json --transcript $P/work/transcript.json --lufs -14
```
- Deliver `final.mp4` + `captions.srt` (for platform upload). Loudness: -14 LUFS social, -16 YouTube/podcast.
- Want to finish in Premiere/Resolve/FCP? `/video-nle-handoff`.
- Multiple deliverables (16:9 + 9:16) share one EDL; captions must be regenerated per aspect.

## Hard rules
1. Never cut inside a word. `qa` checks this; a FAIL blocks delivery.
2. Never alter the speaker's voice, face or words (no AI voice/face) unless explicitly asked.
3. Never full-quality render before the cut list is approved (unless told "no stops").
4. Raw footage is read-only. Everything you make goes in `work/` or `out/`.
5. Captions are generated from the same EDL that is rendered. Regenerate them after every EDL change.
6. Keep text and graphics inside title-safe (80%); on 9:16 keep clear of the bottom 20% and right 15% (platform UI).
7. Report honestly: if QA warns, say so; if transcription confidence is low, say which words.
