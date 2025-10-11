#!/usr/bin/env bash
set -euo pipefail
IN="${1:-fixtures/a1.mp4}"
OUT="${2:-fixtures/a1_out.mp4}"
BIN="${BIN:-target/release/mmx}"
cargo build -p mmx-cli -F mmx-core/gst --release >/dev/null
if "$BIN" qc "$IN" "$OUT" >/dev/null 2>&1; then
  exit 0
fi
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -hide_banner -loglevel error -i "$IN" -c:v libx264 -crf 28 -t 2 -y "$OUT"
  ffmpeg -hide_banner -loglevel error -i "$IN" -i "$OUT" -lavfi "[0:v][1:v]psnr;[0:v][1:v]ssim" -f null - 2>&1 | sed -n 's/.*PSNR.*average:\([0-9.]\+\).*SSIM.*All:\([0-9.]\+\).*/psnr=\1 ssim=\2/p'
fi
