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
| `speed` | 1 | 0.25–4. Audio keeps pitch (atempo). Output length = (end−start)/speed |
| `fit` | `cover` | `cover` fill + crop · `contain` letterbox · `blur` letterbox over a blurred fill (vertical clip in a 16:9 edit, or vice versa) |
| `focus` | `[reframe, 0.5]` | crop anchor x,y 0..1. Vertical crop of a person on the left third: `[0.33, 0.4]` |
| `zoom` | 1 | punch-in factor (1.1–1.2 hides jump cuts) |
| `zoom_to` | — | animate zoom → Ken Burns / slow push. Images get 1→1.08 automatically (`"ken_burns": false` to stop) |
| `grade`, `lut` | EDL-level | per-shot look (see `/video-color`) |
| `stabilize` | false | ffmpeg deshake for handheld shots |
| `volume_db`, `mute` | 0, false | per-shot level; mute b-roll that has wind/noise |
| `transition_in` | none | `{"type", "dur"}` into this shot from the previous. Types: fade, dissolve, dip-black, dip-white, whip / slideleft / slideright / slideup / slidedown, wipeleft…, smoothleft…, circleopen, circleclose, radial, pixelize, zoomin, hblur. Overlaps the two shots by `dur` (the edit gets shorter by `dur`). |

## Output-level keys
| key | meaning |
|---|---|
| `reframe` | default horizontal crop anchor for every shot |
| `grade` / `lut` | global look (`none natural punchy bright warm cool cinematic teal-orange moody vintage film bw bw-contrast vibrant auto`) or a `.cube` file |
| `texts[]` | `text` (use `\n` for line breaks), `start`, `end`, `pos` (top, center, bottom, lower-third, top-left, top-right, bottom-left, bottom-right), `size` (fraction of the short side, default 0.075), `color`, `box` (background colour) , `anim` (pop, fade, none), `font`, `bold` |
| `overlays[]` | `file` (alpha .mov/.webm, video, or png), `start`, `end`, `in` (seconds into the file to start from: b-roll cutaways), `fit` (fill the frame with a crop, default unless `w`), `focus` (crop anchor for fit), `w` (px width), `x`/`y` (px or ffmpeg expressions like `W-w-60`), `opacity` |
| `sfx[]` | `file`, `at` (output s), `gain_db` |
| `music` | `file` (loops if short), `start` (offset into the track), `gain_db` (−18…−24 under speech, −6…−10 for montages), `duck` (sidechain under dialogue), `fade_out` |
| `audio_track` | `{"src", "start", "gain_db"}`: one continuous audio file under the whole edit (multicam mixes, music videos with the original song). Segment audio is ignored. |
| `audio.enhance` | voice clean-up on the dialogue bus: high-pass, denoise, de-ess, compression |

## Timing maths
Output start of segment k = sum of previous output lengths − overlaps of transitions. `vs` computes
it for captions, QA and filmstrips; to place a text or overlay on word *w* of segment *k*:
`out = seg_out_start + (w.s − seg.start) / speed`. When in doubt, render a preview and check with
`vs filmstrip --at <t>`.
