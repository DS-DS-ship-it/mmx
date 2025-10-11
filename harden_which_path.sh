#!/usr/bin/env bash
set -euo pipefail

MAIN="mmx-cli/src/main.rs"
[[ -f "$MAIN" ]] || { echo "!! $MAIN not found"; exit 1; }

# Replace the entire which_path() with a safer version
perl -0777 -i -pe '
  s{
    fn\s+which_path\s*\(\s*bin:\s*&str\s*\)\s*->\s*Option<String>\s*\{
    .*?
    \}
  }{
fn which_path(bin: &str) -> Option<String> {
    // 1) ENV override (FFMPEG/FFPROBE/GST-LAUNCH-1.0), but only if it exists
    if let Ok(envv) = std::env::var(bin.to_uppercase()) {
        let p = envv.trim();
        if !p.is_empty() && std::path::Path::new(p).is_file() {
            return Some(p.to_string());
        }
    }
    // 2) Search PATH
    let path = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path) {
        if dir.as_os_str().is_empty() { continue; }
        let mut candidates = vec![dir.join(bin)];
        #[cfg(windows)]
        {
            for ext in [".exe", ".bat", ".cmd"] {
                candidates.push(dir.join(format!("{bin}{ext}")));
            }
        }
        for cand in candidates {
            if cand.is_file() {
                return Some(cand.to_string_lossy().to_string());
            }
        }
    }
    None
}
  }gsx
' "$MAIN"

echo "[ok] which_path() hardened"
echo "Building…"
cargo build -p mmx-cli -F mmx-core/gst --release

echo
echo "Now try:"
echo "  unset FFMPEG FFPROBE  # (optional, lets PATH be authoritative)"
echo "  target/release/mmx doctor"
echo "  target/release/mmx remux --input in.mp4 --output out_copy.mp4 --ss 0 --to 2.5 --stream-map '0:v:0,0:a:0,0:s?'"
