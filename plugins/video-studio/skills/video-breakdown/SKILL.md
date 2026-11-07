---
name: video-breakdown
description: Break down how a reference video was made, shot by shot - cuts and pacing, camera moves (static, handheld, pan, tilt, push in, pull out), look and grade, transitions, music tempo and cuts on the beat, sound-effect hits, and (with the optional rea-video forensics) whether each shot is live action, AI video, 3D, animation, screen recording or a code-made template, plus its on-screen text timeline - then turn it into a remake plan and a ready-to-fill EDL. Use when someone asks "how was this made", "is this AI", "what would it take to remake this", "break down this ad", or shares winning ads to turn into a template.
---

# Break down a reference video

The output answers three questions with evidence: **how was it cut**, **how was each shot made**, and **what
would it take to remake it** (what to film, what to generate, what to build as graphics). Only break down videos
the person may study; a remake uses their own footage, music and script, never the reference's.

## 1. Measure (always)
From a link (Instagram, TikTok, YouTube, X, Vimeo, Drive, a direct file...), watch it first:
```bash
vs watch "<link>" -o work/ref          # video + caption + transcript + breakdown + frame sheets -> watch.md
```
For a file you already have:
```bash
vs breakdown ref.mp4 -o work/ref
```
Gives `work/ref/report.md` (read this first), `breakdown.json`, `sheet.png` (one frame per shot) and
`remake_edl.json`. It measures:
- **Pacing**: shots, cuts/min, median and spread of shot lengths, first cut (the hook length), even vs varied rhythm.
- **Camera per shot**: `frozen / still` (photo, graphic hold, freeze), `static`, `handheld`, `pan`, `tilt`,
  `push in`, `pull out`, with speeds. Push-ins between cuts on the same set usually mean digital punch-ins.
- **Look per shot**: brightness, contrast, saturation, warmth, palette, nearest grade preset.
- **Transitions**: dips to black/white at cuts (whips and wipes show as fast pans or as cuts; check the sheet).
- **Sound**: loudness, tempo with a confidence check, % of cuts within 70 ms of a beat, strong transients
  (sound-effect candidates: confirm by listening, or with earshot if installed).

`--threshold 0.25` finds soft cuts in dark or low-contrast footage; raise it to 0.4 if handheld motion
creates false cuts. Check the shot count against `sheet.png` before trusting the numbers.

## 2. Look (always)
Open `sheet.png` and, for any shot that matters, `vs filmstrip ref.mp4 -o work/ref/sN.png --at a,b,c`. Decide
per shot what the numbers can't: **source** (live action, stock, AI video, avatar/lip-sync, 3D render, 2D
animation, stop-motion, screen recording, code/template graphics, photo with a push), **framing** (wide,
medium, close-up, overhead, POV), **who/what is in frame**, and **text on screen** (captions, titles,
stickers, their style and timing). Say how sure you are; write "unclear" rather than guess. Tells for AI video:
warping hands and text, physics that drifts, texture that crawls, generator watermarks, one continuous
camera move per clip at a fixed length (4/5/8/10 s).

## 3. Deep forensics (optional)
For many shots, mixed AI and live footage, or an exact text/caption timeline, use rea-video (Apache-2.0,
by JuneYaooo; installs its own venv, ~1 GB with OCR models):
```bash
vs setup --rea                                   # once
vs rea decompose ref.mp4 -o work/ref/rea --lang en
vs rea summary work/ref/rea/breakdown.json       # read this, not the full JSON
vs rea review work/ref/rea                       # writes review_tasks.json; look at the images it lists
vs rea apply-review work/ref/rea --by claude     # merge your judgements back into its report
```
It classifies each shot into 11 source types with evidence, reads on-screen text into SRT/ASS with
colours and entrances, finds stickers and picture-in-picture, separates vocals from music, and estimates
lighting setups. Its vision-model mode (`--vlm`) needs an API key in an env file: never ask for keys in chat.
Treat its labels as evidence to check, not answers.

## 4. Write the remake plan
Per shot, one line: time, length, what it shows, source type, **route** (film it / use stock or the
person's library / generate / build as a graphic with `/motion-graphics` or HyperFrames / screen-record), and
the camera move and look to match. Then totals: what to shoot (a shot list with framing and lighting
notes), what to generate (prompts that keep characters consistent), what to build, what music and
sound to find (tempo from step 1, `/video-music`, `/video-sound-design`).

## 5. Fill the template
`remake_edl.json` already holds one slot per shot with the reference's lengths, camera moves (as
keyframes), transitions, overall grade and a music slot at the reference tempo. Replace each `SLOT_xx` with a
real file and its `start`/`end`, the music slot with a licensed track, add texts/captions, then follow
`/video-edit` (render a preview, QA, notes). `vs beats snap` puts the cuts back on the new track's beat.

## Templates from winning ads
To turn several approved ads into a reusable format, break each one down, then write the shared pattern
into `video-studio/style/moves.md` with `/video-style-guide`: hook length, shots per second, the order of beats
(hook → problem → product → proof → CTA), caption style, music tempo, and which shot types repeat.
