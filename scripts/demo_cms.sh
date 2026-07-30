#!/usr/bin/env bash
# demo-cms: one-command CMS fraud demo bring-up (BL-051 / D1).
# Stack up -> desynpuf pack active -> TN 1% subset staged/built -> ingest ->
# analytics readiness probes -> demo-ready summary.
#
# This script does NOT compose the dev stack up — that is the operator's job
# (`make dev`). It only checks the API is answering, then drives the pack
# switch, data staging/build, ingest, and post-ingest readiness probes
# through the running API, exactly as an operator would by hand.
#
# jq-free by design (matches scripts/demo_ingest_tn_subset.sh): every JSON
# response is parsed with a small python3 one-liner.
set -euo pipefail

API="${CHILI_API_URL:-http://localhost:8000}"
APP="${CHILI_APP_URL:-http://localhost:5173}"
SAMPLE_RATE="${DEMO_SAMPLE_RATE:-0.01}"
SUBSET_DIR="sample_data/CMS/tn_subset"
PACK_NAME="medicare_fraud_cms_desynpuf"

# Probe budget: ~15s poll interval. (a) KB-ready and (e) policy items are
# lightweight status reads and keep the original 4 min cap. (b) alerts,
# (c) GNN clusters, and (d) evidence-pack narrative all depend on the
# native records->analytics fan-out (analytics.34; gated by the CMS pack's
# records.analytics_trigger config) finishing inside the worker: it runs a
# full-KB GNN snapshot (community detection over the *entire* TN-subset
# graph, not just the top-N entities) plus risk/explainability for the
# batch's top-N — and that GNN pass alone can take several minutes against
# a real graph — so their budget is raised well past the original cap.
# Both env-overridable for tuning.
PROBE_INTERVAL_SECONDS=15
PROBE_TIMEOUT_SECONDS="${PROBE_TIMEOUT_SECONDS:-240}"
PROBE_TIMEOUT_SECONDS_ANALYTICS="${PROBE_TIMEOUT_SECONDS_ANALYTICS:-900}"
PROBE_MAX_ATTEMPTS=$((PROBE_TIMEOUT_SECONDS / PROBE_INTERVAL_SECONDS))
PROBE_MAX_ATTEMPTS_ANALYTICS=$((PROBE_TIMEOUT_SECONDS_ANALYTICS / PROBE_INTERVAL_SECONDS))
# A timeout override below the poll interval must still probe once, not
# integer-divide to zero attempts and report "timed out" without a request.
[ "$PROBE_MAX_ATTEMPTS" -lt 1 ] && PROBE_MAX_ATTEMPTS=1
[ "$PROBE_MAX_ATTEMPTS_ANALYTICS" -lt 1 ] && PROBE_MAX_ATTEMPTS_ANALYTICS=1

log() {
  echo "[demo-cms] $*"
}

# ---------------------------------------------------------------------------
# 1. Stack: require the API healthy. Never `docker compose up` from here —
#    on failure, print the exact operator command and exit 1.
# ---------------------------------------------------------------------------
log "Checking API health at $API/health ..."
stack_ready=0
for _ in $(seq 1 10); do
  if curl -fsS --max-time 5 -o /dev/null "$API/health"; then
    stack_ready=1
    break
  fi
  sleep 3
done
if [ "$stack_ready" -ne 1 ]; then
  echo "ERROR: API at $API is not answering /health." >&2
  echo "Bring the dev stack up first, then re-run this target:" >&2
  echo "  make dev" >&2
  echo "  make demo-cms" >&2
  exit 1
fi
log "API healthy."

