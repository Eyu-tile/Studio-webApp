"""What an agent turn's Claude Code can reach, and nothing more.

Claude runs commands decided by a model that reads untrusted input (footage transcripts, library files, web pages),
so a prompt injection must not be able to reach the worker's own credentials or another brand's files. Layers, each
enough on its own for some attacks and together for all we know of:

  environment  Claude Code starts through worker/agent_exec.py with only the turn's variables (allowlist below):
               no DATABASE_URL, S3 keys, SECRETS_KEY or worker cloud role. The SDK can't do this itself: it always
               merges the worker's whole environment under the options.
  user         with AGENT_USER (production): Claude runs as an unprivileged user that owns only this turn's
               workspace while the turn runs. Other processes' /proc/<pid>/environ, the app's files, other projects'
               workspaces and other turns' Claude homes are closed to it by the kernel. Leftover processes are killed
               and the files handed back when the turn ends.
  sandbox      Claude Code's sandbox (bubblewrap on Linux) for every Bash command: writes only in the workspace and
               network only to an allowlist of domains, so no cloud metadata service (the worker's IAM role), Redis
               or Postgres. Commands can't opt out of it. A turn fails closed if it can't run.
  policy       app.agent_policy keeps the file tools (Read, Grep, Glob, LS) out of /proc, the app and other workspaces.

Not covered here (see docs/ARCHITECTURE.md §6): the brand's own keys and the Anthropic credential are, by design, in
the turn's environment; WebFetch / WebSearch are not sandboxed; one container per turn would be stronger still.
"""
import json
import logging
import os
import shutil
import signal
import stat
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

from app.config import Settings, get_settings

log = logging.getLogger("studio.agent")

WORKER_DIR = Path(__file__).resolve().parent
LAUNCHER = WORKER_DIR / "bin" / "claude-exec"
APP_DIR = WORKER_DIR.parent                     # webapp/api (dev) or /srv/api (image): app code, .env

# Variables from the worker's own environment that Claude may see: locale, certificates, proxy, tool locations and
# the non-secret switches for Bedrock / Vertex. Anything else must be named by the turn or by AGENT_ENV_PASSTHROUGH.
PASSTHROUGH = (
    "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TERM",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
    "PUPPETEER_EXECUTABLE_PATH", "CHROME_PATH", "CHROME_BIN", "PLAYWRIGHT_BROWSERS_PATH", "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD",
    "VS_VENV", "VS_BIN", "WHISPER_MODEL_DIR",
    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "AWS_REGION", "ANTHROPIC_VERTEX_PROJECT_ID", "CLOUD_ML_REGION",
)
# set by the SDK itself on the CLI's environment
SDK_VARS = ("CLAUDE_CODE_ENTRYPOINT", "CLAUDE_AGENT_SDK_VERSION", "CLAUDE_AGENT_SDK_CLIENT_APP",
            "CLAUDE_AGENT_SDK_DERIVED_CLIENT_APP")
# the worker's own credentials: never in Claude's environment, whatever the configuration says
NEVER = {"DATABASE_URL", "REDIS_URL", "SECRETS_KEY", "SECRET_KEY", "OIDC_CLIENT_SECRET", "AWS_ACCESS_KEY_ID",
         "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_WEB_IDENTITY_TOKEN_FILE", "AWS_PROFILE",
         "GOOGLE_APPLICATION_CREDENTIALS"}
NEVER_PREFIXES = ("S3_", "AWS_CONTAINER_", "STUDIO_AGENT_", "SECRETS_")

# where Claude's commands may connect: the client tools the plugin uses, media CDNs, fonts and packages it renders with
DEFAULT_DOMAINS = (
    "api.elevenlabs.io", "api.heygen.com", "api2.heygen.com", "*.heygen.ai", "api.openai.com",
    "generativelanguage.googleapis.com", "api.dropboxapi.com", "content.dropboxapi.com", "*.dropboxusercontent.com",
    "www.googleapis.com", "drive.google.com", "*.googleusercontent.com", "api.pexels.com", "*.pexels.com",
    "pixabay.com", "cdn.pixabay.com", "api.unsplash.com", "images.unsplash.com", "freesound.org", "*.freesound.org",
    "api.jamendo.com", "*.jamendo.com", "api.openverse.org", "*.higgsfield.ai", "fonts.googleapis.com",
    "fonts.gstatic.com", "cdn.jsdelivr.net", "registry.npmjs.org",
)


class IsolationError(RuntimeError):
    """The turn can't run with the isolation this worker is configured for (it fails; nothing runs unisolated)."""


def _csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def forbidden(name: str) -> bool:
    return name in NEVER or name.startswith(NEVER_PREFIXES)


def network_domains(s: Settings) -> list[str]:
    return _csv(s.agent_network_domains) or list(DEFAULT_DOMAINS)


