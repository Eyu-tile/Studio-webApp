---
name: video-repurpose
description: Turn long videos (podcasts, webinars, livestreams, talks, interviews, YouTube videos) into multiple short clips for Reels, TikTok, Shorts and LinkedIn - find the best moments, give each a hook, reframe to vertical, caption, and batch-render. Use for "make clips from this", "find the viral moments", "cut this into shorts", "repurpose this podcast".
---

# Repurpose long → shorts

## 1. Find moments (text first)
1. `vs transcribe <long> -o $P/work/long.transcript --model small` and read the packed `.md`
   (for > 30 min, spawn `edit-planner` with the brief "find clip candidates" so the main context stays small).
2. Score candidates on: a self-contained idea (makes sense with zero context), a strong first sentence
   (or one you can move to the front), a payoff/punchline, emotion or a surprising fact, 20–60 s of speech.
3. Present a table → **approval gate**:
   ```
   #  source range       len   hook (first line on screen)            why it works
   1  14:02.1–14:48.6   46 s  "Nobody tells you this about pricing"   contrarian, clear payoff at 14:40
   ```
   Typical yield: 5–10 clips per hour of good conversation. Ask how many they want.

## 2. Build each clip
For each approved clip, write `work/clip_<n>.edl.json`:
- `vs cuts` on the transcript then keep only that range, or write segments by hand from word times.
- Hook: open on the strongest line (reorder), cut the warm-up, end right after the payoff.
- Reframe for 9:16: `focus` on the speaker (check a frame: `vs filmstrip <src> --at <t>`); multicam
  sources → pick the angle of whoever speaks, wide shots become `fit: "blur"`.
- Hook text for the first 2–3 s: `texts` at `top`, `anim: pop`; captions `bold-pop`.
- Optional: music bed −22 dB ducked, punch-ins on alternate cuts.

## 3. Batch render + QA
```bash
for n in 1 2 3; do
  vs captions $P/work/long.transcript.json $P/work/clip_$n.edl.json -o $P/work/clip_$n.cap --style bold-pop --preset reels
  vs render $P/work/clip_$n.edl.json -o $P/out/clip_$n.mp4 --preset reels --captions $P/work/clip_$n.cap.ass --preview
  vs qa $P/out/clip_$n.mp4 --edl $P/work/clip_$n.edl.json --transcript $P/work/long.transcript.json --preset reels
done
```
Show all drafts together (paths + contact sheets), take notes, then final renders without `--preview`.

## 4. Package
For each clip: title, caption text + hashtags (ask for the brand voice), cover frame (`vs thumbs --at`),
`.srt`. Write them to `$P/out/clips.md`.
