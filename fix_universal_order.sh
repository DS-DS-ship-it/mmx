#!/usr/bin/env bash
set -euo pipefail

FILE="scripts/mmx_release.sh"
[[ -f "$FILE" ]] || { echo "!! $FILE not found (run in repo root)"; exit 1; }

# Quick no-op if already in correct order
u_line="$(grep -n '^# ---------- universal' "$FILE" | head -n1 | cut -d: -f1 || true)"
d_line="$(grep -n '^# ---------- dispatcher ----------' "$FILE" | head -n1 | cut -d: -f1 || true)"
if [[ -n "${u_line:-}" && -n "${d_line:-}" && "$u_line" -lt "$d_line" ]]; then
  echo "[ok] universal block is already before dispatcher"
  exit 0
fi

bk="$FILE.bak.$(date +%s)"
cp -a "$FILE" "$bk"

tmp_no="$(mktemp)"; tmp_uni="$(mktemp)"; tmp_new="$(mktemp)"
trap 'rm -f "$tmp_no" "$tmp_uni" "$tmp_new"' EXIT

# 1) Extract the full "universal" block (header + function body)
awk -v UOUT="$tmp_uni" -v NOUNI="$tmp_no" '
BEGIN{cap=0; sawstart=0; depth=0}
{
  if(cap){
    print > UOUT
    if($0 ~ /^chunk_universal\(\)\s*{/){ sawstart=1 }
    if(sawstart){
      opens = gsub(/\{/,"{")
      closes= gsub(/\}/,"}")
      depth += opens - closes
      if(depth<=0){ cap=0; next }
    }
    next
  }
  if($0 ~ /^# ---------- universal .*$/){ cap=1; sawstart=0; depth=0; print > UOUT; next }
  print > NOUNI
}' "$FILE"

if [[ ! -s "$tmp_uni" ]]; then
  echo "!! universal block not found in $FILE (aborting)."
  mv "$bk" "$FILE" 2>/dev/null || true
  exit 1
fi

# 2) Insert the universal block just BEFORE the dispatcher block
awk -v UOUT="$tmp_uni" '
BEGIN{ins=0}
{
  if(!ins && $0 ~ /^# ---------- dispatcher ----------/){
    while((getline line < UOUT) > 0) print line
    close(UOUT)
    ins=1
  }
  print
}
END{ if(!ins){ exit 1 } }
' "$tmp_no" > "$tmp_new" || {
  echo "!! could not insert universal block before dispatcher"; exit 1; }

mv "$tmp_new" "$FILE"
echo "[ok] chunk_universal() moved above dispatcher in $FILE (backup: $bk)"
