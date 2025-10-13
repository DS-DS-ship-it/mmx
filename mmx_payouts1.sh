#!/usr/bin/env bash
set -euo pipefail

# Config (override via env)
OWNER="${OWNER:-DS-DS-ship-it}"
REPO="${REPO:-mmx}"
PAYOUT_PERCENT="${PAYOUT_PERCENT:-30}"      # percent of revenue to share
REVENUE_FILE="${REVENUE_FILE:-revenue/monthly_revenue.csv}"  # CSV: date,amount

mkdir -p revenue logs tmp

# 1) Contributors -> JSON array [{login, contributions}]
CONTRIB_JSON="tmp/contributors.json"
gh api "repos/$OWNER/$REPO/contributors?per_page=100" \
  --jq '[.[] | {login:.login, contributions:(.contributions // 0)}]' \
  > "$CONTRIB_JSON"

# 2) Revenue and pool
if [[ -f "$REVENUE_FILE" ]]; then
  TOTAL_REVENUE="$(awk -F, 'NR>1 && $2 ~ /^[0-9.]+$/ {sum+=$2} END {printf("%.2f", (sum+0))}' "$REVENUE_FILE")"
else
  TOTAL_REVENUE="0.00"
fi
POOL="$(printf "%.2f" "$(echo "$TOTAL_REVENUE * $PAYOUT_PERCENT / 100" | bc -l)")"

# 3) Total contribution weight (safe for empty -> 0)
TOTAL_WEIGHT="$(jq '[.[].contributions] | add // 0' "$CONTRIB_JSON")"

# 4) Compute per-user shares (handle TOTAL_WEIGHT==0)
PAYOUTS_JSON="tmp/payouts.json"
jq --argjson pool "$POOL" --argjson total "$TOTAL_WEIGHT" '
  if ($total|tonumber) == 0 then
    []
  else
    [ .[] | .share = ((.contributions / $total) * 1.0)
          | .amount = ($pool * .share)
          | .share = (.share * 100)
          | .amount = (.amount | tonumber)
    ]
  end
' "$CONTRIB_JSON" > "$PAYOUTS_JSON"

# 5) Print table
jq -r '
  if length==0 then
    "No contributors or zero pool."
  else
    (["login","contribs","share_%","amount_usd"] | @tsv),
    ( .[] | [ .login, .contributions, (.share|. * 1 | tostring), (.amount|@text "%0.2f") ] | @tsv )
  end
' "$PAYOUTS_JSON" \
| column -t
