---
name: video-montage
description: Music-driven and footage-driven edits without a script - b-roll montages, music videos, travel/vacation films, event and sports highlights, brand sizzle reels, photo slideshows, wedding highlight films, beat-synced cuts. Use when the edit is built from many clips or photos and a song rather than from what someone says.
---

# Montage / music-driven edits

## 1. Gather and log
Editor's media first: `vs add <folders|zips|links> --project <name>`. Gaps (an establishing shot, a texture, a song)
→ `/video-assets` stock search. Then:
```bash
vs ingest $P/raw -o $P/work/media          # catalogue + a contact sheet per clip
vs scenes $P/raw/<long-clip> -o $P/work/<clip>.scenes   # split long camera rolls into shots
vs beats detect $P/raw/<song> -o $P/work/beats.json      # bpm, beats, downbeats
```
Read `media.md` and the contact sheets you need. For 20+ clips spawn `footage-logger` to rate shots
(subject, motion, quality 1–5, best moment in/out) into `work/shotlog.md`.

## 2. Structure before shots
- Map the song: intro / build / drop or chorus / outro from beat energy and length (ask if unsure).
- Story arc: establishing (wide, place) → people/action → peak moments on the drop/chorus → calm ending.
- Shot length by section: intro 2–4 beats, build 2 beats, drop 1 beat, outro 4+ beats.
- Present this as a storyboard table (section, beats, shot ideas) → **approval gate**.

## 3. Assemble
1. Pick the best 1–3 s of each chosen shot (motion peaks, faces, no shake). Write segments with `src`,
   `start`, `end`, `mute: true` (unless natural sound is wanted), `stabilize` for handheld.
2. Photos: image segments with Ken Burns (automatic) — vary direction with `focus` and `zoom_to` < 1 for pull-outs.
3. Mixed orientation: `fit: "blur"` for vertical clips in 16:9 (or landscape in 9:16) instead of hard crops,
   or `focus` to crop on the subject.
4. Speed: `speed` 0.5 for slow-mo moments (needs 50/60 fps source to look smooth), 2–4 for time-lapse feels.
5. Add `"music": {"file": song, "gain_db": -6, "duck": false}` (use `start` to skip an intro).
6. Snap to the beat: `vs beats snap $P/work/edl.json --beats $P/work/beats.json -o $P/work/edl.beat.json --every 2`
   (`--every 1` for the drop, `--downbeats` for slow sections; snap section by section if pacing changes:
   split the EDL, snap each, recombine).
7. Transitions after snapping, sparingly: `dissolve`/`fade` 0.4–0.8 s for emotional pieces, `whip`/slide
   0.2 s for energetic ones, `dip-black` between chapters. Hard cuts on the beat are usually best.
8. Titles: place, date, names as `texts` (lower-third or center, `fade`), end card via `/motion-graphics`.
9. Look: one `grade` for everything (`cinematic`, `film`, `warm`, `vibrant`), per-shot fixes via `/video-color`.

## 4. Check
`vs render --preview` → `vs filmstrip --cuts` → `vs qa`. Watch for: two similar shots back-to-back,
a cut half a beat late, horizon tilts, faces cropped by reframing, the music ending abruptly (end on a
downbeat; set `music.fade_out`).

## Music video with the original song
Use `"audio_track": {"src": song}` instead of `music` so the song plays untouched and the picture
cuts on its beats; lip-sync shots must keep source times aligned with the song (sync performance takes
to the song with `vs sync song.wav take1.mp4 ...`, then set each segment's `start` = song time − offset).
