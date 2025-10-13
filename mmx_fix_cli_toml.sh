#!/usr/bin/env bash
set -euo pipefail
cd "${MMX_REPO:-$PWD}"

TOML="mmx-cli/Cargo.toml"
test -f "$TOML" || { echo "[fail] $TOML missing"; exit 1; }
cp -n "$TOML" "$TOML.bak_cli_fix" || true

awk '
BEGIN{printed_deps=0; skipping=0}
# When we hit the first [dependencies], replace its contents with a clean block
/^\[dependencies\]\s*$/{
  if(printed_deps==0){
    print "[dependencies]"
    print "anyhow = \"1\""
    print "clap = { version = \"4\", features = [\"derive\"] }"
    print "serde = { version = \"1\", features = [\"derive\"] }"
    print "serde_json = \"1\""
    print "which = \"6\""
    print "regex = \"1\""
    print "mmx-core = { path = \"../mmx-core\", default-features = false, features = [\"gst\"] }"
    printed_deps=1
    skipping=1
    next
  } else {
    # subsequent [dependencies] headers get skipped; wait until next header
    skipping=1
    next
  }
}
# If skipping the body of an overridden [dependencies] block,
# resume printing when the next table header appears.
skipping==1 && /^\[[^]]+\]\s*$/{
  skipping=0
  print $0
  next
}
# If currently skipping, ignore lines
skipping==1 { next }
# Otherwise, print line as-is
{ print $0 }
' "$TOML" > "$TOML.new"

mv "$TOML.new" "$TOML"
