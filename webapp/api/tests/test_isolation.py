"""What Claude's tools can reach on a worker (worker/agent_isolation.py): the launcher really starts the CLI with a
clean environment and (as root) as another user, the jail hands the workspace over and back without following
planted links, leftovers are killed, the policy keeps file tools out of /proc and other projects, and a turn fails
closed when the sandbox can't run."""
import json
import os
import pwd
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

import pytest

from app import agent_policy
from app.config import get_settings
from worker import agent_isolation as iso

ROOT = os.geteuid() == 0
as_root = pytest.mark.skipif(not ROOT, reason="switching users needs the worker to run as root")
WORKER_SECRETS = {"DATABASE_URL": "postgresql://studio:pw@db/studio", "SECRETS_KEY": "master-fernet-key",
                  "S3_SECRET_ACCESS_KEY": "bucket-secret", "AWS_SESSION_TOKEN": "role-token",
                  "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI": "/v2/creds", "REDIS_URL": "redis://redis:6379/0"}


@pytest.fixture
def tmp_path():
    """Like pytest's, but reachable by another user (pytest's sits in a folder only root can enter)."""
    import shutil
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="studio-iso-", dir="/tmp"))
    d.chmod(0o755)
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    """A stand-in `claude` that reports who it runs as and what it can see, then exits."""
    cli = tmp_path / "bin" / "claude"
    cli.parent.mkdir()
    cli.write_text("#!" + sys.executable + " -I\n" + textwrap.dedent("""
        import json, os, sys
        out = {"env": dict(os.environ), "uid": os.getuid(), "gid": os.getgid(), "groups": os.getgroups(),
               "argv": sys.argv[1:]}
        try:
            open(f"/proc/{int(sys.argv[-1])}/environ").read()   # the worker's (the test's) own environment
            out["read_parent_environ"] = True
        except (PermissionError, ValueError, FileNotFoundError):
            out["read_parent_environ"] = False
        print(json.dumps(out))
    """))
    cli.chmod(0o755)
    cli.parent.chmod(0o755)
    monkeypatch.setattr(get_settings(), "claude_cli_path", str(cli))
    return cli


def _launch(env: dict, *args) -> dict:
    r = subprocess.run([str(iso.LAUNCHER), *args], env={**os.environ, **WORKER_SECRETS, **env},
                       capture_output=True, text=True, timeout=30, check=False)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _jail(tmp_path, monkeypatch, user=None) -> iso.TurnJail:
    s = get_settings()
    monkeypatch.setattr(s, "worker_root", tmp_path / "worker")
    monkeypatch.setattr(s, "agent_user", user)
    monkeypatch.setattr(s, "agent_sandbox", False)
    ws = s.worker_root / "proj-1"
    (ws / "video-studio" / "projects" / "p" / "out").mkdir(parents=True)
    return iso.TurnJail(ws, uuid.uuid4(), s)


def test_launcher_keeps_only_the_turns_variables(tmp_path, monkeypatch, fake_cli):
    jail = _jail(tmp_path, monkeypatch)
    with jail:
        env = jail.environment({"ELEVENLABS_API_KEY": "el-key", "ANTHROPIC_API_KEY": "sk-ant", "VS_WORKSPACE": "/w",
                                "PATH": os.environ["PATH"]})
        got = _launch(env, "--print", str(os.getpid()))
    seen = got["env"]
    for name in WORKER_SECRETS:
        assert name not in seen, name
    assert not [k for k in seen if k.startswith("STUDIO_AGENT_")]
    assert seen["ELEVENLABS_API_KEY"] == "el-key" and seen["ANTHROPIC_API_KEY"] == "sk-ant"
    assert seen["HOME"].startswith(str(get_settings().worker_root / ".agent"))
    assert seen["CLAUDE_CONFIG_DIR"].startswith(seen["HOME"])
    assert got["argv"][0] == "--print"
    assert not jail.private.exists()                              # the turn's private home is gone afterwards


@as_root
def test_launcher_runs_claude_as_the_agent_user(tmp_path, monkeypatch, fake_cli):
    nobody = pwd.getpwnam("nobody")
    jail = _jail(tmp_path, monkeypatch, user="nobody")
    with jail:
        got = _launch(jail.environment({"PATH": os.environ["PATH"]}), str(os.getpid()))
        assert jail.ws_root.stat().st_uid == nobody.pw_uid         # the workspace is the agent's during the turn
    assert got["uid"] == nobody.pw_uid and got["gid"] == nobody.pw_gid
    assert got["groups"] in ([], [nobody.pw_gid])                 # root's group and supplementary groups are gone
    assert got["read_parent_environ"] is False                    # the worker's environment is closed to it
    assert jail.ws_root.stat().st_uid == 0                        # handed back


@as_root
def test_launcher_refuses_root():
    r = subprocess.run([str(iso.LAUNCHER)], env={**os.environ, "STUDIO_AGENT_CLI": "/bin/true",
                                                 "STUDIO_AGENT_PYTHON": sys.executable, "STUDIO_AGENT_USER": "root"},
                       capture_output=True, text=True, check=False)
    assert r.returncode != 0 and "uid 0" in r.stderr


