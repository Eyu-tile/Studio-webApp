---
name: video-captions
description: Burned-in and sidecar captions/subtitles for edited videos, including word-by-word highlight "Hormozi/TikTok" captions, clean YouTube/LinkedIn subtitles, SRT export, caption restyling, safe zones for Reels/TikTok/Shorts, and fixing caption sync after cuts. Use when someone asks to add, restyle, fix or export captions or subtitles.
---

# Captions

Captions are generated from the word transcript remapped through the EDL, so they
stay in sync after cuts. Tool: `vs captions` → `<out>.ass` (burn) + `<out>.srt` (upload).

```bash
vs captions work/transcript.json work/edl.json -o work/captions \
  --style bold-pop --aspect 9:16 --accent "<brand colour>" --font "<brand font>"
vs render work/edl.json -o out/draft.mp4 --preview --aspect 9:16 --captions work/captions.ass
```

## Pick a style
| style | use for | look |
|-------|---------|------|
| `bold-pop` | Reels, TikTok, Shorts, ads | 1–3 words, UPPERCASE, active word in the accent colour, ~30% up from bottom |
| `karaoke` | music, lyric videos, energetic talking | up to 6 words, each word fills with the accent colour as it's spoken |
| `clean` | YouTube, LinkedIn, explainers, webinars | up to 8 words on a soft dark box, bottom third |
| `minimal` | brand films, calm pieces | small, thin outline, low |

Tune with `--max-words`, `--font`, `--accent`, `--text-color`; `--preset reels` sets the aspect. Take colours and font from `video-studio/style/brand.md`.

Multicam edits: caption from the mix transcript; words are mapped through each shot automatically.
Speed changes and transitions are accounted for.

## Rules
- `--aspect` must match the render's `--aspect`. Regenerate after EVERY EDL change.
- Fix transcript typos (brand names, jargon) in `work/transcript.json` `words[i].w` before generating, never in the .ass by hand. Re-transcribe with `--prompt "<names>"` if many are wrong.
- Numbers: write as digits ("3x faster", "$40k") by editing the word text.
- Safe zones: pass `--preset` (reels, tiktok, shorts, story, feed) and captions stay out of that platform's UI
  (Reels ads: top 14%, bottom 35%, sides 6%); without a preset, 9:16 keeps out of the bottom 30% and right 15%; 16:9 inside 80% title-safe. Check with `vs filmstrip out/draft.mp4 -o work/strip.png --every 3` and look for collisions with faces, slides or lower thirds. Move with a lower/higher style or by editing `MarginV` in the generated .ass `Style:` line.
- Platforms that auto-caption (YouTube, LinkedIn): also deliver the `.srt` so viewers can toggle.
- Fancier animated captions (per-word bounce, emoji, karaoke fills with motion): build them as a HyperFrames composition (`/hyperframes`, its `references/captions.md`) and place via EDL `overlays`.

Other languages: `/video-translate` (translated SRT/ASS on the edited timeline, and dubbing).
