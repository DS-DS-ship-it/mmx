#!/usr/bin/env bash
set -Eeuo pipefail

: "${BASE_URL:=http://localhost:3000}"
: "${AMOUNT:=36000}"       # cents to add to available balance
: "${PERIOD:=$(date +%Y-%m)}"
: "${POOL_PERCENT:=30}"

jqbin="$(command -v jq || true)"

echo "== create top-up =="
TOP_JSON="$(stripe topups create -d amount="$AMOUNT" -d currency=usd -d description="MMX seed" -d statement_descriptor="MMXSeed")"

if [[ -n "$jqbin" ]]; then
  TOP_ID="$(printf '%s' "$TOP_JSON" | jq -r '.id // empty')"
else
  TOP_ID="$(python3 - <<'PY' "$TOP_JSON"
import sys, json; j=json.loads(sys.argv[1]); print(j.get("id",""))
PY
)"
fi

[[ -n "${TOP_ID:-}" ]] || { echo "[fail] top-up create failed:"; echo "$TOP_JSON"; exit 1; }
echo "topup_id=$TOP_ID"

echo "== confirm top-up =="
stripe topups confirm "$TOP_ID" >/dev/null

need="$AMOUNT"
echo "need_available_cents=$need"

echo "== wait for available balance =="
for i in $(seq 1 60); do
  BAL_JSON="$(stripe balance retrieve)"
  if [[ -n "$jqbin" ]]; then
    avail="$(printf '%s' "$BAL_JSON" | jq -r '.available[]|select(.currency=="usd")|.amount' | head -n1)"
  else
    avail="$(python3 - <<'PY' "$BAL_JSON"
import sys,json
j=json.loads(sys.argv[1])
print(next((a.get("amount",0) for a in j.get("available",[]) if a.get("currency")=="usd"),0))
PY
)"
  fi
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
