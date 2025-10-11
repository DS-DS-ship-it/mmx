#!/usr/bin/env bash
# open_core_launch.sh
set -euo pipefail

# -------- config --------
GH_USER="${GH_USER:-derekwardlaw}"
CORE_REPO="${CORE_REPO:-mmx}"
PRO_REPO="${PRO_REPO:-mmx-pro}"
VERSION="${VERSION:-v1.0.0}"
DIST_DIR="${DIST_DIR:-dist}"
SDK_TGZ="${SDK_TGZ:-$DIST_DIR/mmx-sdk.tar.gz}"
MAIN_BRANCH="${MAIN_BRANCH:-main}"
HOMEPAGE="${HOMEPAGE:-https://github.com/$GH_USER/$CORE_REPO}"
BUY_URL="${BUY_URL:-https://example.com/buy}"           # replace with Stripe/Gumroad checkout
SUPPORT_EMAIL="${SUPPORT_EMAIL:-support@example.com}"   # replace with your email

command -v git >/dev/null || { echo "git not found"; exit 1; }
command -v gh  >/dev/null || { echo "gh (GitHub CLI) not found"; exit 1; }

mkdir -p "$DIST_DIR" .github/workflows scripts

# -------- core files --------
cat > LICENSE <<'MIT'
MIT License

Copyright (c) 2025 MMX

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the “Software”), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, subject to the following conditions:

This license applies only to the open-core components: mmx-core and mmx-cli.
Any pro or cloud components (including but not limited to mmx-pro) are licensed
separately under commercial terms.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND.
MIT

cat > README.md <<EOF
# MMX — Hybrid Media Engine (Open Core)

