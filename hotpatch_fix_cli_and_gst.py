#!/usr/bin/env python3
from pathlib import Path
import re

root = Path.cwd()

def patch_cli_main_rs():
    p = root / "mmx-cli" / "src" / "main.rs"
    src = p.read_text()

    changed = False

    # 1) Ensure RunArgs has `manifest` and `progress_json`
    m = re.search(r'(?s)#\s*\[derive\(\s*Args\s*\)\]\s*struct\s+RunArgs\s*\{.*?\n\}', src)
    if m:
        block = m.group(0)
        if "manifest:" not in block:
            block = block[:-1] + '\n    /// Write a JSON job manifest to this file (Tier-0 resumability)\n    #[arg(long)]\n    manifest: Option<String>,\n}\n'
            changed = True
        if "progress_json:" not in block:
            block = block[:-2] + '    /// Stream progress as JSON lines to stdout (Tier-0 progress)\n    #[arg(long = "progress-json", default_value_t = false)]\n    progress_json: bool,\n}\n'
            changed = True
        src = src[:m.start()] + block + src[m.end():]

    # 2) Ensure we import doctor_inspect if we reference it
    if "doctor_inspect()" in src and "use mmx_core::doctor::doctor_inspect;" not in src:
        # place after the first `use` line
        src = re.sub(r'^(use .+\n)', r'\1use mmx_core::doctor::doctor_inspect;\n', src, count=1, flags=re.M)
        changed = True

    # 3) Make sure we wire a.manifest / a.progress_json (if the function exists)
    m = re.search(r'(?s)fn\s+cmd_run\s*\(\s*a:\s*RunArgs\s*\)\s*->\s*anyhow::Result<\(\)>\s*\{.*?\n\}', src)
    if m:
        block = m.group(0)
        if "opts.manifest = a.manifest;" not in block:
            block = block.replace("opts.execute = a.execute;", "opts.execute = a.execute;\n    opts.manifest = a.manifest;")
            changed = True
        if "opts.progress_json = a.progress_json;" not in block:
            block = block.replace("opts.manifest = a.manifest;", "opts.manifest = a.manifest;\n    opts.progress_json = a.progress_json;")
            changed = True
        src = src[:m.start()] + block + src[m.end():]

    if changed:
        p.write_text(src)
        print(f"[ok] patched {p}")
    else:
        print(f"[ok] no CLI changes needed ({p})")

def patch_core_backend_gst_rs():
    p = root / "mmx-core" / "src" / "backend_gst.rs"
    src = p.read_text()
    changed = False

    # 1) Ensure imports for RunOptions and OffsetDateTime
    if "use crate::backend::RunOptions;" not in src:
        # insert near other crate imports
        src = re.sub(r'(\nuse\s+crate::backend::\{[^}]*\}\s*;)',
                     r'\1\nuse crate::backend::RunOptions;',
                     src, count=1) or ("use crate::backend::RunOptions;\n" + src)
        changed = True
    if "use time::OffsetDateTime;" not in src:
        src = "use time::OffsetDateTime;\n" + src
        changed = True

    # 2) Ensure the param name is `run_opts` and all references match
    sig = re.search(r'(fn\s+run\s*\(\s*&self\s*,\s*)(\w+)(\s*:\s*&\s*RunOptions)', src)
    if sig and sig.group(2) != "run_opts":
        old_name = sig.group(2)
        src = src[:sig.start(2)] + "run_opts" + src[sig.end(2):]
        # replace whole-word occurrences of old_name. (avoid changing other identifiers)
        src = re.sub(rf'\b{re.escape(old_name)}\.', 'run_opts.', src)
        changed = True

    # 3) Ensure build_pipeline_string is called with run_opts
    src2 = src.replace('build_pipeline_string(opts)', 'build_pipeline_string(run_opts)')
    if src2 != src:
        src = src2; changed = True

    # 4) GStreamer query_duration result handling and Some(...) wrap
    src2 = src.replace(
        'if let Ok((dur, _fmt)) = pipeline.query_duration::<gst::ClockTime>()',
        'if let Some(dur) = pipeline.query_duration::<gst::ClockTime>()'
    )
    if src2 != src:
        src = src2; changed = True
    src2 = src.replace(
        'duration_ns = dur.nseconds() as u128;',
        'duration_ns = Some(dur.nseconds() as u128);'
    )
    if src2 != src:
        src = src2; changed = True

    if changed:
        p.write_text(src)
        print(f"[ok] patched {p}")
    else:
        print(f"[ok] no GST backend changes needed ({p})")

def main():
    patch_cli_main_rs()
    patch_core_backend_gst_rs()
    print("\nNext:\n  cargo build\n  cargo build -p mmx-cli -F mmx-core/gst")

if __name__ == "__main__":
    main()
