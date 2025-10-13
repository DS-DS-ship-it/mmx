cat > mmx_ops_verify.sh <<'BASH'
#!/usr/bin/env bash
set -euo pipefail

# ---------- config ----------
ENV_FILE="${ENV_FILE:-.env}"
OWNER="${OWNER:-DS-DS-ship-it}"
REPO="${REPO:-mmx}"
PORT="${PORT:-3000}"
BASE_URL="${BASE_URL:-http://localhost:${PORT}}"

# ---------- load env ----------
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a

: "${STRIPE_SECRET_KEY="REDACTED""
: "${STRIPE_WEBHOOK_SECRET="REDACTED""
: "${STRIPE_CLIENT_ID="REDACTED""
: "${GITHUB_TOKEN:?missing GITHUB_TOKEN}"
: "${GITHUB_WEBHOOK_SECRET="REDACTED""

# ---------- deps ----------
command -v node >/dev/null
command -v gh >/dev/null
command -v stripe >/dev/null
command -v jq >/dev/null
command -v curl >/dev/null

# ---------- start server ----------
if [ -f server.js ]; then
  pkill -f "node server.js" >/dev/null 2>&1 || true
  NODE_ENV=development PORT="$PORT" BASE_URL="$BASE_URL" \
  STRIPE_SECRET_KEY="REDACTED"" \
  STRIPE_CLIENT_ID="REDACTED"" \
  STRIPE_WEBHOOK_SECRET="REDACTED"" \
  GITHUB_TOKEN="GITHUB_TOKEN_REDACTED" \
  GITHUB_WEBHOOK_SECRET="REDACTED"" \
  nohup node server.js > /tmp/mmx_server.log 2>&1 &
  echo $! > /tmp/mmx_server.pid
fi

# ---------- wait + health ----------
sleep 1
curl -fsS "http://localhost:${PORT}/health" | jq .

# ---------- ensure GH remote exists ----------
git remote -v | grep -q origin || {
  gh repo view "${OWNER}/${REPO}" >/dev/null || gh repo create "${OWNER}/${REPO}" --public -y --source . --remote origin --push
}

# ---------- add/replace GitHub webhook ----------
HOOK_PAYLOAD_URL="${BASE_URL}/github_webhook"
EXISTING="$(gh api "repos/${OWNER}/${REPO}/hooks" --jq '.[] | select(.config.url=="'"${HOOK_PAYLOAD_URL}"'") | .id' || true)"
if [ -n "${EXISTING:-}" ]; then
  HOOK_ID="$EXISTING"
else
  HOOK_ID="$(gh api -X POST "repos/${OWNER}/${REPO}/hooks" \
    -f name=web \
    -f active=true \
    -f events='["push","issues","pull_request","discussion","discussion_comment","issue_comment"]' \
    -f config.url="$HOOK_PAYLOAD_URL" \
    -f config.content_type=application/json \
    -f config.secret="$GITHUB_WEBHOOK_SECRET" \
    --jq .id)"
fi

# ---------- send GitHub ping ----------
gh api -X POST "repos/${OWNER}/${REPO}/hooks/${HOOK_ID}/pings" >/dev/null

# ---------- start Stripe forwarder ----------
pkill -f "stripe listen" >/dev/null 2>&1 || true
nohup stripe listen --forward-to "http://localhost:${PORT}/stripe_webhook" >/tmp/mmx_stripe_listen.log 2>&1 &
echo $! > /tmp/mmx_stripe_listen.pid
sleep 1

# ---------- fire Stripe test event ----------
stripe trigger payment_intent.succeeded >/dev/null

# ---------- print where to click for Connect OAuth ----------
echo "Connect OAuth start URL:"
echo "${BASE_URL}/start_connect?github=$(gh api user -q .login)"

echo "Server logs: tail -f /tmp/mmx_server.log"
echo "Stripe logs: tail -f /tmp/mmx_stripe_listen.log"
BASH

chmod +x mmx_ops_verify.sh
./mmx_ops_verify.sh
