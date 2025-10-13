#!/usr/bin/env bash
set -Eeuo pipefail

: "${BASE_URL:=http://localhost:3000}"
: "${PERIOD:=$(date +%Y-%m)}"
: "${POOL_PERCENT:=30}"
: "${AMOUNT:=120000}"   # cents

JQ="$(command -v jq || true)"

echo "== create & confirm PaymentIntent with 0077 (adds funds to AVAILABLE) =="
PI_JSON="$(stripe payment_intents create \
  -d amount="$AMOUNT" \
  -d currency=usd \
  -d confirm=true \
  -d "automatic_payment_methods[enabled]"=true \
  -d "automatic_payment_methods[allow_redirects]"=never \
  -d "payment_method_data[type]"=card \
  -d "payment_method_data[card][number]"=4000000000000077 \
  -d "payment_method_data[card][exp_month]"=12 \
  -d "payment_method_data[card][exp_year]"=2035 \
  -d "payment_method_data[card][cvc]"=123 \
)"

if [[ -n "$JQ" ]]; then
  PI_ID="$(printf '%s' "$PI_JSON" | jq -r '.id // empty')"
  PI_STATUS="$(printf '%s' "$PI_JSON" | jq -r '.status // empty')"
else
  PI_ID="$(python3 - <<'PY' "$PI_JSON"
import sys,json
j=json.loads(sys.argv[1]);print(j.get("id",""))
PY
)"
  PI_STATUS="$(python3 - <<'PY' "$PI_JSON"
import sys,json
j=json.loads(sys.argv[1]);print(j.get("status",""))
PY
)"
fi

[[ -n "${PI_ID:-}" ]] || { echo "[fail] PaymentIntent creation failed:"; echo "$PI_JSON"; exit 1; }
echo "payment_intent=$PI_ID status=$PI_STATUS"
[[ "$PI_STATUS" == "succeeded" ]] || { echo "[fail] PaymentIntent not succeeded"; echo "$PI_JSON"; exit 1; }

NEEDED=$(( AMOUNT * POOL_PERCENT / 100 ))
echo "need_available_cents=$NEEDED"

echo "== wait for available balance =="
for i in $(seq 1 60); do
  BAL_JSON="$(stripe balance retrieve)"
  if [[ -n "$JQ" ]]; then
    AVAIL="$(printf '%s' "$BAL_JSON" | jq -r '.available[]|select(.currency=="usd")|.amount' | head -n1)"
  else
    AVAIL="$(python3 - <<'PY' "$BAL_JSON"
import sys,json
j=json.loads(sys.argv[1])
print(next((a.get("amount",0) for a in j.get("available",[]) if a.get("currency")=="usd"),0))
PY
)"
  fi
  AVAIL="${AVAIL:-0}"
  echo "available_cents=$AVAIL"
  [[ "$AVAIL" -ge "$NEEDED" ]] && break
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
