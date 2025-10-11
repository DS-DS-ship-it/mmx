#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path.cwd()

def patch_cli_main_rs():
    p = ROOT / "mmx-cli" / "src" / "main.rs"
    src = p.read_text()

    changed = False

    # --- Ensure RunArgs has manifest and progress_json ---
    m = re.search(r'(?s)#\s*\[\s*derive\s*\(\s*Args\s*\)\s*\]\s*struct\s+RunArgs\s*\{.*?\n\}', src)
    if m:
        block = m.group(0)

        if "manifest:" not in block:
            # add just before closing brace
            block = re.sub(r'\n\}\s*$', '\n    /// Write a JSON job manifest to this file (Tier-0 resumability)\n'
                                        '    #[arg(long)]\n'
                                        '    manifest: Option<String>,\n'
                                        '}\n', block, count=1)
            changed = True

        if "progress_json:" not in block:
            block = re.sub(r'\n\}\s*$', '\n    /// Stream progress as JSON lines to stdout (Tier-0 progress)\n'
                                        '    #[arg(long = "progress-json", default_value_t = false)]\n'
                                        '    progress_json: bool,\n'
                                        '}\n', block, count=1)
            changed = True

        src = src[:m.start()] + block + src[m.end():]

    # --- If doctor_inspect is called, import it from mmx_core::doctor ---
    if "doctor_inspect()" in src and "use mmx_core::doctor::doctor_inspect;" not in src:
        # insert after first use line
        src = re.sub(r'^(use .+\n)', r'\1use mmx_core::doctor::doctor_inspect;\n', src, count=1, flags=re.M)
        changed = True

    # --- Wire opts.manifest / opts.progress_json inside cmd_run(RunArgs) ---
    m = re.search(r'(?s)fn\s+cmd_run\s*\(\s*a:\s*RunArgs\s*\)\s*->\s*anyhow::Result<\(\)>\s*\{.*?\n\}', src)
    if m:
        block = m.group(0)
        # ensure both assignments appear after opts.execute
        if "opts.manifest = a.manifest;" not in block:
            block = block.replace("opts.execute = a.execute;", "opts.execute = a.execute;\n    opts.manifest = a.manifest;")
            changed = True
        if "opts.progress_json = a.progress_json;" not in block:
            # place after manifest assignment
            block = block.replace("opts.manifest = a.manifest;", "opts.manifest = a.manifest;\n    opts.progress_json = a.progress_json;")
            changed = True

        src = src[:m.start()] + block + src[m.end():]

    if changed:
        p.write_text(src)
        print(f"[ok] patched {p}")
    else:
        print(f"[ok] no CLI changes needed ({p})")

def patch_core_backend_gst_rs():
    p = ROOT / "mmx-core" / "src" / "backend_gst.rs"
    src = p.read_text()
    changed = False

    # Remove duplicate import of RunOptions if present (keep the one inside the braces)
    # Example: 
    # use crate::backend::{Backend, RunOptions, QcOptions};
    # use crate::backend::RunOptions;   <- remove this
    lines = src.splitlines()
    keep_lines = []
    for line in lines:
        if line.strip() == "use crate::backend::RunOptions;":
            changed = True
            continue
        keep_lines.append(line)
    src = "\n".join(keep_lines)

    # Make sure function signature uses run_opts as the param name
    sig = re.search(r'(fn\s+run\s*\(\s*&self\s*,\s*)(\w+)(\s*:\s*&\s*RunOptions)', src)
    if sig and sig.group(2) != "run_opts":
        old = sig.group(2)
        src = src[:sig.start(2)] + "run_opts" + src[sig.end(2):]
        # replace whole-word old. occurrences with run_opts.
        src = re.sub(rf'\b{re.escape(old)}\.', 'run_opts.', src)
        changed = True

    # If run_opts symbols are still missing (previously called `opts`), migrate them
    if "run_opts." in src and "opts." in src:
        src = src.replace("opts.", "run_opts.")
        changed = True

    # Query duration: ensure we use Option and wrap duration_ns with Some(...)
    src2 = src.replace(
        'if let Ok((dur, _fmt)) = pipeline.query_duration::<gst::ClockTime>()',
        'if let Some(dur) = pipeline.query_duration::<gst::ClockTime>()'
    )
    if src2 != src:
        src = src2
        changed = True

    src2 = src.replace('duration_ns = dur.nseconds() as u128;', 'duration_ns = Some(dur.nseconds() as u128);')
    if src2 != src:
        src = src2
        changed = True

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
