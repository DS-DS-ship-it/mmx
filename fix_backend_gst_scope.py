# save as fix_backend_gst_scope.py, then run:
#   python3 fix_backend_gst_scope.py --dir ~/mmx
import re, sys
from pathlib import Path

root = Path(sys.argv[sys.argv.index("--dir")+1]) if "--dir" in sys.argv else Path(".").resolve()
gst = root/"mmx-core/src/backend_gst.rs"

def read(p): return p.read_text(encoding="utf-8")
def write(p,s): p.write_text(s, encoding="utf-8"); print(f"[write] {p}")

s = read(gst)

# 1) Ensure imports present
if "use crate::backend::RunOptions;" not in s:
    # insert after first "use " line
    s = s.replace("\nuse ", "\nuse crate::backend::RunOptions;\nuse ", 1) if "\nuse " in s else "use crate::backend::RunOptions;\n"+s

if "use time::OffsetDateTime;" not in s and "OffsetDateTime" in s:
    s = s.replace("\nuse ", "\nuse time::OffsetDateTime;\nuse ", 1) if "\nuse " in s else "use time::OffsetDateTime;\n"+s

# 2) Normalize variable name to `opts`
s = s.replace("run_run_opts.", "opts.").replace("run_opts.", "opts.")

# 3) Rename `run` param name to `opts`
s = re.sub(r"(fn\s+run\s*\(\s*&self\s*,\s*)(\w+)(\s*:\s*&\s*RunOptions)",
           r"\1opts\3", s)

# 4) Make build_pipeline_string take &RunOptions and name param `opts`
# a) if it existed with no args: add arg
s = re.sub(r"(fn\s+build_pipeline_string\s*)\(\s*\)\s*->\s*String",
           r"\1(opts: &RunOptions) -> String", s)

# b) if it existed with some other arg name/type: force to (&RunOptions) named opts
s = re.sub(r"(fn\s+build_pipeline_string\s*)\(\s*[^)]*\)\s*->\s*String",
           r"\1(opts: &RunOptions) -> String", s)

# 5) Pass opts from run() into build_pipeline_string()
s = re.sub(r"build_pipeline_string\s*\(\s*\)", "build_pipeline_string(opts)", s)
s = re.sub(r"build_pipeline_string\s*\(\s*run_opts\s*\)", "build_pipeline_string(opts)", s)

# 6) If duration_ns expects Option<u128>, wrap value
s = s.replace("duration_ns = dur.nseconds() as u128;",
              "duration_ns = Some(dur.nseconds() as u128);")

write(gst, s)

print("\nNext:")
print("  cargo build")
print("  cargo build -p mmx-cli -F mmx-core/gst")
