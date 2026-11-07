# Skills gallery: agentic video editing

Research snapshot, **October 2026**. Star counts are approximate (GitHub pages or directory
listings at the time of research) and move fast. Re-check a repo before you install it: skills
run with full agent permissions.

## Installed in this repo

| skill | source | why |
|-------|--------|-----|
| `video-edit` | ours (`.claude/skills/video-edit`) | director workflow: transcript → cut list gate → EDL → render → QA → iterate |
| `video-captions` | ours | word-synced burned captions (bold-pop / clean / minimal) + SRT |
| `video-qa` | ours | automated + visual QA before anything is shown |
| `video-style-guide` | ours | turn reference videos into numbered "moves" |
| `motion-graphics` | ours | HyperFrames graphics composited via EDL overlays |
| `video-nle-handoff` | ours | CMX3600 / FCPXML export, Resolve & FCP MCP pointers |
| `video-setup` | ours | toolchain install/repair |
| `hyperframes`, `hyperframes-cli`, `hyperframes-registry`, `media-use` | [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) (~74.6k ★, Apache-2.0) | HTML→MP4 deterministic video; the core skill set HeyGen recommends |

Subagents (`.claude/agents/`): `edit-planner`, `motion-designer`, `video-qa-reviewer`.

## Video frameworks (motion graphics as code)

| repo | ★ | install | notes |
|------|---|---------|-------|
| [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) | ~74.6k | `npx skills add heygen-com/hyperframes` · `npx hyperframes skills update` · plugin: `claude plugin marketplace add heygen-com/hyperframes` then `claude plugin install hyperframes@hyperframes` | Node 22+, FFmpeg. 7 published skills; on-demand ones: `figma`, `slideshow`, `remotion-to-hyperframes`. **Vendored here.** |
| [remotion-dev/skills](https://github.com/remotion-dev/skills) | ~5.8k | `npx skills add remotion-dev/skills` · `npx remotion skills add` | React video. Skills: `remotion-best-practices`, `-create`, `-captions`, `-render`, `-multimedia`, … Remotion needs a paid company license above a team-size threshold, so check before commercial use. `bash video-studio/setup.sh --remotion` |

## End-to-end editing kits (raw footage → final.mp4)

| repo | ★ | approach | fit for us |
|------|---|----------|-----------|
| [browser-use/video-use](https://github.com/browser-use/video-use) | ~30k | transcribe → pack → LLM reasons → EDL → render → self-eval (≤3 loops); filmstrip+waveform composites on demand; `project.md` memory; 12 hard production rules. MIT | The design our `video-edit` follows (transcript-first, EDL, gates, self-eval). Uses **ElevenLabs** for transcription (paid API key). Install alongside if you prefer it: clone + symlink to `~/.claude/skills/video-use`. |
| [huzaifa-hb/video-edit](https://github.com/huzaifa-hb/video-edit) | small | fork of video-use with local whisper.cpp, HyperFrames captions, OpenCV reframing | macOS-only, fully local |
| [digitalsamba/claude-code-video-toolkit](https://github.com/digitalsamba/claude-code-video-toolkit) | ~2.3k | workspace bundling Remotion, ElevenLabs, FFmpeg, Playwright skills + voice/image/music gen | Good for faceless/explainer production with generated media |
| [watzing/claude-video-editor](https://github.com/watzing/claude-video-editor) | small | screencast → Whisper → cut proposals → browser editor | Screen recordings |
| [6missedcalls/video-editing-skill](https://github.com/6missedcalls/video-editing-skill) | small | pure Bash + FFmpeg + Whisper: trim, jump cut, captions | Minimal reference |
| [jordanrendric/claude-video-vision](https://github.com/jordanrendric/claude-video-vision) | small | plugin: frame extraction + audio analysis so Claude can "watch" | Analysis, not editing |

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

## Install policy for this repo
1. Prefer skills from the framework's own org (heygen-com, remotion-dev, anthropics).
2. Read a third-party SKILL.md and its scripts before installing; skills run with your permissions.
3. Vendor (commit) only permissively licensed skills, recorded in `skills-lock.json`
   (`npx skills update` refreshes them). Install others per machine.