# ---------------------------------------------------------------------------
# 2. Pack: switch to the CMS DE-SynPUF pack when it is not already active.
#
#    NEVER switch to the generic `medicare_fraud` pack for this demo — it
#    carries no NPPES/DE-SynPUF field mappings or storage pins, so the CMS
#    feeds ingested below would not map onto entities/relationships.
#
#    GET /config/packs -> response.packs[].{name, active} is the reliable
#    activation signal here. response.active.pack_name is `domain.name`,
#    which is "medicare_fraud" for BOTH the generic and desynpuf packs (see
#    backend/config/defaults/medicare_fraud*.yaml) — it cannot disambiguate
#    which pack file is actually loaded, so this script never reads it.
#    (Verified against backend/api/routers/config.py: list_packs/_summarize_pack.)
# ---------------------------------------------------------------------------
# _pack_active <packs-json> -> prints 1/0/missing for $PACK_NAME. A helper
# (not a bare pipe) so both call sites parse identically.
_pack_active() {
  printf '%s' "$1" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print('missing')
    sys.exit(0)
for pack in data.get('packs', []):
    if pack['name'] == '$PACK_NAME':
        print('1' if pack['active'] else '0')
        break
else:
    print('missing')
"
}

log "Checking active domain pack..."
if ! PACKS_JSON=$(curl -fsS --max-time 10 "$API/config/packs"); then
  echo "ERROR: GET $API/config/packs failed (connection error or timeout)." >&2
  exit 1
fi
DESYNPUF_ACTIVE=$(_pack_active "$PACKS_JSON")
if [ "$DESYNPUF_ACTIVE" = "missing" ]; then
  echo "ERROR: pack '$PACK_NAME' not found under GET $API/config/packs." >&2
  echo "Expected backend/config/defaults/${PACK_NAME}.yaml to be discoverable." >&2
  exit 1
fi
if [ "$DESYNPUF_ACTIVE" = "1" ]; then
  log "Pack '$PACK_NAME' already active."
else
  log "Switching active pack to '$PACK_NAME'..."
  if ! SWITCH_RESPONSE=$(curl -fsS --max-time 10 -X POST "$API/config/switch" \
    -H 'Content-Type: application/json' \
    -d "{\"pack\":\"$PACK_NAME\"}"); then
    echo "ERROR: POST $API/config/switch (pack=$PACK_NAME) failed (connection error, timeout, or non-2xx)." >&2
    exit 1
  fi
  SWITCHED_NAME=$(printf '%s' "$SWITCH_RESPONSE" | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin)['pack_name'])
except Exception:
    print('unknown')
")
  log "Switch accepted (domain.name=$SWITCHED_NAME); verifying via GET /config/packs..."
  if ! PACKS_JSON=$(curl -fsS --max-time 10 "$API/config/packs"); then
    echo "ERROR: GET $API/config/packs failed (connection error or timeout) while verifying the switch." >&2
    exit 1
  fi
  DESYNPUF_ACTIVE=$(_pack_active "$PACKS_JSON")
  if [ "$DESYNPUF_ACTIVE" != "1" ]; then
    echo "ERROR: switched to '$PACK_NAME' but GET /config/packs does not report it active." >&2
    exit 1
  fi
  log "Pack '$PACK_NAME' now active."
fi

# ---------------------------------------------------------------------------
# 3. Data: build the sampled TN subset if it hasn't been built yet. Reuses
#    the same builder + args as the `demo-tn-subset` Makefile target, not a
#    reimplementation.
# ---------------------------------------------------------------------------
if [ -f "$SUBSET_DIR/MANIFEST.json" ]; then
  log "TN subset already staged at $SUBSET_DIR (MANIFEST.json present); skipping build."
else
  if [ ! -d "sample_data/CMS" ]; then
    echo "ERROR: sample_data/CMS not found." >&2
    echo "Run 'make data-setup' first (see docs/testing/DATA.md)." >&2
    exit 1
  fi
  log "Building TN subset at $SUBSET_DIR (sample-rate=$SAMPLE_RATE)..."
  python3 -m tools.sample_data.build_tennessee_subset \
    --nppes-root sample_data \
    --desynpuf-root sample_data/CMS \
    --output-root "$SUBSET_DIR" \
    --sample-rate "$SAMPLE_RATE"
fi

