#!/usr/bin/env bash
# Inserts a cross-compile guard into scripts/mmx_release.sh (before cargo build --target "$t")
set -euo pipefail

FILE="scripts/mmx_release.sh"
[[ -f "$FILE" ]] || { echo "!! $FILE not found. Run this from your repo root."; exit 1; }

# Don’t double-insert
if grep -q 'BEGIN cross-guard (auto-inserted)' "$FILE"; then
  echo "[ok] Guard already present — nothing to do."
  exit 0
fi

cp -a "$FILE" "${FILE}.bak.$(date +%s)"

awk '
BEGIN { inserted = 0 }
{
  # Match the cargo build line inside chunk_build
  if (!inserted && $0 ~ /\(cd "[^"]*" && cargo build [^"]*--target "\$t"\)/) {
    print "    # BEGIN cross-guard (auto-inserted)"
    print "    if ! rustup target list --installed | grep -q \"^\\$t$\"; then"
    print "      warn \"target \\$t not installed; skipping (hint: rustup target add \\$t)\""
    print "      continue"
    print "    fi"
    print ""
    print "    # Apple Silicon -> Intel: require Intel Homebrew pkg-config and set vars"
    print "    if [[ \"$(uname -s)/$(uname -m)\" == \"Darwin/arm64\" && \"\\$t\" == \"x86_64-apple-darwin\" ]]; then"
    print "      if [[ ! -x /usr/local/bin/pkg-config ]]; then"
    print "        warn \"Intel pkg-config (/usr/local/bin/pkg-config) not found; skipping \\$t. Install Intel Homebrew + glib/gstreamer.\""
    print "        continue"
    print "      fi"
    print "      export PKG_CONFIG=/usr/local/bin/pkg-config"
    print "      export PKG_CONFIG_PATH=/usr/local/lib/pkgconfig:/usr/local/opt/libffi/lib/pkgconfig"
    print "      export PKG_CONFIG_DIR="
    print "      export PKG_CONFIG_SYSROOT_DIR=/"
    print "    fi"
    print "    # END cross-guard"
    inserted = 1
  }
  print
}
END {
  if (!inserted) {
    print "!! Could not locate cargo build line to patch. File left unchanged." > "/dev/stderr"
    exit 1
  }
}
' "$FILE" > "${FILE}.new"

mv "${FILE}.new" "$FILE"
echo "[ok] Guard inserted into $FILE"
