#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MMX_BIN="$ROOT/target/release/mmx"
INPUT=""
OUTPUT=""
SS=""
TO=""
MAP="0:v:0,0:a?,0:s?"

usage() {
  echo "Usage: $(basename "$0") --input in.mp4 --output out.mp4 [--ss 0] [--to 2.5] [--map \"0:v:0,0:a?,0:s?\"]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)  INPUT="$2"; shift 2;;
    --output) OUTPUT="$2"; shift 2;;
    --ss)     SS="$2"; shift 2;;
    --to)     TO="$2"; shift 2;;
    --map|--stream-map) MAP="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1;;
  esac
done

[[ -n "$INPUT"  ]] || { echo "!! --input required" >&2; usage; exit 1; }
[[ -n "$OUTPUT" ]] || { echo "!! --output required" >&2; usage; exit 1; }
[[ -f "$INPUT"  ]] || { echo "!! input not found: $INPUT" >&2; exit 1; }

echo "== mmx doctor =="
"$MMX_BIN" doctor || true
echo
echo "== mmx remux =="
cmd=( "$MMX_BIN" remux --input "$INPUT" --output "$OUTPUT" --stream-map "$MAP" )
[[ -n "$SS" ]] && cmd+=( --ss "$SS" )
[[ -n "$TO" ]] && cmd+=( --to "$TO" )
printf '  '; printf '%q ' "${cmd[@]}"; echo
"${cmd[@]}"