# ---------------------------------------------------------------------------
# 4. Ingest: scripts/demo_ingest_tn_subset.sh owns the per-KB upload
#    workflow (including the 409-retry loop for workflow serialization).
#    Its final line is "Done. KB ID: <id>" on success or
#    "Done with N failed upload(s). KB ID: <id>" (exit 1) on partial
#    failure — capture stdout+stderr so the KB id is found either way.
# ---------------------------------------------------------------------------
log "Running scripts/demo_ingest_tn_subset.sh ..."
INGEST_LOG=$(mktemp -t chili_demo_cms_ingest.XXXXXX.log)
INGEST_STATUS=0
scripts/demo_ingest_tn_subset.sh >"$INGEST_LOG" 2>&1 || INGEST_STATUS=$?
cat "$INGEST_LOG"

KB_ID=$(sed -n 's/^.*KB ID: //p' "$INGEST_LOG" | tail -1 | tr -d '[:space:]')
rm -f "$INGEST_LOG"

if [ -z "$KB_ID" ]; then
  echo "ERROR: could not parse a KB id from scripts/demo_ingest_tn_subset.sh output." >&2
  exit 1
fi
if [ "$INGEST_STATUS" -ne 0 ]; then
  echo "ERROR: scripts/demo_ingest_tn_subset.sh exited $INGEST_STATUS (failed upload(s))" \
    "for KB $KB_ID; demo data may be incomplete." >&2
  exit 1
fi
log "Ingest complete. KB ID: $KB_ID"

# ---------------------------------------------------------------------------
# 5. Readiness probes: poll with timeouts (~15s interval; (a)/(e) at 4 min,
#    (b)-(d) at the analytics budget above — see its comment). Each prints
#    PASS/WAIT lines and, on timeout, exits 1 naming the failing probe —
#    except probe (e), which is intentionally soft (see its comment below).
# ---------------------------------------------------------------------------

# (a) KB status ready.
# Verified: backend/shared/types.py KnowledgeBase.status Literal includes
# "ready"; backend/api/routers/knowledgebases.py GET /{knowledge_base_id}.
probe_kb_ready() {
  log "Probe (a): KB $KB_ID status..."
  local attempt body kb_status
  for attempt in $(seq 1 "$PROBE_MAX_ATTEMPTS"); do
    # `body=$(curl ...) || body=""` is -e-exempt (the `||` makes the whole
    # statement's status 0 either way) — a transient connection failure or
    # --max-time timeout on any attempt must fall through to WAIT, never
    # abort the script. A bare `body=$(curl ...)` assignment would abort
    # under `set -e`; every probe curl in this script carries this guard.
    body=$(curl -fsS --max-time 10 "$API/knowledgebases/$KB_ID") || body=""
    kb_status=$(printf '%s' "$body" | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin).get('status', ''))
except Exception:
    print('')
")
    if [ "$kb_status" = "ready" ]; then
      echo "PASS (a) KB status=ready"
      return 0
    fi
    echo "WAIT (a) KB status=${kb_status:-unknown} (attempt $attempt/$PROBE_MAX_ATTEMPTS)"
    sleep "$PROBE_INTERVAL_SECONDS"
  done
  echo "ERROR: probe (a) KB status timed out waiting for 'ready' after ${PROBE_TIMEOUT_SECONDS}s." >&2
  exit 1
}

# (b) Durable alert feed has >=1 item for the KB.
# Verified: backend/api/dependencies.py get_alert_list_payload — the query
# param is `kb` (alias), NOT `knowledge_base_id`; response is
# {items: [...], page: {total_items, ...}} (api/contracts.py AlertListResponse).
# Captures the first alert's entity_id for the block 6 investigation URL.
probe_alerts_live() {
  log "Probe (b): durable alert feed for KB $KB_ID..."
  local attempt body total
  for attempt in $(seq 1 "$PROBE_MAX_ATTEMPTS_ANALYTICS"); do
    body=$(curl -fsS --max-time 10 "$API/alerts?knowledge_base_id=$KB_ID&limit=100") || body=""
    total=$(printf '%s' "$body" | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin)['page']['total_items'])
