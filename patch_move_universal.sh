#!/usr/bin/env bash
set -euo pipefail

F="scripts/mmx_release.sh"
[[ -f "$F" ]] || { echo "!! $F not found (run from repo root)"; exit 1; }

# Canonical universal chunk text we want placed BEFORE the dispatcher.
read -r -d '' UNIV <<'UNI'
# ---------- universal (create Universal 2 binary + tarball) ----------
chunk_universal() {
  local arm="target/aarch64-apple-darwin/release/mmx"
  local x86="target/x86_64-apple-darwin/release/mmx"
  if [[ ! -x "$arm" || ! -x "$x86" ]]; then
    warn "missing arm64 or x86_64 binary; build both first (CROSS_TARGETS=\"aarch64-apple-darwin x86_64-apple-darwin\" scripts/mmx_release.sh build)"
    return 0
  fi
  log "Creating Universal 2 binary…"
  mkdir -p target/universal-apple-darwin/release
  lipo -create -output target/universal-apple-darwin/release/mmx "$arm" "$x86"
  file target/universal-apple-darwin/release/mmx | sed -e 's/^/[ mmx ] /'

  # Package
  mkdir -p "$DIST_DIR"
  local name="mmx-macos-universal"
  local pkg_dir="target/pkg/$name"
  rm -rf "$pkg_dir"
  mkdir -p "$pkg_dir"
  cp target/universal-apple-darwin/release/mmx "$pkg_dir/mmx"
  [[ -f README.md ]] && cp README.md "$pkg_dir/README.md"
  [[ -f LICENSE   ]] && cp LICENSE   "$pkg_dir/LICENSE"

  (cd target/pkg && tar -czf "../../$DIST_DIR/${name}.tar.gz" "$name")
  local sum
  if command -v shasum >/dev/null 2>&1; then
    sum="$(shasum -a 256 "$DIST_DIR/${name}.tar.gz" | awk '{print $1}')"
  else
    sum="$(sha256sum      "$DIST_DIR/${name}.tar.gz" | awk '{print $1}')"
  fi
  echo "$sum  ${name}.tar.gz" > "$DIST_DIR/${name}.tar.gz.sha256"
  log "Packed ${name}.tar.gz (sha256: $sum)"
}
UNI

cp -a "$F" "${F}.bak.$(date +%s)"

# Rewrite the file:
#  - Drop any existing universal block (the one we previously appended)
#  - Insert the canonical universal chunk right BEFORE the dispatcher header
awk -v UNIV="$UNIV" '
BEGIN {
  inserted = 0
  deleting = 0
}
# Start deleting at the universal header we previously added
/^# ---------- universal \(create Universal 2 binary \+ tarball\) ----------/ {
  deleting = 1
  next
}
# Stop deleting right before dispatcher header
deleting && /^# ---------- dispatcher ----------/ {
  deleting = 0
  # fall through to insertion below
}
deleting { next }

# When we hit the dispatcher header, insert the universal chunk exactly once
/^# ---------- dispatcher ----------/ && !inserted {
  print UNIV
  print
  inserted = 1
  next
}

# Normal passthrough
{ print }

END {
  if (!inserted) {
    # If the dispatcher marker wasn’t found for some reason, append at end.
    print UNIV
  }
}
' "$F" > "$F.new"

mv "$F.new" "$F"

# Make sure dispatcher has a universal branch; if not, add it.
if ! grep -qE '^[[:space:]]*universal\)[[:space:]]*chunk_universal' "$F"; then
  # macOS vs GNU sed inline
  SED_INPLACE=(-i)
  sed --version >/dev/null 2>&1 || SED_INPLACE=(-i '')
  sed "${SED_INPLACE[@]}" $'s/package) *chunk_package *;;/package)   chunk_package ;;\\\n    universal) chunk_universal ;;/' "$F"
fi

# Ensure "all" includes universal in its sequence
if ! grep -q 'chunk_build; chunk_smoke; chunk_package; chunk_universal; chunk_homebrew' "$F"; then
  SED_INPLACE=(-i)
  sed --version >/dev/null 2>&1 || SED_INPLACE=(-i '')
  sed "${SED_INPLACE[@]}" 's/chunk_build; chunk_smoke; chunk_package; chunk_homebrew/chunk_build; chunk_smoke; chunk_package; chunk_universal; chunk_homebrew/' "$F"
fi

echo "[ok] chunk_universal placed before dispatcher and wired in."
