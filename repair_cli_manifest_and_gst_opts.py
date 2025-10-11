# repair_cli_manifest_and_gst_opts.py
# Usage: python3 repair_cli_manifest_and_gst_opts.py --dir ~/mmx

import sys, re
from pathlib import Path

def read(p): return Path(p).read_text(encoding="utf-8")
def write(p, s): Path(p).write_text(s, encoding="utf-8"); print(f"[write] {p}")

def ensure_pathbuf_use(src: str) -> str:
    if "use std::path::PathBuf;" in src:
        return src
    # insert after first std:: use if present, else at top
    m = re.search(r'(^\s*use\s+std::[^\n;]+;\s*)', src, flags=re.M)
    if m:
        return src[:m.end()] + "use std::path::PathBuf;\n" + src[m.end():]
    return "use std::path::PathBuf;\n" + src

def fix_cli_main(path: Path):
    if not path.exists():
        print(f"[skip] missing {path}")
        return
    s = read(path)

    # 1) Make sure RunArgs exists
    if "struct RunArgs" not in s:
        print("[info] RunArgs struct not found; skipping CLI struct patch")
        return

    s = ensure_pathbuf_use(s)

    # 2) In RunArgs: remove any duplicate `manifest` fields; ensure a single one of type Option<PathBuf>
    # locate RunArgs block
    m = re.search(r'(#[^\n]*\n)?(pub\s+)?struct\s+RunArgs\s*\{.*?\n\}', s, flags=re.S)
    if not m:
        print("[warn] Could not locate RunArgs block; skipping CLI struct patch")
    else:
        block = m.group(0)

        # remove all manifest lines first
        block_no_manifest = re.sub(r'(?m)^\s*manifest\s*:\s*Option\s*<[^>]+>\s*,\s*\n', '', block)
        # insert our canonical manifest field near the top (after first line)
        lines = block_no_manifest.splitlines(keepends=True)
        # find insertion index: after opening brace line
        ins_idx = 0
        for i, L in enumerate(lines):
            if '{' in L:
                ins_idx = i + 1
                break
        manifest_field = (
            "    /// Write a job manifest to this path (JSON)\n"
            "    #[arg(long = \"manifest\")]\n"
            "    manifest: Option<PathBuf>,\n"
        )
        # ensure progress_json field exists; if not present, add it as well
        has_progress = re.search(r'\bprogress_json\s*:\s*bool\b', block_no_manifest) is not None
        if not has_progress:
            manifest_field += (
                "    /// Stream progress as JSON lines to stdout\n"
                "    #[arg(long = \"progress-json\", default_value_t = false)]\n"
                "    progress_json: bool,\n"
            )
        lines.insert(ins_idx, manifest_field)
        new_block = "".join(lines)
        s = s.replace(block, new_block)

    # 3) Ensure cmd_run maps both fields (types already compatible)
    # manifest
    if not re.search(r'opts\.manifest\s*=\s*a\.manifest\s*;', s):
        # add assignment next to other opts.* assigns within cmd_run
        s = re.sub(
            r'(opts\.execute\s*=\s*a\.execute\s*;\s*)',
            r'\1    opts.manifest = a.manifest;\n    opts.progress_json = a.progress_json;\n',
            s,
            count=1
        )

    # If progress_json assignment missing, ensure it’s there (idempotent)
    if not re.search(r'opts\.progress_json\s*=\s*a\.progress_json\s*;', s):
        s = s.replace("opts.manifest = a.manifest;", "opts.manifest = a.manifest;\n    opts.progress_json = a.progress_json;")

    write(path, s)

def fix_backend_gst(path: Path):
    if not path.exists():
        print(f"[skip] missing {path}")
        return
    s = read(path)

    # Remove duplicate RunOptions import if present twice
    s = re.sub(r'(?m)^\s*use\s+crate::backend::RunOptions;\s*\n', '', s)

    # Force the run signature to use `opts`
    # capture current param binding name for &RunOptions and normalize to `opts`
    m = re.search(r'fn\s+run\s*\(\s*&self\s*,\s*(\w+)\s*:\s*&\s*RunOptions\s*\)', s)
    if m:
        name = m.group(1)
        if name != "opts":
            s = s[:m.start(1)] + "opts" + s[m.end(1):]
            # replace occurrences of old name followed by dot (to avoid touching other words)
            s = re.sub(rf'\b{name}\.', 'opts.', s)
    else:
        # If no match, try to add the param if it’s missing entirely (rare)
        s = re.sub(
            r'(fn\s+run\s*\(\s*&self\s*)\)',
            r'\1, opts: &RunOptions)',
            s,
            count=1
        )

    # Convert any stray aliases to opts.
    s = s.replace("run_run_opts.", "opts.").replace("run_opts.", "opts.")

    write(path, s)

def main():
    if "--dir" not in sys.argv:
        print("usage: python3 repair_cli_manifest_and_gst_opts.py --dir <repo_root>")
        sys.exit(2)
    root = Path(sys.argv[sys.argv.index("--dir")+1]).expanduser().resolve()

    fix_cli_main(root / "mmx-cli/src/main.rs")
    fix_backend_gst(root / "mmx-core/src/backend_gst.rs")

    print("\nNext:")
    print("  cargo build")
    print("  cargo build -p mmx-cli -F mmx-core/gst")

if __name__ == "__main__":
    main()
