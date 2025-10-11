#!/usr/bin/env bash
# Robustly insert a cross-compile guard into scripts/mmx_release.sh
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
BEGIN { in_chunk=0; inserted=0 }
{
  line = $0

  # detect start of chunk_build() { … }
  if (line ~ /^[[:space:]]*chunk_build\(\)[[:space:]]*\{[[:space:]]*$/) {
    in_chunk = 1
  }

  # If inside chunk_build and we see the cargo build line for the loop target, inject guard before it
  if (in_chunk && !inserted &&
      line ~ /cargo[[:space:]]+build/ &&
      line ~ /--target/ &&
      (line ~ /\$t/ || line ~ /\$\{t\}/)) {

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

  print line

  # crude end of function (good enough here)
  if (in_chunk && line ~ /^[[:space:]]*\}[[:space:]]*$/) {
    in_chunk = 0
  }
}
END {
  if (!inserted) {
    print "!! Could not locate cargo build line to patch inside chunk_build(). File left unchanged." > "/dev/stderr"
    exit 1
  }
}
' "$FILE" > "${FILE}.new"

mv "${FILE}.new" "$FILE"
echo "[ok] Guard inserted into $FILE"
