#!/bin/bash

# Set the real MMX project path here:
MMX_PROJECT_DIR="$HOME/mmx"
MMX_BIN_DIR="$MMX_PROJECT_DIR/target/debug"
WRAPPER_PATH="/usr/local/bin/mmx"

# Confirm binaries exist
if [ ! -f "$MMX_BIN_DIR/transcode" ] || [ ! -f "$MMX_BIN_DIR/remux" ]; then
  echo "❌ MMX binaries not found. Building them now..."
  cd "$MMX_PROJECT_DIR" || { echo "Project dir not found"; exit 1; }
  cargo build --bins || { echo "❌ Build failed"; exit 1; }
else
  echo "✅ MMX binaries found."
fi

# Write the wrapper
echo "⚙️ Writing MMX shell wrapper to $WRAPPER_PATH"

cat <<EOF | sudo tee "$WRAPPER_PATH" > /dev/null
#!/bin/bash
MMX_BIN="$MMX_BIN_DIR"

case "\$1" in
  transcode)
    shift
    "\$MMX_BIN/transcode" "\$@"
    ;;
  remux)
    shift
    "\$MMX_BIN/remux" "\$@"
    ;;
  doctor)
    shift
    "\$MMX_BIN/doctor" "\$@"
    ;;
  *)
    echo "Usage: mmx {transcode|remux|doctor} [args...]"
    exit 1
    ;;
esac
EOF

# Make it executable
sudo chmod +x "$WRAPPER_PATH"
echo "✅ Installed: mmx now runs from anywhere"

# Optional test
echo "🧪 Try it: mmx remux input.mp4 output.mp4"
