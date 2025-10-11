set -euo pipefail

ROOT="${1:-.}"
CLI_MAIN="$ROOT/mmx-cli/src/main.rs"
CLI_TOML="$ROOT/mmx-cli/Cargo.toml"

if [[ ! -f "$CLI_MAIN" || ! -f "$CLI_TOML" ]]; then
  echo "Run from repo root (must contain mmx-cli/src/main.rs and mmx-cli/Cargo.toml)" >&2
  exit 1
fi

echo "[1/5] Remove 'use which::which;' imports (if any)…"
perl -0777 -i -pe 's/^\s*use\s+which::which\s*;\s*\n//m' "$CLI_MAIN"

echo "[2/5] Replace which::which(...) -> which_path(...), add helper if missing…"
perl -0777 -i -pe 's/\bwhich::which\(/which_path(/g' "$CLI_MAIN"

if ! grep -q 'fn which_path' "$CLI_MAIN"; then
  cat >> "$CLI_MAIN" <<'RUST'
#[cfg(unix)]
fn which_path(cmd: &str) -> Option<String> {
    use std::process::Command;
    let out = Command::new("sh").arg("-lc").arg(format!("command -v {}", cmd)).output().ok()?;
    if !out.status.success() { return None; }
    let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
    if s.is_empty() { None } else { Some(s) }
}

#[cfg(windows)]
fn which_path(cmd: &str) -> Option<String> {
    use std::process::Command;
    let out = Command::new("where").arg(cmd).output().ok()?;
    if !out.status.success() { return None; }
    let s = String::from_utf8_lossy(&out.stdout).lines().next().unwrap_or_default().trim().to_string();
    if s.is_empty() { None } else { Some(s) }
}
RUST
  echo "  -> inserted which_path() helper"
else
  echo "  -> which_path() already present"
fi

echo "[3/5] Clean Cargo.toml: remove bogus bin.0.* keys and optional which dep…"
# remove stray "bin.0.*" lines
perl -0777 -i -pe 's/^\s*bin\.0\.(axum|regex|tokio|which).*?\n//mg' "$CLI_TOML"
# remove which = "…"
perl -0777 -i -pe 's/^\s*which\s*=\s*".*?"\s*\n//mg' "$CLI_TOML"

echo "[4/5] Sanity check: ensure no remaining which::which references…"
if grep -n 'which::which(' "$CLI_MAIN" >/dev/null 2>&1; then
  echo "  ! still found 'which::which(' in $CLI_MAIN — replacing again"
  perl -0777 -i -pe 's/\bwhich::which\(/which_path(/g' "$CLI_MAIN"
fi

echo "[5/5] Build with gst feature…"
cargo build -p mmx-cli -F mmx-core/gst --release
echo "Build OK."
echo "Try:"
echo "  target/release/mmx --help"
