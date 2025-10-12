use std::process::Command;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 3 {
        eprintln!("Usage: mmx remux <input> <output>");
        std::process::exit(1);
    }

    let input = &args[1];
    let output = &args[2];

    let status = Command::new("ffmpeg")
        .args(["-y", "-i", input, "-map", "0", "-c", "copy", output])
        .status()
        .expect("❌ Failed to invoke ffmpeg");

    if status.success() {
        println!("✅ Remux complete: {}", output);
    } else {
        println!("❌ ffmpeg exited with status: {}", status);
    }
}
