#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
APP_BASE_URL="${APP_BASE_URL:-http://localhost:5173}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.dev.yaml}"
SEARCH_QUERY="${SEARCH_QUERY:-CLAIM-GRAPH-SMOKE-001}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-90}"
CLEANUP="${CLEANUP:-0}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DOC="$(mktemp -t chiliai-graph-smoke.XXXXXX.json)"
KB_ID=""

cleanup() {
  rm -f "$TMP_DOC"
  if [[ "$CLEANUP" == "1" && -n "$KB_ID" ]]; then
    curl -sS -X DELETE "$API_BASE_URL/knowledgebases/$KB_ID" >/dev/null || true
  fi
}
trap cleanup EXIT

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"

cat >"$TMP_DOC" <<JSON
{
  "npi": "1234567890",
  "specialty": "Cardiology",
  "state": "TX",
  "hic_number": "HICSMOKE001",
  "age": 72,
  "chronic_conditions": ["diabetes", "hypertension"],
  "claim_id": "$SEARCH_QUERY",
  "amount": 1250.50,
  "service_date": "2026-04-26",
  "procedure_codes": ["99213"],
  "facility_id": "FAC-SMOKE-001",
  "name": "Austin Smoke Clinic",
  "type": "outpatient"
}
JSON

printf 'Creating smoke knowledge base...\n'
KB_ID="$({
  curl -sS -X POST "$API_BASE_URL/knowledgebases" \
    -H 'Content-Type: application/json' \
    -d '{"name":"Graph Workflow Smoke","description":"temporary live-stack smoke test"}'
} | "$PYTHON_BIN" -c 'import json, sys; print(json.load(sys.stdin)["id"])'
)"
printf 'KB_ID=%s\n' "$KB_ID"

printf 'Uploading smoke document...\n'
curl -sS -X POST "$API_BASE_URL/knowledgebases/$KB_ID/documents" \
  -F "files=@$TMP_DOC;type=application/json" >/dev/null

printf 'Waiting for kb.ready and investigation search result...\n'
ENTITY_ID=""
DEADLINE=$((SECONDS + TIMEOUT_SECONDS))
while (( SECONDS < DEADLINE )); do
  docker compose -f "$ROOT_DIR/$COMPOSE_FILE" exec -T redis \
    redis-cli XREAD BLOCK 2000 COUNT 10 STREAMS chili.kb.ready '$' >/dev/null 2>&1 || true

  SEARCH_PAYLOAD="$(curl -sS "$API_BASE_URL/investigation/search?kb_id=$KB_ID&q=$SEARCH_QUERY&limit=10")"
  ENTITY_ID="$(printf '%s' "$SEARCH_PAYLOAD" | "$PYTHON_BIN" -c 'import json, sys; payload = json.load(sys.stdin); items = payload.get("items", []); print(items[0]["id"] if items else "")')"
  if [[ -n "$ENTITY_ID" ]]; then
    break
  fi
done

if [[ -z "$ENTITY_ID" ]]; then
  printf 'Graph smoke failed: no investigation search result for %s in KB %s.\n' "$SEARCH_QUERY" "$KB_ID" >&2
  printf 'Recent worker logs:\n' >&2
  docker compose -f "$ROOT_DIR/$COMPOSE_FILE" logs --tail=120 worker >&2 || true
  exit 1
fi

printf 'ENTITY_ID=%s\n' "$ENTITY_ID"
printf 'Validating entity detail...\n'
curl -sS "$API_BASE_URL/investigation/entities/$ENTITY_ID?kb_id=$KB_ID" | "$PYTHON_BIN" -c '
import json
import sys
payload = json.load(sys.stdin)
entity = payload["entity"]
assert entity["id"]
assert entity["properties"]
print(json.dumps({"id": entity["id"], "type": entity["type"], "properties": entity["properties"]}, indent=2, sort_keys=True))
'

printf 'Validating neighborhood...\n'
curl -sS "$API_BASE_URL/investigation/entities/$ENTITY_ID/neighborhood?kb_id=$KB_ID&depth=2" | "$PYTHON_BIN" -c '
import json
import sys
payload = json.load(sys.stdin)
assert payload["entities"], "expected neighborhood entities"
print(json.dumps({"entity_count": len(payload["entities"]), "relationship_count": len(payload["relationships"])}, indent=2, sort_keys=True))
'

INVESTIGATION_URL="$APP_BASE_URL/investigation?kb_id=$KB_ID&entity_id=$ENTITY_ID"
printf '\nGraph workflow smoke passed.\n'
printf 'Open Investigation route:\n%s\n' "$INVESTIGATION_URL"
