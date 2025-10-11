#!/usr/bin/env bash
set -Eeuo pipefail

: "${BASE_URL:=http://localhost:3000}"
: "${AMOUNT:=36000}"
: "${PERIOD:=$(date +%Y-%m)}"
: "${POOL_PERCENT:=30}"

jq -r .id >/dev/null 2>&1 || { echo "jq required"; exit 1; }

echo "== create test PaymentMethod 0077 =="
PM_JSON="$(stripe payment_methods create \
  --type card \
  --card[number]=4000000000000077 \
  --card[exp_month]=12 \
  --card[exp_year]=2030 \
  --card[cvc]=123)"
PM_ID="$(printf '%s' "$PM_JSON" | jq -r '.id // empty')"
[[ -n "$PM_ID" ]] || { echo "$PM_JSON"; exit 1; }
echo "pm=$PM_ID"

echo "== create & confirm PaymentIntent =="
PI_JSON="$(stripe payment_intents create \
  --amount "$AMOUNT" \
  --currency usd \
  --payment_method "$PM_ID" \
  --confirm \
  --return_url http://localhost/return)"
PI_STATUS="$(printf '%s' "$PI_JSON" | jq -r '.status // empty')"
echo "pi_status=$PI_STATUS"

echo "== wait for available balance =="
for _ in $(seq 1 90); do
  AVAIL="$(stripe balance retrieve | jq '[.available[]|select(.currency=="usd")|.amount]|add // 0')"
  echo "available_cents=$AVAIL"
  [[ "$AVAIL" -ge "$AMOUNT" ]] && break
  sleep 1
done

echo "== record revenue =="
curl -sS -X POST "$BASE_URL/revenue" \
  -H 'content-type: application/json' \
  -d "{\"period\":\"$PERIOD\",\"amount_cents\":$AMOUNT}" >/dev/null
echo "ok"

echo "== distribute payouts =="
curl -sS -X POST "$BASE_URL/distribute_payouts" \
  -H 'content-type: application/json' \
  -d "{\"period\":\"$PERIOD\",\"pool_percent\":$POOL_PERCENT}"
echo
