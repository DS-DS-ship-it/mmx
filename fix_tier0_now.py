# save as fix_tier0_now.py and run:  python3 fix_tier0_now.py --dir ~/mmx
import re, sys
from pathlib import Path

root = Path(sys.argv[sys.argv.index("--dir")+1]) if "--dir" in sys.argv else Path(".").resolve()
cli = root/"mmx-cli/src/main.rs"
gst = root/"mmx-core/src/backend_gst.rs"

def read(p): return p.read_text(encoding="utf-8")
def write(p,s): p.write_text(s, encoding="utf-8"); print(f"[write] {p}")

# --- 1) CLI: map manifest String -> PathBuf on assignment
if cli.exists():
    s = read(cli)
    # Ensure we convert: opts.manifest = a.manifest.map(PathBuf::from)
    if "opts.manifest = a.manifest;" in s:
        s = s.replace("opts.manifest = a.manifest;",
                      "opts.manifest = a.manifest.map(std::path::PathBuf::from);")
        write(cli, s)
    else:
        print("[ok] CLI manifest assignment already mapped or not present")

# --- 2) GST backend: use the parameter name that exists in scope
if gst.exists():
    s = read(gst)
    # If the fn param is named `opts`, normalize body references
    # (safer than changing the signature again)
    s2 = s.replace("run_opts.", "opts.")
    # Also normalize any lingering 'run_run_opts.'
    s2 = s2.replace("run_run_opts.", "opts.")
    # Optional: if signature param is not opts, rename it to opts
    s2 = re.sub(r"(fn\s+run\s*\(\s*&self\s*,\s*)(\w+)(\s*:\s*&\s*RunOptions)",
                r"\1opts\3", s2)
    if s2 != s:
        write(gst, s2)
    else:
        print("[ok] GST backend already uses `opts`")

print("\nNext:")
print("  cargo build")
print("  cargo build -p mmx-cli -F mmx-core/gst")
