"""Starts Claude Code for one agent turn with nothing of the worker's but what the turn needs.

The Agent SDK always launches the CLI with the worker's whole environment (DATABASE_URL, S3 keys, SECRETS_KEY) merged
under the options it was given; options can add variables, never remove them. So the SDK launches this instead
(`cli_path` points at a two-line shell wrapper that runs it), and this:

  1. keeps only the variables named in STUDIO_AGENT_KEEP (the turn's own: the brand's keys, the workspace, the
     Anthropic credential) and drops everything else, the STUDIO_AGENT_* control variables included
  2. if STUDIO_AGENT_USER is set: drops to that Unix user, with its own group only (no supplementary groups, not
     root's group), and refuses to go on if it is still root
  3. execs the real CLI (STUDIO_AGENT_CLI) with the same arguments, so the SDK talks to it exactly as before

Standard library only, run with `python -I`: it runs before anything in the workspace can be trusted.
"""
import os
import sys

CONTROL = ("STUDIO_AGENT_CLI", "STUDIO_AGENT_KEEP", "STUDIO_AGENT_USER", "STUDIO_AGENT_PYTHON")


def clean_env(environ: dict[str, str]) -> dict[str, str]:
    keep = {n for n in environ.get("STUDIO_AGENT_KEEP", "").split(",") if n and n not in CONTROL}
    return {k: v for k, v in environ.items() if k in keep}


def drop_to(user: str) -> None:
    import pwd
    pw = pwd.getpwnam(user)
    if pw.pw_uid == 0:
        raise SystemExit(f"studio agent: refusing to run Claude as {user} (uid 0)")
    if os.geteuid() != 0:
        raise SystemExit(f"studio agent: the worker must run as root to start Claude as {user}")
    os.setgroups([])
    os.setgid(pw.pw_gid)
    os.setuid(pw.pw_uid)
    if os.getuid() == 0 or os.geteuid() == 0 or os.getegid() == 0 or 0 in os.getgroups():
        raise SystemExit("studio agent: could not leave root")


def main(argv: list[str]) -> None:
    cli = os.environ.get("STUDIO_AGENT_CLI")
    if not cli or not os.path.isabs(cli):
        raise SystemExit("studio agent: STUDIO_AGENT_CLI must be the absolute path of the claude binary")
    env = clean_env(dict(os.environ))
    user = os.environ.get("STUDIO_AGENT_USER")
    if user:
        drop_to(user)
    os.execve(cli, [cli, *argv], env)


if __name__ == "__main__":
    main(sys.argv[1:])
