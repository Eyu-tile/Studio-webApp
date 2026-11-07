#!/usr/bin/env bash
# Put the plugin's `vs` CLI on PATH for every Bash command in the session.
[ -n "${CLAUDE_ENV_FILE:-}" ] && [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] || exit 0
printf 'export PATH="%s/bin:$PATH"\nexport VS_ROOT="%s"\n' "$CLAUDE_PLUGIN_ROOT" "$CLAUDE_PLUGIN_ROOT" >> "$CLAUDE_ENV_FILE"
exit 0
