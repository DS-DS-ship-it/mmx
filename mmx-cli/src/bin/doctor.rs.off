fn main() {
    let tools = ["ffmpeg", "ffprobe", "gst-launch-1.0"];
    for tool in tools {
        let found = which::which(tool);
        match found {
            Ok(path) => println!("✅ Found: {}", path.display()),
            Err(_) => println!("❌ Not found: {}", tool),
        }
    }
}
