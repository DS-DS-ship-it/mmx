#!/usr/bin/env bash
set -euo pipefail
mkdir -p fixtures
if command -v ffmpeg >/dev/null 2>&1; then
  test -f fixtures/a1.mp4 || ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=128x72:rate=24 -f lavfi -i sine=f=440:duration=3 -shortest -c:v libx264 -t 3 -pix_fmt yuv420p -c:a aac -b:a 96k fixtures/a1.mp4
  test -f fixtures/vonly.mp4 || ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc2=size=160x90:rate=24 -t 2 -c:v libx264 -pix_fmt yuv420p fixtures/vonly.mp4
fi
