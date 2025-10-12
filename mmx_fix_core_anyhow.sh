#!/usr/bin/env bash
set -euo pipefail
cd "${MMX_REPO:-$PWD}"

CTOML="mmx-core/Cargo.toml"
SRC="mmx-core/src/backend.rs"

test -f "$CTOML" || { echo "[fail] $CTOML missing"; exit 1; }
cp -n "$CTOML" "$CTOML.bak_anyhow_fix" || true

awk '
BEGIN{ins=0; saw=0}
^\[dependencies\]\s*$/{saw=1; print; next}
saw==1 && /^anyhow\s*=/ {ins=1}
{print}
END{
  if(saw==0){ print ""; print "[dependencies]"; print "anyhow = \"1\"" }
  else if(ins==0){
    print ""; print "# added by mmx_fix_core_anyhow.sh"
    print "anyhow = \"1\""
  }
}' "$CTOML" > "$CTOML.new"
mv "$CTOML.new" "$CTOML"

if test -f "$SRC"; then
  if ! grep -q 'use anyhow::anyhow;' "$SRC"; then
    awk '
      BEGIN{done=0}
      /^use anyhow::Result;/{ print; print "use anyhow::anyhow;"; done=1; next }
      { print }
      END{ if(done==0){ print "use anyhow::anyhow;" } }
    ' "$SRC" > "$SRC.new"
    mv "$SRC.new" "$SRC"
  fi
fi
