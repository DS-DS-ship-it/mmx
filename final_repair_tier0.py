#!/usr/bin/env python3
"""
final_repair_tier0.py

Repairs Tier-0 wiring in-place:

- CLI (mmx-cli/src/main.rs):
  * Adds RunArgs.manifest (Option<String>) and --progress-json (bool).
  * Wires a.manifest / a.progress_json into RunOptions in cmd_run().
  * Adds `use mmx_core::doctor::doctor_inspect;` if doctor subcommand exists.

- Core GST backend (mmx-core/src/backend_gst.rs):
  * Normalizes `fn run(&self, run_opts: &RunOptions)` param name.
  * Rewrites run_run_opts./opts. -> run_opts.
  * Fixes query_duration to Option<ClockTime> and wraps duration_ns in Some(...).
  * Dedupes RunOptions imports; ensures grouped import contains RunOptions.

- Core RunOptions defaults (mmx-core/src/backend.rs):
  * Ensures manifest: None and progress_json: false appear exactly once.

Prints a clear diff-style summary of what it did.
"""
import argparse, re, shutil, sys
from pathlib import Path

def backup(p: Path):
    if not p.exists():
        return
    b = p.with_suffix(p.suffix + ".bak")
    if not b.exists():
        shutil.copyfile(p, b)

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def write(p: Path, s: str, tag: str):
    backup(p)
    p.write_text(s, encoding="utf-8")
    print(f"[write] {tag}: {p}")

def ensure_runargs_fields_and_wiring(cli_path: Path):
    src = read(cli_path)
    orig = src
    changed = False

    # Add fields to RunArgs
    m = re.search(r'(?s)#\s*\[\s*derive\s*\(\s*Args\s*\)\s*\]\s*struct\s+RunArgs\s*\{(.*?)\n\}', src)
    if m:
        body = m.group(1)
        need_manifest = " manifest:" not in body
        need_progress = " progress_json:" not in body and "progress-json" not in body
        insert = ""
        if need_manifest:
            insert += (
                '    /// Write a JSON job manifest to this file (Tier-0 resumability)\n'
                '    #[arg(long)]\n'
                '    manifest: Option<String>,\n'
            )
        if need_progress:
            insert += (
                '    /// Stream progress as JSON lines to stdout (Tier-0 progress)\n'
                '    #[arg(long = "progress-json", default_value_t = false)]\n'
                '    progress_json: bool,\n'
            )
        if insert:
            start, end = m.span(1)
            # Ensure a trailing newline before our insert
            seg = m.group(1)
            if not seg.endswith("\n"):
                seg = seg + "\n"
            seg = seg + insert
            src = src[:start] + seg + src[end:]
            changed = True
            print("[fix] CLI: added RunArgs.manifest/progress_json")
    else:
        print("[skip] CLI: RunArgs struct not found (already customized?)")

    # Wire fields in cmd_run()
    m2 = re.search(r'(?s)fn\s+cmd_run\s*\(\s*a:\s*RunArgs\s*\)\s*->\s*anyhow::Result<\(\)>\s*\{(.*?)\n\}', src)
    if m2:
        block = m2.group(1)
        need_manifest_set = "opts.manifest = a.manifest;" not in block
        need_progress_set = "opts.progress_json = a.progress_json;" not in block

        if need_manifest_set or need_progress_set:
            # Insert after opts.execute assignment
            if "opts.execute = a.execute;" in block:
                if need_manifest_set:
                    block = block.replace("opts.execute = a.execute;", "opts.execute = a.execute;\n    opts.manifest = a.manifest;")
                if need_progress_set:
                    if "opts.manifest = a.manifest;" in block:
                        block = block.replace("opts.manifest = a.manifest;", "opts.manifest = a.manifest;\n    opts.progress_json = a.progress_json;")
                    else:
                        block = block.replace("opts.execute = a.execute;", "opts.execute = a.execute;\n    opts.manifest = a.manifest;\n    opts.progress_json = a.progress_json;")
                changed = True
                print("[fix] CLI: wired manifest/progress_json into RunOptions")
            else:
                # Fallback: append near other opts.* wires
                inject_after = re.search(r'opts\.[^\n]+;', block)
                if inject_after:
                    idx = inject_after.end()
                    add = ""
                    if need_manifest_set:
                        add += "\n    opts.manifest = a.manifest;"
                    if need_progress_set:
                        add += "\n    opts.progress_json = a.progress_json;"
                    block = block[:idx] + add + block[idx:]
                    changed = True
                    print("[fix] CLI: appended wiring for manifest/progress_json")
        src = src[:m2.start(1)] + block + src[m2.end(1):]
    else:
        print("[skip] CLI: cmd_run() not found")

    # doctor import (non-fatal, only if doctor() subcommand exists)
    if "fn cmd_doctor" in src and "use mmx_core::doctor::doctor_inspect;" not in src:
        # Put import near other use lines
        src = src.replace("use clap", "use mmx_core::doctor::doctor_inspect;\nuse clap", 1)
        changed = True
        print("[fix] CLI: imported doctor_inspect")

    if changed and src != orig:
        write(cli_path, src, "CLI")
    else:
        print("[ok] CLI: manifest/progress_json already present and wired")

