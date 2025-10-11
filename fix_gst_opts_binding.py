# save as: fix_gst_opts_binding.py
# usage: python3 fix_gst_opts_binding.py --dir ~/mmx
import sys, re
from pathlib import Path

root = Path(sys.argv[sys.argv.index("--dir")+1]).expanduser().resolve()
p = root / "mmx-core/src/backend_gst.rs"
s = p.read_text(encoding="utf-8")

# Remove duplicate RunOptions import lines if any duplicates were introduced
lines = [ln for ln in s.splitlines(True)]
seen = set()
out = []
for ln in lines:
    if ln.strip().startswith("use crate::backend::RunOptions;"):
        if "RUNOPT_SEEN" in seen:
            continue
        seen.add("RUNOPT_SEEN")
    out.append(ln)
s = "".join(out)

# Detect run() parameter name and normalize all references to it
m = re.search(r'fn\s+run\s*\(\s*&self\s*,\s*(\w+)\s*:\s*&\s*RunOptions', s)
if m:
    param = m.group(1)
    # If code uses a different name (opts or run_opts or run_run_opts), rewrite to the actual param
    for wrong in ("opts", "run_opts", "run_run_opts"):
        if wrong != param:
            s = re.sub(rf'\b{wrong}\.', f'{param}.', s)

# If build_pipeline_string takes &RunOptions, normalize its parameter use inside that function too
m2 = re.search(r'(fn\s+build_pipeline_string\s*\(\s*(\w+)\s*:\s*&\s*RunOptions\s*\)\s*->\s*String\s*\{)', s)
if m2:
    param2 = m2.group(2)
    # Scope-limited replace: within the function body
    start = m2.end(1)
    # naive function body matcher (up to next unmatched closing brace)
    depth = 1
    i = start
    while i < len(s) and depth > 0:
        if s[i] == '{': depth += 1
        elif s[i] == '}': depth -= 1
        i += 1
    body = s[start:i-1]
    for wrong in ("opts", "run_opts", "run_run_opts"):
        if wrong != param2:
            body = re.sub(rf'\b{wrong}\.', f'{param2}.', body)
    s = s[:start] + body + s[i-1:]

p.write_text(s, encoding="utf-8")
print(f"[write] {p}")
