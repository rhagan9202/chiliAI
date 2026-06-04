#!/usr/bin/env bash
set -euo pipefail

API="${CHILI_API_URL:-http://localhost:8000}"

KB_RESPONSE=$(curl -s -X POST "$API/knowledgebases" \
  -H 'Content-Type: application/json' \
  -d '{"name":"TN Demo","description":"Tennessee NPPES+DE-SynPUF subset"}')
KB_ID=$(echo "$KB_RESPONSE" | python3 -c "import json, sys; print(json.load(sys.stdin)['id'])")
echo "Created KB $KB_ID"

upload() {
  local feed="$1"
  local path="$2"
  if [ ! -f "$path" ]; then
    echo "Skipping $feed: $path not found" >&2
    return 0
  fi
  echo "Uploading $feed from $path..."
  curl -s -X POST "$API/records/$KB_ID/files" \
    -F "file=@$path" \
    -F "feed=$feed" \
    | python3 -m json.tool
}

upload "nppes_providers"  sample_data/CMS/tn_subset/nppes_providers_tn.csv
upload "inpatient_claims"  sample_data/CMS/tn_subset/desynpuf_inpatient_claims_tn.csv
upload "outpatient_claims" sample_data/CMS/tn_subset/desynpuf_outpatient_claims_tn.csv
upload "carrier_claims_a"  sample_data/CMS/tn_subset/desynpuf_carrier_claims_tn.csv
upload "beneficiary_2010"  sample_data/CMS/tn_subset/desynpuf_beneficiaries_tn.csv

# ---------------------------------------------------------------------------
# Policy corpus (BL-014) — upload synthetic policy DOCUMENTS into the same KB
# via the document endpoint so the demo shows a policy graph (policy/
# procedure_code/regulation_section + applies_to->provider) that joins the
# records graph. Best-effort: skipped if the corpus directory is absent.
# Set DEMO_SKIP_POLICIES=1 to disable.
# ---------------------------------------------------------------------------
POLICIES_DIR="${DEMO_POLICIES_DIR:-backend/tests/ingestion/fixtures/policies}"

upload_document() {
  local path="$1"
  if [ ! -f "$path" ]; then
    return 0
  fi
  echo "Uploading policy document $(basename "$path")..."
  # Markdown is uploaded as text/plain (text/markdown is not in the default
  # allowed content types; the plain-text parser passes content through so the
  # extractor still sees the full policy text).
  local ctype="text/plain"
  case "$path" in
    *.html) ctype="text/html" ;;
    *.json) ctype="application/json" ;;
    *.docx) ctype="application/vnd.openxmlformats-officedocument.wordprocessingml.document" ;;
    *.txt|*.md) ctype="text/plain" ;;
  esac
  curl -s -X POST "$API/knowledgebases/$KB_ID/documents" \
    -F "files=@$path;type=$ctype" \
    | python3 -m json.tool || true
}

if [ "${DEMO_SKIP_POLICIES:-0}" != "1" ] && [ -d "$POLICIES_DIR" ]; then
  echo "Uploading policy corpus from $POLICIES_DIR..."
  for doc in "$POLICIES_DIR"/*.md "$POLICIES_DIR"/*.html "$POLICIES_DIR"/*.json \
             "$POLICIES_DIR"/*.txt "$POLICIES_DIR"/*.docx; do
    [ -e "$doc" ] || continue
    upload_document "$doc"
  done
else
  echo "Skipping policy corpus (DEMO_SKIP_POLICIES set or $POLICIES_DIR missing)." >&2
fi

echo "Done. KB ID: $KB_ID"
