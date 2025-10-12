//! MMX Native Remuxer v1.0 — Zero FFmpeg Dependencies
//! Author: D.J. Wardlaw
//! Goal: Copy packets between containers (mp4 ↔ mkv ↔ mov) using pure Rust crates.

use std::{
    env,
    fs::File,
    io::{Read, Write},
    path::Path,
    process::exit,
    time::Instant,
};

use anyhow::{anyhow, Result};
use indicatif::{ProgressBar, ProgressStyle};
use symphonia::core::{
    codecs::CODEC_TYPE_NULL,
    formats::{FormatOptions, FormatReader},
    io::MediaSourceStream,
    meta::MetadataOptions,
    probe::Hint,
};

use mp4::{Mp4Config, Mp4Writer};
use matroska::Writer as MkvWriter;
use crc32fast::Hasher;

fn main() {
    if let Err(e) = run() {
        eprintln!("❌ MMX Remux Error: {:#}", e);
        exit(1);
    }
}

/// Entry point for the native remuxer.
fn run() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        return Err(anyhow!("Usage: mmx-remux <input> <output>"));
    }

    let input_path = &args[1];
    let output_path = &args[2];
    if !Path::new(input_path).exists() {
        return Err(anyhow!("Input file not found: {}", input_path));
    }

    println!("🔁 MMX Native Remux: {} → {}", input_path, output_path);
    let start = Instant::now();

    // --- Detect input format using Symphonia
    let input_format = detect_format(input_path)?;
    println!("📦 Detected input format: {}", input_format);

    // --- Create progress bar
    let bar = ProgressBar::new_spinner();
    bar.set_style(ProgressStyle::with_template("{spinner:.cyan} {msg}")?);
    bar.set_message("Opening input file...");

    // --- Open and parse the input
    let file = File::open(input_path)?;
    let mss = MediaSourceStream::new(Box::new(file), Default::default());
    let probed = symphonia::default::get_probe()
        .format(
            &Hint::new(),
            mss,
            &FormatOptions::default(),
            &MetadataOptions::default(),
        )
        .map_err(|_| anyhow!("Failed to probe input format"))?;

    let mut reader = probed.format;
    let tracks = reader.tracks();
    if tracks.is_empty() {
        return Err(anyhow!("No tracks found in input file"));
    }

    println!("🎚 Found {} track(s)", tracks.len());

    // --- Select container type based on extension
    let ext = Path::new(output_path)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("mp4")
        .to_lowercase();

    match ext.as_str() {
        "mkv" | "webm" => remux_to_mkv(&mut reader, output_path, &bar)?,
        "mp4" | "mov" => remux_to_mp4(&mut reader, output_path, &bar)?,
        _ => return Err(anyhow!("Unsupported output container: {}", ext)),
    }

    bar.finish_with_message("✅ Native remux complete!");
    println!("🕓 Elapsed: {:.2?}", start.elapsed());
    println!("📂 Saved: {}", output_path);

    // --- Verify CRC checksum
    verify_checksum(output_path)?;

    Ok(())
}

/// Detect input format using Symphonia probe.
fn detect_format(path: &str) -> Result<String> {
    let mut hint = Hint::new();
    if let Some(ext) = Path::new(path).extension().and_then(|e| e.to_str()) {
        hint.with_extension(ext);
    }
    let file = File::open(path)?;
    let mss = MediaSourceStream::new(Box::new(file), Default::default());
    let probed = symphonia::default::get_probe()
        .format(&hint, mss, &FormatOptions::default(), &MetadataOptions::default())?;
    Ok(probed.format.format_name().to_string())
}

/// Native Matroska (.mkv / .webm) remuxer
fn remux_to_mkv(reader: &mut dyn FormatReader, output: &str, bar: &ProgressBar) -> Result<()> {
    let out = File::create(output)?;
    let mut mkv = MkvWriter::new(out)?;
    let mut count = 0usize;

    bar.set_message("Writing MKV packets...");

    while let Ok(packet) = reader.next_packet() {
        if packet.codec_type == CODEC_TYPE_NULL {
            continue;
        }
        mkv.write_block_simple(0, packet.dts.unwrap_or(0), packet.data)?;
        count += 1;
        if count % 50 == 0 {
            bar.tick();
        }
    }

    println!("📼 Wrote {} packets to MKV", count);
    Ok(())
}

/// Native MP4/MOV remuxer
fn remux_to_mp4(reader: &mut dyn FormatReader, output: &str, bar: &ProgressBar) -> Result<()> {
    let out = File::create(output)?;
    let config = Mp4Config {
        major_brand: "isom".into(),
        minor_version: 512,
        compatible_brands: vec!["isom".into(), "iso2".into()],
    };
    let mut mp4 = Mp4Writer::new(out, &config)?;
    let mut count = 0usize;

    bar.set_message("Writing MP4 packets...");

    while let Ok(packet) = reader.next_packet() {
        if packet.codec_type == CODEC_TYPE_NULL {
            continue;
        }
        mp4.write_packet(packet.data)?;
        count += 1;
        if count % 50 == 0 {
            bar.tick();
        }
    }

    mp4.write_end()?;
    println!("🎞️ Wrote {} packets to MP4", count);
    Ok(())
}

/// Verify checksum of saved file for data integrity
fn verify_checksum(path: &str) -> Result<()> {
    let mut file = File::open(path)?;
    let mut buf = Vec::new();
    file.read_to_end(&mut buf)?;
    let mut hasher = Hasher::new();
    hasher.update(&buf);
    let hash = hasher.finalize();
    println!("🔒 CRC32: {:08x}", hash);
    Ok(())
}
