#!/usr/bin/env python3
"""Higgsfield accounts per project: save several, switch smoothly, bill the right client.

Two kinds of account:
  workspace  a client's team workspace that your one Higgsfield login was invited to. Switching is
             built into Higgsfield (select_workspace); works in every Claude surface, cloud included.
  login      a client's own, separate Higgsfield login. Each gets its own named MCP connection
             (higgsfield-<name>) in Claude Code, signed in once with that client's login.

  vs hf add acme --workspace <id> [--label "Acme Inc"]   save a team workspace (ids: list_workspaces)
  vs hf add zeta --login [--label "Zeta Ltd"]            add a separate login as MCP server higgsfield-zeta
  vs hf list                                             saved accounts, and which project uses which
  vs hf use acme [--project P]                           bill this project to acme (cwd project if omitted)
  vs hf current [--project P] [--json]                   which account this project bills, and how to select it
  vs hf default acme | --clear                           account for projects without their own choice
  vs hf remove acme

Only names, workspace ids and server names are stored (no tokens):
~/.config/video-studio/higgsfield.json ($VS_KEYS_DIR moves it). Login tokens stay in Claude Code.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

MCP_URL = os.environ.get("VS_HF_MCP_URL", "https://mcp.higgsfield.ai/mcp")
NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,30}")
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def reg_path():
    return Path(os.environ.get("VS_KEYS_DIR") or Path.home() / ".config" / "video-studio") / "higgsfield.json"


def load():
    p = reg_path()
    if p.exists():
        d = json.loads(p.read_text())
    else:
        d = {}
    d.setdefault("accounts", {})
    d.setdefault("projects", {})
    d.setdefault("default", None)
    return d


def save(d):
    p = reg_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, indent=1, sort_keys=True) + "\n")
    os.chmod(p, 0o600)


def detect_project(explicit):
    if explicit:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", explicit):
            die("project name may only use letters, digits, '.', '_' and '-'")
        return explicit
    parts = Path.cwd().resolve().parts
    for i in range(len(parts) - 2, -1, -1):
        if parts[i] == "projects" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def claude_cmd():
    custom = os.environ.get("VS_CLAUDE_CMD")  # tests
    if custom:
        return custom.split()
    return ["claude"] if shutil.which("claude") else None


def server_name(name):
    return f"higgsfield-{name}"


def describe(name, acc):
    if acc["kind"] == "workspace":
        return f"team workspace {acc.get('workspace_name') or ''} {acc['workspace_id']}".replace("  ", " ")
    return f"separate login, MCP server {acc['server']}"


def selection(d, project):
    """(name, account, why) for a project: its own choice, else the default, else None."""
    if project and project in d["projects"]:
        n = d["projects"][project]
        if n in d["accounts"]:
            return n, d["accounts"][n], f"project {project}"
    if d["default"] and d["default"] in d["accounts"]:
        return d["default"], d["accounts"][d["default"]], "default"
    return None, None, None


def how_to_select(acc):
    if acc is None:
        return ("No Higgsfield account chosen. Ask which client this is for (`vs hf list`), then "
                "`vs hf use <name> --project <P>`, or add one with `vs hf add`.")
    if acc["kind"] == "workspace":
        return (f"Call list_workspaces on the Higgsfield connection; if workspace {acc['workspace_id']} is not "
                f"is_selected, call select_workspace(workspace_id='{acc['workspace_id']}'). Confirm its credits "
                f"before the first billable call.")
    return (f"Use only the tools of MCP server '{acc['server']}' (mcp__{acc['server']}__*), not other higgsfield "
            f"servers. Check its balance first. If the server is missing or not signed in, the person runs /mcp "
            f"in Claude Code and signs in to that client's Higgsfield login.")


def cmd_add(a, d):
    if not NAME.fullmatch(a.name):
        die("name: lowercase letters, digits and '-' (e.g. acme, zeta-media)")
    if a.name in d["accounts"] and not a.force:
        die(f"'{a.name}' already exists; use --force to replace it")
    if bool(a.workspace) == bool(a.login):
        die("give exactly one of --workspace <id> or --login")
    if a.workspace:
        if not UUID.fullmatch(a.workspace):
            die("--workspace takes a workspace UUID from list_workspaces")
        d["accounts"][a.name] = {"kind": "workspace", "workspace_id": a.workspace,
                                 "workspace_name": a.workspace_name, "label": a.label}
        save(d)
        print(f"saved '{a.name}': team workspace {a.workspace}")
        return
    srv = server_name(a.name)
    d["accounts"][a.name] = {"kind": "login", "server": srv, "label": a.label}
    save(d)
    cmd = ["mcp", "add", "--transport", "http", "--scope", "user", srv, MCP_URL]
    c = claude_cmd()
    if c and not a.no_register:
        p = subprocess.run(c + cmd, capture_output=True, text=True)
        if p.returncode == 0:
            print(f"saved '{a.name}' and added MCP server {srv} ({MCP_URL}).")
        elif "already exists" in (p.stdout + p.stderr):
            print(f"saved '{a.name}'; MCP server {srv} was already configured.")
        else:
            print(f"saved '{a.name}', but adding the MCP server failed:\n{p.stderr.strip()}\n"
                  f"Add it yourself:  claude {' '.join(cmd)}", file=sys.stderr)
            sys.exit(4)
    else:
        print(f"saved '{a.name}'. Add the connection on the computer that runs Claude Code:\n  claude {' '.join(cmd)}")
    print(f"Next: run /mcp in Claude Code, pick {srv}, and sign in with that client's Higgsfield login "
          f"(use a private browser window if you are signed in to another Higgsfield account).")


def cmd_list(a, d):
    if not d["accounts"]:
        print("no Higgsfield accounts saved. Add one: vs hf add <name> --workspace <id>  |  --login")
        return
    project = detect_project(a.project)
    cur, _, _ = selection(d, project)
    print("Higgsfield accounts:")
    for n, acc in sorted(d["accounts"].items()):
        users = sorted(p for p, v in d["projects"].items() if v == n)
        mark = "*" if n == cur else " "
        dflt = " (default)" if d["default"] == n else ""
        label = f" {acc['label']}" if acc.get("label") else ""
        print(f" {mark} {n:14}{label}{dflt}  {describe(n, acc)}")
        if users:
            print(f"     projects: {', '.join(users)}")
    if project:
        print(f"* = used by project {project}" if cur else f"project {project} has no account yet: vs hf use <name>")


def cmd_use(a, d):
    if a.name not in d["accounts"]:
        die(f"unknown account '{a.name}'. Saved: {', '.join(sorted(d['accounts'])) or 'none'}")
    project = detect_project(a.project)
    if not project:
        die("which project? pass --project <name> (or run inside <workspace>/projects/<name>/)")
    d["projects"][project] = a.name
    save(d)
    acc = d["accounts"][a.name]
    print(f"project {project} now bills Higgsfield account '{a.name}' ({describe(a.name, acc)}).")
    print(how_to_select(acc))


def cmd_current(a, d):
    project = detect_project(a.project)
    n, acc, why = selection(d, project)
    out = {"project": project, "account": n, "chosen_by": why, "kind": acc and acc["kind"],
           "workspace_id": acc and acc.get("workspace_id"), "server": acc and acc.get("server"),
           "label": acc and acc.get("label"), "how_to_select": how_to_select(acc)}
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        print(f"{'project ' + project if project else 'no project'}: "
              f"{('account ' + n + ' (' + why + ', ' + describe(n, acc) + ')') if n else 'no account chosen'}")
        print(out["how_to_select"])
    if not n:
        sys.exit(1)


def cmd_default(a, d):
    if a.clear:
        d["default"] = None
    else:
        if a.name not in d["accounts"]:
            die(f"unknown account '{a.name}'")
        d["default"] = a.name
    save(d)
    print(f"default Higgsfield account: {d['default'] or 'none'}")


def cmd_remove(a, d):
    acc = d["accounts"].pop(a.name, None)
    if not acc:
        die(f"unknown account '{a.name}'")
    d["projects"] = {p: v for p, v in d["projects"].items() if v != a.name}
    if d["default"] == a.name:
        d["default"] = None
    save(d)
    print(f"removed '{a.name}'")
    if acc["kind"] == "login":
        print(f"To also remove its connection and sign-in:  claude mcp remove {acc['server']} --scope user")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add")
    s.add_argument("name")
    s.add_argument("--workspace", help="team workspace UUID (from list_workspaces)")
    s.add_argument("--workspace-name")
    s.add_argument("--login", action="store_true", help="a separate Higgsfield login (own MCP connection)")
    s.add_argument("--label", help="client name to show")
    s.add_argument("--force", action="store_true")
    s.add_argument("--no-register", action="store_true", help="don't run `claude mcp add`; just print it")
    s = sub.add_parser("list")
    s.add_argument("--project")
    s = sub.add_parser("use")
    s.add_argument("name")
    s.add_argument("--project")
    s = sub.add_parser("current")
    s.add_argument("--project")
    s.add_argument("--json", action="store_true")
    s = sub.add_parser("default")
    s.add_argument("name", nargs="?")
    s.add_argument("--clear", action="store_true")
    s = sub.add_parser("remove")
    s.add_argument("name")
    a = ap.parse_args()
    if a.cmd == "default" and not a.clear and not a.name:
        die("usage: vs hf default <name> | --clear")
    d = load()
    {"add": cmd_add, "list": cmd_list, "use": cmd_use, "current": cmd_current,
     "default": cmd_default, "remove": cmd_remove}[a.cmd](a, d)


if __name__ == "__main__":
    main()
