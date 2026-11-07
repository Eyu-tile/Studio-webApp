---
name: motion-graphics
description: Make motion graphics for an edit - title cards, lower thirds, keyword pops, animated charts/stats, kinetic text, logo stings, end cards, explainer animations - as code (HyperFrames HTML or Remotion React), rendered with transparency and composited over footage via the EDL. Use when an edit needs graphics, or someone asks for an animated title, lower third, intro/outro, overlay or explainer scene.
---

# Motion graphics for edits

Graphics are code, rendered deterministically, then laid over the cut via the EDL `overlays`
array. Default engine: **HyperFrames** (vendored skills: `/hyperframes`, `/hyperframes-cli`,
`/hyperframes-registry`, `/media-use`). Use **Remotion** only if the person asks for it or the
project already uses React video (`vs setup --remotion` adds its skills; mind
Remotion's company license).

## When to add one
Only where it explains or brands: a name/title the first time it appears (lower third), a
number or claim worth seeing (stat pop/chart), a section change, the end CTA. Check
`video-studio/style/moves.md`. Never cover the speaker's face. One idea per graphic.

## Workflow
1. From the approved cut list, pick the trigger word and read its OUTPUT time: sum the kept
   segment lengths before it + (word.s − segment.start).
2. Scaffold once per project: `cd video-studio/projects/<name>/work/gfx && npx hyperframes init <graphic>`.
   Size it to the output (1080×1920 for 9:16, 1920×1080 for 16:9), duration = on-screen time.
3. Build per `/hyperframes` (read it first: its contract and registry come before hand-writing).
   Brand colours, fonts and logo from `video-studio/style/brand.md`. Keep inside title-safe.
4. `npx hyperframes check --json` → fix; `npx hyperframes snapshot` → look at it.
5. Render with alpha: `npx hyperframes render --format mov` (or `--format webm`); both carry transparency (not with `--resolution 4k`).
6. Add to `work/edl.json`:
   ```json
   "overlays": [{"file": "video-studio/projects/<name>/work/gfx/lower-third/out.mov", "start": 2.1, "end": 5.1}]
   ```
   `fit: true` (default) scales the overlay to the frame; use `"fit": false, "x": .., "y": ..` for a smaller element.
7. Re-render the preview, then `vs filmstrip --at <start+0.5>,<end-0.3>` to check placement.

## Full-screen scenes
An explainer scene that replaces the picture: render it opaque (`--format mp4`) and insert it as
its own EDL segment (`{"src": ".../scene.mp4", "start": 0, "end": <dur>}`). If the speaker's voice
must keep playing under the scene (J/L cut), `vs render` can't split picture and sound: build that
section in HyperFrames with the footage inside the composition, render it as one MP4, and insert that.

## Sound
After rendering a HyperFrames film: `vs sfx plan --hyperframes <project dir> -o work/sfx_plan.json`, review,
then `vs sfx apply <render> --plan work/sfx_plan.json -o <render>_sfx.mp4` (`/video-sound-design`).

## Parallelism
Several graphics → spawn one `motion-designer` subagent per graphic with: output size, duration,
copy, brand file path, output path. Review each snapshot before compositing.
