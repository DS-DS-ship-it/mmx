# force_fix_which_path.py
import re
from pathlib import Path

SRC = Path("mmx-cli/src/main.rs")
CODE = SRC.read_text()

FIXED_FN = r'''
fn which_path(bin: &str) -> Option<String> {
    // Env override: FFMPEG/FFPROBE/GST_LAUNCH_1_0 style
    let env_key = bin.to_uppercase().replace('-', "_").replace('.', "_");
    if let Ok(p) = std::env::var(&env_key) {
        let p = p.trim();
        if !p.is_empty() && std::path::Path::new(p).is_file() {
            return Some(p.to_string());
        }
    }

    let path = match std::env::var("PATH") { Ok(x) => x, Err(_) => return None };
    #[cfg(windows)] let sep = ';';
    #[cfg(not(windows))] let sep = ':';

    for dir in path.split(sep) {
        if dir.is_empty() { continue; }
        #[cfg(windows)] {
            for ext in ["", ".exe", ".bat", ".cmd"] {
                let cand = std::path::Path::new(dir).join(format!("{bin}{ext}"));
                if cand.is_file() { return Some(cand.to_string_lossy().to_string()); }
            }
        }
        #[cfg(not(windows))] {
            let cand = std::path::Path::new(dir).join(bin);
            if cand.is_file() { return Some(cand.to_string_lossy().to_string()); }
        }
    }
    None
}
'''.strip()

# Step 1: Replace full which_path() block
def replace_function_block(text, fn_name, new_code):
    fn_pattern = rf'\bfn\s+{re.escape(fn_name)}\s*\([^)]*\)\s*\{{'
    m = re.search(fn_pattern, text)
    if not m:
        raise SystemExit(f"[!] Could not find {fn_name}() in {SRC}")
    start = m.start()
    i = m.end() - 1
    depth = 0
    while i < len(text):
        if text[i] == '{': depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0: break
        i += 1
    end = i + 1
    return text[:start] + new_code + text[end:]

CODE = replace_function_block(CODE, "which_path", FIXED_FN)

# Step 2: Look for next unmatched brace AFTER this block and nuke just one if needed
brace_depth = 0
cleaned = ""
skipped_extra = False
for line in CODE.splitlines(keepends=True):
    brace_depth += line.count("{")
    brace_depth -= line.count("}")
    if not skipped_extra and brace_depth < 0:
        if line.strip() == "}":
            skipped_extra = True
            continue
    cleaned += line

SRC.write_text(cleaned)
print("[ok] which_path() replaced and unmatched trailing '}' removed.")
