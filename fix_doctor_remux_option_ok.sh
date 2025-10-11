#!/usr/bin/env bash
set -euo pipefail

MAIN="mmx-cli/src/main.rs"
[[ -f "$MAIN" ]] || { echo "!! $MAIN not found (run from repo root)"; exit 1; }

echo "[1/2] Patching Option::ok() misuse around which_path()…"
perl -0777 -i -pe '
  s/which_path\("ffmpeg"\)\.ok\(\)\.map\(\|p\| p\.to_string_lossy\(\)\.to_string\(\)\)/which_path("ffmpeg")/g;
  s/which_path\("ffprobe"\)\.ok\(\)\.map\(\|p\| p\.to_string_lossy\(\)\.to_string\(\)\)/which_path("ffprobe")/g;
  s/which_path\("gst-launch-1\.0"\)\.ok\(\)\.map\(\|p\| p\.to_string_lossy\(\)\.to_string\(\)\)/which_path("gst-launch-1.0")/g;

  s/\.or_else\(\|\| which_path\("ffmpeg"\)\.ok\(\)\.map\(\|p\| p\.to_string_lossy\(\)\.to_string\(\)\)\)/.or_else(|| which_path("ffmpeg"))/g;
  s/\.or_else\(\|\| which_path\("ffprobe"\)\.ok\(\)\.map\(\|p\| p\.to_string_lossy\(\)\.to_string\(\)\)\)/.or_else(|| which_path("ffprobe"))/g;
' "$MAIN"

echo "[2/2] Building (gst feature)…"
cargo build -p mmx-cli -F mmx-core/gst --release

echo
echo "Try:"
echo "  target/release/mmx doctor"
echo "  target/release/mmx remux --input in.mp4 --output out_copy.mp4 --ss 0 --to 2.5 --stream-map \"0:v:0,0:a:0,0:s?\""
