# Cue sheet reference

The numbers `vs sfx plan` uses, and the ones to use when editing a plan by hand. Every value here is
what the planner does by default, so a hand-made cue and a planned cue sound the same.

## 1. Which point of the sound goes on the frame

A sound file is not "one moment". Measure it first (`vs sfx analyse <file|dir>`), then put the right
point on the frame, not the start of the file.

| sound | anchor | why | `vs sfx analyse` column |
|---|---|---|---|
| whoosh, swish, whip | **crest** (loudest 50 ms) | the object passes the camera on the cut | `crest` |
| riser, swell, reverse cymbal | **crest** | it tops out on the reveal, then gets cut | `crest` |
| impact, boom, braam, hit | **hit** (first 50 ms within 3 dB of the loudest) | skips silent lead-ins and pre-swells; a sustained boom starts on the frame | `hit` |
| click, pop, chime, typing, glitch, shutter, paper | **onset** (first 10 ms within 20 dB of the loudest) | starts on the action | `onset` |

`at = frame − anchor`. When that is before 0 s, the head is trimmed (`in`), never slid late.

Measured on the bundled library, these are the errors a fixed lead (whoosh 0.12 s early, others on the frame) causes:

| file | anchor | anchor time | error with a fixed lead |
|---|---|---|---|
| whoosh-cinematic.mp3 | crest | 2.90 s | 2.8 s late |
| riser.mp3 (10.03 s file) | crest | 3.02 s | "climax − 10.03 s" puts the crest 7 s early; the last 5.5 s are silence |
| chime.mp3 | onset | 0.41 s | 0.41 s late (10 frames at 25 fps) |
| impact-bass-2.mp3 | hit | 0.04 s | aligning its loudest frame (1.83 s) instead would put the boom 1.8 s early |

## 2. How long it plays

| rule | default | flag |
|---|---|---|
| build-up before the anchor, at most | 0.8 s (a longer one starts part-way in, faded in over ≤ 0.15 s) | `--max-head` |
| ring after the anchor, at most | 2.0 s, faded out over ≤ 0.25 s | `--max-tail` |
| a tail never covers the next hit | fades out by the next cue's frame + 0.05 s | always on |
| risers stop at the reveal | crest + 0.12 s, then cut (the hit takes over) | always on |
| risers fit the room | build = min(gap since the previous cue − 0.3 s, file's crest, 4 s); needs ≥ 1 s; one per 6 s | `--risers` |

## 3. How loud

Recordings from Openverse, Freesound and packs differ by up to 30 dB (bundled library: −1.6 to −31.6 dBFS
loudest-50 ms). Every file is normalised first: its loudest 50 ms RMS goes to **−12 dBFS** (at most +18 dB
of lift, sample peak never above −1 dBFS). A cue's `level_db` is relative to that, so 0 dB ≈ a dialogue
peak. `gain_db` in the plan is the final volume, already including the normalisation (`norm_db`).

| moment | cue | sound | level |
|---|---|---|---|
| fast transition (whip, slide, wipe, zoom) | transition-fast | whoosh → swell | −8 |
| glitch/pixelize transition | transition-glitch | glitch → whoosh | −12 |
| dip to black | transition-dip | impact → swell | −10 |
| soft dissolve | transition-soft | swell → whoosh | −14 |
| cut to another source | cut-section | whoosh → impact | −12 |
| every hard cut (montage) | cut | click → pop | −18 |
| big/centred title | text-big | impact → pop | −10 |
| small text / lower third | text | pop → click | −12 |
| overlay / sticker enters | overlay | whoosh → pop | −12 |
| logo / end card | logo | chime → impact | −10 |
| chart / number | chart | click → pop | −14 |
| photo reveal | image | swell → whoosh | −16 |
| typing on screen | type | typing → click | −16 |
| photo / flash | camera | shutter → click | −12 |
| downbeat (with `--beats --on-beats N`) | beat | impact | −9 |
| scene change in a finished video | scene | whoosh → click | −14 |
| build into logo / big title (`--risers`) | riser | riser → swell | −14 |

A cue that lands on a word (`--words` = `vs transcribe` JSON **of the edit itself**, so the times are
output times) is lowered by `--speech-duck` dB (6 by default, 8 for talking-head and tutorial styles).

## 4. How many: styles

`--style` sets density and level; any explicit flag overrides it.

| style | min gap | tick every cut | level offset | risers | dropped when over a word |
|---|---|---|---|---|---|
| talking-head | 5.0 s | no | −2 dB | no | cut, scene, chart, type |
| tutorial | 1.5 s | no | −2 dB | no | cut, scene |
| ugc-ad | 0.8 s | yes | 0 | no | cut |
| montage | 0.5 s | yes | 0 | yes | none |
| launch | 0.25 s | yes | +2 dB | yes | none |
| (none) | 0.35 s | no | 0 | no | none |

When two moments fall within the min gap, the more important one is kept:
logo > text-big > transition-fast > transition-glitch > transition-dip > beat > cut-section > overlay >
chart > transition-soft > image > camera > type > text > scene > cut.

Stereo: whooshes on a left-moving transition (whip, whip-left, *left) are panned −0.4, right-moving +0.4.

## 5. Finding the right sound

Search words that return usable effects on Openverse/Freesound (`vs fetch search "<words>" --type sfx --max-dur 4`):

| category | search words | avoid |
|---|---|---|
| whoosh | `whoosh fast`, `swish air`, `swoosh transition`, `whip pan` | "transition" alone (returns music stings) |
| riser | `riser cinematic`, `uplifter`, `tension rise`, `reverse cymbal` | anything over 8 s |
| impact | `impact cinematic`, `boom sub`, `braam`, `punch hit` | "explosion" (debris tails) |
| pop | `pop mouth`, `bubble pop`, `ui pop` | "pop music" |
| click | `ui click`, `button click`, `mouse click`, `switch toggle` | |
| chime | `chime notification`, `success ding`, `bell short`, `sparkle` | "bell" alone (church bells) |
| glitch | `glitch digital`, `static burst`, `data glitch` | |
| type | `typing keyboard`, `typewriter key` | |
| camera | `camera shutter`, `shutter click` | |
| swell | `swell whoosh`, `reverse swell`, `suck back` | |
| paper | `page flip`, `paper rustle` | |

Save it with the category word first in the filename (`whoosh_air_fast.wav`) so the planner files it.
Prefer files under 4 s, with < 0.3 s of silence before the sound, 44.1/48 kHz, CC0 or CC BY.
Then run `vs sfx analyse` on the folder: a sound whose `hit dB` is below −40 or whose `onset` is past 1 s
is either mostly silence or the wrong cut; trim it or drop it.

## 6. Checks before showing a draft

1. `sfx_plan.md`: no category marked missing; no two identical files in a row.
2. Listen at the cue times, or `vs earshot timeline out/draft_sfx.mp4 --json`: every event within 1 frame
   (40 ms at 25 fps) of its `frame` column.
3. Talking content: no cue over a word at a level above −14 dB; `vs qa` loudness still on target.
4. Music + SFX: if a big hit is masked, lower the music 2–3 dB around it; never duck the music for small cues.
