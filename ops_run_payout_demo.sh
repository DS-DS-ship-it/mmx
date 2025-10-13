#!/usr/bin/env bash
set -Eeuo pipefail

: "${BASE_URL:=http://localhost:3000}"
PERIOD="${PERIOD:-$(date +%Y-%m)}"
POOL_PERCENT="${POOL_PERCENT:-30}"

jqbin="$(command -v jq || true)"

echo "== contributors =="
curl -s "$BASE_URL/contributors" | { [[ -n "$jqbin" ]] && jq . || cat; }

ACCT_ID="$(curl -s "$BASE_URL/contributors" | { [[ -n "$jqbin" ]] && jq -r 'map(select(.stripe_account_id!=null))[0].stripe_account_id // empty' || sed -n 's/.*"stripe_account_id":"\([^"]*\)".*/\1/p' | head -n1; })"
[[ -n "$ACCT_ID" ]] || { echo "no connected accounts yet"; exit 1; }
echo "using connected account: $ACCT_ID"

echo "== seed platform balance (test charge) =="
stripe payment_intents create \
  --amount 120000 --currency usd \
  --payment-method pm_card_visa --confirm >/dev/null
echo "ok"

echo "== record revenue =="
curl -sS -X POST "$BASE_URL/revenue" \
  -H 'content-type: application/json' \
  -d "{\"period\":\"$PERIOD\",\"amount_cents\":120000}" | { [[ -n "$jqbin" ]] && jq . || cat; }

echo "== distribute payouts =="
curl -sS -X POST "$BASE_URL/distribute_payouts" \
  -H 'content-type: application/json' \
  -d "{\"period\":\"$PERIOD\",\"pool_percent\":$POOL_PERCENT}" | { [[ -n "$jqbin" ]] && jq . || cat; }