Open-core multimedia stack in Rust:
- \`mmx-core\` — engine & APIs (MIT)
- \`mmx-cli\` — CLI (MIT)
- \`mmx-pro\` — commercial add-ons (GPU/GUI/Cloud)

## Install (from source)
\`\`\`bash
cargo build -p mmx-cli -F mmx-core/gst --release
./target/release/mmx --help
\`\`\`

## Pricing
| Tier     | Includes                                     | Price |
|----------|----------------------------------------------|-------|
| Community| mmx-core + mmx-cli (MIT)                     | Free  |
| Indie    | GPU accel + ABR presets + error aide         | \$49  |
| Studio   | GUI + Cloud scheduler + priority support     | \$499 |

**Buy Pro:** $BUY_URL

## Telemetry
Opt-in only: set \`MMX_TELEMETRY=on\`. Captures command, exit, duration (no paths).

## License
Core is MIT. Pro is commercial.
EOF

cat > .github/FUNDING.yml <<EOF
github: [$GH_USER]
custom: ["$BUY_URL"]
EOF

cat > .github/workflows/release.yml <<'YML'
name: Release
on:
  push:
    tags: ["v*"]
jobs:
  build:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - name: Build CLI
        run: cargo build -p mmx-cli -F mmx-core/gst --release
      - name: Pack SDK
        run: |
          mkdir -p dist
          tar -czf dist/mmx-sdk.tar.gz mmx-core mmx-cli
      - name: Upload
        uses: softprops/action-gh-release@v2
        with:
          files: dist/mmx-sdk.tar.gz
YML

cat > scripts/release_core.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
VERSION="${1:-v1.0.0}"
mkdir -p dist
tar -czf dist/mmx-sdk.tar.gz mmx-core mmx-cli
gh release create "$VERSION" dist/mmx-sdk.tar.gz --title "MMX SDK $VERSION" --notes "Open Core release"
SH
chmod +x scripts/release_core.sh

# -------- create minimal crates if missing --------
if [[ ! -d mmx-core ]]; then
  cargo new mmx-core --lib >/dev/null
  cat > mmx-core/src/lib.rs <<'RS'
pub mod telemetry {
    pub fn enabled() -> bool {
        std::env::var("MMX_TELEMETRY").map(|v| v == "on").unwrap_or(false)
    }
    pub fn emit(cmd: &str, status: i32, ms: u128) {
        if enabled() {
            println!("{}", serde_json::json!({
              "event":"telemetry","cmd":cmd,"status":status,"ms":ms
            }));
        }
    }
}
pub mod probe {
    use serde::Serialize;
    #[derive(Serialize)]
    pub struct BasicProbe { pub path:String, pub duration:f32, pub streams:u32 }
    pub fn probe_basic(path:&str)->BasicProbe {
        BasicProbe{ path:path.into(), duration:0.0, streams:1 }
    }
}
RS
  sed -i '' '1s/^/[package]\nname="mmx-core"\nversion="0.1.0"\nedition="2021"\n\n[dependencies]\nserde = { version="1", features=["derive"] }\nserde_json="1"\n/' mmx-core/Cargo.toml
fi

if [[ ! -d mmx-cli ]]; then
  cargo new mmx-cli >/dev/null
  cat > mmx-cli/Cargo.toml <<'TOML'
[package]
name = "mmx-cli"
version = "0.1.0"
edition = "2021"

[dependencies]
clap = { version = "4", features = ["derive"] }
anyhow = "1"
serde = { version="1", features=["derive"] }
serde_json = "1"
mmx-core = { path = "../mmx-core" }

[features]
default = []
mmx-core/gst = []
TOML
  cat > mmx-cli/src/main.rs <<'RS'
use clap::{Parser, Subcommand};
use anyhow::Result;

#[derive(Parser, Debug)]
#[command(name="mmx", about="MMX — media swiss-army CLI")]
struct Cli {
    #[command(subcommand)]
    cmd: Command
}

#[derive(Subcommand, Debug)]
enum Command {
    Probe { #[arg(long)] input: String, #[arg(long)] enhanced: bool },
    Doctor,
    Run   { #[arg(long)] backend: String, #[arg(long)] input:String, #[arg(long)] output:String, #[arg(long, default_value_t=false)] execute: bool },
    Remux { #[arg(long)] input:String, #[arg(long)] output:String, #[arg(long)] ss: Option<f64>, #[arg(long)] to: Option<f64>, #[arg(long, default_value="0:v:0,0:a?,0:s?")] stream_map:String },
    Ffmpeg { #[arg(trailing_var_arg=true)] args: Vec<String> }
}

fn main() -> Result<()> {
    let t0 = std::time::Instant::now();
    let cli = Cli::parse();
    let rc = match cli.cmd {
        Command::Probe{ input, enhanced } => {
            if enhanced {
                println!("{}", serde_json::json!({"engine":"ffprobe","path":input,"note":"raw passthrough not yet implemented"}));
            } else {
                let p = mmx_core::probe::probe_basic(&input);
                println!("{}", serde_json::to_string_pretty(&p)?);
            }
            0
        }
        Command::Doctor => {
            println!("{}", serde_json::json!({
                "deps": {
                    "ffmpeg": std::env::var("FFMPEG").unwrap_or_default(),
                    "ffprobe": std::env::var("FFPROBE").unwrap_or_default()
                },
                "env": {
                    "PATH": std::env::var("PATH").unwrap_or_default()
                },
                "mmx":"ok"
            }));
            0
        }
        Command::Run{ backend, input, output, execute } => {
            println!("{}", serde_json::json!({
              "backend": backend,
              "input": input,
              "output": output,
              "execute": execute,
              "status": "not-implemented"
            }));
            0
        }
        Command::Remux{ input, output, ss, to, stream_map } => {
            let ff = std::env::var("FFMPEG").ok().unwrap_or_else(|| "ffmpeg".into());
            let mut args: Vec<String> = vec!["-y".into(), "-hide_banner".into(), "-nostdin".into()];
            if let Some(s)=ss { args.push("-ss".into()); args.push(format!("{s}")); }
            args.push("-i".into()); args.push(input);
            if let Some(t)=to { args.push("-to".into()); args.push(format!("{t}")); }
            for part in stream_map.split(',').map(|x| x.trim()).filter(|x| !x.is_empty()) {
                args.push("-map".into()); args.push(part.into());
            }
            args.extend(["-c:v".into(),"copy".into(), "-c:a".into(),"copy".into(), "-c:s".into(),"copy".into()]);
            args.push(output);
            let status = std::process::Command::new(&ff).args(&args).status();
            match status {
                Ok(s) if s.success() => 0,
                Ok(s) => { eprintln!("ffmpeg failed: {s}"); 234 },
                Err(e) => { eprintln!("spawn failed: {e}"); 235 }
            }
        }
        Command::Ffmpeg{ args } => {
            let ff = std::env::var("FFMPEG").ok().unwrap_or_else(|| "ffmpeg".into());
            let status = std::process::Command::new(&ff).args(&args).status();
            match status {
                Ok(s) if s.success() => 0,
                Ok(s) => { eprintln!("ffmpeg failed: {s}"); 234 },
                Err(e) => { eprintln!("spawn failed: {e}"); 235 }
            }
        }
    };
    let ms = t0.elapsed().as_millis();
    mmx_core::telemetry::emit("mmx", rc, ms);
    if rc == 0 { Ok(()) } else { std::process::exit(rc) }
}
RS
fi

# -------- ensure SDK tarball --------
if [[ ! -f "$SDK_TGZ" ]]; then
  tar -czf "$SDK_TGZ" mmx-core mmx-cli
fi

# -------- git init and push --------
if [[ ! -d .git ]]; then
  git init
  git checkout -b "$MAIN_BRANCH"
fi
git add .
git commit -m "MMX Open Core $VERSION"
if ! gh repo view "$GH_USER/$CORE_REPO" >/dev/null 2>&1; then
  gh repo create "$GH_USER/$CORE_REPO" --public --source . --remote origin --push
else
  git remote remove origin 2>/dev/null || true
  git remote add origin "https://github.com/$GH_USER/$CORE_REPO.git" 2>/dev/null || true
  git push -u origin "$MAIN_BRANCH"
fi

# -------- create release with asset --------
if gh release view "$VERSION" >/dev/null 2>&1; then
  gh release upload "$VERSION" "$SDK_TGZ" --clobber
else
  gh release create "$VERSION" "$SDK_TGZ" --title "MMX SDK $VERSION (Open Core)" --notes "Open Core base: mmx-core + mmx-cli (MIT)."
fi

# -------- pro repo bootstrap --------
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT
mkdir -p "$TMPDIR/$PRO_REPO"
cat > "$TMPDIR/$PRO_REPO/README.md" <<EOF
# MMX Pro (Commercial)

GPU acceleration, ABR presets, GUI, Cloud scheduler.

Contact: $SUPPORT_EMAIL  
Buy: $BUY_URL
EOF

cat > "$TMPDIR/$PRO_REPO/LICENSE" <<'LIC'
MMX Pro Commercial License

The MMX Pro source code and binaries are licensed for a fee. Redistribution,
sublicensing, or use without a valid license key is prohibited.
LIC

mkdir -p "$TMPDIR/$PRO_REPO/crates/mmx-pro-license"
cat > "$TMPDIR/$PRO_REPO/crates/mmx-pro-license/Cargo.toml" <<'TOML'
[package]
name = "mmx-pro-license"
version = "0.1.0"
edition = "2021"
TOML
cat > "$TMPDIR/$PRO_REPO/crates/mmx-pro-license/src/lib.rs" <<'RS'
pub fn check() -> bool {
    if let Ok(k) = std::fs::read_to_string(dirs::home_dir().unwrap_or_default().join(".mmx_license")) {
        return k.contains("MMX-PRO-VALID");
    }
    false
}
RS

if ! gh repo view "$GH_USER/$PRO_REPO" >/dev/null 2>&1; then
  (cd "$TMPDIR/$PRO_REPO" && git init && git add . && git commit -m "MMX Pro bootstrap" && gh repo create "$GH_USER/$PRO_REPO" --private --source . --remote origin --push)
fi

# -------- done --------
echo "OK: https://github.com/$GH_USER/$CORE_REPO"
echo "OK: https://github.com/$GH_USER/$PRO_REPO (private)"
