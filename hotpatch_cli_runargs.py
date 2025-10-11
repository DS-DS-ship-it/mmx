#!/usr/bin/env python3
from pathlib import Path
import re, sys

root = Path.cwd()
cli = root / "mmx-cli" / "src" / "main.rs"
src = cli.read_text()

changed = False

# 1) Clean up imports (drop ValueHint and any stray doctor import path)
src2 = re.sub(r"use\s+clap::\{[^}]*\}", lambda m: m.group(0).replace("ValueHint, ", ""), src)
if src2 != src:
    src = src2; changed = True

src2 = re.sub(r"backend::\{([^}]*)doctor::doctor_inspect[^}]*\}", r"backend::{\1}", src)
if src2 != src:
    src = src2; changed = True

# 2) Add fields to RunArgs
def add_field(block: str, field_txt: str) -> str:
    if field_txt.split(":")[0].strip() in block:
        return block
    # insert before closing brace of struct
    return re.sub(r"\n\}\s*$", f"\n{field_txt}\n}}\n", block, flags=re.M)

m = re.search(r"(?s)#\[derive\(\s*Args\s*\)\]\s*struct\s+RunArgs\s*\{.*?\}\s*", src)
if m:
    block = m.group(0)
    orig = block
    # --manifest
    block = add_field(block, '    /// Write a JSON job manifest to this file (Tier-0 resumability)\n    #[arg(long)]\n    manifest: Option<String>,')
    # --progress-json
    block = add_field(block, '    /// Stream progress as JSON lines to stdout (Tier-0 progress)\n    #[arg(long = "progress-json", default_value_t = false)]\n    progress_json: bool,')
    if block != orig:
        src = src[:m.start()] + block + src[m.end():]
        changed = True
else:
    print("[-] Could not locate RunArgs struct; no changes to it.", file=sys.stderr)

# 3) Wire into cmd_run(): opts.manifest / opts.progress_json assignments
def ensure_assign(s, lhs, rhs):
    if re.search(rf"\b{re.escape(lhs)}\s*=\s*{re.escape(rhs)}\s*;", s):
        return s
    # put after opts.execute = a.execute;
    s2 = re.sub(
        r"(opts\.execute\s*=\s*a\.execute\s*;\s*)",
        r"\1" + f"{lhs} = {rhs};\n    ",
        s,
        count=1
    )
    return s2

m = re.search(r"(?s)fn\s+cmd_run\s*\(\s*a:\s*RunArgs\s*\)\s*->\s*anyhow::Result<\(\)\>\s*\{.*?\n\}\s*", src)
if m:
    block = m.group(0)
    orig = block
    block = ensure_assign(block, "opts.manifest", "a.manifest")
    block = ensure_assign(block, "opts.progress_json", "a.progress_json")
    if block != orig:
        src = src[:m.start()] + block + src[m.end():]
        changed = True
else:
    print("[-] Could not locate cmd_run(); no changes to it.", file=sys.stderr)

if changed:
    cli.write_text(src)
    print(f"[ok] patched {cli}")
else:
    print("[ok] no changes needed (already patched)")
