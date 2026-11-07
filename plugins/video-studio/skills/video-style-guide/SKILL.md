---
name: video-style-guide
description: Learn an editing style from reference videos (the person's past edits or creators they like) and write it into reusable rules - pacing, cut rhythm, caption look, punch-ins, graphics, music, hooks. Use when someone says "edit it like this", "match my style", "copy this creator's style", shares reference videos/links, or wants a brand video style guide. Updates video-studio/style/moves.md and brand.md.
---

# Style guide from references

Goal: turn 2–3 reference videos into concrete, numbered "moves" in
`video-studio/style/moves.md` that every future edit applies.

## 1. Collect
- Local files → `video-studio/style/refs/` (gitignored).
- Links (only content the person has rights to study): `vs yt-dlp -f "bv*[height<=720]+ba/b[height<=720]" -o "video-studio/style/refs/%(title).60s.%(ext)s" <url>`
  Instagram/TikTok often need a login: add `--cookies-from-browser chrome` (or safari/firefox) after the person
  has logged in there, or ask them to save the file into `style/refs/`.

## 2. Measure (numbers, not vibes)
For each reference:
```bash
R=video-studio/style/refs/<file>
vs probe "$R"
vs transcribe "$R" -o video-studio/style/refs/<name>.transcript --model small
vs scenes "$R" -o video-studio/style/refs/<name>.scenes      # cuts/min, median shot, one frame per shot
vs filmstrip "$R" -o video-studio/style/refs/<name>.png --every 2 --max 40
vs qa "$R"                                                      # loudness of the reference
```
From these derive:
- **Pacing**: cuts/min and median shot from `scenes.json`, words per minute from the transcript, longest pause kept.
- **Hook**: what happens in the first 3 s (cold open line? text hook? motion?).
- **Captions**: words per card, case, position (% from bottom), highlight colour, font weight. Read the PNG.
- **Framing**: punch-ins (zoom jumps between cuts), split screens, b-roll ratio.
- **Graphics**: lower thirds, keyword pops, charts, emoji, progress bars; durations.
- **Sound**: music under voice? ducking depth? SFX on cuts/graphics? loudness. Music tempo: `vs beats detect "$R"`, and whether cuts land on beats.
- **Look**: grade (warm/cool, contrast, saturation, grain, vignette) → nearest `/video-color` grade.
- **Transitions**: hard cuts vs whips/fades and where (`scenes.png` shows them).
- **End**: CTA style, end card length.

## 3. Write
- Update `moves.md` table rows: trigger → spec with numbers (e.g. "punch-in 112% on every 2nd cut, hard cut, never two in a row").
- Map caption look to `vs captions` flags (`--style`, `--max-words`, `--accent`) and note them.
- Update `brand.md` only for brand facts (colour, type, logo), not per-video choices.
- Show the person a 10-line summary and ask what to keep/drop before saving.

## 4. Apply
`/video-edit` reads `moves.md` before planning. When feedback contradicts a move, update the move.
