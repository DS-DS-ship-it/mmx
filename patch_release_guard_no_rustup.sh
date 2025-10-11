#!/usr/bin/env bash
set -euo pipefail
F="scripts/mmx_release.sh"
[[ -f "$F" ]] || { echo "!! $F not found"; exit 1; }

cp -a "$F" "$F.bak.$(date +%s)"

awk '
BEGIN{inblock=0}
# Replace the whole cross-guard block
/# BEGIN cross-guard/ {
  print "# BEGIN cross-guard (auto-inserted)"
  print "    # Allow host build even if rustup is missing; require rustup for cross targets"
  print "    if command -v rustup >/dev/null 2>&1; then"
  print "      if ! rustup target list --installed | awk '\''{print $1}'\'' | grep -qx \"\\$t\"; then"
  print "        host=$(host_triple)"
  print "        if [[ \"\\$t\" != \"\\$host\" ]]; then"
  print "          warn \"target \\$t not installed; skipping (hint: rustup target add \\$t)\""
  print "          continue"
  print "        fi"
  print "      fi"
  print "    else"
  print "      host=$(host_triple)"
  print "      if [[ \"\\$t\" != \"\\$host\" ]]; then"
  print "        warn \"rustup not found; skipping cross target \\$t (install rustup or set CROSS_TARGETS=host)\""
  print "        continue"
  print "      fi"
  print "    fi"
  print ""
  print "    # Apple Silicon -> Intel: require Intel Homebrew pkg-config and set vars"
  print "    if [[ \"$(uname -s)/$(uname -m)\" == \"Darwin/arm64\" && \"\\$t\" == \"x86_64-apple-darwin\" ]]; then"
  print "      if [[ ! -x /usr/local/bin/pkg-config ]]; then"
  print "        warn \"Intel pkg-config (/usr/local/bin/pkg-config) not found; skipping \\$t. Install Intel Homebrew (+ glib/gstreamer).\""
  print "        continue"
  print "      fi"
  print "      export PKG_CONFIG=/usr/local/bin/pkg-config"
  print "      export PKG_CONFIG_PATH=/usr/local/lib/pkgconfig:/usr/local/opt/libffi/lib/pkgconfig"
  print "      export PKG_CONFIG_DIR="
  print "      export PKG_CONFIG_SYSROOT_DIR=/"
  print "    fi"
  print "# END cross-guard"
  inblock=1
  next
}
# Skip the original block contents until its end
inblock == 1 && /# END cross-guard/ { inblock=0; next }
inblock == 1 { next }
{ print }
' "$F" > "$F.new"

mv "$F.new" "$F"
chmod +x "$F"
echo "[ok] Updated guard; host builds proceed without rustup."
