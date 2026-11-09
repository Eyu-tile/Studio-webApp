---
description: Connect a Higgsfield account (each account gets its own named connection and sign-in) and choose which one this project generates with
argument-hint: "[account name, e.g. brand-a]"
---

Connect a Higgsfield account for AI presenter / b-roll generation (see the `ai-presenter` skill).

1. Run `vs higgsfield list` to see the Higgsfield connections that exist and which one is active.
2. If no account name was given ($ARGUMENTS is empty), ask with AskUserQuestion: "Which Higgsfield account do
   you want to connect or use?" Offer the existing connections from step 1 (the plugin's default `higgsfield`
   counts as one) plus "a new account", and for a new one ask for a short name (client or brand, e.g. `brand-a`).
3. New account: run `vs higgsfield add <name>`. Then tell the person, in two short lines:
   "Type /mcp, choose higgsfield-<name> and press Authenticate. Your browser opens Higgsfield's sign-in:
   log in with the account for <name>." Wait for them to say it's done.
4. Check it: `vs higgsfield list` shows the connection without "Needs authentication", and your tool search for
   `higgsfield-<name>` finds its tools. If the tools don't show, ask them to reconnect it in /mcp (or restart
   Claude Code) and check again. Never claim a connection works before its tools respond.
5. Make it the active account: `vs higgsfield use <name>` (add `--project <project folder>` when this is for one
   project). From now on `vs gen plan` records this account and its jobs run with its `mcp__higgsfield-<name>__`
   tools.
6. Confirm in one line which account is active. There is no key or link to paste: the connection is the sign-in.
   In the Claude app (not Claude Code), the same thing is Settings -> Connectors -> Add custom connector with
   `https://mcp.higgsfield.ai/mcp`, one connector per account, each signed in once.