@as_root
def test_jail_hands_back_without_following_planted_links(tmp_path, monkeypatch):
    nobody = pwd.getpwnam("nobody")
    outside = tmp_path / "outside.txt"
    outside.write_text("not the agent's")
    jail = _jail(tmp_path, monkeypatch, user="nobody")
    out = jail.ws_root / "video-studio" / "projects" / "p" / "out"
    with jail:
        # what a prompt-injected command could leave behind
        (out / "link").symlink_to(outside)
        made = out / "made.srt"
        subprocess.run(["sh", "-c", f"echo hi > {made}; sleep 300 & echo started"], check=True,
                       user=nobody.pw_uid, group=nobody.pw_gid, extra_groups=[])
        assert iso.alive_pids(nobody.pw_uid)                     # a background job outliving the command
    assert outside.stat().st_uid == 0                              # the link's target never changed hands
    assert made.stat().st_uid == 0                                 # the agent's file is the worker's again
    assert not iso.alive_pids(nobody.pw_uid)                      # killed before anything was handed back
    other = tmp_path / "worker" / "proj-2"
    other.mkdir()
    iso.give(other, "root")
    assert oct(other.stat().st_mode & 0o777) == "0o700"            # other projects: closed to the agent user


def test_config_refuses_what_would_leak(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "agent_env_passthrough", "AWS_REGION,DATABASE_URL")
    with pytest.raises(iso.IsolationError, match="DATABASE_URL"):
        iso.check_config(s)
    monkeypatch.setattr(s, "agent_env_passthrough", "")
    monkeypatch.setattr(s, "env", "production")
    monkeypatch.setattr(s, "agent_user", None)
    with pytest.raises(iso.IsolationError, match="AGENT_USER"):
        iso.check_config(s)
    monkeypatch.setattr(s, "agent_user", "nobody")
    monkeypatch.setattr(s, "agent_sandbox", False)
    if ROOT:
        with pytest.raises(iso.IsolationError, match="AGENT_SANDBOX"):
            iso.check_config(s)


def test_passthrough_never_carries_worker_credentials(tmp_path, monkeypatch):
    for k, v in WORKER_SECRETS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(get_settings(), "agent_env_passthrough", "AWS_REGION")
    jail = _jail(tmp_path, monkeypatch)
    keep = jail.environment({"ELEVENLABS_API_KEY": "k"})["STUDIO_AGENT_KEEP"].split(",")
    assert "ELEVENLABS_API_KEY" in keep and "AWS_REGION" in keep
    assert not set(keep) & set(WORKER_SECRETS)
    tools = iso.tool_env({"OPENAI_API_KEY": "o"})                  # the media tools' environment, too
    assert tools["OPENAI_API_KEY"] == "o" and not set(tools) & set(WORKER_SECRETS)


def test_sandbox_settings():
    s = get_settings()
    sb = iso.sandbox_settings(s)
    assert sb["enabled"] and sb["allowUnsandboxedCommands"] is False and sb["autoAllowBashIfSandboxed"] is False
    domains = sb["network"]["allowedDomains"]
    assert "api.elevenlabs.io" in domains and not [d for d in domains if "169.254" in d or d == "*"]


WS = Path("/tmp/studio-test-worker/proj")
PRIVATE = (Path("/tmp/studio-test-worker"), iso.APP_DIR)


@pytest.mark.parametrize("tool,args,want", [
    ("Read", {"file_path": "/tmp/studio-test-worker/proj/video-studio/projects/x/work/edl.json"}, agent_policy.ALLOW),
    ("Read", {"file_path": "video-studio/projects/x/work/edl.json"}, agent_policy.ALLOW),
    ("Read", {"file_path": "/etc/passwd"}, agent_policy.ALLOW),
    ("Read", {"file_path": "/proc/1/environ"}, agent_policy.DENY),
    ("Read", {"file_path": "/proc/self/environ"}, agent_policy.DENY),
    ("Read", {"file_path": "/tmp/studio-test-worker/other-project/video-studio/raw/a.mp4"}, agent_policy.DENY),
    ("Read", {"file_path": "/tmp/studio-test-worker/.agent/123/home/.claude/x.jsonl"}, agent_policy.DENY),
    ("Read", {"file_path": str(iso.APP_DIR / ".env")}, agent_policy.DENY),
    ("Read", {"file_path": str(iso.APP_DIR / "app" / "config.py")}, agent_policy.DENY),
    ("Read", {"file_path": "/srv/other/.env.production"}, agent_policy.DENY),
    ("Grep", {"pattern": "KEY", "path": "/"}, agent_policy.DENY),
    ("Grep", {"pattern": "KEY", "path": "/tmp"}, agent_policy.DENY),
    ("Grep", {"pattern": "KEY"}, agent_policy.ALLOW),
    ("Glob", {"pattern": "/proc/*/environ"}, agent_policy.DENY),
    ("Glob", {"pattern": "**/*.json"}, agent_policy.ALLOW),
    ("LS", {"path": "/tmp/studio-test-worker"}, agent_policy.DENY),
])
def test_file_tools_stay_out_of_private_places(tool, args, want):
    assert agent_policy.decide(tool, args, WS, PRIVATE).action == want


def test_a_link_in_the_workspace_is_judged_by_its_target(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "env").symlink_to("/proc/self/environ")
    assert agent_policy.decide("Read", {"file_path": "env"}, ws, (tmp_path,)).action == agent_policy.DENY
