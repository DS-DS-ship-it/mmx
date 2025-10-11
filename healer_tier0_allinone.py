#!/usr/bin/env python3
import re, subprocess, sys
from pathlib import Path

ROOT = Path(sys.argv[sys.argv.index("--dir")+1]) if "--dir" in sys.argv else Path(".").resolve()
CLI = ROOT/"mmx-cli/src/main.rs"
CORE = ROOT/"mmx-core/src"
BACKEND_RS = CORE/"backend.rs"
GST_RS = CORE/"backend_gst.rs"

def read(p): return p.read_text(encoding="utf-8")
def write(p,s): p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s, encoding="utf-8"); print(f"[write] {p}")

def sh(cmd, cwd=None):
    print("→", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd or ROOT, text=True, capture_output=True)

def ensure_runargs_fields_and_wiring():
    if not CLI.exists(): return
    src = read(CLI)
    changed = False

    # 1) Ensure RunArgs has --manifest and --progress-json
    # Find struct RunArgs { ... }
    m = re.search(r"(?s)struct\s+RunArgs\s*\{([^}]*)\}", src)
    if m:
        body = m.group(1)
        need = []
        if "manifest:" not in body:
            need.append('    /// Job manifest path (Tier-0)\n    #[arg(long="manifest")]\n    manifest: Option<String>,\n')
        if "progress_json:" not in body:
            need.append('    /// Stream progress as JSON lines (Tier-0)\n    #[arg(long="progress-json", default_value_t=false)]\n    progress_json: bool,\n')
        if need:
            new_body = body + ("\n" if not body.endswith("\n") else "") + "".join(need)
            src = src[:m.start(1)] + new_body + src[m.end(1):]
            changed = True

    # 2) Wire into cmd_run()
    # Find cmd_run(a: RunArgs)
    m = re.search(r"(?s)fn\s+cmd_run\s*\(\s*a\s*:\s*RunArgs\s*\)\s*->\s*anyhow::Result<\(\)>\s*\{\s*(.*?)\n\}", src)
    if m:
        block = m.group(1)
        # Ensure we assign manifest/progress_json to opts
        if "opts.manifest =" not in block or "opts.progress_json =" not in block:
            # Locate where existing fields are assigned; tack ours after execute
            block = re.sub(r"(opts\.execute\s*=\s*a\.execute\s*;)",
                           r"\1\n    opts.manifest = a.manifest;\n    opts.progress_json = a.progress_json;",
                           block)
            src = src[:m.start(1)] + block + src[m.end(1):]
            changed = True

    if changed: write(CLI, src)
    else: print("[ok] CLI already has manifest/progress_json & wiring")

def ensure_runoptions_default():
    if not BACKEND_RS.exists(): return
    s = read(BACKEND_RS)
    # Detect impl Default for RunOptions { Self { ... } }
    m = re.search(r"(?s)impl\s+Default\s+for\s+RunOptions\s*\{\s*fn\s+default\(\)\s*->\s*Self\s*\{\s*Self\s*\{(.*?)\}\s*\}\s*\}", s)
    if not m:
        print("[warn] Couldn’t find RunOptions::default initializer; skipping")
        return
    fields = m.group(1)
    # Remove any existing manifest/progress_json lines to avoid duplicates
    fields2 = re.sub(r"\s*manifest\s*:\s*None\s*,", "", fields)
    fields2 = re.sub(r"\s*progress_json\s*:\s*false\s*,", "", fields2)
    # Insert right after execute:
    fields2 = re.sub(r"(execute\s*:\s*false\s*,)",
                     r"\1\n            manifest: None,\n            progress_json: false,",
                     fields2)
    if fields2 != fields:
        s2 = s[:m.start(1)] + fields2 + s[m.end(1):]
        write(BACKEND_RS, s2)
    else:
        print("[ok] RunOptions::default already includes manifest/progress_json")

def normalize_gst_backend():
    if not GST_RS.exists(): return
    s = read(GST_RS)
    changed = False

    # De-duplicate RunOptions import
    s2 = re.sub(r"(?m)^use\s+crate::backend::RunOptions;\n", "", s)
    if s2 != s: changed, s = True, s2

    # Ensure combined import has RunOptions
    if "use crate::backend::{Backend, RunOptions" not in s:
        s = re.sub(r"use\s+crate::backend::\{Backend(,|\s*}\s*;)",
                   r"use crate::backend::{Backend, RunOptions\1",
                   s)
        changed = True

    # Ensure time::OffsetDateTime import
    if "use time::OffsetDateTime;" not in s:
        first_use = s.find("\nuse ")
        if first_use != -1:
            s = s[:first_use+1] + "use time::OffsetDateTime;\n" + s[first_use+1:]
        else:
            s = "use time::OffsetDateTime;\n" + s
        changed = True

    # Parameter must be named run_opts
    s = re.sub(r"fn\s+run\s*\(\s*&self\s*,\s*(\w+)\s*:\s*&\s*RunOptions",
               lambda m: m.group(0).replace(m.group(1), "run_opts"),
               s)
    # Replace stale identifiers
    for bad in ("opts.", "run_run_opts."):
        if bad in s:
            s = s.replace(bad, "run_opts.")
            changed = True

    # query_duration: Option form
    s = s.replace(
        "if let Ok((dur, _fmt)) = pipeline.query_duration::<gst::ClockTime>()",
        "if let Some(dur) = pipeline.query_duration::<gst::ClockTime>()"
    )
    # duration_ns assign Some(...)
    s = s.replace(
        "duration_ns = dur.nseconds() as u128;",
        "duration_ns = Some(dur.nseconds() as u128);"
    )

    if changed: write(GST_RS, s)
    else: print("[ok] GST backend already normalized")

def build_all():
    r = sh(["cargo","build"])
    print(r.stdout, r.stderr)
    if r.returncode != 0:
        # Target the two common CLI errors and rerun once
        out = r.stderr
        need_cli = ("no field `manifest` on type `RunArgs`" in out) or ("no field `progress_json` on type `RunArgs`" in out)
        if need_cli:
            ensure_runargs_fields_and_wiring()
            r = sh(["cargo","build"])
            print(r.stdout, r.stderr)
            if r.returncode != 0: sys.exit(1)
    r2 = sh(["cargo","build","-p","mmx-cli","-F","mmx-core/gst"])
    print(r2.stdout, r2.stderr)
    if r2.returncode != 0: sys.exit(1)

def main():
    ensure_runargs_fields_and_wiring()
    ensure_runoptions_default()
    normalize_gst_backend()
    build_all()
    print("\n[done] Tier-0 fields + gst backend wired. Try:")
    print("  target/debug/mmx run --backend gst --input in.mp4 --output out_exec.mp4 --cfr --fps 30 --execute --manifest job.mmx.json --progress-json")

if __name__ == "__main__":
    main()
