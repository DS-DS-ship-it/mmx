#!/usr/bin/env bash
set -Eeuo pipefail

: "${BASE_URL:=http://localhost:3000}"
: "${GITHUB_LOGIN:=DS-DS-ship-it}"
JQ="$(command -v jq || true)"

say(){ printf "\n== %s ==\n" "$*"; }

say "Health checks"
curl -sSf "$BASE_URL/health" && echo
curl -sSf "$BASE_URL/healthz" && echo

say "Contributors (before onboarding)"
if [[ -n "$JQ" ]]; then curl -s "$BASE_URL/contributors" | jq .; else curl -s "$BASE_URL/contributors"; fi

say "Stripe Connect onboarding URL (open this in a browser to link a contributor)"
echo "$BASE_URL/start_connect?github=${GITHUB_LOGIN}"
if command -v open >/dev/null 2>&1; then open "$BASE_URL/start_connect?github=${GITHUB_LOGIN}" || true; fi

say "Record test revenue for current month"
PERIOD="$(date +%Y-%m)"
curl -sSf -X POST "$BASE_URL/revenue" \
  -H 'Content-Type: application/json' \
  -d "{\"period\":\"$PERIOD\",\"amount_cents\":123456}" | { [[ -n "$JQ" ]] && jq . || cat; }

say "Try a payout distribution (safe if no connected accounts—pool will be 0)"
curl -sS -X POST "$BASE_URL/distribute_payouts" \
  -H 'Content-Type: application/json' \
  -d "{\"period\":\"$PERIOD\",\"pool_percent\":30}" | { [[ -n "$JQ" ]] && jq . || cat; }

say "Contributors (after onboarding if you completed the Stripe flow)"
if [[ -n "$JQ" ]]; then curl -s "$BASE_URL/contributors" | jq .; else curl -s "$BASE_URL/contributors"; fi

say "Webhook endpoints (configure these in Stripe & GitHub)"
echo "Stripe webhook:  $BASE_URL/webhook/stripe"
echo "GitHub webhook:  $BASE_URL/webhook/github"
