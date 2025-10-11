#!/usr/bin/env bash
set -euo pipefail
ARCH="$(uname -m)"
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
NAME="mmx-${OS}-${ARCH}.tar.gz"
mkdir -p dist
cargo build -p mmx-cli -F mmx-core/gst --release
tar -C target/release -czf "dist/${NAME}" mmx
shasum -a 256 "dist/${NAME}" | awk '{print $1}' > "dist/${NAME}.sha256"
if [[ "$OS" == "darwin" ]]; then
  bash scripts/mmx_release.sh universal || true
  test -f dist/mmx-macos-universal.tar.gz && shasum -a 256 dist/mmx-macos-universal.tar.gz | awk '{print $1}' > dist/mmx-macos-universal.tar.gz.sha256 || true
fi
ls -lh dist | sed 's/^/dist /'
