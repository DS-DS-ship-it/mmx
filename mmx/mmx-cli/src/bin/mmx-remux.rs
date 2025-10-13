use symphonia::default::{get_probe};
use symphonia::core::io::MediaSourceStream;
use symphonia::core::probe::Hint;
use std::env;
use std::fs::File;
use anyhow::{Result, anyhow};

fn main() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        return Err(anyhow!("Usage: mmx-remux <input> <output>"));
    }

    let input = &args[1];
    let output = &args[2];

    let file = File::open(input)?;
    let mss = MediaSourceStream::new(Box::new(file), Default::default());

    let mut hint = Hint::new();
    if input.ends_with(".mp4") {
        hint.with_extension("mp4");
    } else if input.ends_with(".mkv") {
        hint.with_extension("mkv");
    }

    let probed = get_probe().format(
        &hint,
        mss,
        &Default::default(),
        &Default::default(),
    )?;

    let format = probed.format;

    println!("✅ Input format detected: {}", format.format_name());
    println!("🚧 Remuxing logic goes here (to be implemented)");
    println!("🎯 Target output path: {}", output);

    Ok(())
}
