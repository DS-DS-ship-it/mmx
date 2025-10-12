#!/usr/bin/env bash
set -euo pipefail
OUT="${1:-$HOME/mmx/fixtures/short.mp4}"
echo "🎬 Creating test fixture: $OUT"
gst-launch-1.0 -q \
  videotestsrc num-buffers=240 ! x264enc tune=zerolatency speed-preset=ultrafast ! h264parse ! mp4mux name=m \
  audiotestsrc num-buffers=210 ! faac ! aacparse ! queue ! m. \
  m. ! filesink location="$OUT"
echo "✅ Fixture ready."
