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

echo "Done. KB ID: $KB_ID"
