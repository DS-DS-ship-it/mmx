# Save as: smoke_doctor_remux.sh
#!/usr/bin/env bash
set -euo pipefail

BIN="target/release/mmx"

# 1) Quick help check (nice to see the subs show up)
echo "== mmx --help =="
$BIN --help || true
echo

# 2) Doctor: pretty-print if jq is present
echo "== mmx doctor =="
if command -v jq >/dev/null 2>&1; then
  $BIN doctor | jq .
else
  $BIN doctor
fi
echo

# 3) Ensure a small sample input exists (3s color)
if [[ ! -f in.mp4 ]]; then
  echo "Creating test in.mp4 via ffmpeg…"
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i color=c=red:s=640x360:d=3 \
    -f lavfi -i sine=f=440:b=1:d=3 \
    -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac -movflags +faststart \
    in.mp4
fi

# 4) Remux: copy v/a (and optional subs) with trims
echo "== mmx remux =="
$BIN remux \
  --input in.mp4 \
  --output out_copy.mp4 \
  --ss 0 \
  --to 2.5 \
  --stream-map "0:v:0,0:a:0,0:s?"

echo
echo "Remux done -> out_copy.mp4"
