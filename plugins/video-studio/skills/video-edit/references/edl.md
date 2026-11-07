# EDL reference (`work/edl.json`)

All paths are relative to the folder `vs` runs in (the project root). Source times are seconds in
the source file; overlay/text/sfx times are seconds on the OUTPUT timeline.

```json
{
  "source": "video-studio/projects/x/raw/a-roll.mp4",
  "segments": [
    {"start": 12.40, "end": 15.10, "zoom": 1.15, "focus": [0.5, 0.4], "note": "hook"},
    {"src": "video-studio/projects/x/raw/broll1.mov", "start": 3.0, "end": 5.2, "speed": 0.5, "mute": true},
    {"start": 31.0, "end": 38.2, "transition_in": {"type": "fade", "dur": 0.3}},
    {"src": "video-studio/projects/x/raw/photo.jpg", "end": 3.0, "zoom": 1.0, "zoom_to": 1.12},
    {"src": "video-studio/projects/x/raw/phone.mp4", "start": 0, "end": 4, "fit": "blur"}
  ],
  "reframe": 0.5,
  "grade": "natural",
  "lut": null,
  "texts": [{"text": "THE FIX", "start": 3.0, "end": 5.0, "pos": "top", "anim": "pop", "box": "#111111"}],
  "overlays": [{"file": "video-studio/projects/x/work/gfx/lt/out.mov", "start": 0.5, "end": 3.5}],
  "sfx": [{"file": "sfx/whoosh.wav", "at": 2.65, "gain_db": -8}],
  "music": {"file": "music/bed.mp3", "gain_db": -20, "duck": true, "start": 0, "fade_out": 1.5},
  "audio_track": null,
  "audio": {"enhance": true}
}
```

## Segment keys
| key | default | meaning |
|---|---|---|
| `src` | EDL `source` | video, audio-less video, or image (jpg/png/webp/heic) |
| `start`, `end` | — | source seconds. Images: `end` = on-screen duration |
| `speed` | 1 | 0.25–4. Audio keeps pitch (atempo). Output length = (end−start)/speed. **Speed ramp:** `[[0, 1], [1.5, 0.3], [3, 1]]` = keys of [source seconds from `start`, speed], interpolated smoothly (exact, frame-accurate) |
| `reverse` | false | play the shot backwards (audio too). Keep reversed shots under ~30 s |
| `freeze` | — | seconds to hold the frame at `start` (freeze frame; `end` not needed, silent) |
| `kf` | — | keyframes, times in seconds from the shot's OUTPUT start: `zoom`, `x`, `y` (focus 0..1: pan/reframe that follows a subject), `rotate` (degrees). Each key `[t, value]` or `[t, value, "linear"/"in"/"out"/"inout"]` (ease into that key, default inout). Example push-in with a pan: `{"zoom": [[0, 1], [3, 1.3]], "x": [[0, 0.3], [3, 0.6]]}` |
| `audio_lead` | 0 | **J-cut**: this shot's audio starts this many seconds before its picture (over the end of the previous shot) |
| `audio_tail` | 0 | **L-cut**: this shot's audio continues this many seconds into the next shot |
| `fit` | `cover` | `cover` fill + crop · `contain` letterbox · `blur` letterbox over a blurred fill (vertical clip in a 16:9 edit, or vice versa) |
| `focus` | `[reframe, 0.5]` | crop anchor x,y 0..1. Vertical crop of a person on the left third: `[0.33, 0.4]` |
| `zoom` | 1 | punch-in factor (1.1–1.2 hides jump cuts) |
| `zoom_to` | — | animate zoom → Ken Burns / slow push. Images get 1→1.08 automatically (`"ken_burns": false` to stop) |
| `grade`, `lut` | EDL-level | per-shot look (see `/video-color`) |
| `stabilize` | false | `true` / `"light"` / `"strong"`: two-pass vid.stab (analysis cached), falls back to deshake |
| `volume_db`, `mute` | 0, false | per-shot level; mute b-roll that has wind/noise |
| `transition_in` | none | `{"type", "dur"}` into this shot from the previous. Types: fade, dissolve, dip-black, dip-white, whip / slideleft / slideright / slideup / slidedown, wipeleft…, smoothleft…, circleopen, circleclose, radial, pixelize, zoomin, hblur. Overlaps the two shots by `dur` (the edit gets shorter by `dur`). |

