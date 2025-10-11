#!/usr/bin/env bash
set -euo pipefail
BIN="${BIN:-target/release/mmx}"
cargo build -p mmx-cli -F mmx-core/gst --release >/dev/null
"$BIN" --help >/dev/null
"$BIN" doctor || true
"$BIN" probe fixtures/a1.mp4 >/dev/null || true
"$BIN" remux fixtures/a1.mp4 --out tmp_remux.mp4 >/dev/null || true
rm -f tmp_remux.mp4 2>/dev/null || true
