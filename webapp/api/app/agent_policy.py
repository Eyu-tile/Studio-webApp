"""What Claude may do on its own in a Studio project, and what needs a person first.

The engine is the video-studio plugin running in Claude Code (Agent SDK) on a worker. Every tool call that Claude
Code would normally ask about comes here (the SDK's `can_use_tool` callback) and gets one of three answers:

  allow     editing work inside the project: reading, `vs` commands, ffmpeg, writing files in the workspace,
            research on the web, read-only Higgsfield calls (balance, cost estimates, listing)
  ask       anything that spends a client's credits or acts outside the studio: Higgsfield generation, ElevenLabs /
            HeyGen / OpenAI / Gemini voice and music, posting to social. A brand lead approves in the browser, and
            the card names the client account that would be charged (the "confirm the account first" rule)
  deny      never: writing outside the workspace, printing secrets, piping the internet into a shell, wiping disks

Pure functions so the rules are unit-tested without a model.
"""
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

ALLOW, ASK, DENY = "allow", "ask", "deny"

# tools that never change anything outside the workspace
SAFE_TOOLS = {"Read", "Glob", "Grep", "LS", "Skill", "Task", "Agent", "TodoWrite", "TodoRead", "WebSearch",
              "WebFetch", "ToolSearch", "BashOutput", "KillShell", "KillBash", "TaskOutput", "TaskStop",
              "ListMcpResourcesTool", "ReadMcpResourceTool"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

# Higgsfield MCP: read-only calls run freely; everything else spends credits or publishes
HF_READ = re.compile(r"^(list_|get_|show_|search_|estimate_|balance$|models_explore$|apps_search$|apps_describe$|"
                     r"jobs_wait$|job_display$|transactions$|gpu_list_|gpu_explore$|gpu_my$|gpu_job_status$|"
                     r"gpu_job_quote$|gpu_rental_logs$|ads_studio_(list|get)_|ads_studio_quote$|ads_studio_story_presets$|"
                     r"ai_influencer_(get|list)_|ai_influencer_prepare$|video_analysis_(status|jobs)$|"
                     r"tiktok_accounts$|tiktok_music_trending$|tiktok_publish_status$|website_status$|"
                     r"resolve_|scene_builder_3d_(get|list|search)_|scene_builder_3d_query_python$|media_confirm$|"
                     r"media_upload$|media_import_url$|get_workflow_|get_preset_instructions$)")
HF_OUTWARD = re.compile(r"^(publish_|unpublish_|share_|delete_|archive_|tiktok_(publish|prepare_publish|connect|reconnect)|"
                        r"meta_ads_(write|connect)|deploy_website|cancel_trial|participate_in_contest|update_project_sharing|"
                        r"website_secrets|send_feedback)")

# Bash commands that spend a client's credits on a third-party API
PAID_BASH = [
    (re.compile(r"heygen-(tts|voice)|lib/heygen|api\.heygen\.com"), "HeyGen", "heygen"),
    (re.compile(r"gemini-tts|generativelanguage\.googleapis|lyria", re.I), "Google Gemini", "gemini"),
    (re.compile(r"api\.elevenlabs\.io|elevenlabs", re.I), "ElevenLabs", "elevenlabs"),
    (re.compile(r"api\.openai\.com/v1/audio|openai.*\btts\b", re.I), "OpenAI", "openai"),
    (re.compile(r"\b(media-use|audio)/scripts/audio\.mjs\b.*\b(tts|voice|music|sfx)\b"), "a voice / music provider", None),
    (re.compile(r"\bvs\s+translate\s+dub\b"), "the dubbing voice provider", "elevenlabs"),
]
OUTWARD_BASH = [
    (re.compile(r"\bcomposio\b"), "Posts to the client's social account (Composio)"),
    (re.compile(r"\bvs\s+social\s+(post|publish)\b"), "Posts to the client's social account"),
    (re.compile(r"\bgit\s+push\b"), "Pushes code to a remote repository"),
]
DENY_BASH = [
    (re.compile(r"(curl|wget)[^|;&]*\|\s*(ba|z)?sh\b"), "piping a download into a shell"),
    (re.compile(r"(^|[;&|]\s*)(env|printenv|set)\s*($|[;&|>])"), "printing the environment (it holds client keys)"),
    (re.compile(r"\$\{?[A-Z0-9_]*(API_KEY|_TOKEN|SECRET|CLIENT_ID|ACCESS_KEY)[A-Z0-9_]*\}?"), "reading a secret variable"),
    (re.compile(r"/proc/[^ ]*/environ"), "reading a process environment"),
    (re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+(/|~|\$HOME)(\s|$)"), "deleting outside the project"),
    (re.compile(r"\b(mkfs|dd\s+if=|shutdown|reboot|:\(\)\s*\{)"), "a system command"),
    (re.compile(r"\b(sudo|su)\s"), "running as another user"),
    (re.compile(r"169\.254\.169\.254|metadata\.google\.internal"), "the cloud metadata service"),
]


@dataclass(frozen=True)
class Decision:
    action: str                     # allow | ask | deny
    reason: str = ""
    title: str = ""                 # one line for the approval card
    paid: bool = False
    provider: str | None = None     # Connection.provider whose account would be used ("higgsfield", "elevenlabs")


def _inside(path: str, root: Path) -> bool:
    try:
        p = Path(path)
        p = (root / p) if not p.is_absolute() else p
        return p.resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def mcp_parts(tool: str) -> tuple[str, str] | None:
    """'mcp__plugin_video-studio_higgsfield__generate_video' -> ('plugin_video-studio_higgsfield', 'generate_video')."""
    if not tool.startswith("mcp__"):
        return None
    rest = tool[5:]
    server, sep, name = rest.rpartition("__")
    return (server, name) if sep else (rest, "")


def short(cmd: str, n: int = 160) -> str:
    cmd = " ".join(cmd.split())
    return cmd if len(cmd) <= n else cmd[: n - 1] + "…"


def decide(tool: str, args: dict, workspace: Path) -> Decision:
    if tool in SAFE_TOOLS:
        return Decision(ALLOW)
    if tool in WRITE_TOOLS:
        path = args.get("file_path") or args.get("notebook_path") or ""
        if path and _inside(path, workspace):
            return Decision(ALLOW)
        return Decision(DENY, f"{tool} outside the project workspace is not allowed ({path or 'no path'})")
    if tool == "Bash":
        return _bash(str(args.get("command", "")), workspace)
    parts = mcp_parts(tool)
    if parts:
        server, name = parts
        if "higgsfield" in server.lower():
            if HF_READ.match(name):
                return Decision(ALLOW)
            if HF_OUTWARD.match(name):
                return Decision(ASK, "Publishes, shares or deletes on the client's Higgsfield account",
                                f"Higgsfield: {name.replace('_', ' ')}", paid=False, provider="higgsfield")
            return Decision(ASK, "Spends the client's Higgsfield credits", f"Higgsfield: {name.replace('_', ' ')}",
                            paid=True, provider="higgsfield")
        return Decision(ASK, f"Uses the {server} tool", f"{server}: {name}")
    if tool in ("AskUserQuestion", "ExitPlanMode", "EnterPlanMode"):
        return Decision(DENY, "Ask in your reply instead; the editor answers in the chat")
    return Decision(ASK, f"{tool} is not on the studio's list of known tools", tool)


def _bash(cmd: str, workspace: Path) -> Decision:
    for rx, why in DENY_BASH:
        if rx.search(cmd):
            return Decision(DENY, f"Not allowed in the studio: {why}")
    for rx, who, provider in PAID_BASH:
        if rx.search(cmd):
            return Decision(ASK, f"Spends credits on the client's {who} account", short(cmd), paid=True,
                            provider=provider)
    for rx, why in OUTWARD_BASH:
        if rx.search(cmd):
            return Decision(ASK, why, short(cmd))
    # writes by redirection to absolute paths outside the workspace (`> /etc/x`, `tee /x`)
    try:
        toks = shlex.split(cmd, posix=True)
    except ValueError:
        toks = cmd.split()
    for i, t in enumerate(toks):
        target = None
        if t in (">", ">>", "tee") and i + 1 < len(toks):
            target = toks[i + 1]
        elif t.startswith(">") and len(t) > 1 and not t.startswith(">&"):
            target = t.lstrip(">")
        if target and target.startswith("/") and not target.startswith("/dev/") and not target.startswith("/tmp/") \
                and not _inside(target, workspace):
            return Decision(DENY, f"Writing outside the project workspace is not allowed ({target})")
    return Decision(ALLOW)
