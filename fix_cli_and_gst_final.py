# fix_cli_and_gst_final.py
# usage: python3 fix_cli_and_gst_final.py --dir ~/mmx
import sys, re
from pathlib import Path

def read(p):  return Path(p).read_text(encoding="utf-8")
def write(p,s): Path(p).write_text(s, encoding="utf-8")

root = Path(sys.argv[sys.argv.index("--dir")+1]).expanduser().resolve()

# ---------- CLI: mmx-cli/src/main.rs ----------
cli = root / "mmx-cli/src/main.rs"
s = read(cli)

# 1) Ensure PathBuf import
if "use std::path::PathBuf;" not in s:
    # insert after last existing use-line near top
    m = list(re.finditer(r'^\s*use [^\n;]+;\s*$', s, flags=re.M))
    if m:
        idx = m[-1].end()
        s = s[:idx] + "\nuse std::path::PathBuf;\n" + s[idx:]
    else:
        s = "use std::path::PathBuf;\n" + s

# 2) Normalize RunArgs block: add manifest, progress_json if missing; remove graph / graph_json if present
# find RunArgs struct body
m = re.search(r'(#[^\n]*\n)?(pub\s+)?struct\s+RunArgs\s*\{(.*?)\n\}', s, flags=re.S)
if m:
    body = m.group(3)

    # remove any lines defining graph / graph_json
    body = re.sub(r'^\s*graph_json\s*:\s*.*?,\s*\n', '', body, flags=re.M)
    body = re.sub(r'^\s*graph\s*:\s*.*?,\s*\n', '', body, flags=re.M)

    # ensure execute exists (don’t duplicate)
    if not re.search(r'^\s*execute\s*:\s*bool\s*,', body, flags=re.M):
        body += (
            "\n    /// Actually execute (instead of planning)\n"
            "    #[arg(long, default_value_t = false)]\n"
            "    execute: bool,\n"
        )

    # ensure manifest: Option<PathBuf>
    if not re.search(r'^\s*manifest\s*:\s*Option\s*<\s*PathBuf\s*>\s*,', body, flags=re.M):
        body += (
            "\n    /// Write a job manifest to this path (JSON)\n"
            "    #[arg(long = \"manifest\")]\n"
            "    manifest: Option<PathBuf>,\n"
        )
    # remove any stray manifest: Option<String>
    body = re.sub(r'^\s*manifest\s*:\s*Option\s*<\s*String\s*>\s*,\s*\n', '', body, flags=re.M)

    # ensure progress_json: bool
    if not re.search(r'^\s*progress_json\s*:\s*bool\s*,', body, flags=re.M):
        body += (
            "\n    /// Stream progress as JSON lines to stdout\n"
            "    #[arg(long = \"progress-json\", default_value_t = false)]\n"
            "    progress_json: bool,\n"
        )

    # stitch back
    s = s[:m.start(3)] + body + s[m.end(3):]

# 3) cmd_run wiring: remove BackendChoice match; wire manifest/progress_json; remove opts.graph* assigns
# replace: opts.backend = match a.backend { ... };
s = re.sub(r'opts\.backend\s*=\s*match\s*a\.backend\s*\{[^}]+\}\s*;', 'opts.backend = a.backend;', s, flags=re.S)

# ensure manifest & progress_json assignments after opts.execute
if "fn cmd_run(" in s:
    # make sure we have the block text to drop in after opts.execute line
    if "opts.manifest = a.manifest;" not in s:
        s = re.sub(r'(opts\.execute\s*=\s*a\.execute\s*;\s*)', r'\1opts.manifest = a.manifest;\n', s, count=1)
    if "opts.progress_json = a.progress_json;" not in s:
        s = re.sub(r'(opts\.manifest\s*=\s*a\.manifest\s*;\s*)', r'\1opts.progress_json = a.progress_json;\n', s, count=1)

# drop any lingering assigns to not-existing fields
s = re.sub(r'^\s*opts\.graph_json\s*=\s*a\.graph_json\s*;\s*\n', '', s, flags=re.M)
s = re.sub(r'^\s*opts\.graph\s*=\s*a\.graph\s*;\s*\n', '', s, flags=re.M)

write(cli, s)
print(f"[write] {cli}")

# ---------- CORE GST: mmx-core/src/backend_gst.rs ----------
gst = root / "mmx-core/src/backend_gst.rs"
g = read(gst)

# remove duplicate 'use crate::backend::RunOptions;' imports
lines = []
seen_ro = False
for ln in g.splitlines(True):
    if ln.strip().startswith("use crate::backend::RunOptions;"):
        if seen_ro:
            continue
        seen_ro = True
    lines.append(ln)
g = "".join(lines)

# normalize parameter name used across run(&self, <param>: &RunOptions)
m = re.search(r'fn\s+run\s*\(\s*&self\s*,\s*(\w+)\s*:\s*&\s*RunOptions', g)
if m:
    param = m.group(1)
    # unify all common aliases to that param
    for alias in ("opts", "run_opts", "run_run_opts"):
        if alias != param:
            g = re.sub(rf'\b{alias}\.', f'{param}.', g)

# also normalize build_pipeline_string(&RunOptions)
m2 = re.search(r'(fn\s+build_pipeline_string\s*\(\s*(\w+)\s*:\s*&\s*RunOptions\s*\)\s*->\s*String\s*\{)', g)
if m2:
    p2 = m2.group(2)
    # replace aliases to p2 within the function body
    start = m2.end(1)
    depth = 1
    i = start
    while i < len(g) and depth > 0:
        if g[i] == '{': depth += 1
        elif g[i] == '}': depth -= 1
        i += 1
    body = g[start:i-1]
    for alias in ("opts", "run_opts", "run_run_opts"):
        if alias != p2:
            body = re.sub(rf'\b{alias}\.', f'{p2}.', body)
    g = g[:start] + body + g[i-1:]

# fix query_duration type (Result -> Option) and assignment
g = g.replace(
    'if let Ok((dur, _fmt)) = pipeline.query_duration::<gst::ClockTime>()',
    'if let Some(dur) = pipeline.query_duration::<gst::ClockTime>()'
)
g = g.replace(
    'duration_ns = dur.map(|d| d.nseconds() as u128);',
    'duration_ns = Some(dur.nseconds() as u128);'
)

write(gst, g)
print(f"[write] {gst}")

print("\nNext:\n  cargo build\n  cargo build -p mmx-cli -F mmx-core/gst")
