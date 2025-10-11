#!/usr/bin/env bash
set -euo pipefail
F="scripts/mmx_release.sh"
[[ -f "$F" ]] || { echo "!! $F not found (run from repo root)"; exit 1; }

# 1) Append the universal chunk if missing
if ! grep -q 'chunk_universal()' "$F"; then
  cat >> "$F" <<'BASH'

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
BASH
  echo "[ok] appended chunk_universal()"
fi

# 2) Add 'universal)' case branch if missing
if ! grep -q 'universal) *chunk_universal' "$F"; then
  # macOS vs GNU sed inline switch
  SED_INPLACE=(-i)
  sed --version >/dev/null 2>&1 || SED_INPLACE=(-i '')
  sed "${SED_INPLACE[@]}" $'s/package) *chunk_package *;;/package)   chunk_package ;;\\\n    universal) chunk_universal ;;/' "$F"
  echo "[ok] dispatcher: added 'universal' option"
fi

# 3) Include universal in `all`
if ! grep -q 'chunk_package; chunk_universal; chunk_homebrew' "$F"; then
  SED_INPLACE=(-i)
  sed --version >/dev/null 2>&1 || SED_INPLACE=(-i '')
  sed "${SED_INPLACE[@]}" 's/chunk_build; chunk_smoke; chunk_package; chunk_homebrew/chunk_build; chunk_smoke; chunk_package; chunk_universal; chunk_homebrew/' "$F"
  echo "[ok] added universal to `all` sequence"
fi

echo "[done] scripts/mmx_release.sh updated."
