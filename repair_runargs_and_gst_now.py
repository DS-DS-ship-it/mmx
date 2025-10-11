#!/usr/bin/env python3
import argparse, re, shutil
from pathlib import Path

def backup(p: Path):
    if p.exists():
        shutil.copyfile(p, p.with_suffix(p.suffix + ".bak"))

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def write(p: Path, s: str):
    backup(p)
    p.write_text(s, encoding="utf-8")
    print(f"[write] {p}")

def patch_runargs_and_cmd_run(cli: Path):
    src = read(cli)
    changed = False

    # ---- Add fields to RunArgs ----
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
            src = src[:end] + ("\n" if not body.endswith("\n") else "") + insert + src[end:]
            changed = True

    # ---- Wire into cmd_run ----
    m2 = re.search(r'(?s)fn\s+cmd_run\s*\(\s*a:\s*RunArgs\s*\)\s*->\s*anyhow::Result<\(\)>\s*\{(.*?)\n\}', src)
    if m2:
        block = m2.group(1)
        if "opts.manifest = a.manifest;" not in block:
            block = block.replace("opts.execute = a.execute;", "opts.execute = a.execute;\n    opts.manifest = a.manifest;")
            changed = True
        if "opts.progress_json = a.progress_json;" not in block:
            # ensure manifest line exists first; if not, add both
            if "opts.manifest = a.manifest;" in block:
                block = block.replace("opts.manifest = a.manifest;", "opts.manifest = a.manifest;\n    opts.progress_json = a.progress_json;")
            else:
                block = block.replace("opts.execute = a.execute;", "opts.execute = a.execute;\n    opts.manifest = a.manifest;\n    opts.progress_json = a.progress_json;")
            changed = True
        src = src[:m2.start(1)] + block + src[m2.end(1):]

    if changed:
        write(cli, src)
    else:
        print("[ok] CLI RunArgs/cmd_run already have manifest/progress_json")

def patch_backend_gst(core_gst: Path):
    src = read(core_gst)
    orig = src

    # Remove duplicate single-line RunOptions import if another grouped import already includes it.
    lines = []
    seen_single = False
    for ln in src.splitlines():
        if ln.strip() == "use crate::backend::RunOptions;":
            seen_single = True
            # skip it for now; keep only if no grouped import contains RunOptions
            continue
        lines.append(ln)
    src = "\n".join(lines)
    # If we removed it but there is no grouped import with RunOptions, add it back once.
    if seen_single and "use crate::backend::{Backend, RunOptions" not in src and "RunOptions," not in src:
        src = src.replace("use crate::backend::{Backend, QcOptions};", "use crate::backend::{Backend, RunOptions, QcOptions};")

    # Ensure function parameter name is run_opts
    # fn run(&self, NAME: &RunOptions
    def repl_sig(m):
        pre, name, post = m.group(1), m.group(2), m.group(3)
        return f"{pre}run_opts{post}"
    src = re.sub(r'(fn\s+run\s*\(\s*&self\s*,\s*)(\w+)(\s*:\s*&\s*RunOptions)', repl_sig, src)

    # Normalize references to run_opts
    src = src.replace("run_run_opts.", "run_opts.")
    src = src.replace("opts.", "run_opts.")

    # Fix query_duration Ok(...) -> Option<ClockTime>
    src = src.replace(
        'if let Ok((dur, _fmt)) = pipeline.query_duration::<gst::ClockTime>()',
        'if let Some(dur) = pipeline.query_duration::<gst::ClockTime>()'
    )
    # Ensure duration_ns = Some(...)
    src = src.replace(
        'duration_ns = dur.map(|d| d.nseconds() as u128);',
        'duration_ns = Some(dur.nseconds() as u128);'
    )
    src = src.replace(
        'duration_ns = dur.nseconds() as u128;',
        'duration_ns = Some(dur.nseconds() as u128);'
    )

    if src != orig:
        write(core_gst, src)
    else:
        print("[ok] GST backend already normalized")

def patch_backend_defaults(core_backend: Path):
    src = read(core_backend)
    orig = src

    # Remove duplicate default fields if they exist
    src = re.sub(r'\n\s*manifest:\s*None,\s*\n', '\n', src)
    src = re.sub(r'\n\s*progress_json:\s*false,\s*\n', '\n', src)

    # Add defaults after execute: false,
    src = re.sub(
        r'(execute:\s*false,\s*\n)',
        r'\1            manifest: None,\n            progress_json: false,\n',
        src, count=1
    )

    if src != orig:
        write(core_backend, src)
    else:
        print("[ok] RunOptions::default already has manifest/progress_json exactly once")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()
    root = Path(args.dir).expanduser().resolve()
    cli = root / "mmx-cli" / "src" / "main.rs"
    core_backend = root / "mmx-core" / "src" / "backend.rs"
    core_gst = root / "mmx-core" / "src" / "backend_gst.rs"

    if not cli.exists() or not core_backend.exists() or not core_gst.exists():
        print("[err] expected files not found; check --dir path")
        return

    patch_runargs_and_cmd_run(cli)
    patch_backend_defaults(core_backend)
    patch_backend_gst(core_gst)
    print("\nNext:\n  cargo build\n  cargo build -p mmx-cli -F mmx-core/gst")

if __name__ == "__main__":
    main()
