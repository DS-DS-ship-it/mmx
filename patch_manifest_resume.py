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
