#!/usr/bin/env bash
set -euo pipefail
ROOT="${ROOT:-$HOME/mmx}"
CLI="$ROOT/mmx-cli"
VER_FILE="$CLI/Cargo.toml"
VER="$(grep -E '^version *= *"' "$VER_FILE" | sed -E 's/.*"([^"]+)".*/\1/')"
DIST="$ROOT/dist"
BIN_NAME="mmx-remux"
PROJ="mmx-cli"

echo "🏗️  Building ${BIN_NAME} v${VER} for macOS arm64 & x86_64…"
rustup target add aarch64-apple-darwin x86_64-apple-darwin >/dev/null 2>&1 || true

cargo build --release -p "${PROJ}" --bin "${BIN_NAME}" --target aarch64-apple-darwin
cargo build --release -p "${PROJ}" --bin "${BIN_NAME}" --target x86_64-apple-darwin

ARM="$ROOT/target/aarch64-apple-darwin/release/${BIN_NAME}"
X86="$ROOT/target/x86_64-apple-darwin/release/${BIN_NAME}"

UNIV="$DIST/${BIN_NAME}-v${VER}-macos-universal2"
mkdir -p "$DIST"
lipo -create -output "$UNIV" "$ARM" "$X86"
chmod +x "$UNIV"

echo "🧪 Verify slices:"
lipo -info "$UNIV"
echo

TARBALL="$DIST/${BIN_NAME}-v${VER}-macos-universal2.tar.gz"
( cd "$DIST" && tar -czf "$(basename "$TARBALL")" "$(basename "$UNIV")" )
SHA="$(shasum -a 256 "$TARBALL" | awk '{print $1}')"

echo "📦 Created:"
echo "  $TARBALL"
echo "🔐 sha256: $SHA"

# Write a mini manifest for release tooling
cat > "$DIST/release_manifest_${VER}.txt" <<EOF
name=${BIN_NAME}
version=${VER}
universal_tar=$(basename "$TARBALL")
sha256=${SHA}
EOF

echo
echo "✅ Packaging complete."
echo "   Next: create a GitHub Release for v${VER}, upload the tarball, and use the sha256 above."
