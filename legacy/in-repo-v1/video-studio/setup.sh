#!/usr/bin/env bash
# Install / verify the agentic video editing toolchain.
#
#   bash video-studio/setup.sh              install what's missing (asks nothing)
#   bash video-studio/setup.sh --check      report only
#   bash video-studio/setup.sh --remotion   also install Remotion agent skills
#   bash video-studio/setup.sh --hf-update  refresh the vendored HyperFrames skills
#
# Core: ffmpeg/ffprobe, Node 22+, Python 3.10+, a Whisper backend
# (mlx-whisper on Apple Silicon, faster-whisper elsewhere), yt-dlp.
set -uo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"
check=0 remotion=0 hfupdate=0
for a in "$@"; do
  case "$a" in
    --check) check=1 ;;
    --remotion) remotion=1 ;;
    --hf-update) hfupdate=1 ;;
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

# ffmpeg
if command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null; then
  ok "ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"
  filters="$(ffmpeg -hide_banner -filters 2>/dev/null)"
  grep -q ' subtitles ' <<<"$filters" && ok "ffmpeg has libass (burned captions)" \
    || bad "ffmpeg lacks libass: captions can't be burned (brew install ffmpeg / apt install ffmpeg)"
else
  pkg_install ffmpeg ffmpeg && ok "ffmpeg installed" || bad "ffmpeg missing: https://ffmpeg.org/download.html"
fi

# node
if command -v node >/dev/null; then
  major="$(node -p 'process.versions.node.split(".")[0]')"
  [ "$major" -ge 22 ] && ok "node $(node -v)" || bad "node $(node -v) < 22 (HyperFrames needs 22+)"
else
  pkg_install node nodejs && ok "node installed" || bad "node missing: https://nodejs.org (22+)"
fi

# python + venv with a whisper backend
if ! command -v python3 >/dev/null; then bad "python3 missing"; fi
venv="$here/.venv"
if [ $check = 0 ] && [ ! -x "$venv/bin/python" ] && command -v python3 >/dev/null; then
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
  ok "whisper backend ($backend)"
elif [ $check = 0 ]; then
  pipi "$backend" && ok "$backend installed into video-studio/.venv" || bad "could not install $backend"
else
  bad "no whisper backend (run setup.sh without --check)"
fi
if command -v yt-dlp >/dev/null || "$py" -c "import yt_dlp" 2>/dev/null; then ok "yt-dlp"
elif [ $check = 0 ]; then pipi yt-dlp && ok "yt-dlp installed (video-studio/.venv/bin/yt-dlp)" || info "yt-dlp optional"
else info "yt-dlp not installed (optional, for downloading reference videos)"; fi

# skills
for s in hyperframes hyperframes-cli hyperframes-registry media-use; do
  [ -f "$root/.claude/skills/$s/SKILL.md" ] && ok "skill $s (vendored)" || bad "skill $s missing"
done
if [ $hfupdate = 1 ] && [ $check = 0 ]; then
  (cd "$root" && npx -y skills add heygen-com/hyperframes --skill hyperframes --skill hyperframes-cli \
     --skill hyperframes-registry --skill media-use --agent claude-code -y) && ok "HyperFrames skills refreshed"
fi
if [ $remotion = 1 ] && [ $check = 0 ]; then
  (cd "$root" && npx -y skills add remotion-dev/skills --agent claude-code -y) && ok "Remotion skills installed" \
    || bad "Remotion skills install failed"
fi
[ -d "$root/.claude/skills/remotion-best-practices" ] && ok "Remotion skills" || info "Remotion skills not installed (optional: --remotion; check Remotion's license for company use)"

chmod +x "$here/vs" 2>/dev/null
echo
[ $missing = 0 ] && echo "ready. try: video-studio/vs new my-first-edit" || { echo "some items need attention (see ✗ above)"; exit 1; }
