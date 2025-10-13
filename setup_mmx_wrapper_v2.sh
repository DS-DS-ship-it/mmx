#!/bin/bash
# =====================================================
# 🧩 MMX Smart CLI Wrapper — Self-Healing Edition
# Makes mmx command a full ffmpeg/ffprobe replacement
# =====================================================

MMX_DIR="$HOME/mmx"
MMX_BIN_DIR="$MMX_DIR/target/debug"
WRAPPER_PATH="/usr/local/bin/mmx"

# Ensure project exists
if [ ! -d "$MMX_DIR" ]; then
  echo "❌ MMX source directory not found at $MMX_DIR"
  exit 1
fi

# Check for Rust build tools
if ! command -v cargo >/dev/null 2>&1; then
  echo "❌ Cargo (Rust) is not installed. Run:"
  echo "brew install rustup-init && rustup-init"
  exit 1
fi

# Build missing binaries if not present
echo "🔍 Checking MMX binaries..."
if [ ! -x "$MMX_BIN_DIR/remux" ] || [ ! -x "$MMX_BIN_DIR/transcode" ]; then
  echo "⚙️  Building MMX binaries..."
  cd "$MMX_DIR" || exit 1
  cargo build --bins || { echo "❌ Build failed"; exit 1; }
else
  echo "✅ MMX binaries present."
fi

# Write the smart wrapper
echo "⚙️  Installing smart wrapper to $WRAPPER_PATH..."

sudo tee "$WRAPPER_PATH" > /dev/null <<'EOF'
#!/bin/bash
MMX_BIN="$HOME/mmx/target/debug"
FFMPEG_FALLBACK="/opt/homebrew/bin/ffmpeg"

# ✅ Self-healing binary check
if [[ ! -x "$MMX_BIN/$1" ]]; then
  echo "⚠️  MMX binary for '$1' not found at $MMX_BIN/$1"
  echo "🛠  Attempting auto-rebuild..."
  (cd "$HOME/mmx" && cargo build --bins >/dev/null 2>&1)
  if [[ -x "$MMX_BIN/$1" ]]; then
    echo "✅ Binary rebuilt successfully."
  else
    echo "❌ Still missing after rebuild. Using FFmpeg fallback (if available)."
    if command -v "$FFMPEG_FALLBACK" >/dev/null 2>&1; then
      "$FFMPEG_FALLBACK" "$@"
      exit $?
    else
      echo "❌ Neither MMX nor FFmpeg available."
      exit 1
    fi
  fi
fi

# ✅ Execute the command
case "$1" in
  transcode|remux|doctor)
    shift
    "$MMX_BIN/$1" "$@"
    ;;
  *)
    echo "Usage: mmx {transcode|remux|doctor} [args...]"
    exit 1
    ;;
esac
EOF

# Set permissions
sudo chmod +x "$WRAPPER_PATH"

echo "✅ MMX wrapper installed with auto-repair + FFmpeg fallback."
echo "🧪 Try running:"
echo "mmx transcode input.mp4 output.webm"
