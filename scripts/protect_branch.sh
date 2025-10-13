#!/usr/bin/env bash
set -euo pipefail
branch="${1:-master}"

if ! command -v gh >/dev/null; then
  echo "Install GitHub CLI: brew install gh"
  exit 1
fi

owner_repo="$(gh repo view --json nameWithOwner -q .nameWithOwner)"
echo "Protecting $branch on $owner_repo (requires gh auth)…"

gh api -X PUT "repos/$owner_repo/branches/$branch/protection" \
  -H "Accept: application/vnd.github+json" \
  -f required_status_checks.strict=true \
  -f required_status_checks.contexts[]="CI" \
  -f enforce_admins=true \
  -f required_pull_request_reviews.dismiss_stale_reviews=true

echo "✅ Protection set."