def ensure_runoptions_defaults(core_backend_path: Path):
    src = read(core_backend_path)
    orig = src

    # Deduplicate existing defaults then re-add exactly once
    src = re.sub(r'\n\s*manifest:\s*None,\s*\n', '\n', src)
    src = re.sub(r'\n\s*progress_json:\s*false,\s*\n', '\n', src)
    # Add after execute: false,
    src, n = re.subn(
        r'(execute:\s*false,\s*\n)',
        r'\1            manifest: None,\n            progress_json: false,\n',
        src, count=1
    )
    if n == 0 and "manifest:" in src and "progress_json:" in src:
        print("[ok] Core RunOptions defaults already good")
    elif src != orig:
        write(core_backend_path, src, "RunOptions::default")
    else:
        print("[warn] Could not locate RunOptions::default initializer")

def ensure_gst_backend(core_gst_path: Path):
    src = read(core_gst_path)
    orig = src
    changed = False

    # Ensure grouped import has RunOptions, remove extra single import
    # Remove duplicate simple import
    src2 = []
    removed_single = False
    for ln in src.splitlines():
        if ln.strip() == "use crate::backend::RunOptions;":
            removed_single = True
            continue
        src2.append(ln)
    if removed_single:
        src = "\n".join(src2)
        changed = True
        print("[fix] GST: removed duplicate `use crate::backend::RunOptions;`")

    if "use crate::backend::{Backend, RunOptions" not in src and "use crate::backend::{Backend, QcOptions" in src:
        src = src.replace("use crate::backend::{Backend, QcOptions};", "use crate::backend::{Backend, RunOptions, QcOptions};")
        changed = True
        print("[fix] GST: ensured RunOptions is in grouped import")

    # Normalize signature param name to run_opts
    def repl_sig(m):
        pre, name, post = m.group(1), m.group(2), m.group(3)
        if name != "run_opts":
            print(f"[fix] GST: renamed param {name} -> run_opts")
        return f"{pre}run_opts{post}"
    src2, n = re.subn(r'(fn\s+run\s*\(\s*&self\s*,\s*)(\w+)(\s*:\s*&\s*RunOptions)', repl_sig, src)
    if n > 0:
        src = src2
        changed = True

    # Rewrite references to run_opts
    if "run_run_opts." in src:
        src = src.replace("run_run_opts.", "run_opts.")
        changed = True
        print("[fix] GST: replaced run_run_opts.* with run_opts.*")
    # Replace stray opts. -> run_opts. (only if backend_gst.rs)
    if " opts." in src or "opts." in src:
        # Try to only replace instances followed by members we know
        src_new = re.sub(r'\bopts\.(backend|input|output|cfr|fps|execute|manifest|progress_json)\b', r'run_opts.\1', src)
        if src_new != src:
            src = src_new
            changed = True
            print("[fix] GST: replaced opts.field -> run_opts.field")

    # query_duration Ok(...) -> Option<ClockTime>
    if 'if let Ok((dur, _fmt)) = pipeline.query_duration::<gst::ClockTime>()' in src:
        src = src.replace(
            'if let Ok((dur, _fmt)) = pipeline.query_duration::<gst::ClockTime>()',
            'if let Some(dur) = pipeline.query_duration::<gst::ClockTime>()'
        )
        changed = True
        print("[fix] GST: query_duration Ok(..) -> Some(..)")

    # duration_ns assignment must be Some(...)
    src2 = src.replace(
        'duration_ns = dur.map(|d| d.nseconds() as u128);',
        'duration_ns = Some(dur.nseconds() as u128);'
    )
    if src2 != src:
        src = src2
        changed = True
        print("[fix] GST: duration_ns map(...) -> Some(...)")

    src2 = re.sub(r'(?<!Some\()\bduration_ns\s*=\s*dur\.nseconds\(\)\s+as\s+u128\s*;', 'duration_ns = Some(dur.nseconds() as u128);', src)
    if src2 != src:
        src = src2
        changed = True
        print("[fix] GST: wrapped duration_ns value in Some(...)")

    if changed and src != orig:
        write(core_gst_path, src, "GST backend")
    else:
        print("[ok] GST backend already consistent")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()
    root = Path(args.dir).expanduser().resolve()
    cli = root / "mmx-cli" / "src" / "main.rs"
    core_backend = root / "mmx-core" / "src" / "backend.rs"
    core_gst = root / "mmx-core" / "src" / "backend_gst.rs"

    missing = [str(p) for p in [cli, core_backend, core_gst] if not p.exists()]
    if missing:
        print("[err] missing:", ", ".join(missing))
        sys.exit(1)

    ensure_runargs_fields_and_wiring(cli)
    ensure_runoptions_defaults(core_backend)
    ensure_gst_backend(core_gst)

    print("\nNext:\n  cargo build\n  cargo build -p mmx-cli -F mmx-core/gst")

if __name__ == "__main__":
    main()
