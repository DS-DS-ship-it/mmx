# fix_opts_scope_and_cli_types.py
# Usage: python3 fix_opts_scope_and_cli_types.py --dir ~/mmx
import sys, re
from pathlib import Path

def read(p): return Path(p).read_text(encoding="utf-8")
def write(p,s): Path(p).write_text(s, encoding="utf-8"); print(f"[write] {p}")

def add_pathbuf_use(src):
    if "use std::path::PathBuf;" in src:
        return src
    # put after the other std:: uses (cheap heuristic)
    return re.sub(r'(\nuse\s+std::[^\n]+;\s*)', r'\1use std::path::PathBuf;\n', src, count=1)

def fix_cli_main(rs):
    # Ensure RunArgs has manifest/progress_json and correct typing, and cmd_run maps to PathBuf
    if "struct RunArgs" not in rs:
        return rs  # file layout may differ; bail gracefully

    rs = add_pathbuf_use(rs)

    # Add fields if missing
    def ensure_field(block, field_line_regex, insert_line):
        if re.search(field_line_regex, block):
            return block
        # insert before closing brace of struct
        return re.sub(r'(\n\})', f"{insert_line}\\1", block, count=1)

    def patch_struct(name, patcher):
        pat = rf"(#[^\n]*\n)?(pub\s+)?struct\s+{name}\s*\{{.*?\n\}}"
        m = re.search(pat, rs, flags=re.S)
        if not m: return rs
        block = m.group(0)
        new_block = patcher(block)
        return rs.replace(block, new_block)

    def patch_runargs(block):
        # manifest: Option<PathBuf>
        block = ensure_field(
            block,
            r"\bmanifest\s*:\s*Option\s*<\s*PathBuf\s*>\s*,",
            '\n    /// Write a job manifest to this path (JSON)\n'
            '    #[arg(long = "manifest")]\n'
            '    manifest: Option<PathBuf>,\n'
        )
        # progress_json: bool
        block = ensure_field(
            block,
            r"\bprogress_json\s*:\s*bool\s*,",
            '\n    /// Stream progress as JSON lines to stdout\n'
            '    #[arg(long = "progress-json", default_value_t = False)]\n'
            '    progress_json: bool,\n'
        )
        # clap default_value_t must be lowercase true/false in Rust, fix case if needed
        block = block.replace("default_value_t = False", "default_value_t = false")
        return block

    rs = patch_struct("RunArgs", patch_runargs)

    # Wire cmd_run: assign manifest (PathBuf) and progress_json
    rs = re.sub(
        r"opts\.manifest\s*=\s*a\.manifest\s*;",
        "opts.manifest = a.manifest;",
        rs
    )
    rs = re.sub(
        r"opts\.progress_json\s*=\s*a\.progress_json\s*;",
        "opts.progress_json = a.progress_json;",
        rs
    )
    # If the code still had String, translate to PathBuf::from at assignment
    rs = re.sub(
        r"opts\.manifest\s*=\s*a\.manifest\s*;",
        "opts.manifest = a.manifest;",
        rs
    )
    rs = add_pathbuf_use(rs)
    return rs

