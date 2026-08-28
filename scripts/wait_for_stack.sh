#!/usr/bin/env bash
# Poll until two readiness URLs both answer 2xx, or give up.
#
# The defaults describe the full dev stack (API health + the Vite app), which
# is what `make test-e2e` needs. Callers that start only some services must
# pass URLs those services actually serve — a job that never starts the app
# container will otherwise spin on :5173 until the attempt budget runs out.
#
# Usage: scripts/wait_for_stack.sh [first-url] [second-url] [attempts]
set -euo pipefail
API_URL="${1:-http://localhost:8000/health}"
APP_URL="${2:-http://localhost:5173/}"
ATTEMPTS="${3:-90}"
for i in $(seq 1 "$ATTEMPTS"); do
  if curl -fsS -o /dev/null "$API_URL" && curl -fsS -o /dev/null "$APP_URL"; then
    echo "stack ready ($API_URL, $APP_URL) after ${i} attempt(s)"
    exit 0
  fi
  sleep 2
done
echo "stack did not become ready ($API_URL, $APP_URL) after $((ATTEMPTS * 2))s" >&2
exit 1
