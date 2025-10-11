#!/usr/bin/env python3
import argparse, subprocess, sys, re, shutil
from pathlib import Path

def sh(cmd, cwd):
    print("→", " ".join(cmd))
    p = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    return p.returncode, p.stdout + p.stderr

def backup(path: Path):
    if path.exists():
        shutil.copyfile(path, path.with_suffix(path.suffix + ".bak"))

def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def write(path: Path, data: str):
    backup(path)
    path.write_text(data, encoding="utf-8")
    print(f"[write] {path}")

def ensure_runargs_fields(cli_main: Path) -> bool:
    src = read(cli_main)
    changed = False
    m = re.search(r'(?s)#\s*\[\s*derive\s*\(\s*Args\s*\)\s*\]\s*struct\s+RunArgs\s*\{.*?\n\}', src)
    if not m:
        return False
    block = m.group(0)
    if "manifest:" not in block:
        block = block[:-2] + (
            '    /// Write a JSON job manifest to this file (Tier-0 resumability)\n'
            '    #[arg(long)]\n'
            '    manifest: Option<String>,\n'
            '}\n'
        )
        changed = True
    if "progress_json:" not in block:
        block = block[:-2] + (
            '    /// Stream progress as JSON lines to stdout (Tier-0 progress)\n'
            '    #[arg(long = "progress-json", default_value_t = false)]\n'
            '    progress_json: bool,\n'
            '}\n'
        )
        changed = True
    if changed:
        src = src[:m.start()] + block + src[m.end():]
    # wire into cmd_run
    m2 = re.search(r'(?s)fn\s+cmd_run\s*\(\s*a:\s*RunArgs\s*\)\s*->\s*anyhow::Result<\(\)>\s*\{.*?\n\}', src)
    if m2:
        block2 = m2.group(0)
        if "opts.manifest = a.manifest;" not in block2:
            block2 = block2.replace("opts.execute = a.execute;", "opts.execute = a.execute;\n    opts.manifest = a.manifest;")
            changed = True
        if "opts.progress_json = a.progress_json;" not in block2:
            block2 = block2.replace("opts.manifest = a.manifest;", "opts.manifest = a.manifest;\n    opts.progress_json = a.progress_json;")
            changed = True
        src = src[:m2.start()] + block2 + src[m2.end():]
    if changed:
        write(cli_main, src)
    return changed

def fix_backend_gst(core_gst: Path) -> bool:
    src = read(core_gst)
    orig = src
    # remove duplicate import of RunOptions
    lines = src.splitlines()
    keep = []
    for line in lines:
        if line.strip() == "use crate::backend::RunOptions;":
            continue
        keep.append(line)
    src = "\n".join(keep)
    # ensure signature uses run_opts
    sig = re.search(r'(fn\s+run\s*\(\s*&self\s*,\s*)(\w+)(\s*:\s*&\s*RunOptions)', src)
    if sig and sig.group(2) != "run_opts":
        old = sig.group(2)
        src = src[:sig.start(2)] + "run_opts" + src[sig.end(2):]
        src = re.sub(rf'\b{re.escape(old)}\.', 'run_opts.', src)
    # normalize any leftovers
    src = src.replace('run_run_opts.', 'run_opts.')
    src = src.replace('opts.', 'run_opts.')
    # query_duration/ClockTime→Option
    src = src.replace(
        'if let Ok((dur, _fmt)) = pipeline.query_duration::<gst::ClockTime>()',
        'if let Some(dur) = pipeline.query_duration::<gst::ClockTime>()'
    )
    src = src.replace('duration_ns = dur.map(|d| d.nseconds() as u128);',
                      'duration_ns = Some(dur.nseconds() as u128);')
    src = src.replace('duration_ns = dur.nseconds() as u128;',
                      'duration_ns = Some(dur.nseconds() as u128);')
    # ensure imports we need exist (without duplicates)
    need_imports = []
    if "use time::OffsetDateTime;" not in src:
        need_imports.append("use time::OffsetDateTime;")
    if need_imports:
        # insert after first "use " line
        src = re.sub(r'^(use .+\n)', r'\1' + "\n".join(need_imports) + "\n", src, count=1, flags=re.M)
    if src != orig:
        write(core_gst, src)
        return True
    return False

def fix_backend_defaults(core_backend: Path) -> bool:
    """Make sure RunOptions::default has manifest/progress_json defaults; avoid duplicates."""
    src = read(core_backend)
    orig = src
    # make sure we only have one pair of manifest/progress_json defaults
    src = re.sub(r'\n\s*manifest:\s*None,\s*\n', '\n', src)
    src = re.sub(r'\n\s*progress_json:\s*false,\s*\n', '\n', src)
    # add right after execute default
    src = re.sub(
        r'(execute:\s*false,\s*\n)',
        r'\1            // Tier-0 fields (job manifest + progress JSON)\n'
        r'            manifest: None,\n'
        r'            progress_json: false,\n',
        src, count=1)
    if src != orig:
        write(core_backend, src)
        return True
    return False

def auto_repair(root: Path):
    cli_main = root / "mmx-cli" / "src" / "main.rs"
    core_gst = root / "mmx-core" / "src" / "backend_gst.rs"
    core_backend = root / "mmx-core" / "src" / "backend.rs"

    touched = False
    if cli_main.exists():
        touched |= ensure_runargs_fields(cli_main)
    if core_backend.exists():
        touched |= fix_backend_defaults(core_backend)
    if core_gst.exists():
        touched |= fix_backend_gst(core_gst)

    # Build; if errors match known patterns, retry once after forcing those fixes again
    rc, out = sh(["cargo", "build"], cwd=root)
    if rc != 0:
        if "E0609" in out and "RunArgs" in out and ("manifest" in out or "progress_json" in out):
            ensure_runargs_fields(cli_main)
        if "run_run_opts" in out or "not found in this scope" in out:
            fix_backend_gst(core_gst)
        if "field `manifest` specified more than once" in out or "field `progress_json` specified more than once" in out:
            fix_backend_defaults(core_backend)
        sh(["cargo", "build"], cwd=root)

    # Build GST feature
    rc2, out2 = sh(["cargo", "build", "-p", "mmx-cli", "-F", "mmx-core/gst"], cwd=root)
    if rc2 != 0:
        # reapply GST fixes if signature/name errors
        if "run_run_opts" in out2 or "not found in this scope" in out2:
            fix_backend_gst(core_gst)
            sh(["cargo", "build", "-p", "mmx-cli", "-F", "mmx-core/gst"], cwd=root)

    print("\n[done] If build still fails, check these quick fixes:")
    print("  • If you see E0609 on RunArgs.manifest/progress_json → script will add fields and wire them.")
    print("  • If you see run_run_opts/opts missing → script normalizes to run_opts.")
    print("  • If query_duration shape mismatches → script switches to Option<ClockTime> form.")
    print("  • If duplicate defaults for manifest/progress_json → script dedupes and re-adds once.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="path to your mmx repo")
    args = ap.parse_args()
    root = Path(args.dir).expanduser().resolve()
    auto_repair(root)

if __name__ == "__main__":
    main()
