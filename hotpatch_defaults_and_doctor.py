#!/usr/bin/env python3
import re, sys, pathlib

ROOT = pathlib.Path(".").resolve()
backend_rs = ROOT / "mmx-core" / "src" / "backend.rs"
doctor_rs  = ROOT / "mmx-core" / "src" / "doctor.rs"

def patch_backend_defaults(p: pathlib.Path):
    src = p.read_text()
    # Find the `impl Default for RunOptions { fn default() -> Self { Self { ... } } }`
    m = re.search(r"impl\s+Default\s+for\s+RunOptions\s*\{.*?fn\s+default\s*\(\s*\)\s*->\s*Self\s*\{(.*?)\}\s*\}",
                  src, flags=re.S|re.M)
    if not m:
        print(f"[warn] couldn’t locate RunOptions::default in {p}")
        return False
    body = m.group(1)

    # Inside that default, locate the Self { ... } initializer
    m2 = re.search(r"Self\s*\{(?P<init>.*)\}", body, flags=re.S)
    if not m2:
        print(f"[warn] couldn’t locate Self {{ … }} initializer in {p}")
        return False
    init = m2.group("init")

    changed = False
    def ensure_field(text, field_line):
        nonlocal changed
        field = field_line.split(":")[0].strip()
        if re.search(rf"\b{re.escape(field)}\s*:", text) is None:
            # insert just before the closing brace of Self { … }
            text = re.sub(r"\}\s*$",
                          f"    {field_line}\n}}",
                          text, flags=re.S)
            changed = True
        return text

    init2 = init
    init2 = ensure_field(init2, "manifest: None,")
    init2 = ensure_field(init2, "progress_json: false,")

    if changed:
        # Rebuild file text
        new_body = body.replace(init, init2)
        new_src  = src[:m.start(1)] + new_body + src[m.end(1):]
        p.write_text(new_src)
        print(f"[fix ] added missing defaults in {p}")
    else:
        print(f"[ok  ] defaults already included in {p}")
    return True

def patch_doctor_gst_ver(p: pathlib.Path):
    if not p.exists():
        print(f"[warn] {p} not found; skipping doctor patch")
        return False
    src = p.read_text()

    # Replace gst_ver() implementation under #[cfg(feature="gst")]
    pattern = re.compile(
        r"(#\[cfg\(feature\s*=\s*\"gst\"\)\]\s*fn\s+gst_ver\(\)\s*->\s*Option<String>\s*\{\s*)(.*?)(\n\})",
        flags=re.S
    )
    def repl(m):
        pre, _old, post = m.group(1), m.group(2), m.group(3)
        new = (
            "    // Some versions don’t expose is_initialized(); just try init and read version.\n"
            "    let _ = gstreamer::init();\n"
            "    Some(format!(\"{}\", gstreamer::version_string()))\n"
        )
        return pre + new + post

    if pattern.search(src):
        src2 = pattern.sub(repl, src, count=1)
        if src2 != src:
            p.write_text(src2)
            print(f"[fix ] patched gst_ver() in {p}")
        else:
            print(f"[ok  ] gst_ver() already patched in {p}")
    else:
        print(f"[warn] couldn’t find gst_ver() in {p}")
        return False
    return True

if __name__ == "__main__":
    ok1 = patch_backend_defaults(backend_rs)
    ok2 = patch_doctor_gst_ver(doctor_rs)
    if not (ok1 and ok2):
        sys.exit(1)
    print("[done] patches applied. Now rebuild:")
    print("  cargo build")
    print("  cargo build -p mmx-cli -F mmx-core/gst")
