#!/usr/bin/env bash
set -euo pipefail

MAIN="mmx-cli/src/main.rs"
[[ -f "$MAIN" ]] || { echo "!! $MAIN not found (run from repo root)"; exit 1; }

python3 - <<'PY'
import re, pathlib
p = pathlib.Path("mmx-cli/src/main.rs")
s = p.read_text()

# 1) Remove any code that trims '?' off map parts, e.g.:
#    let p = if part.ends_with('?') { .. } else { part };
s = re.sub(
    r"""let\s+p\s*=\s*if\s*part\.ends_with\(\s*['"]\?['"]\s*\)\s*\{
        [^{}]*?
        \}\s*else\s*\{
        [^{}]*?
        \}\s*;\s*""",
    "",
    s,
    flags=re.S | re.X,
)

# 2) Make sure we push the original part verbatim to -map
s = re.sub(r'args\.push\(\s*p\.into\(\)\s*\)', 'args.push(part.into())', s)

# 3) Normalize the map loop body (idempotent)
s = re.sub(
    r"""for\s+part\s+in\s+a\.stream_map\.split\([^)]*\)\s*\.\s*map\([^)]*\)\s*\.\s*filter\([^)]*\)\s*\{
        .*?
        \}""",
    '''for part in a.stream_map.split(",").map(|x| x.trim()).filter(|x| !x.is_empty()) {
        args.push("-map".into());
        args.push(part.into());
    }''',
    s,
    flags=re.S | re.X,
)

# 4) Set safer default: audio/subs optional by default
s = re.sub(
    r'(#[^\n]*\bdefault_value\s*=\s*")([^"]*)(")',
    lambda m: m.group(1) + '0:v:0,0:a?,0:s?' + m.group(3),
    s,
    count=1
)

p.write_text(s)
print("[ok] main.rs patched: keep '?' in -map, default=0:v:0,0:a?,0:s?")
PY

echo "Building (gst feature)…"
cargo build -p mmx-cli -F mmx-core/gst --release

echo
echo "Try (defaults make a/v/subs optional):"
echo "  target/release/mmx remux --input in.mp4 --output out_copy.mp4 --ss 0 --to 2.5"
echo
echo "Or explicit:"
echo '  target/release/mmx remux --input in.mp4 --output out_copy.mp4 --ss 0 --to 2.5 --stream-map "0:v:0,0:a?,0:s?"'
