#!/bin/bash
# MMX CLI Wrapper v3 — Fixed Argument Parser

MMX_BIN="$HOME/mmx/target/debug"
FFMPEG_FALLBACK="/opt/homebrew/bin/ffmpeg"

COMMAND="$1"
shift

# 🧠 Validate command
case "$COMMAND" in
  remux|transcode|doctor)
    ;;
  *)
    echo "❌ Invalid command: $COMMAND"
    echo "Usage: mmx {remux|transcode|doctor} [input] [output]"
    exit 1
    ;;
esac

# 🧠 Check binary exists
if [[ ! -x "$MMX_BIN/$COMMAND" ]]; then
  echo "⚠️  MMX binary for '$COMMAND' not found at $MMX_BIN/$COMMAND"
  echo "🛠  Attempting auto-rebuild..."
  (cd "$HOME/mmx" && cargo build --bins >/dev/null 2>&1)

  if [[ -x "$MMX_BIN/$COMMAND" ]]; then
    echo "✅ Binary rebuilt successfully."
  else
    echo "❌ Still missing after rebuild. Using FFmpeg fallback (if available)."
    if command -v "$FFMPEG_FALLBACK" >/dev/null 2>&1; then
      "$FFMPEG_FALLBACK" "$COMMAND" "$@"
      exit $?
    else
      echo "❌ Neither MMX nor FFmpeg available."
      exit 1
    fi
  fi
fi

# ✅ Execute MMX command properly
"$MMX_BIN/$COMMAND" "$@"
