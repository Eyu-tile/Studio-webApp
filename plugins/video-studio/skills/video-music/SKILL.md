---
name: video-music
description: Background music for any video - choose the right mood, genre and tempo, find free licensed tracks on the internet (Jamendo, Openverse, Incompetech / Kevin MacLeod, ccMixter, Internet Archive, Freesound) or use the person's own, fit the track to the exact edit length on downbeats, mix it under dialogue with ducking, and log the credit line. Use for "add background music", "find a track", "the music doesn't fit", "make the song end with the video", "music for my reel/ad/vlog".
---

# Background music

## 1. Brief → search terms (before searching)
From the brief, transcript and `style/brand.md` decide, and say in one line:
- **Role**: bed under speech (instrumental, steady, no big drops) vs. lead (montage, ad, trailer).
- **Mood**: uplifting, confident, warm, playful, inspiring, dark, tense, calm, epic, nostalgic.
- **Genre/texture**: corporate pop, lo-fi, acoustic, piano, ambient, electronic, cinematic, hip-hop, funk, orchestral.
- **Tempo**: calm 70–90 BPM, conversational 90–110, energetic 110–130, hype 128+. Shorts usually 100–128.
- **Length**: the edit length (`vs music fit` handles the rest).

## 2. Find tracks
```bash
vs fetch search "uplifting corporate acoustic" --type music --instrumental --bpm-min 95 --bpm-max 120 --project P
# -> work/assets/<query>_music.md: provider, title, length, BPM/speed, tags, licence, credit needed
vs fetch get video-studio/projects/P/work/assets/<query>_music.json 2 5
vs music analyze video-studio/projects/P/assets/music/<file>     # BPM, loudness, intro/outro, downbeats
```
| source | what | key |
|---|---|---|
| `jamendo` | 500k+ CC tracks with mood/genre/instrument tags, instrumental filter | free client id: `vs keys set jamendo` |
| `openverse` | CC music from Jamendo, ccMixter, Freesound and more | none |
| `incompetech` | Kevin MacLeod's 2,000+ production tracks (CC BY 4.0), searchable by feel/genre/BPM | none |
| `ccmixter` | CC remixes, beds and instrumentals | none |
| `archive` | public-domain recordings and CC albums | none |
| `freesound` | loops, ambiences, stingers | free key |
| person's files / library | `vs add track.mp3 --as music --project P` or `--library` | — |
| GitHub packs | `vs packs add <repo> --kind music --license ...` for a CC0/CC BY music repo | — |
| generated | `/media-use` (only when asked or nothing fits) | — |

Defaults exclude NonCommercial/NoDerivatives licences (`--allow-nc` for personal projects only). Shortlist 2–3
tracks, tell the person why each fits, and let them choose when taste matters (or pick for "no stops").
Never use a reference video's song, chart music, or anything ripped from a streaming service.

## 3. Fit it to the edit
```bash
vs music fit video-studio/projects/P/assets/music/<file> --edl video-studio/projects/P/work/edl.json \
  -o video-studio/projects/P/work/music_fit.wav
```
- Longer track → keeps the opening and the real ending and removes whole bars from the middle on a downbeat:
  the song ends on the last frame, no fade-out needed.
- Shorter track → loops whole bars of the body with crossfades, then the ending.
- With `--edl`, it writes the EDL `music` entry: −20 dB and ducking under dialogue, −8 dB without.
  `--start 12.5` to begin later in the song, `--gain-db` to override.
- Montage on the beat: fit first, then `vs beats detect work/music_fit.wav` and `vs beats snap` (`/video-montage`).

## 4. Mix & check
- Render, then `vs qa` (loudness) and listen by data: speech must stay intelligible. If music fights the voice,
  lower `gain_db` 2–4 dB or pick a sparser track (fewer mids, no vocals).
- Big moments: let music swell where there's no speech (place the hook/drop on a visual peak), and keep the
  ending on the final frame or a logo hit.
- Optional: `vs earshot timeline out/draft.mp4` (do the music accents land on cuts?), and for promos
  `vs earshot critique out/draft.mp4`.

## 5. Credits
CC BY / BY-SA tracks need a credit line: `vs credits --project P` prints them (Incompetech's exact required
wording included). Put them in the video description and tell the person.
