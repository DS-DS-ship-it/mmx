#!/usr/bin/env bash
set -euo pipefail
: "${BASE_URL:=http://localhost:3000}"
: "${POOL_PERCENT:=30}"
per="$(curl -sS "$BASE_URL/periods/latest" | awk -F'"' '/period/ {print $4}')"
[ -n "$per" ] || { echo "no period"; exit 0; }
curl -sS -X POST "$BASE_URL/distribute_payouts" \
  -H 'content-type: application/json' \
  -d "{\"period\":\"$per\",\"pool_percent\":$POOL_PERCENT}"
echo
