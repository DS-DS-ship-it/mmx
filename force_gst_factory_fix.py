#!/usr/bin/env python3
# 0BSD — force-enable gst backend factory arm and add --backend to `probe`

import pathlib, sys, re, shutil, subprocess

def edit(path, fn):
    p = pathlib.Path(path)
    s = p.read_text(encoding="utf-8")
    t = fn(s)
    if t != s:
        backup = p.with_suffix(p.suffix + ".pre_fix")
        shutil.copy2(p, backup)
        p.write_text(t, encoding="utf-8")
        print(f"[patched] {p}")
    else:
        print(f"[ok] {p} already good")

root = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
if not root or not (root/"mmx-core"/"src"/"backend.rs").exists():
    print("usage: python3 force_gst_factory_fix.py /path/to/mmx")
    sys.exit(2)

# 1) Ensure mmx-core/src/lib.rs declares backend_gst and shell_escape (if not yet present)
def fix_lib_rs(s: str) -> str:
    if "pub mod shell_escape;" not in s:
        s = s.replace("pub mod qc;", "pub mod qc;\npub mod shell_escape;")
    if "pub mod backend_gst;" not in s:
        s = s.replace("pub mod qc;", "pub mod qc;\n#[cfg(feature=\"gst\")]\npub mod backend_gst;")
        # If qc line already duplicated above, ensure only one insertion:
        s = re.sub(r"(pub mod qc;\n)(?:(?:#\[cfg\(feature=\"gst\"\)\]\n)?pub mod backend_gst;\n)?",
                   r"\1#[cfg(feature=\"gst\")]\npub mod backend_gst;\n", s, count=1)
    return s

# 2) Force the factory to return GstBackend when feature is on
def fix_backend_rs(s: str) -> str:
    # Ensure use line exists
    if "GstBackend" not in s:
        s = s.replace("pub fn find_backend(name: &str) -> Box<dyn Backend + Send> {",
                      "#[cfg(feature=\"gst\")]\nuse crate::backend_gst::GstBackend;\n\npub fn find_backend(name: &str) -> Box<dyn Backend + Send> {")
    # Ensure match arm present
    if '"gst" => Box::new(GstBackend),' not in s:
        s = s.replace("match name {", 'match name {\n        #[cfg(feature="gst")]\n        "gst" => Box::new(GstBackend),')
    return s

# 3) Add --backend to `mmx probe`
def fix_cli_probe(s: str) -> str:
    # Add backend enum to ProbeArgs
    s = s.replace(
        "@derive(Args)] struct ProbeArgs { #[arg(long)] input: String }".replace("@","["),
        "@derive(Args)] struct ProbeArgs { #[arg(long)] input: String, #[arg(long, value_enum, default_value=\"mock\")] backend: BackendKind }".replace("@","[")
    )
    # Route to chosen backend
    s = s.replace(
        "fn cmd_probe(a: ProbeArgs) -> Result<()> {\n    let be = find_backend(\"mock\");",
        "fn cmd_probe(a: ProbeArgs) -> Result<()> {\n    let be = find_backend(a.backend.as_str());"
    )
    return s

edit(root/"mmx-core"/"src"/"lib.rs", fix_lib_rs)
edit(root/"mmx-core"/"src"/"backend.rs", fix_backend_rs)
edit(root/"mmx-cli"/"src"/"main.rs", fix_cli_probe)

# Rebuild normal and gst feature
def sh(cmd):
    print("→", " ".join(cmd))
    r = subprocess.run(cmd, cwd=root, text=True)
    if r.returncode != 0:
        sys.exit(r.returncode)

sh(["cargo","build"])
sh(["cargo","build","-p","mmx-cli","-F","mmx-core/gst"])

print("\n[ok] Factory + probe patched. Try:")
print("  target/debug/mmx probe --backend gst --input in.mp4")
print("  target/debug/mmx run   --backend gst --input in.mp4 --output out.mp4 --cfr --fps 30")