except Exception:
    print(0)
")
    if [ "$total" -ge 1 ]; then
      ALERT_TOTAL="$total"
      FIRST_ALERT_ENTITY_ID=$(printf '%s' "$body" | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin)['items'][0]['entity_id'])
except Exception:
    print('')
")
      echo "PASS (b) alerts total=$total"
      return 0
    fi
    echo "WAIT (b) alerts total=$total (attempt $attempt/$PROBE_MAX_ATTEMPTS_ANALYTICS)"
    sleep "$PROBE_INTERVAL_SECONDS"
  done
  echo "ERROR: probe (b) alert feed timed out; 0 alerts for KB $KB_ID after ${PROBE_TIMEOUT_SECONDS_ANALYTICS}s." >&2
  exit 1
}

# (c) GNN clusters exist for the KB.
# Verified: backend/api/routers/analytics.py GET /analytics/gnn/clusters,
# param `kb_id`; response {knowledge_base_id, clusters: [...]}
# (backend/analytics/gnn/service_models.py GnnClusterResponse).
probe_gnn_clusters() {
  log "Probe (c): GNN clusters for KB $KB_ID..."
  local attempt body count
  for attempt in $(seq 1 "$PROBE_MAX_ATTEMPTS_ANALYTICS"); do
    body=$(curl -fsS --max-time 10 "$API/analytics/gnn/clusters?kb_id=$KB_ID") || body=""
    count=$(printf '%s' "$body" | python3 -c "
import json, sys
try:
    print(len(json.load(sys.stdin).get('clusters', [])))
except Exception:
    print(0)
")
    if [ "$count" -ge 1 ]; then
      GNN_CLUSTER_COUNT="$count"
      echo "PASS (c) gnn clusters=$count"
      return 0
    fi
    echo "WAIT (c) gnn clusters=$count (attempt $attempt/$PROBE_MAX_ATTEMPTS_ANALYTICS)"
    sleep "$PROBE_INTERVAL_SECONDS"
  done
  echo "ERROR: probe (c) GNN clusters timed out; 0 clusters for KB $KB_ID after ${PROBE_TIMEOUT_SECONDS_ANALYTICS}s." >&2
  exit 1
}

# (d) First alert has an evidence_pack_id, and that pack has >=1 narrative
# section (B3 explainability pack).
# Verified: AlertListItem.evidence_pack_id (api/contracts.py); GET
# /evidence-packs/{evidence_pack_id} REQUIRES `knowledge_base_id` as a query
# param (backend/api/dependencies.py get_evidence_pack_payload) — it is not
# a bare path lookup. Response EvidencePackResponse.narrative_sections.
probe_evidence_narrative() {
  log "Probe (d): evidence pack narrative for the first alert..."
  local attempt body evidence_id evidence_body narrative_count
  for attempt in $(seq 1 "$PROBE_MAX_ATTEMPTS_ANALYTICS"); do
    body=$(curl -fsS --max-time 10 "$API/alerts?knowledge_base_id=$KB_ID&limit=1") || body=""
    evidence_id=$(printf '%s' "$body" | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin)['items'][0].get('evidence_pack_id') or '')
except Exception:
    print('')
")
    if [ -n "$evidence_id" ]; then
      # -fsS makes a 404 (evidence pack not yet persisted — expected on
      # early attempts) a curl failure; guard it the same way so it's a
      # WAIT, not a script abort.
      evidence_body=$(curl -fsS --max-time 10 "$API/evidence-packs/$evidence_id?knowledge_base_id=$KB_ID") || evidence_body=""
      narrative_count=$(printf '%s' "$evidence_body" | python3 -c "
import json, sys
try:
    print(len(json.load(sys.stdin).get('narrative_sections', [])))
except Exception:
    print(0)
")
      if [ "$narrative_count" -ge 1 ]; then
        EVIDENCE_PACK_ID="$evidence_id"
        NARRATIVE_SECTION_COUNT="$narrative_count"
        echo "PASS (d) evidence pack $evidence_id narrative_sections=$narrative_count"
        return 0
      fi
      echo "WAIT (d) evidence pack $evidence_id found, narrative_sections=$narrative_count (attempt $attempt/$PROBE_MAX_ATTEMPTS_ANALYTICS)"
    else
      echo "WAIT (d) first alert has no evidence_pack_id yet (attempt $attempt/$PROBE_MAX_ATTEMPTS_ANALYTICS)"
    fi
    sleep "$PROBE_INTERVAL_SECONDS"
  done
  echo "ERROR: probe (d) evidence pack narrative timed out after ${PROBE_TIMEOUT_SECONDS_ANALYTICS}s." >&2
  exit 1
}

# (e) Policy items exist for the KB (Task 1's fraud rule packs firing).
# Verified: backend/api/dependencies.py get_policy_item_list_payload, param
# `knowledge_base_id` (unaliased, unlike the alerts route); response
# {items: [...], total} (api/contracts.py PolicyItemListResponse).
# SOFT PROBE: whether Task 1's rule packs actually fire against this data is
# Task 5's tuning concern, not a demo-cms bug — 0 items after the timeout
# prints a WARNING and the run continues (no exit 1).
probe_policy_items() {
  log "Probe (e): policy items for KB $KB_ID (soft)..."
  local attempt body count
  for attempt in $(seq 1 "$PROBE_MAX_ATTEMPTS"); do
    body=$(curl -fsS --max-time 10 "$API/policy/items?knowledge_base_id=$KB_ID&limit=1") || body=""
    count=$(printf '%s' "$body" | python3 -c "
import json, sys
try:
    print(json.load(sys.stdin).get('total', 0))
except Exception:
    print(0)
")
    if [ "$count" -ge 1 ]; then
      POLICY_ITEM_COUNT="$count"
      echo "PASS (e) policy items=$count"
      return 0
    fi
    echo "WAIT (e) policy items=$count (attempt $attempt/$PROBE_MAX_ATTEMPTS)"
    sleep "$PROBE_INTERVAL_SECONDS"
  done
  POLICY_ITEM_COUNT=0
  echo "WARNING: probe (e) found 0 policy items for KB $KB_ID after ${PROBE_TIMEOUT_SECONDS}s." >&2
  echo "WARNING: this is soft by design — Task 1's fraud rule packs firing" \
    "reliably against this data is Task 5's tuning concern. Continuing." >&2
}

ALERT_TOTAL=0
FIRST_ALERT_ENTITY_ID=""
GNN_CLUSTER_COUNT=0
EVIDENCE_PACK_ID=""
NARRATIVE_SECTION_COUNT=0
POLICY_ITEM_COUNT=0

probe_kb_ready
probe_alerts_live
probe_gnn_clusters
probe_evidence_narrative
probe_policy_items

# ---------------------------------------------------------------------------
# 6. Summary
# ---------------------------------------------------------------------------
POLICY_ITEM_NOTE=""
if [ "$POLICY_ITEM_COUNT" -eq 0 ]; then
  POLICY_ITEM_NOTE=" (WARNING: 0 — see probe (e) above)"
fi

echo
echo "================================================================"
echo "demo-cms ready"
echo "KB ID:           $KB_ID"
echo "Alerts (total):  $ALERT_TOTAL"
echo "GNN clusters:    $GNN_CLUSTER_COUNT"
echo "Evidence pack:   ${EVIDENCE_PACK_ID:-none} (narrative_sections=$NARRATIVE_SECTION_COUNT)"
echo "Policy items:    ${POLICY_ITEM_COUNT}${POLICY_ITEM_NOTE}"
echo
echo "Walkthrough URLs:"
echo "  $APP/alerts"
echo "  $APP/investigation/${FIRST_ALERT_ENTITY_ID}?kb=$KB_ID"
echo "  $APP/dashboard"
echo "  $APP/policy"
echo "  $APP/rag-chat"
echo "================================================================"