## Output-level keys
| key | meaning |
|---|---|
| `reframe` | default horizontal crop anchor for every shot |
| `grade` / `lut` | global look (`none natural punchy bright warm cool cinematic teal-orange moody vintage film bw bw-contrast vibrant auto`) or a `.cube` file |
| `texts[]` | `text` (use `\n` for line breaks), `start`, `end`, `pos` (top, center, bottom, lower-third, top-left, top-right, bottom-left, bottom-right), `size` (fraction of the short side, default 0.075), `color`, `box` (background colour) , `anim` (pop, fade, none), `font`, `bold` |
| `overlays[]` | `file` (alpha .mov/.webm, video, or png), `start`, `end`, `in` (seconds into the file to start from: b-roll cutaways), `fit` (fill the frame with a crop, default unless `w`), `focus` (crop anchor for fit), `w` (px width), `x`/`y` (px or ffmpeg expressions like `W-w-60`), `opacity`, `key` (`"green"`, `"blue"` or `{"color": "#00FF00", "similarity": 0.12, "blend": 0.08}`: green-screen key with despill), `fade_in`/`fade_out` (s), `kf` (`x`/`y` keyframes in px, times from the overlay's start: slide-ins, follow a subject) |
| `blurs[]` | hide faces, plates, logos: `start`, `end`, `x`, `y`, `w`, `h` (fractions of the frame), `mode` (`blur` or `pixelate`), `strength`, `kf` (`x`/`y` keyframes in OUTPUT seconds to follow a moving subject) |
| `tracks[]` | extra audio tracks (ambience, second music bed, VO): `name`, `gain_db` or `gain` (volume automation `[[t, dB], ...]`), `duck` (true or `{"threshold", "ratio", "attack", "release"}`), `clips[]`: `file`, `at` (output s), `in` (s into the file), `dur`, `gain_db`, `fade_in`, `fade_out`, `loop` |
| `sfx[]` | `file`, `at` (output s), `gain_db` |
| `music` | `file` (loops if short), `start` (offset into the track), `gain_db` (−18…−24 under speech, −6…−10 for montages), `duck` (sidechain under dialogue), `fade_out` |
| `audio_track` | `{"src", "start", "gain_db"}`: one continuous audio file under the whole edit (multicam mixes, music videos with the original song). Segment audio is ignored. |
| `audio.enhance` | voice clean-up on the dialogue bus: high-pass, denoise, de-ess, compression |
| `audio.gain` | dialogue-bus volume automation `[[t, dB], ...]` |

## Render options that matter
- `--preview`: half resolution, fast, and uses proxies (`vs proxy raw/`) so 4K/long sources stay quick. The audio always comes from the originals.
- Long edits (≥ 3 min) render in chunks split at hard cuts, in parallel, cached in `out/.vs-cache`: change one shot and only its chunk re-renders. `--chunks off|<seconds>`, `--jobs N`, `--no-cache`.
- `--codec h265 --10bit` or `--codec prores` for banding-free 10-bit masters; `--hdr` keeps HDR10/HLG sources HDR (otherwise they are tone-mapped to SDR).

## Timing maths
Output start of segment k = sum of previous output lengths − overlaps of transitions. `vs` computes
it for captions, QA and filmstrips; to place a text or overlay on word *w* of segment *k*:
`out = seg_out_start + (w.s − seg.start) / speed`. When in doubt, render a preview and check with
`vs filmstrip --at <t>`.
