# fix_which_path_brace.py
import pathlib, re

MAIN = pathlib.Path("mmx-cli/src/main.rs")
src = MAIN.read_text()

# ---- 1) Replace the whole which_path() with a canonical, brace-balanced version
def replace_block(text, fn_name, new_body):
    # Find "fn which_path(...){", then scan braces to the end of that fn
    m = re.search(rf'\bfn\s+{re.escape(fn_name)}\s*\([^)]*\)\s*\{{', text)
    if not m:
        # If it doesn't exist, inject new fn after the last `use` line.
        ins_at = 0
        um = list(re.finditer(r'^\s*use\s+.*?;\s*$', text, flags=re.M))
        if um: ins_at = um[-1].end()
        return text[:ins_at] + "\n" + new_body + "\n" + text[ins_at:]
    i = m.end() - 1
    depth = 0
    end = None
    while i < len(text):
        if text[i] == '{': depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    assert end is not None, "Unbalanced braces in which_path()"
    return text[:m.start()] + new_body + text[end:]

WHICH_FN = r'''
fn which_path(bin: &str) -> Option<String> {
    // Env override: FFMPEG/FFPROBE/GST_LAUNCH_1_0 style (normalize bin -> ENV)
    let env_key = bin.to_uppercase().replace('-', "_").replace('.', "_");
    if let Ok(p) = std::env::var(&env_key) {
        let p = p.trim();
        if !p.is_empty() && std::path::Path::new(p).is_file() {
            return Some(p.to_string());
        }
    }

    // PATH search
    let path = match std::env::var("PATH") { Ok(x) => x, Err(_) => return None };
    #[cfg(windows)]
    let sep = ';';
    #[cfg(not(windows))]
    let sep = ':';

    for dir in path.split(sep) {
        if dir.is_empty() { continue; }
        #[cfg(windows)]
        {
            let exts = ["", ".exe", ".bat", ".cmd"];
            for e in exts {
                let cand = std::path::Path::new(dir).join(format!("{bin}{e}"));
                if cand.is_file() {
                    return Some(cand.to_string_lossy().to_string());
                }
            }
        }
        #[cfg(not(windows))]
        {
            let cand = std::path::Path::new(dir).join(bin);
            if cand.is_file() {
                return Some(cand.to_string_lossy().to_string());
            }
        }
    }
    None
}
'''.strip() + "\n"

src = replace_block(src, "which_path", WHICH_FN)

# ---- 2) If there is an immediate stray '}' right after the function, drop it
# Find the new function we just wrote to locate its end precisely.
m2 = re.search(re.escape(WHICH_FN.strip()), src, flags=re.S)
if m2:
    end = m2.end()
    # Consume whitespace/newlines, then remove a lone '}' on its own line.
    tail = src[end:]
    m3 = re.match(r'(\s*\n)*\s*\}\s*(\n|$)', tail)
    if m3:
        # Remove just that one stray brace block
        src = src[:end] + tail[m3.end():]

MAIN.write_text(src)
print("[ok] which_path() replaced and any immediate stray closing brace removed.")