def fix_gst_backend(rs):
    # 0) Remove duplicate standalone RunOptions import if present
    rs = re.sub(r'(?m)^\s*use\s+crate::backend::RunOptions;\s*\n', '', rs)

    # 1) Normalize random variants to "opts."
    rs = rs.replace("run_run_opts.", "opts.").replace("run_opts.", "opts.").replace("opts..", "opts.")

    # 2) Ensure run(&self, opts:&RunOptions)
    rs = re.sub(
        r'(fn\s+run\s*\(\s*&self\s*,\s*)(\w+)(\s*:\s*&\s*RunOptions\s*\))',
        r'\1opts\3',
        rs
    )

    # 3) Any helper function/method using `opts.` must accept `opts: &RunOptions`
    #    We scan for fn ... { ... opts. ... } blocks without RunOptions in their param list.
    fn_pat = re.compile(r'(fn\s+([A-Za-z0-9_]+)\s*\((.*?)\)\s*->\s*[^ \{]+\s*\{)|(fn\s+([A-Za-z0-9_]+)\s*\((.*?)\)\s*\{)', re.S)
    # Collect names that need opts
    names_need_opts = set()
    for m in re.finditer(r'fn\s+([A-Za-z0-9_]+)\s*\((.*?)\)\s*\{', rs, flags=re.S):
        name, params = m.group(1), m.group(2)
        # crude body slice
        start = m.end()
        # find matching brace
        depth = 1; i = start
        while i < len(rs) and depth > 0:
            if rs[i] == '{': depth += 1
            elif rs[i] == '}': depth -= 1
            i += 1
        body = rs[start:i-1]
        if "opts." in body and "RunOptions" not in params:
            names_need_opts.add(name)

    # Add &RunOptions to those function signatures
    def add_param_to_sig(src, fname):
        return re.sub(
            rf'(fn\s+{fname}\s*\()\s*([^)]*)\)',
            lambda m: (
                f"{m.group(1)}{m.group(2).strip() + ', ' if m.group(2).strip() else ''}opts: &RunOptions)"
            ),
            src
        )

    for n in names_need_opts:
        rs = add_param_to_sig(rs, n)

    # 4) Pass `opts` at callsites: <name>(...) -> <name>(..., opts) or <name>(self, ...) -> <name>(self, ..., opts)
    for n in names_need_opts:
        # avoid rewriting the fn signature line again
        rs = re.sub(
            rf'(?<!fn\s){n}\s*\((?P<args>[^)]*)\)',
            lambda m: f"{n}({m.group('args').strip() + ', ' if m.group('args').strip() else ''}opts)",
            rs
        )

    # 5) Ensure build_pipeline_string takes opts and is called with it
    rs = re.sub(
        r'(fn\s+build_pipeline_string\s*)\(\s*[^)]*\)\s*->\s*String',
        r'\1(opts: &RunOptions) -> String',
        rs
    )
    rs = re.sub(r'build_pipeline_string\s*\(\s*\)', 'build_pipeline_string(opts)', rs)

    # 6) query_duration returns Option<ClockTime> on 0.22 — convert correctly
    rs = rs.replace(
        "if let Ok((dur, _fmt)) = pipeline.query_duration::<gst::ClockTime>() {",
        "if let Some(dur) = pipeline.query_duration::<gst::ClockTime>() {"
    ).replace(
        "duration_ns = dur.map(|d| d.nseconds() as u128);",
        "duration_ns = Some(dur.nseconds() as u128);"
    )

    # 7) Import OffsetDateTime if file uses it
    if "OffsetDateTime" in rs and "use time::OffsetDateTime;" not in rs:
        rs = rs.replace("use crate::backend::{Backend, RunOptions, QcOptions};",
                        "use crate::backend::{Backend, RunOptions, QcOptions};\nuse time::OffsetDateTime;")

    return rs

def main():
    if "--dir" not in sys.argv:
        print("usage: python3 fix_opts_scope_and_cli_types.py --dir <repo_root>")
        raise SystemExit(2)
    root = Path(sys.argv[sys.argv.index("--dir")+1]).expanduser().resolve()

    cli = root / "mmx-cli/src/main.rs"
    gst = root / "mmx-core/src/backend_gst.rs"

    # Patch CLI
    if cli.exists():
        write(cli, fix_cli_main(read(cli)))
    else:
        print(f"[skip] missing {cli}")

    # Patch GST backend
    if gst.exists():
        write(gst, fix_gst_backend(read(gst)))
    else:
        print(f"[skip] missing {gst}")

    print("\nNext:")
    print("  cargo build")
    print("  cargo build -p mmx-cli -F mmx-core/gst")

if __name__ == "__main__":
    main()
