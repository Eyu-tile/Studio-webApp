---
name: video-color
description: Colour and look for video edits - correct dark, flat or washed-out footage, apply a look (cinematic, warm, punchy, film, black and white), apply LUTs (.cube), handle iPhone HDR / log footage, match shots from different cameras, and match a reference video's look. Use for "make it look cinematic", "colour grade", "it looks dull", "apply this LUT", "the colours don't match".
---

# Colour

Grades are ffmpeg filter chains chosen by name, per EDL (`"grade"`) or per segment (`seg.grade`), plus
optional LUTs (`"lut": "path.cube"`). Always judge on stills: `vs render --preview --range a-b` then
`vs filmstrip --at ...` and Read the PNG; compare before/after side by side.

## Built-in grades
| name | for |
|---|---|
| `natural` | gentle contrast/saturation lift: safe default for people |
| `punchy` | social: more contrast, saturation, slight sharpen |
| `bright` | under-exposed indoor footage |
| `warm` / `cool` | white-balance shift (golden / clinical-tech) |
| `cinematic` | teal shadows, warm highlights, softer saturation, vignette |
| `teal-orange` | stronger blockbuster split-tone |
| `moody` | darker, desaturated, vignette |
| `vintage` / `film` | faded curves / film contrast + grain |
| `bw` / `bw-contrast` | monochrome |
| `vibrant` | boosts muted colours without over-saturating skin |
| `auto` | normalises black/white points per frame (fixes flat/log-ish footage; can pump on lighting changes) |

## Workflow
1. Correct first, then style: fix problem shots per segment (`bright`, `auto`, `warm`) so they sit together,
   then one global look.
2. Mixed cameras: pick the best-looking shot as reference; per segment adjust with `warm`/`cool`/`bright`
   until filmstrip frames read as one scene. For precise matches use a LUT per camera.
3. LUTs: camera log footage (S-Log, V-Log, Apple Log, D-Log) needs the manufacturer's log→Rec.709 LUT as `seg.lut`
   first; creative LUTs go on the EDL `lut`. Only one `lut` per level, so bake log conversion per segment and
   creative look globally.
4. iPhone/Android HDR (HLG/Dolby Vision) is tone-mapped to SDR automatically (`hdr` flag in probe/ingest);
   if it still looks flat, add `natural` or `punchy`.
5. Skin tones are the test: if faces go orange/green, back off. Prefer subtle.

## Match a reference look
Grab 3–4 reference frames (`vs filmstrip ref.mp4 --every 5`) and your footage at similar moments. Describe
the difference (contrast, black level, saturation, warmth, split-tone, grain, vignette), choose the nearest
grade, and iterate per segment. To match exactly, fit a LUT from a reference frame:
`vs ai match ref.png raw/camB.mp4 -o assets/luts/camB.cube --at 12 [--strength 0.8]` (mean/covariance +
per-channel histogram transfer, prints the colour distance before/after), then `"lut": "assets/luts/camB.cube"` on
that camera's shots. Matching camera B to camera A in multicam: use a frame of A as the reference. Record the final choice in `style/moves.md` so future edits reuse it.