def check_config(s: Settings) -> None:
    bad = [n for n in _csv(s.agent_env_passthrough) if forbidden(n)]
    if bad:
        raise IsolationError(f"AGENT_ENV_PASSTHROUGH may not include the worker's credentials: {', '.join(bad)}")
    if s.is_production and not s.agent_user:
        raise IsolationError("Claude turns need AGENT_USER in production (Claude must not run as the worker's user)")
    if s.is_production and not s.agent_sandbox:
        raise IsolationError("Claude turns need AGENT_SANDBOX in production")
    if s.agent_user:
        if os.geteuid() != 0:
            raise IsolationError(f"AGENT_USER={s.agent_user} needs the worker to run as root (it switches users)")
        import pwd
        try:
            if pwd.getpwnam(s.agent_user).pw_uid == 0:
                raise IsolationError("AGENT_USER must not be root")
        except KeyError:
            raise IsolationError(f"AGENT_USER={s.agent_user} does not exist on this worker") from None


@lru_cache
def _sandbox_ok(user: str | None) -> str | None:
    """None when Claude Code's sandbox can run here (as the user Claude runs as), else why not."""
    if sys.platform == "darwin":
        return None                                  # sandbox-exec ships with macOS
    if not sys.platform.startswith("linux"):
        return f"Claude Code's sandbox doesn't run on {sys.platform}"
    missing = [b for b in ("bwrap", "socat") if not shutil.which(b)]
    if missing:
        return f"install {' and '.join(missing)} on the worker (Claude Code's sandbox needs them)"
    kw = {}
    if user:
        import pwd
        pw = pwd.getpwnam(user)
        kw = {"user": pw.pw_uid, "group": pw.pw_gid, "extra_groups": []}
    try:
        r = subprocess.run(["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--unshare-net", "--unshare-pid", "true"],
                           capture_output=True, text=True, timeout=15, check=False, **kw)
    except (OSError, subprocess.SubprocessError) as e:
        return f"bubblewrap could not start: {e}"
    if r.returncode != 0:
        return f"bubblewrap can't create namespaces here ({(r.stderr or '').strip()[:200]}); see docs/DEPLOY.md"
    return None


def sandbox_settings(s: Settings) -> dict:
    return {
        "enabled": True,
        "autoAllowBashIfSandboxed": False,      # every command still goes through the studio's approvals policy
        "allowUnsandboxedCommands": False,      # no dangerouslyDisableSandbox escape hatch
        "enableWeakerNestedSandbox": bool(s.agent_sandbox_weaker_nested),
        "network": {"allowedDomains": network_domains(s)},
    }


def _ids(user: str | None) -> tuple[int, int]:
    if not user:
        return os.getuid(), os.getgid()
    import pwd
    pw = pwd.getpwnam(user)
    return pw.pw_uid, pw.pw_gid


def give(root: Path, user: str | None, *, only_from: set[int] | None = None) -> None:
    """chown a tree to `user` without following symlinks. Hard-linked files are skipped (a planted hard link must
    not make the worker hand over a file from elsewhere); `only_from` limits it to entries owned by those uids."""
    if not user or os.geteuid() != 0 or not root.exists():
        return
    uid, gid = _ids(user)

    def one(path: str, is_dir: bool):
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            return
        if only_from is not None and st.st_uid not in only_from:
            return
        if not is_dir and not stat.S_ISLNK(st.st_mode) and st.st_nlink > 1:
            log.warning("not changing owner of hard-linked %s", path)
            return
        os.lchown(path, uid, gid)

    one(str(root), True)
    os.chmod(root, 0o700)
    for base, dirs, files in os.walk(root):
        for d in dirs:
            one(os.path.join(base, d), True)
        for f in files:
            one(os.path.join(base, f), False)


def alive_pids(uid: int) -> list[int]:
    """Processes running as `uid`, not counting zombies (killed, waiting to be reaped)."""
    pids = []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            if p.stat().st_uid != uid:
                continue
            state = (p / "stat").read_text().rsplit(")", 1)[1].split()[0]
        except (FileNotFoundError, ProcessLookupError, IndexError):
            continue
        if state not in ("Z", "X"):
            pids.append(int(p.name))
    return pids


def kill_user_processes(user: str | None, wait: float = 5.0) -> int:
    """SIGKILL everything left running as `user` (background shells Claude started) and wait until it is gone.
    Returns how many were killed; raises if any survive (the workspace must not be handed back under a live one)."""
    if not user or os.geteuid() != 0:
        return 0
    uid, _ = _ids(user)
    killed: set[int] = set()
    deadline = time.monotonic() + wait
    while pids := alive_pids(uid):
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
                killed.add(pid)
            except ProcessLookupError:
                pass
        if time.monotonic() > deadline:
            raise IsolationError(f"processes of {user} would not stop: {pids[:10]}")
        time.sleep(0.05)
    return len(killed)


