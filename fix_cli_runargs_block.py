# save as: fix_cli_runargs_block.py
# usage: python3 fix_cli_runargs_block.py --dir ~/mmx
import sys, re
from pathlib import Path

root = Path(sys.argv[sys.argv.index("--dir")+1]).expanduser().resolve()
p = root / "mmx-cli/src/main.rs"
src = p.read_text(encoding="utf-8")

# Ensure PathBuf import
if "use std::path::PathBuf;" not in src:
    m = re.search(r'^use [^\n;]+;\s*$', src, flags=re.M)
    if m:
        src = src[:m.end()] + "\nuse std::path::PathBuf;\n" + src[m.end():]
    else:
        src = "use std::path::PathBuf;\n" + src

# Replace the RunArgs struct block with a canonical one
runargs_re = re.compile(r'(#[^\n]*\n)?(pub\s+)?struct\s+RunArgs\s*\{.*?\n\}', re.S)
new_block = (
    "#[derive(Args, Debug)]\n"
    "struct RunArgs {\n"
    "    /// Backend name\n"
    "    #[arg(long)]\n"
    "    backend: String,\n"
    "\n"
    "    /// Input path\n"
    "    #[arg(long)]\n"
    "    input: String,\n"
    "\n"
    "    /// Output path\n"
    "    #[arg(long)]\n"
    "    output: String,\n"
    "\n"
    "    /// Constant framerate\n"
    "    #[arg(long, default_value_t = false)]\n"
    "    cfr: bool,\n"
    "\n"
    "    /// Target fps when --cfr\n"\
    "    #[arg(long)]\n"
    "    fps: Option<u32>,\n"
    "\n"
    "    /// Actually execute (instead of planning)\n"
    "    #[arg(long, default_value_t = false)]\n"
    "    execute: bool,\n"
    "\n"
    "    /// Write a job manifest to this path (JSON)\n"
    "    #[arg(long = \"manifest\")]\n"
    "    manifest: Option<PathBuf>,\n"
    "\n"
    "    /// Stream progress as JSON lines to stdout\n"
    "    #[arg(long = \"progress-json\", default_value_t = false)]\n"
    "    progress_json: bool,\n"
    "}\n"
)

src, n = runargs_re.subn(new_block, src, count=1)

# Ensure RunArgs derives are compatible with clap Subcommand usage
if "enum Command" in src and "Run(RunArgs)" in src:
    # ok; the derive(Args) we set above satisfies FromArgMatches
    pass

# Wire fields in cmd_run
if "fn cmd_run(" in src:
    # add assigns if missing (idempotent)
    assigns = [
        ("opts.manifest = a.manifest;", r'opts\.manifest\s*=\s*a\.manifest\s*;'),
        ("opts.progress_json = a.progress_json;", r'opts\.progress_json\s*=\s*a\.progress_json\s*;'),
    ]
    for text, pattern in assigns:
        if not re.search(pattern, src):
            src = re.sub(r'(opts\.execute\s*=\s*a\.execute\s*;\s*)', r'\1    ' + text + "\n", src, count=1)

p.write_text(src, encoding="utf-8")
print(f"[write] {p}")
