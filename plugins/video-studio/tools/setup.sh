#!/usr/bin/env bash
# Install / verify the video-studio toolchain. Run through the CLI:
#   vs setup             install what's missing
#   vs doctor            report only
#   vs setup --remotion  also install Remotion agent skills into the current project
#
# Core: ffmpeg/ffprobe (with libass), Node 22+, Python 3.10+, a Whisper backend
# (mlx-whisper on Apple Silicon, faster-whisper elsewhere), yt-dlp.
set -uo pipefail
root="${VS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
venv="${VS_VENV:-$HOME/.cache/video-studio/venv}"
check=0 remotion=0 earshot=0 packs=0
for a in "$@"; do
  case "$a" in
    --check) check=1 ;;
    --remotion) remotion=1 ;;
    --earshot) earshot=1 ;;
    --packs) packs=1 ;;
    *) echo "unknown flag $a" >&2; exit 2 ;;
  esac
done

ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$*"; missing=1; }
info() { printf '  · %s\n' "$*"; }
missing=0
os="$(uname -s)"; arch="$(uname -m)"

pkg_install() {  # pkg_install <brew-name> <apt-name>
  [ $check = 1 ] && return 1
  if command -v brew >/dev/null; then brew install "$1"
  elif command -v apt-get >/dev/null; then
    if [ "$(id -u)" = 0 ]; then apt-get update -qq && apt-get install -y -qq "$2"
    else sudo apt-get update -qq && sudo apt-get install -y -qq "$2"; fi
  else return 1; fi
}

echo "video-studio toolchain ($os/$arch)"

if command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null; then
  ok "ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"
  filters="$(ffmpeg -hide_banner -filters 2>/dev/null)"
  grep -q ' subtitles ' <<<"$filters" && ok "ffmpeg has libass (burned captions)" \
    || bad "ffmpeg lacks libass: captions can't be burned (brew install ffmpeg / apt install ffmpeg)"
else
  pkg_install ffmpeg ffmpeg && ok "ffmpeg installed" || bad "ffmpeg missing: https://ffmpeg.org/download.html"
fi

if command -v node >/dev/null; then
  major="$(node -p 'process.versions.node.split(".")[0]')"
  [ "$major" -ge 22 ] && ok "node $(node -v)" || bad "node $(node -v) < 22 (HyperFrames needs 22+)"
else
  pkg_install node nodejs && ok "node installed" || bad "node missing: https://nodejs.org (22+)"
fi

if ! command -v python3 >/dev/null; then bad "python3 missing"; fi
if [ $check = 0 ] && [ ! -x "$venv/bin/python" ] && command -v python3 >/dev/null; then
  mkdir -p "$(dirname "$venv")"
  if command -v uv >/dev/null; then uv venv -q "$venv"; else python3 -m venv "$venv"; fi
fi
py="$venv/bin/python"; [ -x "$py" ] || py="python3"
pipi() {
  if command -v uv >/dev/null && [ -x "$venv/bin/python" ]; then uv pip install -q --python "$venv/bin/python" "$@"
  else "$py" -m pip install -q "$@"; fi
}
if [ "$os" = Darwin ] && [ "$arch" = arm64 ]; then backend=mlx-whisper mod=mlx_whisper
else backend=faster-whisper mod=faster_whisper; fi
if "$py" -c "import $mod" 2>/dev/null || "$py" -c "import faster_whisper" 2>/dev/null; then
  ok "whisper backend ($backend) in $venv"
elif [ $check = 0 ]; then
  pipi "$backend" && ok "$backend installed into $venv" || bad "could not install $backend"
else
  bad "no whisper backend (run: vs setup)"
fi
if "$py" -c "import numpy" 2>/dev/null; then ok "numpy (beats, sync, multicam)"
elif [ $check = 0 ]; then pipi numpy && ok "numpy installed" || bad "could not install numpy"
else bad "numpy missing (run: vs setup)"; fi
if "$py" -c "import gdown" 2>/dev/null; then ok "gdown (Google Drive links)"
elif [ $check = 0 ]; then pipi gdown && ok "gdown installed" || info "gdown optional (Google Drive links)"
else info "gdown not installed (Google Drive links; run: vs setup)"; fi
if [ -x "$venv/bin/yt-dlp" ] || "$py" -c "import yt_dlp" 2>/dev/null; then ok "yt-dlp"
elif [ $check = 0 ]; then pipi yt-dlp && ok "yt-dlp installed (vs yt-dlp ...)" || info "yt-dlp optional"
else info "yt-dlp not installed (optional, for downloading reference videos)"; fi

for s in video-edit video-montage video-multicam hyperframes hyperframes-cli hyperframes-registry media-use; do
  [ -f "$root/skills/$s/SKILL.md" ] && ok "skill $s" || bad "skill $s missing from plugin"
done
if [ $remotion = 1 ] && [ $check = 0 ]; then
  npx -y skills add remotion-dev/skills --agent claude-code -y && ok "Remotion skills installed in $(pwd)/.claude/skills" \
    || bad "Remotion skills install failed"
fi

# earshot (optional): an AI listener for sound - describe/critique/forge, 250+ code-made SFX. ~1.3 GB with models.
eh="${VS_EARSHOT_HOME:-$HOME/.cache/video-studio/earshot}"
if [ $earshot = 1 ] && [ $check = 0 ]; then
  if [ ! -d "$eh/.git" ]; then git clone --depth 1 https://github.com/Leonxlnx/earshot "$eh" || bad "earshot clone failed"; fi
  if [ -d "$eh" ]; then
    (cd "$eh" && { [ -x .venv/bin/python ] || python3 -m venv .venv; } \
      && .venv/bin/python -m pip install -q torch --index-url https://download.pytorch.org/whl/cpu \
      && .venv/bin/python -m pip install -q -e ".[mcp]" \
      && .venv/bin/python -m earshot doctor) && ok "earshot installed ($eh)" || bad "earshot install failed (see output)"
    info "use it from Claude: vs earshot ... ; optional MCP server: claude mcp add earshot --scope user -e EARSHOT_THREADS=3 -- $eh/.venv/bin/python -m earshot mcp"
    info "render its sound bank into your library: vs sfx bank --from earshot"
  fi
fi
if [ -x "$eh/.venv/bin/python" ]; then ok "earshot (vs earshot ...)"; else info "earshot not installed (optional: vs setup --earshot)"; fi

if [ $packs = 1 ] && [ $check = 0 ]; then
  VS_ROOT="$root" "$py" "$root/tools/packs.py" install --defaults && ok "free GitHub sound packs installed into the workspace library"
fi

keys_file="${VS_KEYS_FILE:-$HOME/.config/video-studio/keys.env}"
if [ -f "$keys_file" ]; then ok "stock API keys file ($(grep -c '=' "$keys_file") set)"
else info "no stock API keys yet (optional, free): vs keys set pexels | pixabay | unsplash | freesound | jamendo"; fi

echo
[ $missing = 0 ] && echo "ready. try: vs new my-first-edit" || { echo "some items need attention (see ✗ above)"; exit 1; }
