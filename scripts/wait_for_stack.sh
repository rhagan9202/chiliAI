#!/usr/bin/env bash
# Poll the API health endpoint until the dev stack is ready (bounded).
# Usage: scripts/wait_for_stack.sh [health-url] [attempts]
set -euo pipefail
URL="${1:-http://localhost:8000/health}"
ATTEMPTS="${2:-90}"
for i in $(seq 1 "$ATTEMPTS"); do
  if curl -fsS -o /dev/null "$URL"; then
    echo "stack ready ($URL) after ${i} attempt(s)"
    exit 0
  fi
  sleep 2
done
echo "stack did not become ready at $URL after $((ATTEMPTS * 2))s" >&2
exit 1
