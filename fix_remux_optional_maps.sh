#!/usr/bin/env bash
set -euo pipefail

MAIN="mmx-cli/src/main.rs"
[[ -f "$MAIN" ]] || { echo "!! $MAIN not found (run from repo root)"; exit 1; }

echo "[1/3] Keep '?' in -map operands…"
# Remove the code that trims the trailing '?' off a.map entries
perl -0777 -i -pe '
  s/\s*let\s+p\s*=\s*if\s*part\.ends_with\((?:'\''\?'\''|"\?")\)\s*\{\s*&part\[\s*\.\.\s*part\.len\(\)\s*-\s*1\s*\]\s*\}\s*else\s*\{\s*part\s*\}\s*;\s*//sg
' "$MAIN"

# Use the original part again (with the '?') when pushing -map
perl -0777 -i -pe 's/args\.push\(\s*p\.into\(\)\s*\)/args.push(part.into())/g' "$MAIN"

echo "[2/3] Safer default mapping (audio/subs optional)…"
# Turn default from 0:v:0,0:a:0,0:s? -> 0:v:0,0:a?,0:s?
perl -0777 -i -pe '
  s/(stream_map[^"\n]*default_value\s*=\s*")0:v:0,0:a:0,0:s\?(")/$10:v:0,0:a?,0:s?$2/s
' "$MAIN"

echo "[3/3] Rebuild…"
cargo build -p mmx-cli -F mmx-core/gst --release

echo
echo "Try:"
echo '  target/release/mmx remux --input in.mp4 --output out_copy.mp4 --ss 0 --to 2.5'
echo '  # (by default uses -map 0:v:0,0:a?,0:s?)'
