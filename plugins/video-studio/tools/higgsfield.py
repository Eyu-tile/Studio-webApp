#!/usr/bin/env python3
"""Higgsfield accounts for Claude Code: one named MCP connection per account.

Higgsfield's MCP (https://mcp.higgsfield.ai/mcp) signs in through the browser (OAuth); there is no key to
paste. Each account gets its own connection, `higgsfield-<name>`, with its own saved sign-in, so switching
accounts never needs a new login. The plugin also ships a default connection called `higgsfield`.

  vs higgsfield add brand-a            create the connection `higgsfield-brand-a` (then sign in: /mcp)
  vs higgsfield list                   connections and their status (connected / needs sign-in)
  vs higgsfield use brand-a [--project P]   the account this workspace (or project) generates with
  vs higgsfield current [--project P]  which account is active, and its MCP tool prefix
  vs higgsfield remove brand-a         delete the connection (sign-out happens in /mcp)
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vs_common import die, load_json, save_json  # noqa: E402

URL = "https://mcp.higgsfield.ai/mcp"
DEFAULT = "higgsfield"


def server(name):
    name = (name or "").strip().lower()
    if name in ("", "default", DEFAULT):
        return DEFAULT
    slug = re.sub(r"[^a-z0-9-]+", "-", name).strip("-")
    if not slug:
        die(f"'{name}' is not a usable account name (letters, numbers, dashes)")
    return f"{DEFAULT}-{slug}"


def claude():
    exe = shutil.which("claude")
    if not exe:
        die("the `claude` command isn't on PATH. In the Claude app instead: Settings -> Connectors -> Add custom "
            f"connector, name it (e.g. Higgsfield brand-a), URL {URL}, then Connect and sign in.")
    return exe


def workspace():
    ws = os.environ.get("VS_WORKSPACE")
    if ws:
        return Path(ws)
    try:
        root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
    except OSError:
        root = ""
    return Path(root or os.getcwd()) / "video-studio"


def state_file(project=None):
    return (Path(project) if project else workspace()) / ".higgsfield.json"


def active(project=None):
    for f in ([state_file(project)] if project else []) + [state_file()]:
        if f.exists():
            return load_json(f).get("account", DEFAULT)
    return DEFAULT


def statuses():
    p = subprocess.run([claude(), "mcp", "list"], capture_output=True, text=True, timeout=120)
    out = {}
    for line in p.stdout.splitlines():
        m = re.match(r"^(higgsfield[\w-]*):\s+(\S+).*?-\s+(.*)$", line.strip())
        if m:
            out[m.group(1)] = m.group(3).strip()
    return out


def cmd_add(a):
    name = server(a.name)
    if name == DEFAULT and not a.force:
        print(f"`{DEFAULT}` comes with the plugin; sign in with /mcp. For another account: vs higgsfield add <name>")
        return
    have = statuses()
    if name in have and not a.force:
        print(f"{name} already exists ({have[name]})")
    else:
        p = subprocess.run([claude(), "mcp", "add", "--transport", "http", "--scope", a.scope, name, URL],
                           capture_output=True, text=True)
        if p.returncode != 0:
            die(f"could not add {name}: {(p.stderr or p.stdout).strip()[-300:]}")
        print(f"added {name} ({URL}, {a.scope} scope)")
    print(f"Sign in: type /mcp, choose {name}, Authenticate: your browser opens Higgsfield's sign-in. Use the "
          f"account this connection is for. Then restart or /mcp reconnect; its tools appear as mcp__{name}__*.")


def cmd_list(a):
    have = statuses()
    cur = active(a.project)
    if not have:
        print(f"no Higgsfield connections. Add one: vs higgsfield add <account-name> (plugin default: {DEFAULT})")
    for k, v in sorted(have.items()):
        print(f"{'*' if k == cur else ' '} {k:<28} {v}")
    if cur == DEFAULT:
        note = "  (the plugin's own connection: shown in /mcp, sign in there)"
    else:
        note = "" if cur in have else "  (not set up in Claude Code yet: vs higgsfield add " + cur[len(DEFAULT) + 1:] + ")"
    print(f"active: {cur}{note}")


def cmd_use(a):
    name = server(a.name)
    f = state_file(a.project)
    save_json(f, {"account": name})
    print(f"{'project' if a.project else 'workspace'} now generates with {name} (tools mcp__{name}__*) -> {f}")


def cmd_current(a):
    name = active(a.project)
    print(json.dumps({"account": name, "tool_prefix": f"mcp__{name}__", "url": URL}))


def cmd_remove(a):
    name = server(a.name)
    p = subprocess.run([claude(), "mcp", "remove", name, "-s", a.scope], capture_output=True, text=True)
    print((p.stdout or p.stderr).strip() or f"removed {name}")
    for f in (state_file(), ):
        if f.exists() and load_json(f).get("account") == name:
            f.unlink()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add")
    s.add_argument("name")
    s.add_argument("--scope", default="user", choices=["user", "local", "project"])
    s.add_argument("--force", action="store_true")
    s = sub.add_parser("list")
    s.add_argument("--project")
    s = sub.add_parser("use")
    s.add_argument("name")
    s.add_argument("--project")
    s = sub.add_parser("current")
    s.add_argument("--project")
    s = sub.add_parser("remove")
    s.add_argument("name")
    s.add_argument("--scope", default="user", choices=["user", "local", "project"])
    a = ap.parse_args()
    {"add": cmd_add, "list": cmd_list, "use": cmd_use, "current": cmd_current, "remove": cmd_remove}[a.cmd](a)


if __name__ == "__main__":
    main()
