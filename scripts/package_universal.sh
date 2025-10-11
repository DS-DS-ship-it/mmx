#!/usr/bin/env bash
set -euo pipefail
mkdir -p dist target/universal-apple-darwin/release

arm="target/aarch64-apple-darwin/release/mmx"
x86="target/x86_64-apple-darwin/release/mmx"

if [[ ! -x "$arm" || ! -x "$x86" ]]; then
  echo "missing arm64 or x86_64 mmx binary; build both first" >&2
  exit 1
fi

lipo -create -output target/universal-apple-darwin/release/mmx "$arm" "$x86"
tar -czf dist/mmx-macos-universal.tar.gz -C target/universal-apple-darwin/release mmx
shasum -a 256 dist/mmx-macos-universal.tar.gz | awk '{print $1"  mmx-macos-universal.tar.gz"}' > dist/mmx-macos-universal.tar.gz.sha256
