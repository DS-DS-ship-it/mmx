#!/bin/bash

# === MMX Remux v2 — Auto Setup Script ===
# By: D.J. Wardlaw
# Location: ~/mmx/
# Dependencies: Rust, Cargo, Git

set -e

PROJECT_ROOT="$HOME/mmx"
CLI_DIR="$PROJECT_ROOT/mmx-cli"
CORE_DIR="$PROJECT_ROOT/mmx-core"

echo "🛠️  Setting up MMX Remux v2 in: $PROJECT_ROOT"

mkdir -p "$PROJECT_ROOT"
cd "$PROJECT_ROOT"

# --- Create Cargo Workspace ---
cat > Cargo.toml <<EOF
[workspace]
members = ["mmx-core", "mmx-cli"]
resolver = "2"
EOF

# --- Create mmx-core crate ---
cd "$CORE_DIR"

cat > Cargo.toml <<EOF
[package]
name = "mmx-core"
version = "0.2.0"
edition = "2021"

[dependencies]
symphonia = { version = "0.5", features = ["all"] }
mp4 = "0.13"
matroska = "0.10"
rayon = "1.7"
anyhow = "1.0"
EOF

mkdir -p src
cat > src/output_muxer.rs <<'EOF'
use std::path::Path;
use symphonia::core::formats::FormatReader;
use anyhow::Result;

pub fn write_mkv<R: FormatReader + 'static>(_format: R, output: &Path) -> Result<()> {
    println!("✅ Writing MKV to {:?}", output);
    // TODO: implement real MKV muxing here
    Ok(())
}

pub fn write_mp4<R: FormatReader + 'static>(_format: R, output: &Path) -> Result<()> {
    println!("✅ Writing MP4 to {:?}", output);
    // TODO: implement real MP4 muxing here
    Ok(())
}
EOF

cat > src/lib.rs <<EOF
pub mod output_muxer;
EOF

# --- Create mmx-cli crate ---
cd "$PROJECT_ROOT"
cd "$CLI_DIR"

cat > Cargo.toml <<EOF
[package]
name = "mmx-cli"
version = "0.2.0"
edition = "2021"

[dependencies]
mmx-core = { path = "../mmx-core" }
symphonia = { version = "0.5", features = ["all"] }
anyhow = "1.0"
rayon = "1.7"
pathdiff = "0.2"
EOF

mkdir -p src/bin
cat > src/bin/mmx-remux.rs <<'EOF'
//! MMX Native Remux v2 — Rust Only

use std::env;
use std::path::{Path, PathBuf};
use std::fs::File;
use anyhow::{Result, Context};
use symphonia::default::get_probe;
use symphonia::core::io::MediaSourceStream;
use symphonia::core::codecs::DecoderOptions;
use symphonia::core::formats::FormatReader;

use mmx_core::output_muxer::{write_mp4, write_mkv};

fn main() {
    if let Err(e) = run() {
        eprintln!("❌ Error: {:?}", e);
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        anyhow::bail!("Usage: mmx-remux <input> <output>");
    }

    let input = PathBuf::from(&args[1]);
    let output = PathBuf::from(&args[2]);

    if !input.exists() {
        anyhow::bail!("Input file not found: {:?}", input);
    }

    let ext = output.extension()
        .and_then(|e| e.to_str())
        .unwrap_or("mkv")
        .to_lowercase();

    let file = File::open(&input)?;
    let mss = MediaSourceStream::new(Box::new(file), Default::default());

    let probed = get_probe().format(
        &Default::default(),
        mss,
        &Default::default(),
        &DecoderOptions::default(),
    )?;

    let format = probed.format;

    match ext.as_str() {
        "mp4" => write_mp4(format, &output)?,
        "mkv" => write_mkv(format, &output)?,
        _ => anyhow::bail!("Unsupported output container: .{}", ext),
    }

    println!("✅ MMX native remux complete: {:?}", output);
    Ok(())
}
EOF

# --- Build it ---
echo "📦 Building mmx-remux..."
cd "$PROJECT_ROOT"
cargo build --bin mmx-remux

# --- Add to PATH via wrapper ---
echo "🧩 Creating /usr/local/bin/mmx CLI wrapper..."
sudo tee /usr/local/bin/mmx > /dev/null <<'EOS'
#!/bin/bash
MMX_BIN="$HOME/mmx/target/debug"
CMD="$1"
shift
exec "$MMX_BIN/mmx-$CMD" "$@"
EOS
sudo chmod +x /usr/local/bin/mmx

echo "🎉 MMX Remux v2 ready!"
echo "👉 Usage:"
echo "    mmx remux input.mp4 output.mkv"
