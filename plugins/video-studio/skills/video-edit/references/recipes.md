# Recipes by video type

Starting points. The person's `style/moves.md` and notes override these.

## Short-form talking head (Reels / TikTok / Shorts)
- Max pause 0.3–0.4 s, fillers out, hook in the first 1.5 s (strongest line, a bold claim, or a question).
- Punch-in 1.12–1.18 on every other cut; captions `bold-pop`; key words as `texts` pops.
- Music bed −20 dB ducked, a soft whoosh on big transitions only. `--preset reels|tiktok|shorts`, −14 LUFS.
- 20–60 s unless asked. End on the payoff or a one-line CTA, no long outro.

## YouTube long-form A-roll
- Max pause 0.5–0.7 s; keep breaths at sentence ends; chapters at topic changes (list them for the description).
- Punch-ins at emphasis, b-roll overlays every 10–20 s where the speaker refers to something visual.
- Captions optional burned (`clean`), always deliver `.srt`. `--preset youtube`, −14 LUFS.

## Ad / product promo (15–60 s)
- Structure: hook (0–3 s) → problem → product in use → proof (number, testimonial) → offer + CTA.
- Every shot ≤ 2.5 s, text on screen for every claim (`texts`, brand colour box), logo end card 2 s.
- Deliver 9:16, 1:1 and 16:9 from one EDL (regenerate captions per aspect; set `focus` per shot).

## Podcast / interview → see `/video-multicam`; clips → `/video-repurpose`

## Tutorial / screen recording → `/video-screencast`

## Montage / music video / travel / event highlights / slideshow → `/video-montage`

## Vlog
- Transcript cut for talking parts, b-roll segments between, music bed changes per location
  (new `music` needs a separate render pass or one long bed), natural sound kept low (`volume_db` −6) on b-roll.
- Grade `natural` or `warm`; stabilise handheld walking shots.

## Wedding / event film
- Speeches and vows: transcript-select the best 20–40 s; under them, slow b-roll (speed 0.5–0.8, `dissolve` 0.5 s).
- Music-led: cut to downbeats (`vs beats snap --downbeats`), `film` or `cinematic` grade, dip-black at chapter changes.

## Explainer / faceless
- Script → voiceover (person's own, or `/media-use` if they ask for generated voice) → HyperFrames scenes per
  paragraph (`/motion-graphics`), b-roll and stills with Ken Burns, captions `clean`.

## Real estate / product 360 / showcase
- Slow, steady: speed 0.8–1.0, `zoom_to` 1.06 pushes, 2–3 s per shot, `dissolve` 0.6 s, light `bright` grade,
  room/feature labels as lower-third `texts`, calm music −10 dB, no voice ducking needed.

## Reaction / commentary
- Two sources: main content full-frame, reaction as overlay `w` ~30% in a corner (`x: "W-w-40", y: 40`), or
  stacked for vertical (render each to half-height and use `fit: false` overlays). Keep commentary audio,
  duck the content audio (`volume_db` −10 on those segments).
