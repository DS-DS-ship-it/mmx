#!/usr/bin/env bash
set -Eeuo pipefail
fail(){ echo "[fail] $*" >&2; exit 1; }
need(){ command -v "$1" >/dev/null || fail "missing $1"; }
need curl
: "${BASE_URL:?missing BASE_URL}"
echo "[check] health: $BASE_URL/health"
curl -sSf "$BASE_URL/health" | grep -qi ok || fail "server not healthy"
echo "[check] stripe webhook endpoint (may return 400/401 if secret not set)"
curl -sS -X POST -H "Content-Type: application/json" -d '{}' "$BASE_URL/stripe_webhook" || true
OWNER="${OWNER:-DS-DS-ship-it}"
REPO="${REPO:-mmx}"
if command -v gh >/dev/null; then
  echo "[check] github repo API"
  gh api "repos/$OWNER/$REPO" >/dev/null || fail "GitHub repo not reachable: $OWNER/$REPO"
else
  echo "[warn] gh not installed; skipping repo check"
fi
echo "[ok] basic checks passed"
