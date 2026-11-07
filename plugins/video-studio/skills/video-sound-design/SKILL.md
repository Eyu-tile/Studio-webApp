---
name: video-sound-design
description: Sound design for edits and motion graphics - find every moment that wants a sound (cuts, transitions, text pops, overlays, logo reveals, chart builds, HyperFrames clip entrances, scene changes in any render) and place real recordings on the exact frame; build an SFX library from Openverse/Freesound/your files or earshot's code-made bank; listen to and score a mix with earshot. Use for "add sound effects", "sound design this", "make it sound like a launch film", "the edit feels flat/silent", or after rendering a HyperFrames/motion piece.
---

# Sound design

Background music is its own skill: `/video-music`. Three layers here, all free:
1. **Real recordings** placed on the frame by `vs sfx` (the plugin's own "real SFX" engine).
2. **Libraries** to draw from: your files, Openverse (no key, CC-licensed sounds), Freesound (free key),
   the CC sounds bundled with `media-use`, and earshot's 250+ code-made effects.
3. **Ears**: earshot (optional, MIT) describes, finds and scores sound, including a launch-film scorecard.

## 1. Build the library (once per machine/workspace, reused by every project)
```bash
vs packs install --defaults                             # free GitHub sound libraries, CC0: uisfx (936 sounds, 12 styles) + Kenney Interface (100)
vs packs list                                           # what's registered / installed
vs packs add https://github.com/<user>/<repo> --name x --path audio --license CC0-1.0   # any free sound repo
vs sfx library                                          # what's available, by category
vs fetch search "whoosh transition" --type sfx --max-dur 3 --library    # Openverse first (no key), then Freesound
vs fetch get <results.json> 1 3 4 --library
vs add ~/Sounds/brand-kit/ --as sfx --library           # your own recordings
vs sfx bank --from earshot                              # render earshot's bank (needs vs setup --earshot)
```
Categories come from filenames (UI cue names like success, swipe, toggle, unlock, level-up are understood):
whoosh, riser, impact, pop, click, chime, glitch, swell, camera, type, paper. uisfx styles (cinematic, glass,
studio, minimal, soft, scifi, arcade, organic, zen, dreamy, rubber, mechanical) are picked with `--prefer`.
Rename files so the category word is in the name (`whoosh_air_fast.wav`). Licences go to `CREDITS.md`.

## 2. Plan (moments → sounds)
```bash
vs sfx plan --edl $P/work/edl.json -o $P/work/sfx_plan.json                 # transitions, text pops, overlays, photos, source changes
vs sfx plan --hyperframes $P/work/gfx/launch -o $P/work/sfx_plan.json       # every timed clip in a HyperFrames film (follows sub-compositions)
vs sfx plan --video $P/out/draft.mp4 -o $P/work/sfx_plan.json               # any finished video: scene changes
  [--prefer cinematic,studio] [--beats $P/work/beats.json --on-beats 1] [--every-cut] [--min-gap 0.35] [--gain-offset -3]
```
Read `sfx_plan.md`. Edit the JSON (swap `file`, move `at`, change `gain_db`, delete cues) until it reads like
a sound designer's cue sheet, then show it to the person for approval along with the draft.

Taste rules:
- Fewer, better: talking heads ≈ one cue per 5–10 s; launch films and motion pieces can hit every beat.
- Whooshes lead the cut by ~0.1 s; impacts and pops land on the frame; risers end on the reveal.
- Never cover speech: keep SFX under −10 dB when someone talks, or place them in pauses.
- Vary: the planner rotates files per category; still listen for a repeated sound in a row.
- Music + SFX: duck nothing for SFX; lower the music 2–3 dB around big hits if they mask each other.

## 3. Apply
```bash
vs sfx apply $P/out/draft.mp4 --plan $P/work/sfx_plan.json -o $P/out/draft_sfx.mp4 --stem $P/out/sfx_stem.wav
vs sfx merge $P/work/edl.json --plan $P/work/sfx_plan.json -o $P/work/edl.sfx.json   # or bake into the EDL and vs render
```
`apply` keeps the picture and original audio untouched and adds the SFX bus; `--stem` writes the SFX alone
as a WAV to drop into Premiere / After Effects / Resolve. For HyperFrames films, apply to the HyperFrames render.

## 4. Listen with earshot (optional, CPU-only, ~1.3 GB)
Install once: `vs setup --earshot` (MIT, https://github.com/Leonxlnx/earshot). Each call loads models (~20–40 s);
for many calls, the person can add its MCP server (setup prints the `claude mcp add earshot ...` line).
```bash
vs earshot critique $P/out/draft_sfx.mp4 --json        # launch-film scorecard vs 7 pro films, timestamped fixes
vs earshot timeline $P/out/draft_sfx.mp4 --json        # what is heard when: events, loudness, beat grid, sync to cuts
vs earshot describe $P/assets/sfx/x.wav                # what a sound is (tags, AudioSet labels)
vs earshot rank "a deep cinematic impact" $P/assets/sfx/*.wav   # pick the best candidate by description
vs earshot find long_recording.wav "a single camera shutter" --top 4    # cut usable hits out of a long take
vs earshot sfx list | sfx render <id> -o x.wav         # code-made effects (no models, offline)
vs earshot kit init --preset launch -o $P/work/kit.json && vs earshot kit render $P/work/kit.json --out $P/assets/sfx/kit
```
Use `critique` as a second opinion, not a verdict: it describes the style of its 7 reference films. Report its
top fixes to the person and apply the ones that fit the brief.

## Related: Clipwing "Real SFX"
A separate free skill from Clipwing (clipwing.pro/skills/real-sfx) does the same job with a CC0 starter pack of
78 UI sounds. If the person has it installed, either tool is fine; this plugin's `vs sfx` needs nothing extra.
