#!/usr/bin/env bash
set -euo pipefail

echo "=== MMX Auto Setup: Stripe + GitHub Integration ==="

# 1️⃣ Prompt for credentials
read -p "Enter your STRIPE_CLIENT_ID (starts with ca_): " STRIPE_CLIENT_ID
read -p "Enter your STRIPE_SECRET_KEY (starts with sk_test_ or sk_live_): " STRIPE_SECRET_KEY
read -p "Enter your STRIPE_WEBHOOK_SECRET (starts with whsec_): " STRIPE_WEBHOOK_SECRET
read -p "Enter your GitHub Personal Access Token (starts with ghp_): " GITHUB_TOKEN

# Generate GitHub Webhook Secret
GITHUB_WEBHOOK_SECRET="REDACTED"

# 2️⃣ Confirm Stripe account ID
echo "Fetching Stripe account ID..."
ACCOUNT_ID=$(curl -s -u "$STRIPE_SECRET_KEY": https://api.stripe.com/v1/account | jq -r .id)
echo "Connected account: $ACCOUNT_ID"

# 3️⃣ Create .env file
cat > .env <<EOF
PORT=3000
BASE_URL="http://localhost:3000"

STRIPE_CLIENT_ID="REDACTED""
STRIPE_SECRET_KEY="REDACTED""
STRIPE_WEBHOOK_SECRET="REDACTED""

GITHUB_TOKEN="$GITHUB_TOKEN"
GITHUB_WEBHOOK_SECRET="REDACTED""
EOF

echo "[ok] Saved environment to .env"

# 4️⃣ Create local webhook endpoints (for development)
echo "Creating test webhook endpoint for Stripe..."
curl -s -X POST https://api.stripe.com/v1/webhook_endpoints \
  -u "$STRIPE_SECRET_KEY": \
  -d "url=http://localhost:3000/webhook/stripe" \
  -d "enabled_events[]=checkout.session.completed" \
  -d "enabled_events[]=transfer.paid" \
  >/dev/null && echo "[ok] Stripe webhook created (local test)"

# 5️⃣ Create GitHub webhook
OWNER="DS-DS-ship-it"
REPO="mmx"
curl -s -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/$OWNER/$REPO/hooks \
  -d "{\"name\": \"web\", \"active\": true, \"events\": [\"push\", \"issues\", \"discussion\"], \"config\": {\"url\": \"http://localhost:3000/webhook/github\", \"content_type\": \"json\", \"secret\": \"$GITHUB_WEBHOOK_SECRET\"}}" \
  >/dev/null && echo "[ok] GitHub webhook registered"

# 6️⃣ Launch Node server
echo "Starting server..."
source .env
node server.js
