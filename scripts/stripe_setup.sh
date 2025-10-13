#!/usr/bin/env bash
set -euo pipefail
if ! command -v gh >/dev/null; then echo "Install GitHub CLI: brew install gh"; exit 1; fi
if [[ -z "${1:-}" ]]; then echo "Usage: $0 sk_live_xxx  [true|false enable payouts now?]"; exit 1; fi
KEY="$1"; ENABLE="${2:-false}"
gh secret set STRIPE_SECRET_KEY -b"$KEY"
gh variable set STRIPE_PAYOUTS_ENABLED -b"${ENABLE}"
echo "✅ Set STRIPE_SECRET_KEY (secret) and STRIPE_PAYOUTS_ENABLED=${ENABLE} (variable)."
echo "   NOTE: money ONLY moves when STRIPE_PAYOUTS_ENABLED == 'true'."
