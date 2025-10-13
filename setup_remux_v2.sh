#!/bin/bash

set -e

echo "🛠️  Setting up MMX Remux v2..."

PROJECT_DIR="$HOME/mmx"
CORE="$PROJECT_DIR/mmx-core"
CLI="$PROJECT_DIR/mmx-cli"

mkdir -p "$PROJECT_DIR"

if [ ! -d "$CORE" ]; then
  cargo new --lib "$CORE"
fi

if [ ! -d "$CLI" ]; then
  cargo new --bin "$CLI"
fi

# Add dependencies with features
for PKG in "$CORE" "$CLI"; do
  cargo add symphonia --features="mp4,mkv" --manifest-path "$PKG/Cargo.toml"
done

# Register binary in CLI manifest
if ! grep -q 'name = "mmx-remux"' "$CLI/Cargo.toml"; then
cat <<EOF >> "$CLI/Cargo.toml"

[[bin]]
name = "mmx-remux"
path = "src/bin/mmx-remux.rs"
EOF
fi

mkdir -p "$CLI/src/bin"

# Write source file
cat <<EOF > "$CLI/src/bin/mmx-remux.rs"
$(cat "$PWD/mmx-remux.rs")
EOF

echo "✅ Done! Now run: cd $CLI && cargo run --bin mmx-remux -- input.mp4 output.mkv"
