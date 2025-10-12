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