class TurnJail:
    """One turn's isolation: a private home and Claude config dir, the workspace handed to the agent user, the
    environment and sandbox settings for ClaudeAgentOptions; everything undone on exit."""

    def __init__(self, ws_root: Path, job_id, s: Settings | None = None):
        self.s = s or get_settings()
        self.ws_root = ws_root                                   # the project's folder: cwd of the turn
        self.private = self.s.worker_root / ".agent" / str(job_id)
        self.home = self.private / "home"
        self.user = self.s.agent_user

    def __enter__(self):
        check_config(self.s)
        if self.s.agent_sandbox:
            why = _sandbox_ok(self.user)
            if why:
                raise IsolationError(f"Claude Code's sandbox can't run on this worker: {why}")
        kill_user_processes(self.user)
        root = self.s.worker_root
        root.mkdir(parents=True, exist_ok=True)
        if os.geteuid() == 0:
            os.chmod(root, 0o711)                                # enter your own folder, list nobody's
            (root / ".agent").mkdir(exist_ok=True)
            os.chmod(root / ".agent", 0o711)
        for d in (self.home, self.home / ".claude", self.home / "tmp"):
            d.mkdir(parents=True, exist_ok=True)
        os.chmod(self.private, 0o700)
        give(self.private, self.user)
        give(self.ws_root, self.user)
        return self

    def __exit__(self, *exc):
        killed = kill_user_processes(self.user)
        if killed:
            log.info("stopped %d leftover process(es) of %s", killed, self.user)
        if self.user and os.geteuid() == 0:
            # what the agent made goes to the media user (or root); nothing else changes hands
            give(self.ws_root, self.s.worker_media_user or "root", only_from={_ids(self.user)[0]})
        shutil.rmtree(self.private, ignore_errors=True)
        return False

    def environment(self, turn_env: dict[str, str]) -> dict[str, str]:
        """The env for ClaudeAgentOptions: the turn's variables plus the launcher's control variables. The SDK merges
        the worker's environment under it; the launcher then keeps only STUDIO_AGENT_KEEP."""
        names = set(turn_env) | set(SDK_VARS) | set(_csv(self.s.agent_env_passthrough))
        names |= {n for n in PASSTHROUGH if n in os.environ}
        names = {n for n in names if not forbidden(n) or n in turn_env}
        env = {**turn_env,
               "HOME": str(self.home), "CLAUDE_CONFIG_DIR": str(self.home / ".claude"), "TMPDIR": str(self.home / "tmp"),
               "XDG_CACHE_HOME": str(self.home / ".cache"), "npm_config_cache": str(self.home / ".npm")}
        names |= {"HOME", "CLAUDE_CONFIG_DIR", "TMPDIR", "XDG_CACHE_HOME", "npm_config_cache"}
        env["STUDIO_AGENT_KEEP"] = ",".join(sorted(names))
        env["STUDIO_AGENT_CLI"] = real_cli(self.s)
        env["STUDIO_AGENT_PYTHON"] = sys.executable
        if self.user:
            env["STUDIO_AGENT_USER"] = self.user
        return env

    def settings_json(self) -> str:
        """--settings for the CLI: the app's own files are never readable, whatever the tools are asked."""
        return json.dumps({"permissions": {"deny": [f"Read(/{APP_DIR}/**)"]}})

    def sandbox(self) -> dict | None:
        return sandbox_settings(self.s) if self.s.agent_sandbox else None


def real_cli(s: Settings) -> str:
    if s.claude_cli_path:
        p = shutil.which(s.claude_cli_path) or s.claude_cli_path
        return str(Path(p).resolve())
    import claude_agent_sdk
    bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude"
    if bundled.is_file():
        return str(bundled)
    found = shutil.which("claude")
    if not found:
        raise IsolationError("Claude Code CLI not found: set CLAUDE_CLI_PATH")
    return str(Path(found).resolve())


# --- media jobs (vs, ffmpeg, ffprobe on uploaded files): no model involved, but untrusted input all the same ----------

def tool_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The environment for the media tools: the allowlist above, the vs engine's own VS_* settings, PATH and HOME,
    and what the job adds (the brand's keys). Never the worker's database, bucket or secrets keys."""
    env = {k: v for k, v in os.environ.items()
           if (k in PASSTHROUGH or k.startswith("VS_") or k in ("PATH", "HOME", "NODE_PATH", "XDG_CACHE_HOME"))
           and not forbidden(k)}
    user = get_settings().worker_media_user
    if user and os.geteuid() == 0:
        import pwd
        env["HOME"] = pwd.getpwnam(user).pw_dir
    return {**env, **(extra or {})}


def media_user_kwargs() -> dict:
    """subprocess arguments that run a media tool as WORKER_MEDIA_USER (own group only) when the worker is root."""
    user = get_settings().worker_media_user
    if not user or os.geteuid() != 0:
        return {}
    uid, gid = _ids(user)
    return {"user": uid, "group": gid, "extra_groups": []}
