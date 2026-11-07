---
name: video-setup
description: Install, verify or repair the local video editing toolchain (ffmpeg with libass, Node 22+, Python venv with faster-whisper / mlx-whisper, yt-dlp, HyperFrames and optional Remotion skills). Use when a video tool is missing, `vs doctor` shows ✗, transcription fails, or someone asks to "set up video editing".
---

# Video toolchain setup

```bash
vs doctor                # report
vs setup                 # install what's missing (venv in ~/.cache/video-studio)
vs setup --remotion      # + Remotion agent skills in this project
vs setup --ai            # optional: OpenCV (face tracking), PySceneDetect, librosa, rembg
vs setup --stems         # optional: Demucs + CPU torch for vocal/music stems (~2 GB)
vs setup --rea           # optional: rea-video shot forensics for /video-breakdown (~1 GB)
vs ai status             # which AI helpers are installed; every one has a fallback
```
GPU extras: put `realesrgan-ncnn-vulkan` (upscaling) and `rife-ncnn-vulkan` (frame interpolation) from their
GitHub releases on PATH; `vs ai upscale` / `vs ai interpolate` use them, else ffmpeg lanczos / minterpolate.
Long-cut silence removal is built in (`vs cuts`, `vs silences`); auto-editor is not needed.

| need | macOS | Linux | Windows |
|------|-------|-------|---------|
| ffmpeg (+libass) | `brew install ffmpeg` | `apt install ffmpeg` | `winget install Gyan.FFmpeg` (use WSL for the scripts) |
| Node 22+ | `brew install node` | nodesource / `nvm install 22` | nodejs.org |
| Whisper | mlx-whisper (Apple Silicon, auto) | faster-whisper (auto; CUDA if present) | faster-whisper |

## Troubleshooting
- **Model download fails** (first transcription downloads from Hugging Face): the network must allow
  `huggingface.co` and `*.hf.co`. In a Claude Code cloud session, add them in the environment's network
  settings, or transcribe locally.
- **Slow transcription on CPU**: `--model small` for planning, `large-v3`/`turbo` only for the final caption pass.
- **"subtitles" filter missing**: ffmpeg built without libass; install the full brew/apt ffmpeg.
- **HyperFrames render needs Chrome**: `npx hyperframes doctor` (see `/hyperframes-cli`).
- **Fonts**: captions use fontconfig. Install Inter (`brew install --cask font-inter` / `apt install fonts-inter`) or pass `--font`.
