#!/usr/bin/env bash
set -euo pipefail

: "${BASE_URL:=http://localhost:3000}"
: "${PERIOD:=$(date +%Y-%m)}"
: "${POOL_PERCENT:=30}"
: "${AMOUNT:=120000}"   # cents

jqbin="$(command -v jq || true)"

echo "== create test card (0077 adds funds to AVAILABLE balance) =="
PM_ID="$(stripe payment_methods create \
  -d type=card \
  -d "card[number]"=4000000000000077 \
  -d "card[exp_month]"=12 \
  -d "card[exp_year]"=2035 \
  -d "card[cvc]"=123 \
| { [[ -n "$jqbin" ]] && jq -r .id || python3 - <<'PY'
import sys, json
print(json.load(sys.stdin).get("id",""))
PY
})"
echo "payment_method=$PM_ID"

echo "== seed available balance with PaymentIntent =="
stripe payment_intents create \
  -d amount="$AMOUNT" \
  -d currency=usd \
  -d payment_method="$PM_ID" \
  -d confirm=true >/dev/null
echo "charge ok"

need=$(( AMOUNT * POOL_PERCENT / 100 ))
echo "need_available_cents=$need"

echo "== wait for available balance =="
for i in $(seq 1 30); do
  avail="$(stripe balance retrieve | { [[ -n "$jqbin" ]] && jq -r '.available[]|select(.currency=="usd")|.amount' | head -n1 || python3 - <<'PY'
import sys, json
j=json.load(sys.stdin)
print(next((a.get("amount",0) for a in j.get("available",[]) if a.get("currency")=="usd"),0))
PY
})"
  avail="${avail:-0}"
  echo "available_cents=$avail"
  [[ "$avail" -ge "$need" ]] && break
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
