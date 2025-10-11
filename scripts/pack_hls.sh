#!/usr/bin/env bash
set -euo pipefail
IN="${1:-fixtures/a1.mp4}"
OUTDIR="${2:-dist/hls}"
mkdir -p "$OUTDIR"
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -hide_banner -loglevel error -i "$IN" -c:v libx264 -c:a aac -b:a 96k -f hls -hls_time 2 -hls_playlist_type vod "$OUTDIR/index.m3u8"
fi
