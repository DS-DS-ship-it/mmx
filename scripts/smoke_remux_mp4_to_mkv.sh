#!/usr/bin/env bash
set -euo pipefail
IN="${1:-$HOME/mmx/fixtures/short.mp4}"
OUT="${2:-$HOME/mmx/fixtures/out.mkv}"
echo "🔁 Remux: $IN → $OUT"
"$HOME/mmx/target/release/mmx-remux" "$IN" "$OUT"
echo "🔎 Inspect:"
gst-discoverer-1.0 "$OUT" | sed -n '1,40p' || true
echo "✅ Remux ok."
