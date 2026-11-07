# Research notes: agentic video editing skills

Research snapshot, **October 2026**. Star counts are approximate (GitHub pages or directory
listings at the time of research) and move fast. Re-check a repo before you install it: skills
run with full agent permissions.

## Included in this plugin

Original (MIT): `video-edit`, `video-captions`, `video-repurpose`, `video-montage`, `video-multicam`,
`video-screencast`, `video-audio`, `video-color`, `video-export`, `video-style-guide`, `motion-graphics`,
`video-qa`, `video-nle-handoff`, `video-setup`; agents `edit-planner`, `footage-logger`, `motion-designer`,
`video-qa-reviewer`; the `vs` CLI.

Bundled: `hyperframes`, `hyperframes-cli`, `hyperframes-registry`, `media-use` from
[heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) (~74.6k ★, Apache-2.0).

## Video frameworks (motion graphics as code)

| repo | ★ | install | notes |
|------|---|---------|-------|
| [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) | ~74.6k | `npx skills add heygen-com/hyperframes` · `npx hyperframes skills update` · plugin: `claude plugin marketplace add heygen-com/hyperframes` then `claude plugin install hyperframes@hyperframes` | Node 22+, FFmpeg. 7 published skills; on-demand ones: `figma`, `slideshow`, `remotion-to-hyperframes`. **Included in this plugin.** |
| [remotion-dev/skills](https://github.com/remotion-dev/skills) | ~5.8k | `npx skills add remotion-dev/skills` · `npx remotion skills add` | React video. Skills: `remotion-best-practices`, `-create`, `-captions`, `-render`, `-multimedia`, … Remotion needs a paid company license above a team-size threshold, so check before commercial use. `vs setup --remotion` |

## End-to-end editing kits (raw footage → final.mp4)

| repo | ★ | approach | fit for us |
|------|---|----------|-----------|
| [browser-use/video-use](https://github.com/browser-use/video-use) | ~30k | transcribe → pack → LLM reasons → EDL → render → self-eval (≤3 loops); filmstrip+waveform composites on demand; `project.md` memory; 12 hard production rules. MIT | The design our `video-edit` follows (transcript-first, EDL, gates, self-eval). Uses **ElevenLabs** for transcription (paid API key). Install alongside if you prefer it: clone + symlink to `~/.claude/skills/video-use`. |
| [huzaifa-hb/video-edit](https://github.com/huzaifa-hb/video-edit) | small | fork of video-use with local whisper.cpp, HyperFrames captions, OpenCV reframing | macOS-only, fully local |
| [digitalsamba/claude-code-video-toolkit](https://github.com/digitalsamba/claude-code-video-toolkit) | ~2.3k | workspace bundling Remotion, ElevenLabs, FFmpeg, Playwright skills + voice/image/music gen | Good for faceless/explainer production with generated media |
| [watzing/claude-video-editor](https://github.com/watzing/claude-video-editor) | small | screencast → Whisper → cut proposals → browser editor | Screen recordings |
| [6missedcalls/video-editing-skill](https://github.com/6missedcalls/video-editing-skill) | small | pure Bash + FFmpeg + Whisper: trim, jump cut, captions | Minimal reference |
| [jordanrendric/claude-video-vision](https://github.com/jordanrendric/claude-video-vision) | small | plugin: frame extraction + audio analysis so Claude can "watch" | Analysis, not editing |

## Sound

| tool | ★ | what | in this plugin |
|------|---|------|----------------|
| [Openverse](https://openverse.org) | — | 800M+ openly licensed images and audio (music, SFX), free API, no key | `vs fetch search --type sfx|music` (default provider) |
| [Leonxlnx/earshot](https://github.com/Leonxlnx/earshot) | ~3.4k (MIT) | gives agents ears: describe/rank/find sounds, launch-film critique vs 7 pro films, 250+ code-made SFX, MCP server | `vs setup --earshot`, `vs earshot …`, `vs sfx bank --from earshot` |
| Clipwing Real SFX ([page](https://clipwing.pro/skills/real-sfx)) | — | finds moments in a video, places real recordings on the frame, CC0 starter pack of 78 UI sounds | same job done natively by `vs sfx plan/apply` (reads EDLs and HyperFrames) |

## Free sound packs on GitHub (`vs packs`)

| repo | ★ | licence | contents |
|------|---|---------|----------|
| [romainsimon/uisfx](https://github.com/romainsimon/uisfx) | ~911 | audio CC0, code MIT | 936 synthesized UI/motion sounds, 78 cues × 12 styles (mp3 + ogg) |
| [hipdiscovery/Free-Sound-Effects](https://github.com/hipdiscovery/Free-Sound-Effects) | new | audio CC0 (Kenney), code MIT | 100 Kenney Interface Sounds + catalog.json (tags, durations, sha256) and a curated directory of free sources |
| [kapishdima/soundcn](https://github.com/kapishdima/soundcn) | ~921 | MIT; most sounds CC0 (Kenney) **but** a 110-sound World of Warcraft set is not free | not registered by default because licensing is mixed per sound |

## Free music sources

| source | access | licence |
|--------|--------|---------|
| [Jamendo](https://developer.jamendo.com/v3.0) | API, free client id | per-track CC (NC/ND excluded by default) |
| [Openverse](https://openverse.org) | API, no key | per-track CC |
| [Incompetech](https://incompetech.com) (Kevin MacLeod) | catalog JSON, no key | CC BY 4.0, fixed credit line |
| [ccMixter](https://ccmixter.org) | query API, no key | per-upload CC |
| [Internet Archive](https://archive.org) | API, no key | public domain / CC per item |
| Mixkit, Pixabay Music, YouTube Audio Library | web only (no API) | free licences; the person downloads, then `vs add` |

## Free footage sources

| source | access | notes |
|--------|--------|-------|
| [Internet Archive](https://archive.org) | advancedsearch + metadata APIs, no key | public-domain & CC films, newsreels, Prelinger home movies; licence per item (`licenseurl`) |
| [Wikipedia](https://www.wikipedia.org) / [Wikimedia Commons](https://commons.wikimedia.org) | MediaWiki API, no key | the images illustrating any topic; licence per file |
| YouTube | yt-dlp | Creative Commons filter (CC BY uploads) by default; everything else is reference-only unless the person has rights |

## NLE bridges (MCP, run on your own machine)

| server | NLE | install |
|--------|-----|---------|
| [Tooflex/davinci-resolve-mcp](https://github.com/tooflex/davinci-resolve-mcp) | DaVinci Resolve Studio | per README; Resolve › Preferences › External scripting = Local |
| [lordhoell/davinci-resolve-mcp](https://github.com/lordhoell/davinci-resolve-mcp) | DaVinci Resolve | ships a Claude Code skill; `claude mcp add davinci-resolve -- davinci-resolve-mcp` |
| dreliq9/fcp-mcp ([listing](https://claudemarketplaces.com/mcp/dreliq9/fcp-mcp)) | Final Cut Pro | `claude mcp add --transport stdio fcp -- uvx fcp-mcp` |
| Premiere Pro | — | no mature MCP found; use `vs export` (.edl) |

## Building blocks (not skills, but the tools skills call)

| tool | ★ | role |
|------|---|------|
| [m-bain/whisperX](https://github.com/m-bain/whisperX) | ~17k | forced-alignment word timestamps + diarization (upgrade path if faster-whisper timings are loose) |
| [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | — | default backend here (CPU/CUDA) |
| mlx-whisper | — | Apple Silicon backend (auto-selected by setup.sh) |
| [WyattBlue/auto-editor](https://github.com/WyattBlue/auto-editor) | — | loudness-based silence cutting, exports to Premiere/Resolve XML |
| FFmpeg | — | every render, QA check and contact sheet here |

## General skill collections and directories

| source | ★ | use |
|--------|---|-----|
| [anthropics/skills](https://github.com/anthropics/skills) | ~184.5k | official. `/plugin marketplace add anthropics/skills` → `example-skills` includes **skill-creator** (use it to evolve our video skills with evals) |
| [ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills) | ~75k | general curated list |
| [travisvn/awesome-claude-skills](https://github.com/travisvn/awesome-claude-skills) | ~12k | general curated list |
| zhuyansen/awesome-claude-video-skills ([listing](https://skillsllm.com/skill/awesome-claude-video-skills)) | small | video-only list (~180 repos, security-graded) |
| [skills.sh](https://skills.sh) · [claudemarketplaces.com](https://claudemarketplaces.com) · [tella.com/skills](https://www.tella.com/skills) | — | directories; `npx skills add <owner/repo>` installs from any GitHub repo |

## Install policy
1. Prefer skills from the framework's own org (heygen-com, remotion-dev, anthropics).
2. Read a third-party SKILL.md and its scripts before installing; skills run with your permissions.
3. Vendor (commit) only permissively licensed skills, recorded in `skills-lock.json`
   (`npx skills update` refreshes them). Install others per machine.
