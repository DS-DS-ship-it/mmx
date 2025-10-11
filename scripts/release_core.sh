#!/usr/bin/env bash
set -euo pipefail
VERSION="${1:-v1.0.0}"
mkdir -p dist
tar -czf dist/mmx-sdk.tar.gz mmx-core mmx-cli
gh release create "$VERSION" dist/mmx-sdk.tar.gz --title "MMX SDK $VERSION" --notes "Open Core release"
