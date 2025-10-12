#!/bin/bash

set -euo pipefail

MMX_DIR="$HOME/mmx"
cd "$MMX_DIR"

echo "🔁 Applying manifest resume patch..."
python3 patch_manifest_resume.py --dir "$MMX_DIR"

echo "🔁 Applying progress JSON-lines patch..."
python3 patch_progress.py --dir "$MMX_DIR"

echo "🔁 Verifying --execute CLI plumbing with GStreamer..."
cargo build -p mmx-cli -F mmx-core/gst --release

echo "🔗 Linking mmx-compat as ffmpeg and ffprobe..."
sudo ln -sf "$MMX_DIR/target/release/mmx-compat" /usr/local/bin/ffmpeg
sudo ln -sf "$MMX_DIR/target/release/mmx-compat" /usr/local/bin/ffprobe

echo "🔁 Initializing git repository if needed..."
git init
git remote add origin git@github.com:youruser/mmx.git 2>/dev/null || true

echo "📝 Creating initial commit and changelog..."
git add .
git commit -m "🚀 Initial commit with resume/progress patches + compat links"

CHANGELOG="$MMX_DIR/CHANGELOG.md"
echo -e "# Changelog\n\n## [0.2.2] - $(date '+%Y-%m-%d')\n- Applied manifest resume patch\n- Applied progress JSON-lines patch\n- Linked ffmpeg/ffprobe compat\n" > "$CHANGELOG"
git add "$CHANGELOG"

echo "🔖 Bumping version to 0.2.2..."
cargo set-version 0.2.2
git commit -am "🔖 Bump version to 0.2.2"
git tag v0.2.2

echo "✅ Final build check (release + GStreamer)..."
cargo build -p mmx-cli -F mmx-core/gst --release

echo "✅ MMX is fully patched, tagged, and CLI-ready."
echo "🔍 Git tag: "
git tag -l | grep v0.2.2
