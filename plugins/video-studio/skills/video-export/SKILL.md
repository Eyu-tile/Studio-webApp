---
name: video-export
description: Deliver finished videos for every platform - Reels, TikTok, Shorts, Stories, YouTube (incl. 4K), LinkedIn, X, feed 4:5, podcasts, broadcast - plus multi-aspect versions from one edit, GIFs, WebM, ProRes masters, audio-only, files under a size limit (email, WhatsApp, Discord), thumbnails/cover frames, subtitles and chapter lists. Use when someone asks to export, deliver, resize, compress, make a GIF, make a thumbnail, or post to a platform.
---

# Export & delivery

## Platform presets (`--preset`)
| preset | aspect | loudness | length check |
|---|---|---|---|
| `reels` | 9:16 | −14 | 90 s |
| `tiktok` | 9:16 | −14 | 10 min |
| `shorts` | 9:16 | −14 | 3 min |
| `story` | 9:16 | −14 | 60 s per card |
| `feed` | 4:5 | −14 | 60 s |
| `linkedin` | 1:1 | −14 | 10 min |
| `x` | 16:9 | −14 | 140 s |
| `youtube` / `youtube-4k` | 16:9 (×2) | −14 | — |
| `podcast` | 16:9 | −16 | — |
| `broadcast` | 16:9 | −23 | — |

`vs render work/edl.json -o out/final_reels.mp4 --preset reels --captions work/cap_916.ass`
then `vs qa out/final_reels.mp4 --edl work/edl.json --preset reels`.

## Several aspects from one edit
For each aspect: set shot `focus` so subjects stay in frame (check with filmstrips), regenerate captions with
the same `--preset`, render. Text/overlays positioned with `pos` adapt; pixel-placed overlays need per-aspect values
(copy the EDL to `edl_916.json` when they differ).

## Formats (`vs convert`)
| need | command |
|---|---|
| GIF | `vs convert out/final.mp4 -o out/clip.gif --width 480 --fps 12 --start 3 --end 9` |
| web / smaller | `vs convert out/final.mp4 -o out/final.webm` |
| master for editors | `vs render ... --codec prores -o out/master.mov` or `vs convert ... -o x.mov` |
| HEVC (smaller, Apple-friendly) | `vs render ... --codec h265` |
| size limit | `vs convert out/final.mp4 -o out/final_16mb.mp4 --target-mb 15` (WhatsApp 16 MB, Discord 10/25 MB, email ~20 MB) |
| audio only | `vs convert out/final.mp4 -o out/final.mp3` |
| resize | `vs convert out/final.mp4 -o out/final_720.mp4 --height 720` |

## Thumbnails / covers
`vs thumbs out/final.mp4 -o work/thumbs --n 8` → `ranked.json` scores each candidate (sharpness, exposure, contrast, colour, faces; dark/blurry rejected); Read `candidates.png` and pick an expressive frame from the top ones →
`vs thumbs out/final.mp4 -o out/thumb.jpg --at <t> --title "3 WORDS MAX" --size 1280x720` (Reels cover
`1080x1920`). Richer designs (cut-out person, arrows, brand layout) via `/motion-graphics` as a still.

## Sidecars
- Subtitles: `work/captions.srt` (re-run `vs captions` on the final EDL). Translations: translate the SRT
  text line by line (keep timings), save `captions.<lang>.srt`; burn with `--captions file.srt` if needed.
- YouTube chapters: list `MM:SS Title` from section starts (first must be 00:00, ≥ 3 chapters, ≥ 10 s each).
- Post copy: title, description, hashtags in the person's voice → `out/post.md`.
