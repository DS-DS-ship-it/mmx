#!/usr/bin/env bash
set -euo pipefail

# --- CONFIG ---
OWNER="${OWNER:-DS-DS-ship-it}"         # GitHub org or username
REPO="${REPO:-mmx}"                    # Repo name
PAYOUT_PERCENT="${PAYOUT_PERCENT:-30}"  # % of total revenue shared
REVENUE_FILE="${REVENUE_FILE:-revenue/monthly_revenue.csv}"
STRIPE_KEY_FILE="${STRIPE_KEY_FILE:-$HOME/.mmx_stripe_key}"  # store key here
STRIPE_API_KEY="$(cat "$STRIPE_KEY_FILE" 2>/dev/null || true)"

DRY_RUN="${DRY_RUN:-1}"  # 1 = simulate only, 0 = real payouts
mkdir -p revenue logs tmp

# --- STEP 1: Get contributors ---
echo "[1/5] Fetching GitHub contributors..."
CONTRIB_JSON="tmp/contributors.json"
gh api "repos/$OWNER/$REPO/contributors?per_page=100" \
  --jq '[.[] | {login:.login, contributions:(.contributions // 0)}]' \
  > "$CONTRIB_JSON" || echo '[]' > "$CONTRIB_JSON"

if [[ "$(jq 'length' "$CONTRIB_JSON")" -eq 0 ]]; then
  echo "[warn] No contributors found."
  exit 0
fi

# --- STEP 2: Calculate pool ---
if [[ -f "$REVENUE_FILE" ]]; then
  TOTAL_REVENUE=$(awk -F, 'NR>1 {sum+=$2} END {printf("%.2f", sum)}' "$REVENUE_FILE")
else
  TOTAL_REVENUE="0.00"
fi
POOL=$(printf "%.2f" "$(echo "$TOTAL_REVENUE * $PAYOUT_PERCENT / 100" | bc -l)")
TOTAL_WEIGHT="$(jq '[.[].contributions] | add // 0' "$CONTRIB_JSON")"

if [[ "$TOTAL_WEIGHT" == "0" || "$POOL" == "0.00" ]]; then
  echo "[warn] No revenue or zero pool."
  exit 0
fi

# --- STEP 3: Compute payout per contributor ---
PAYOUTS_JSON="tmp/payouts.json"
jq --argjson pool "$POOL" --argjson total "$TOTAL_WEIGHT" '
  [ .[] 
    | .share = ((.contributions / $total) * 100)
    | .amount = ($pool * (.share / 100))
    | {login, contributions, share: (.share|tonumber), amount: (.amount|tonumber)}
  ]
' "$CONTRIB_JSON" > "$PAYOUTS_JSON"

echo "[2/5] Calculated shares:"
jq -r '.[] | "\(.login)\t\(.contributions)\t\(.share|@text "%.2f")%\t$" + (.amount|@text "%.2f")' "$PAYOUTS_JSON" | column -t

# --- STEP 4: Stripe payouts (if DRY_RUN=0) ---
if [[ "$DRY_RUN" != "0" ]]; then
  echo "[dry-run] Skipping real Stripe transfers."
  exit 0
fi

if [[ -z "$STRIPE_API_KEY" ]]; then
  echo "[error] Stripe API key not found. Save it in: $STRIPE_KEY_FILE"
  echo "Example: echo 'STRIPE_SECRET_REDACTED' > $STRIPE_KEY_FILE && chmod 600 $STRIPE_KEY_FILE"
  exit 1
fi

echo "[3/5] Sending payouts via Stripe..."

# Requires mapping GitHub usernames → Stripe account IDs in stripe_accounts.json
if [[ ! -f stripe_accounts.json ]]; then
  echo "{}" > stripe_accounts.json
  echo "[warn] stripe_accounts.json missing. Add mappings like: {\"username\":\"acct_1234\"}"
fi

jq -r '.[] | "\(.login) \(.amount)"' "$PAYOUTS_JSON" | while read -r login amount; do
  account_id=$(jq -r --arg u "$login" '.[$u]' stripe_accounts.json)
  [[ "$account_id" != "null" && -n "$account_id" ]] || { echo "[skip] No Stripe account for $login"; continue; }

  cents=$(printf "%.0f" "$(echo "$amount * 100" | bc -l)")
  echo "[payout] $login → $account_id  ($amount USD)"

  curl -sS -u "$STRIPE_API_KEY:" https://api.stripe.com/v1/transfers \
    -d amount="$cents" \
    -d currency=usd \
    -d destination="$account_id" \
    -d description="MMX Contributor Revenue Share $(date +%Y-%m)" \
    >> logs/payout_$(date +%Y%m%d).log
done

echo "[done] All payouts processed."
