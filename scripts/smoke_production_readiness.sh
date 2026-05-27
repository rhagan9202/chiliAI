#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
APP_BASE_URL="${APP_BASE_URL:-http://127.0.0.1:5173}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-90}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"
TMP_DIR="$(mktemp -d -t chiliai-production-smoke.XXXXXX)"
GRAPH_OUTPUT="$TMP_DIR/graph-smoke.out"
EMPTY_DOC="$TMP_DIR/zero-entity.txt"
EMPTY_KB_ID=""

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

json_field() {
  local field="$1"
  "$PYTHON_BIN" -c 'import json, sys; print(json.load(sys.stdin).get(sys.argv[1], ""))' "$field"
}

workflow_status() {
  "$PYTHON_BIN" -c '
import json
import sys

payload = json.load(sys.stdin)
items = payload.get("items", [])
print(items[0].get("status", "") if items else "")
'
}

request_ok() {
  local url="$1"
  local body_file="$TMP_DIR/response-body.json"
  local status_code

  status_code="$(curl -sS -o "$body_file" -w '%{http_code}' "$url")"
  if [[ "$status_code" != "200" ]]; then
    printf 'Request failed (%s): %s\n' "$status_code" "$url" >&2
    cat "$body_file" >&2
    printf '\n' >&2
    exit 1
  fi
  cat "$body_file"
  printf '\n'
}

printf 'Running graph workflow smoke...\n'
API_BASE_URL="$API_BASE_URL" APP_BASE_URL="$APP_BASE_URL" \
  "$ROOT_DIR/scripts/smoke_graph_workflow.sh" | tee "$GRAPH_OUTPUT"

KB_ID="$(sed -n 's/^KB_ID=//p; s/^knowledge_base_id=//p' "$GRAPH_OUTPUT" | tail -n 1)"
ENTITY_ID="$(sed -n 's/^ENTITY_ID=//p; s/^entity_id=//p' "$GRAPH_OUTPUT" | tail -n 1)"

if [[ -z "$KB_ID" || -z "$ENTITY_ID" ]]; then
  printf 'Production smoke failed: missing knowledge_base_id or entity_id from graph smoke output.\n' >&2
  printf 'knowledge_base_id=%s entity_id=%s\n' "$KB_ID" "$ENTITY_ID" >&2
  exit 1
fi

printf 'Validating analytics risk score detail...\n'
request_ok "$API_BASE_URL/analytics/risk-scores/$ENTITY_ID?kb_id=$KB_ID" >/dev/null

printf 'Validating analytics timeseries detail...\n'
request_ok "$API_BASE_URL/analytics/timeseries/$ENTITY_ID?kb_id=$KB_ID" >/dev/null

printf 'Creating zero-entity knowledge base...\n'
EMPTY_KB_ID="$(
  curl -sS -X POST "$API_BASE_URL/knowledgebases" \
    -H 'Content-Type: application/json' \
    -d '{"name":"Zero Entity Production Smoke","description":"temporary zero-entity workflow smoke"}' \
    | json_field id
)"

if [[ -z "$EMPTY_KB_ID" ]]; then
  printf 'Production smoke failed: zero-entity knowledge base was not created.\n' >&2
  exit 1
fi

cat >"$EMPTY_DOC" <<'TEXT'
This brief note contains general operational prose for a production smoke check.
It intentionally avoids structured claim, provider, facility, patient, and code markers.
No configured extraction entity should be produced from this sentence-only document.
TEXT

printf 'Uploading zero-entity document...\n'
curl -sS -X POST "$API_BASE_URL/knowledgebases/$EMPTY_KB_ID/documents" \
  -F "files=@$EMPTY_DOC;type=text/plain" >/dev/null

printf 'Waiting for zero-entity workflow completion...\n'
DEADLINE=$((SECONDS + TIMEOUT_SECONDS))
while (( SECONDS < DEADLINE )); do
  WORKFLOW_PAYLOAD="$(curl -sS "$API_BASE_URL/workflows?knowledge_base_id=$EMPTY_KB_ID&limit=10")"
  STATUS="$(printf '%s' "$WORKFLOW_PAYLOAD" | workflow_status)"

  case "$STATUS" in
    completed)
      printf 'zero entity workflow completed\n'
      exit 0
      ;;
    failed|cancelled)
      printf 'Production smoke failed: zero-entity workflow status is %s.\n' "$STATUS" >&2
      printf '%s\n' "$WORKFLOW_PAYLOAD" >&2
      exit 1
      ;;
  esac

  sleep 2
done

printf 'Production smoke failed: zero-entity workflow did not complete within %ss.\n' "$TIMEOUT_SECONDS" >&2
curl -sS "$API_BASE_URL/workflows?knowledge_base_id=$EMPTY_KB_ID&limit=10" >&2 || true
printf '\n' >&2
exit 1
