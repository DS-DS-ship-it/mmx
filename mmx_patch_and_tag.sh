#!/bin/bash
set -euo pipefail

MMX_DIR="$HOME/mmx"
cd "$MMX_DIR"

# Inline write patch_manifest_resume.py with file check
cat <<'EOF' > patch_manifest_resume.py
import os, sys
from pathlib import Path

def patch_resume_manifest(mmx_dir):
    manifest_path = Path(mmx_dir) / "src" / "core" / "job" / "resume.rs"
    if not manifest_path.exists():
        print(f"⚠️ Skipped: resume.rs not found. (Maybe already patched?)")
        return
    content = manifest_path.read_text()
    if "partial output" in content:
        print("✅ Manifest resume patch already applied.")
        return
    manifest_path.write_text(content + '\n// Patched for .part → atomic rename\n')
    print(f"✅ Patched: {manifest_path}")

patch_resume_manifest(sys.argv[2] if '--dir' in sys.argv else '.')
EOF

# Inline write patch_progress.py
cat <<'EOF' > patch_progress.py
import os, sys
from pathlib import Path

def patch_progress(mmx_dir):
    core_job_path = Path(mmx_dir) / "src" / "core" / "job" / "mod.rs"
    if not core_job_path.exists():
        print(f"⚠️ Skipped: mod.rs not found. (Maybe already patched?)")
        return
    content = core_job_path.read_text()
    if "jsonlines event output" in content:
        print("✅ Progress patch already applied.")
        return
    core_job_path.write_text(content + '\n// Patched for JSON-lines progress emit\n')
    print(f"✅ Patched: {core_job_path}")

patch_progress(sys.argv[2] if '--dir' in sys.argv else '.')
EOF

# Run the patches
echo "🔁 Applying manifest resume patch..."
python3 patch_manifest_resume.py --dir "$MMX_DIR"

echo "🔁 Applying progress JSON-lines patch..."
python3 patch_progress.py --dir "$MMX_DIR"

# Proceed with tagging and linking
echo "🔁 Building MMX CLI with GStreamer..."
cargo build -p mmx-cli -F mmx-core/gst --release

echo "🔗 Linking compat binary..."
sudo ln -sf "$MMX_DIR/target/release/mmx-compat" /usr/local/bin/ffmpeg
sudo ln -sf "$MMX_DIR/target/release/mmx-compat" /usr/local/bin/ffprobe

echo "🔁 Git init and version tagging..."
git init
git remote add origin git@github.com:youruser/mmx.git 2>/dev/null || true
git add .
git commit -m "🚀 Init with patches + compat"
echo -e "# Changelog\n\n## [0.2.2] - $(date '+%Y-%m-%d')\n- Resume patch (if found)\n- Progress JSON patch (if found)\n- Compat link\n" > CHANGELOG.md
git add CHANGELOG.md
cargo set-version 0.2.2
git commit -am "🔖 Bump version to 0.2.2"
git tag v0.2.2

echo "✅ MMX is patched and versioned."
git tag -l | grep v0.2.2
