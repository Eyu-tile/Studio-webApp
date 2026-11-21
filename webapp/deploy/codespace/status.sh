#!/usr/bin/env bash
# Shown each time the editor connects to the codespace: where Studio stands.
STATUS=/tmp/studio-status.txt
if [ ! -f "$STATUS" ]; then
  echo "Studio hasn't started yet. Start it with: bash webapp/deploy/codespace/start.sh"
  exit 0
fi
if grep -q '^building' "$STATUS"; then
  echo "Studio is $(cat "$STATUS")."
  echo "Following the build below (Ctrl+C stops following, not the build). Run this again any time:"
  echo "  bash webapp/deploy/codespace/status.sh"
  echo
  tail -n 5 -f /tmp/studio-build.log 2>/dev/null &
  TAIL=$!
  while grep -q '^building' "$STATUS" 2>/dev/null; do sleep 5; done
  kill "$TAIL" 2>/dev/null
  echo
fi
cat "$STATUS"
