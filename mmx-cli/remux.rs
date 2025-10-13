//! MMX Native Remuxer (No Fallback)
//! Goal: Stub that avoids calling ffmpeg/gst, does not panic, and proves native execution.

use std::env;
use std::path::Path;
use anyhow::{anyhow, Result};

fn main() {
    if let Err(e) = run() {
        eprintln!("❌ MMX native remux error: {:#}", e);
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        return Err(anyhow!("Usage: remux <input> <output>"));
    }

    let input_path = &args[1];
    let output_path = &args[2];

    if !Path::new(input_path).exists() {
        return Err(anyhow!("Input file not found: {}", input_path));
    }

    println!("🧪 Native MMX remux stub running!");
    println!("Input:  {}", input_path);
    println!("Output: {}", output_path);
    println!("(⚠️  Real remuxing logic not implemented yet — no fallback used)");

    Ok(())
}
