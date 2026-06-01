#!/usr/bin/env bash
# Poll until the dev stack is ready: API health AND the app (Vite) are serving.
# Usage: scripts/wait_for_stack.sh [api-health-url] [app-url] [attempts]
set -euo pipefail
API_URL="${1:-http://localhost:8000/health}"
APP_URL="${2:-http://localhost:5173/}"
ATTEMPTS="${3:-90}"
for i in $(seq 1 "$ATTEMPTS"); do
  if curl -fsS -o /dev/null "$API_URL" && curl -fsS -o /dev/null "$APP_URL"; then
    echo "stack ready (api: $API_URL, app: $APP_URL) after ${i} attempt(s)"
    exit 0
  fi
  sleep 2
done
echo "stack did not become ready (api: $API_URL, app: $APP_URL) after $((ATTEMPTS * 2))s" >&2
exit 1
