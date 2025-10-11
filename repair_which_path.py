#!/usr/bin/env python3
from pathlib import Path
import re, sys

main = Path("mmx-cli/src/main.rs")
if not main.exists():
    print("!! mmx-cli/src/main.rs not found (run from repo root)")
    sys.exit(1)

src = main.read_text()

needle = "fn which_path"
start = src.find(needle)
if start == -1:
    print("!! which_path() not found; nothing to fix")
    sys.exit(0)

# Find the opening brace of the function
obr = src.find("{", start)
if obr == -1:
    print("!! opening brace not found")
    sys.exit(1)

# Walk forward tracking brace depth to find the matching closing brace
depth = 0
end = None
for i in range(obr, len(src)):
    c = src[i]
    if c == "{":
        depth += 1
    elif c == "}":
        depth -= 1
        if depth == 0:
            end = i
            break

if end is None:
    print("!! could not locate end of which_path()")
    sys.exit(1)

new_fn = """fn which_path(bin: &str) -> Option<String> {
    // ENV override (FFMPEG/FFPROBE/GST-LAUNCH-1.0) only if the file exists
    if let Ok(envv) = std::env::var(bin.to_uppercase()) {
        let p = envv.trim();
        if !p.is_empty() && std::path::Path::new(p).is_file() {
            return Some(p.to_string());
        }
    }
    // Search PATH
    let path = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path) {
        if dir.as_os_str().is_empty() { continue; }
        let mut cands = vec![dir.join(bin)];
        #[cfg(windows)]
        {
            for ext in [".exe", ".bat", ".cmd"] {
                cands.push(dir.join(format!("{bin}{ext}")));
            }
        }
        for cand in cands {
            if cand.is_file() {
                return Some(cand.to_string_lossy().to_string());
            }
        }
    }
    None
}
"""

fixed = src[:start] + new_fn + src[end+1:]

# Also remove ONE stray lone '}' line if it exists just after the function
fixed = re.sub(r'(?m)^\s*\}\s*$\n?', '', fixed, count=1)

main.write_text(fixed)
print("[ok] which_path() repaired and any stray closing brace removed")

