use std::collections::BTreeMap;

fn main() {
    // Initialize GStreamer (reports Ok even if no plugins present).
    if let Err(e) = gstreamer::init() {
        eprintln!("❌ GStreamer init failed: {e}");
        std::process::exit(1);
    }

    let required = [
        // demux/mux
        "qtdemux", "matroskademux",
        "mp4mux", "matroskamux",
        // parsers (common)
        "h264parse", "aacparse",
        // IO
        "filesrc", "filesink",
    ];

    let mut report = BTreeMap::new();

    for name in required {
        let ok = gstreamer::ElementFactory::find(name).is_some();
        report.insert(name.to_string(), ok);
    }

    // Print a friendly table + machine-readable JSON.
    println!("🔎 mmx doctor — GStreamer elements");
    for (k, v) in &report {
        println!("  {:16} {}", k, if *v { "✅" } else { "❌" });
    }

    let have_all = report.values().all(|v| *v);
    println!();
    println!("JSON:");
    println!("{}", serde_json::to_string_pretty(&report).unwrap());

    if !have_all {
        println!("\n⚠️  Missing elements. On macOS:");
        println!("   brew install gst-plugins-base gst-plugins-good gst-plugins-bad");
        std::process::exit(2);
    }
}
