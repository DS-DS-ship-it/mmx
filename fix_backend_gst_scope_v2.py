# fix_backend_gst_scope_v2.py
# Usage:
#   python3 fix_backend_gst_scope_v2.py --dir ~/mmx
import re, sys
from pathlib import Path

if "--dir" not in sys.argv:
    print("usage: fix_backend_gst_scope_v2.py --dir <repo_root>")
    raise SystemExit(2)

root = Path(sys.argv[sys.argv.index("--dir")+1]).expanduser().resolve()
gst = root / "mmx-core/src/backend_gst.rs"

src = gst.read_text(encoding="utf-8")

# 1) Drop duplicate standalone import if the grouped one also imports RunOptions
src = re.sub(
    r'(?m)^\s*use\s+crate::backend::RunOptions;\s*\n', 
    '', 
    src
)

# 2) Ensure grouped import includes Backend and QcOptions (keep as-is if already correct)
# (No-op if already there.)

# 3) Normalize variable names used throughout
src = src.replace("run_run_opts.", "opts.").replace("run_opts.", "opts.")

# 4) Make the run() parameter name exactly `opts`
src = re.sub(
    r'(fn\s+run\s*\(\s*&self\s*,\s*)(\w+)(\s*:\s*&\s*RunOptions\s*\))',
    r'\1opts\3',
    src
)

# 5) Ensure build_pipeline_string takes &RunOptions named opts
#    (works whether it had no args or a different arg list)
src = re.sub(
    r'(fn\s+build_pipeline_string\s*)\(\s*[^)]*\)\s*->\s*String',
    r'\1(opts: &RunOptions) -> String',
    src
)
# 6) Pass opts at callsites
src = re.sub(r'build_pipeline_string\s*\(\s*\)', 'build_pipeline_string(opts)', src)

# 7) If you previously set duration_ns to a bare u128, wrap into Some(...)
src = src.replace(
    "duration_ns = dur.nseconds() as u128;",
    "duration_ns = Some(dur.nseconds() as u128);"
)

gst.write_text(src, encoding="utf-8")
print(f"[write] {gst}")

print("\nNext:")
print("  cargo build")
print("  cargo build -p mmx-cli -F mmx-core/gst")
