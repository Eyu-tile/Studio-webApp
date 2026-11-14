---
name: higgsfield-accounts
description: Use several Higgsfield accounts, one per client or project - add a connection, list saved accounts, switch which account a project bills, and check the right account is active before any billable Higgsfield generation. Use for "switch Higgsfield account", "use the client's Higgsfield", "add a new Higgsfield account", "which Higgsfield account is this using", and before every Higgsfield generate/upload call in a video-studio project.
---

# Higgsfield accounts per client

Clients pay for their own generations, so every billable Higgsfield call must go to the account chosen for
that project. `vs hf` keeps the list of accounts and which project uses which. It stores names, workspace ids
and server names only. Logins stay in Claude Code and Higgsfield.

## Two kinds of account
- **workspace**: the client invited the person's Higgsfield login into the client's team workspace. Switching is
  built into Higgsfield: `select_workspace`. Works everywhere, cloud sessions included. Prefer this one.
- **login**: the client has a separate Higgsfield login. It gets its own MCP connection named
  `higgsfield-<name>` in Claude Code on the person's computer, signed in once via `/mcp`. Its tools are
  `mcp__higgsfield-<name>__*`. A cloud session has one Higgsfield connector, so a separate login works there only
  by reconnecting that connector to the other login.

## Before every billable Higgsfield call (generate, batch, upload, upscale, ...)
1. `vs hf current --project <P> --json`.
2. No account (exit 1): show `vs hf list` and ask which client this project is for, or offer to add one (below).
   Then `vs hf use <name> --project <P>`. Do not fall back to whatever account happens to be active.
3. **workspace**: call `list_workspaces`. If that `workspace_id` is not `is_selected`, call
   `select_workspace(workspace_id=...)`. The selection persists across sessions and projects, so always check;
   never assume it is still set from earlier.
   **login**: use only that server's tools (`mcp__higgsfield-<name>__...`). Ignore other Higgsfield servers and
   the claude.ai connector for this project. If the server is not listed or asks to authenticate, ask the person
   to run `/mcp`, pick `higgsfield-<name>` and sign in, then wait.
4. Call `balance` on that account and say in one line which account and how many credits before spending:
   "Billing Acme's Higgsfield (team workspace, 2,140 credits)."
5. Pass the project's `folder_id`/project only within that account. Job ids, media ids and folders don't carry
   across accounts: re-upload reference media into the new account after a switch.

## Add a new connection
Ask the person which kind it is:
- **Invited to the client's team workspace**: call `list_workspaces`, show the names and credits, and let them
  pick. Then `vs hf add <name> --workspace <id> --workspace-name "<name>" --label "<Client>"`.
  If the workspace isn't listed, the client hasn't invited them yet: the client invites the person's
  Higgsfield email from their Higgsfield team settings.
- **Separate login**: `vs hf add <name> --login --label "<Client>"`. This registers MCP server
  `higgsfield-<name>` (`claude mcp add --transport http --scope user ... https://mcp.higgsfield.ai/mcp`). Then the
  person runs `/mcp`, picks it, and signs in with the client's login. Suggest a private browser window when the
  browser is already signed in to another Higgsfield account. Claude Code may need a restart to load the server.
- Then `vs hf use <name> --project <P>`. Optionally `vs hf default <name>` for projects without their own choice.

## List and switch
- `vs hf list`: saved accounts; `*` marks the current project's account, with the projects using each.
- `vs hf use <name> --project <P>`: switch a project. Then run the "before every billable call" check.
- `vs hf remove <name>`: forget an account. For a login account, also give the printed
  `claude mcp remove higgsfield-<name> --scope user` so the person can remove the connection.

Never ask for Higgsfield passwords or tokens in chat. Sign-in always happens in Higgsfield's own browser page.
