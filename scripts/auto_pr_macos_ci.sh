#!/bin/bash
set -e

BRANCH="roadmap-$(date +%Y%m%d_%H%M%S)"
TITLE="Fix CI for macOS with GStreamer support"
BODY="- Enables mmx-cli to build on macOS 14\n- Adds missing regex dependency\n- Ensures GStreamer-related features build correctly\n- CI passed locally"

# Create branch and push
git checkout -b "$BRANCH"
git add .github/workflows/ci.yml
git commit -m "$TITLE"
git push --set-upstream origin "$BRANCH"

# Create PR
gh pr create --base master --head "$BRANCH" \
  --title "$TITLE" \
  --body "$BODY"
