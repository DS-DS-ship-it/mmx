#!/bin/bash

set -e

MMX_ROOT="$HOME/mmx"
MMX_CORE="$MMX_ROOT/mmx-core"
MMX_CLI="$MMX_ROOT/mmx-cli"

echo "🛠️  Setting up MMX Remux v2 in: $MMX_ROOT"

mkdir -p "$MMX_ROOT"
cd "$MMX_ROOT"

if [ ! -d "$MMX_CORE/src" ]; then
    cargo new --lib mmx-core
fi

if [ ! -d "$MMX_CLI/src" ]; then
    cargo new --bin mmx-cli
fi

# 🧠 Add mmx-core to mmx-cli
echo "⚙️  Linking mmx-core to mmx-cli..."

cat > "$MMX_CLI/Cargo.toml" <<EOF
[package]
name = "mmx-cli"
version = "0.2.0"
edition = "2021"

[dependencies]
anyhow = "1"
symphonia = { version = "0.5.5", features = ["all"] }
mmx-core = { path = "../mmx-core" }

[[bin]]
name = "mmx-remux"
path = "src/bin/mmx-remux.rs"
EOF

mkdir -p "$MMX_CLI/src/bin"

# 🧠 Add stub mmx-core lib
cat > "$MMX_CORE/src/lib.rs" <<EOF
use std::path::Path;
use anyhow::Result;
use symphonia::core::formats::FormatReader;

pub fn write_mp4<R: FormatReader + 'static>(_reader: R, _output: &Path) -> Result<()> {
    println!("🔧 Writing MP4 container (stub — implement me)");
    Ok(())
}

pub fn write_mkv<R: FormatReader + 'static>(_reader: R, _output: &Path) -> Result<()> {
    println!("🔧 Writing MKV container (stub — implement me)");
    Ok(())
}
EOF

# 🧠 Add mmx-remux main binary
cat > "$MMX_CLI/src/bin/mmx-remux.rs" <<'EOF'
use std::env;
use std::fs::File;
use std::path::Path;
use anyhow::{Result, anyhow};
use symphonia::core::probe::Hint;
use symphonia::core::io::MediaSourceStream;
use symphonia::core::meta::Metadata;
use symphonia::core::formats::FormatOptions;
use symphonia::default::{get_probe};
use symphonia::default::formats::{IsoMp4Reader, MkvReader};

use mmx_core::{write_mp4, write_mkv};

fn main() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 3 {
        return Err(anyhow!("Usage: mmx-remux <input> <output>"));
    }

    let input_path = Path::new(&args[1]);
    let output_path = Path::new(&args[2]);

    let file = File::open(input_path)?;
    let mss = MediaSourceStream::new(Box::new(file), Default::default());

    let probed = get_probe().format(
        &Hint::new(),
        mss,
        &FormatOptions::default(),
        &mut Metadata::new()
    )?;

    let format = probed.format;

    if let Some(mp4_reader) = format.downcast::<IsoMp4Reader>().ok() {
        write_mp4(*mp4_reader, output_path)?;
    } else if let Some(mkv_reader) = format.downcast::<MkvReader>().ok() {
        write_mkv(*mkv_reader, output_path)?;
    } else {
        return Err(anyhow!("Unsupported format — MMX only supports .mp4 and .mkv"));
    }

    println!("✅ MMX native remux complete: {}", output_path.display());
    Ok(())
}
EOF

# 🧪 Build the binary
echo "🔨 Building mmx-remux..."
cd "$MMX_CLI"
cargo build --bin mmx-remux

# 🧷 Symlink to /usr/local/bin
echo "🔗 Linking to /usr/local/bin/mmx-remux"
sudo ln -sf "$MMX_CLI/target/debug/mmx-remux" /usr/local/bin/mmx-remux

echo "🎉 Done. Run:"
echo "    mmx-remux input.mp4 output.mkv"
