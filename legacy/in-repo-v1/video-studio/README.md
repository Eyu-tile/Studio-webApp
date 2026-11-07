# video-studio: agentic video editing with Claude Code

Claude doesn't "magically edit" in a chat window. Here Claude Code is the **director**: it
reads a word-level transcript, writes an edit decision list (EDL), shows you a cut list,
renders with FFmpeg, QA-checks its own output, and iterates on your notes. Motion graphics are
code (HyperFrames), and the rough cut can go to Premiere/Resolve/FCP for final polish.

```
raw footage ──transcribe──▶ transcript.json/.md ──plan──▶ edl.json ──[you approve cut list]──▶
  render --preview ──qa + filmstrip──▶ draft.mp4 ──[your notes]──▶ final.mp4 + captions.srt
                                          ▲ graphics (HyperFrames, alpha) via EDL overlays
```

## Quick start
```bash
bash video-studio/setup.sh            # ffmpeg check, venv + faster-whisper/mlx-whisper, yt-dlp
video-studio/vs new launch-teaser     # → video-studio/projects/launch-teaser/{raw,work,out}
cp ~/Movies/take1.mp4 video-studio/projects/launch-teaser/raw/
claude                                # then:
```
> Edit `projects/launch-teaser/raw/take1.mp4` into a 45 s Reel: remove pauses, ums and retakes,
> bold-pop captions, a lower third when I say my name. Show me the cut list first.

Claude picks up the `video-edit` skill automatically. Use a strong model with high effort
for planning (`/model`, then a higher `/effort`). Video work uses a lot of tokens, so start with short clips.

## What's here
| path | what |
|------|------|
| `vs` | CLI wrapper: `vs help` |
| `scripts/` | stdlib Python tools: `transcribe`, `pack`, `propose_cuts`, `silences`, `render`, `captions`, `filmstrip`, `qa`, `export_edl` |
| `style/brand.md` | Nexa brand (colours from the site, type, logo, voice) |
| `style/moves.md` | your editing "moves" (build with the `video-style-guide` skill from reference videos) |
| `style/notes.md` | feedback rules that persist across sessions |
| `templates/project.md` | per-project memory, created by `vs new` |
| `projects/` | your footage and renders (git-ignored) |
| `SKILLS_GALLERY.md` | researched list of video skills, kits and MCP servers with install commands |

Skills (`.claude/skills/`): `video-edit`, `video-captions`, `video-qa`, `video-style-guide`,
`motion-graphics`, `video-nle-handoff`, `video-setup`, plus vendored HyperFrames
(`hyperframes`, `hyperframes-cli`, `hyperframes-registry`, `media-use`).
Subagents (`.claude/agents/`): `edit-planner`, `motion-designer`, `video-qa-reviewer`.

## EDL format
```json
{
  "version": 1,
  "source": "video-studio/projects/x/raw/take1.mp4",
  "segments": [
    {"start": 0.42, "end": 3.08, "text": "Hello and welcome to Nexa."},
    {"src": "video-studio/projects/x/raw/broll.mp4", "start": 10.0, "end": 12.5}
  ],
  "overlays": [{"file": "video-studio/projects/x/work/gfx/lt/out.mov", "start": 1.0, "end": 4.0}],
  "music": {"file": "video-studio/projects/x/raw/bed.mp3", "gain_db": -20, "duck": true},
  "reframe": 0.5
}
```
Segment times are source seconds; overlay times are output seconds. Paths are relative to the repo root.

## Tips
- Always get the cut list before a full render; drafts use `--preview` (half-res, ultrafast).
- Start with short, single-take talking heads. Expect a few rounds of notes on the first videos.
  Every note that should stick goes into `style/notes.md`.
- Give the transcriber your vocabulary: `--prompt "Nexa IT Solution, Supabase, <names>"`.
- 9:16 safe zones: keep captions/graphics out of the bottom 20% and right 15%.
- Heavy multicam, colour grading or artistic finishing: `vs export` → your NLE.

## Optional: fewer permission prompts
Add to `.claude/settings.json` (or `.claude/settings.local.json` for just you):
```json
{
  "permissions": {
    "allow": [
      "Bash(video-studio/vs:*)",
      "Bash(ffprobe:*)",
      "Bash(ffmpeg:*)",
      "Bash(npx hyperframes:*)"
    ]
  }
}
```

## Cloud sessions (claude.ai/code)
`setup.sh` works in the cloud container, but the first transcription downloads a Whisper model
from Hugging Face. Allow `huggingface.co` and `*.hf.co` in the environment's network settings, or
transcribe locally and commit nothing but the `transcript.json`.
