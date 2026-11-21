#!/usr/bin/env bash
# Starts Studio inside a GitHub Codespace (runs on every codespace start; safe to run again by hand).
# The first start builds the images: 20 to 40 minutes. Later starts take about a minute.
set -euo pipefail
cd "$(dirname "$0")/../.."                                     # webapp/
FREE=deploy/free
ENV_FILE=$FREE/.env
COMPOSE=(docker compose -f $FREE/docker-compose.yml -f deploy/codespace/docker-compose.codespace.yml --env-file $ENV_FILE)
LOG=/tmp/studio-start.log

: "${CODESPACE_NAME:?run this inside a GitHub Codespace (see README.md)}"
DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"

for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done   # Docker starts with the codespace

if [ ! -f "$ENV_FILE" ]; then
  rand() { openssl rand -hex "${1:-24}"; }
  GATE_PASSWORD="$(rand 9)"
  GATE_HASH="$(docker run --rm caddy:2.10-alpine caddy hash-password --plaintext "$GATE_PASSWORD")"
  umask 077
  cat > "$ENV_FILE" <<ENV
# Studio in this codespace. Generated on $(date -u +%F). Private: it holds every secret of this install.
APP_HOST=${CODESPACE_NAME}-8080.${DOMAIN}
S3_HOST=${CODESPACE_NAME}-8333.${DOMAIN}
GATE_USER=studio
GATE_PASSWORD=${GATE_PASSWORD}
GATE_HASH='${GATE_HASH}'
PG_PASSWORD=$(rand)
S3_USER=studio
S3_PASSWORD=$(rand)
SECRET_KEY=$(rand 32)
SECRETS_KEY=$(openssl rand -base64 32 | tr '+/' '-_')
AUTH_MODE=dev
BOOTSTRAP_ADMINS=
# Claude tab: a key from console.anthropic.com (set a spend limit there), then: bash deploy/codespace/start.sh
ANTHROPIC_API_KEY=
AGENT_BRAND_MONTHLY_BUDGET_USD=25
AGENT_TURN_BUDGET_USD=3
ENV
fi
set -a; . "$ENV_FILE"; set +a

echo "Building and starting Studio (first time: 20-40 min). Log: $LOG"
if ! "${COMPOSE[@]}" up -d --build --remove-orphans >"$LOG" 2>&1; then
  tail -n 30 "$LOG"; echo "Studio didn't start: see $LOG"; exit 1
fi
for _ in $(seq 1 60); do curl -fsS http://localhost:8080/api/healthz >/dev/null 2>&1 && break; sleep 3; done

# share both ports (the team can't reach private ones); needs a token allowed to change this codespace
PUBLIC=no
if command -v gh >/dev/null && gh codespace ports visibility 8080:public 8333:public -c "$CODESPACE_NAME" >/dev/null 2>&1; then
  PUBLIC=yes
fi

cat <<MSG

  Studio is running.
MSG
if [ "$PUBLIC" = no ]; then cat <<MSG
  1. Ports tab: right-click ports 8080 and 8333 > Port Visibility > Public (once per codespace).
MSG
fi
cat <<MSG
  2. Open https://${APP_HOST}
     user "${GATE_USER}", password "${GATE_PASSWORD}", then sign in with your email (the first one becomes admin).

  Logs: docker compose -f $FREE/docker-compose.yml -f deploy/codespace/docker-compose.codespace.yml --env-file $ENV_FILE logs -f
MSG
