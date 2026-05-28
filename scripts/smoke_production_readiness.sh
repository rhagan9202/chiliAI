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

is_2xx() {
  case "$1" in
    2??) return 0 ;;
    *) return 1 ;;
  esac
}

http_request() {
  local body_file="$1"
  shift
  local status_code

  if ! status_code="$(curl -sS -o "$body_file" -w '%{http_code}' "$@")"; then
    printf 'Request failed before receiving an HTTP response: curl %s\n' "$*" >&2
    if [[ -s "$body_file" ]]; then
      cat "$body_file" >&2
      printf '\n' >&2
    fi
    return 1
  fi

  printf '%s' "$status_code"
}

print_response_failure() {
  local message="$1"
  local status_code="$2"
  local body_file="$3"

  printf '%s (%s).\n' "$message" "$status_code" >&2
  if [[ -s "$body_file" ]]; then
    cat "$body_file" >&2
  else
    printf '<empty response body>' >&2
  fi
  printf '\n' >&2
}

json_field_from_file() {
  local body_file="$1"
  local field="$2"
  "$PYTHON_BIN" - "$body_file" "$field" <<'PY'
import json
import sys

body_file = sys.argv[1]
field = sys.argv[2]

try:
    with open(body_file, encoding="utf-8") as fh:
        payload = json.load(fh)
except (OSError, json.JSONDecodeError):
    sys.exit(2)

if not isinstance(payload, dict):
    sys.exit(3)

value = payload.get(field)
if not isinstance(value, str) or not value:
    sys.exit(4)

print(value)
PY
}

workflow_status_from_file() {
  local body_file="$1"
  "$PYTHON_BIN" - "$body_file" <<'PY'
import json
import sys

body_file = sys.argv[1]

try:
    with open(body_file, encoding="utf-8") as fh:
        payload = json.load(fh)
except (OSError, json.JSONDecodeError):
    sys.exit(2)

if not isinstance(payload, dict):
    sys.exit(3)

if "items" not in payload:
    sys.exit(4)

items = payload["items"]
if not isinstance(items, list):
    sys.exit(4)

if not items:
    print("")
    sys.exit(0)

first = items[0]
if not isinstance(first, dict):
    sys.exit(5)

status = first.get("status")
if not isinstance(status, str) or not status:
    sys.exit(6)

print(status)
PY
}

request_ok() {
  local url="$1"
  local body_file="$TMP_DIR/response-body.json"
  local status_code

  status_code="$(http_request "$body_file" "$url")"
  if [[ "$status_code" != "200" ]]; then
    print_response_failure "Request failed: $url" "$status_code" "$body_file"
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
CREATE_KB_BODY="$TMP_DIR/create-empty-kb.json"
CREATE_KB_STATUS="$(http_request "$CREATE_KB_BODY" \
  -X POST "$API_BASE_URL/knowledgebases" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Zero Entity Production Smoke","description":"temporary zero-entity workflow smoke"}')"

if ! is_2xx "$CREATE_KB_STATUS"; then
  print_response_failure "Production smoke failed: zero-entity knowledge base creation failed" "$CREATE_KB_STATUS" "$CREATE_KB_BODY"
  exit 1
fi

if ! EMPTY_KB_ID="$(json_field_from_file "$CREATE_KB_BODY" id)"; then
  printf 'Production smoke failed: zero-entity knowledge base response did not include a valid id.\n' >&2
  cat "$CREATE_KB_BODY" >&2
  printf '\n' >&2
  exit 1
fi

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
UPLOAD_BODY="$TMP_DIR/upload-empty-doc.json"
UPLOAD_STATUS="$(http_request "$UPLOAD_BODY" \
  -X POST "$API_BASE_URL/knowledgebases/$EMPTY_KB_ID/documents" \
  -F "files=@$EMPTY_DOC;type=text/plain")"

if ! is_2xx "$UPLOAD_STATUS"; then
  print_response_failure "Production smoke failed: zero-entity document upload failed" "$UPLOAD_STATUS" "$UPLOAD_BODY"
  exit 1
fi

printf 'Waiting for zero-entity workflow completion...\n'
DEADLINE=$((SECONDS + TIMEOUT_SECONDS))
while (( SECONDS < DEADLINE )); do
  WORKFLOW_BODY="$TMP_DIR/workflows-empty-kb.json"
  WORKFLOW_STATUS_CODE="$(http_request "$WORKFLOW_BODY" "$API_BASE_URL/workflows?knowledge_base_id=$EMPTY_KB_ID&limit=10")"

  if ! is_2xx "$WORKFLOW_STATUS_CODE"; then
    print_response_failure "Production smoke failed: workflow polling request failed" "$WORKFLOW_STATUS_CODE" "$WORKFLOW_BODY"
    exit 1
  fi

  if ! STATUS="$(workflow_status_from_file "$WORKFLOW_BODY")"; then
    printf 'Production smoke failed: workflow polling response had an unexpected JSON shape.\n' >&2
    cat "$WORKFLOW_BODY" >&2
    printf '\n' >&2
    exit 1
  fi

  case "$STATUS" in
    completed)
      printf 'zero entity workflow completed\n'
      exit 0
      ;;
    failed|cancelled)
      printf 'Production smoke failed: zero-entity workflow status is %s.\n' "$STATUS" >&2
      cat "$WORKFLOW_BODY" >&2
      printf '\n' >&2
      exit 1
      ;;
  esac

  sleep 2
done

printf 'Production smoke failed: zero-entity workflow did not complete within %ss.\n' "$TIMEOUT_SECONDS" >&2
TIMEOUT_BODY="$TMP_DIR/workflows-empty-kb-timeout.json"
if TIMEOUT_STATUS="$(http_request "$TIMEOUT_BODY" "$API_BASE_URL/workflows?knowledge_base_id=$EMPTY_KB_ID&limit=10")"; then
  print_response_failure "Last workflow polling response" "$TIMEOUT_STATUS" "$TIMEOUT_BODY"
fi
printf '\n' >&2
exit 1
