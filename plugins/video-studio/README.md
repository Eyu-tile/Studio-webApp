# video-studio: agentic video editing for Claude Code

Claude becomes your editor and director. It understands footage through transcripts, shot lists
and beat maps, plans the edit, shows you a cut list for approval, renders deterministically with
FFmpeg, checks its own work, and iterates on your notes. It handles any common edit.

| you have | you get |
|---|---|
| a talking-head recording | a tight Reel/Short/YouTube cut: pauses, ums, retakes gone, captions, punch-ins, music |
| a long podcast or webinar | 5–10 vertical clips with hooks, captions and covers |
| 2–4 camera angles + a mixer recording | an auto-switched multicam edit that follows whoever is talking |
| a folder of b-roll / photos + a song | a beat-synced montage, travel film, highlight reel or slideshow |
| a screen recording | a tutorial with dead time cut, speed-ups, zooms on the action, step titles |
| a reference video you like | its pacing, captions, moves, look and sound written as rules and applied to your footage |
| a brief and no b-roll | footage, photos, music and SFX from the free internet (Internet Archive, Wikipedia/Commons, Creative Commons YouTube, Openverse) and stock libraries (Pexels, Pixabay, Unsplash, Freesound, NASA), downloaded with licences logged; only the seconds you need from long films |
| no music | mood/genre/tempo-matched tracks from Jamendo, Openverse, Incompetech, ccMixter, Archive; fitted to the exact edit length on downbeats so the song ends on the last frame, ducked under speech, credit lines logged |
| a silent edit or HyperFrames film | every moment found (cuts, transitions, text pops, logo reveals, chart builds) and a real recording placed on the exact frame, plus an SFX stem; optional earshot scoring against pro launch films |
| files, folders, zips, brand kits, Drive/Dropbox/YouTube links | everything imported and sorted into the project (footage linked, not duplicated), with a credits ledger |
| a finished cut | every platform version, GIF, size-limited file, thumbnail, SRT, chapters, or a timeline for Premiere/Resolve/FCP |

## Install
```
/plugin marketplace add Eyu-tile/video-studio-claude-plugin        (or a local path to this marketplace folder)
/plugin install video-studio@video-studio-marketplace
```
Once per machine, ask Claude "set up video editing" (runs `vs setup`). Requirements: FFmpeg built
with libass (Homebrew and apt builds are), Node 22+, Python 3.10+. A Whisper model downloads on first
transcription (mlx-whisper on Apple Silicon, faster-whisper elsewhere).

## Use
```
vs init                 # in your project: creates video-studio/{style,projects}
vs new launch-reel      # video-studio/projects/launch-reel/{raw,work,out}
```
Drop footage into `raw/` and talk to Claude:
> Edit launch-reel into a 45 s Reel like the reference in style/refs/, bold captions, show me the cut list first.

## What's inside
**Skills**
| skill | does |
|---|---|
| `video-edit` | the director loop and router: brief → understand → plan (gate) → draft → QA → notes (gate) → final |
| `video-captions` | bold-pop, karaoke, clean, minimal captions, SRT, safe zones |
| `video-repurpose` | long → many shorts |
| `video-montage` | music- and footage-driven edits, beat sync, slideshows |
| `video-multicam` | audio sync, auto camera switching, tightened conversations |
| `video-screencast` | tutorials and demos |
| `video-audio` | voice clean-up, music, ducking, SFX, loudness |
| `video-color` | grades, LUTs, HDR, camera matching |
| `video-assets` | stock search + download, editor-provided files/links/brand kits, credits ledger |
| `video-music` | choose, find, fit and mix background music |
| `video-sound-design` | SFX on the exact frame from EDLs, HyperFrames or any video; libraries; earshot listening |
| `video-export` | platform presets, multi-aspect, GIF/WebM/ProRes/MP3, size limits, thumbnails, chapters |
| `video-style-guide` | learn a style from reference videos |
| `motion-graphics` | titles, lower thirds, charts, end cards with HyperFrames |
| `video-qa` | automated and visual checks |
| `video-nle-handoff` | CMX3600 / FCPXML export, Resolve and FCP MCP pointers |
| `video-setup` | install/repair tools |
| `hyperframes`, `hyperframes-cli`, `hyperframes-registry`, `media-use` | HeyGen HyperFrames v0.9.19 (Apache-2.0) |
| `reverse-any-video`, `style-sampling` | HyperFrames: rebuild a reference video as an editable project; new episodes in proven explainer styles |

**Agents**: `edit-planner`, `footage-logger`, `broll-researcher`, `motion-designer`, `video-qa-reviewer`.

**CLI** (`vs help`): `setup doctor init new where add fetch keys credits probe ingest transcribe pack scenes
silences filmstrip beats sync cuts multicam captions music packs sfx earshot render proxy qa convert thumbs export yt-dlp`.

**Renderer features**: frame-accurate cuts from any number of sources, still images, speed 0.25–4×
with pitch-kept audio, smooth speed ramps, reverse and freeze frames, J/L cuts, keyframed zoom / pan /
rotation (reframing that follows a subject), cover/contain/blurred-fill reframing to any aspect,
25+ transitions, 14 colour grades and `.cube` LUTs per shot, automatic HDR tone-mapping (or HDR10/HLG
kept) and VFR conforming, two-pass vid.stab stabilisation, text overlays with animations, alpha overlays,
green-screen keying, keyframed picture-in-picture, blur/pixelate regions, burned captions, voice enhancement,
SFX, multiple audio tracks with volume automation and ducking, continuous audio tracks for multicam,
EBU R128 loudness, h264/h265/ProRes and 10-bit, proxies, chunked parallel rendering with a per-chunk cache
(only changed shots re-render), partial-range previews.

## Optional extras
- **Free sound packs from GitHub** (`vs setup --packs` or `vs packs install --defaults`): uisfx (936 CC0 sounds in
  12 styles) and Kenney Interface Sounds (100 CC0 recordings); add any other free sound repo with `vs packs add`.
- **earshot** (`vs setup --earshot`, MIT, CPU-only, ~1.3 GB): lets Claude hear: describe, rank and find sounds,
  critique a mix against 7 professional launch films, and render 250+ code-made sound effects.

## Stock media keys (optional, free)
Pexels, Pixabay, Unsplash and Freesound need a free API key each: `vs keys set pexels` (stored in
`~/.config/video-studio/keys.env`, mode 600; environment variables `PEXELS_API_KEY` etc. also work). Internet
Archive, Wikipedia, Wikimedia Commons, Creative Commons YouTube, Openverse and NASA work without keys. NonCommercial/NoDerivs licences are excluded by default.

## Privacy
The bundled HyperFrames CLI sends usage telemetry (and a usage beacon when its skill starts). Turn it off with
`npx hyperframes telemetry disable`. The plugin's own `vs` tools send nothing.

## Workspace
Style files, projects and a shared `library/` (logos, fonts, LUTs, music) live in your repo (`video-studio/`), so brand rules, notes from past feedback
and editing "moves" travel with the project. Footage and renders are git-ignored by the generated `.gitignore`.

## Limits
- No generative video/voice by default; `media-use` can add it on request (HeyGen or local tools).
- Very heavy colour work, audio restoration beyond denoise/de-ess, and complex compositing are better
  finished in an NLE (`video-nle-handoff`).
- Instagram/TikTok downloads usually need browser cookies; you can always drop files in manually.

Third-party notices: `THIRD_PARTY_NOTICES.md`. Research behind the tool choices: `SKILLS_GALLERY.md`.
