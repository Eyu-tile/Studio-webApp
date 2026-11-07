---
name: video-screencast
description: Edit screen recordings - software tutorials, product demos, walkthroughs, course lessons, bug repro videos, Loom-style recordings - with dead-time removal, speed-ups for typing/loading, zooms into the part of the screen that matters, step titles, webcam bubble, and captions. Use when the footage is mostly a screen.
---

# Screen recordings

## 1. Understand
- Narrated: `vs transcribe` → the narration drives the cut (like a talking head).
- Silent: `vs silences` won't help; use `vs scenes <rec> -o work/rec.scenes --threshold 0.08` (screen
  changes are subtle) plus `vs filmstrip --every 3` to see what happens when.
- Find the action: which region of the screen matters at each step (Read contact sheets at those times).

## 2. Cut
- Remove: waiting/loading, mistakes and their undo, long pauses, mouse wandering, "um, let me find it".
- Speed instead of cut where continuity matters: typing, installs, scrolling → `speed` 2–6, `mute: true`
  (or keep narration and speed only the gap). Tell viewers with a small `texts` "3× speed" top-right.
- Steps: a `texts` title per step ("Step 2 · Connect your account", lower-third or top, `box` brand colour).

## 3. Zoom where it matters
Screen text is unreadable on phones. Per segment set `zoom` (1.5–2.5) and `focus` to the region's centre
(x,y as fractions of the screen: a button at 1500,200 on a 1920×1080 recording → `[0.78, 0.19]`).
Use `zoom_to` for a smooth push-in when attention moves into a region, then a hard cut back to 1.0.
Vertical (9:16) versions of tutorials need zoom on almost every shot.

## 4. Webcam bubble
Separate webcam file: sync it (`vs sync screen.mp4 cam.mp4`), then add as an overlay
`{"file": cam, "start": 0, "end": <len>, "w": 360, "x": "W-w-40", "y": "H-h-40"}` (rectangular; for a circle,
render the cam through a HyperFrames composition with a circular mask via `/motion-graphics`).

## 5. Finish
- Captions `clean` (16:9) and `.srt`. Audio `{"enhance": true}` for laptop mics.
- `--preset youtube` (16:9) and a vertical cut if wanted. Export chapters (step titles + times) for the description.
- Sharpness: export at the recording's native resolution (no `--aspect` scaling) for crisp text.
