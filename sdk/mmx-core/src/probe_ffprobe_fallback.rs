
use anyhow::{anyhow, Result};
use std::path::Path;
use std::process::Command;

pub fn probe_ffprobe_json(input: &Path) -> Result<serde_json::Value> {
    let ffprobe = std::env::var("FFPROBE").unwrap_or_else(|_| "ffprobe".to_string());
    let mut base = vec![
        "-v","error",
        "-of","json=c=1",
        "-show_format",
        "-show_streams",
        "-show_programs",
        "-show_chapters",
    ];
    let out = Command::new(&ffprobe).args(&base).arg(input).output()
        .map_err(|e| anyhow!("failed to run ffprobe (install it or set FFPROBE): {e}"))?;
    if !out.status.success() {
        return Err(anyhow!("ffprobe failed with status: {:?}", out.status));
    }
    let mut v: serde_json::Value = serde_json::from_slice(&out.stdout)?;

    if std::env::var("MMX_FFPROBE_FRAMES").ok().as_deref() == Some("1") {
        let frames = Command::new(&ffprobe).args([
            "-v","error","-of","json=c=1","-show_frames:stream=0"
        ]).arg(input).output();
        if let Ok(fr) = frames {
            if fr.status.success() {
                if let Ok(frjson) = serde_json::from_slice::<serde_json::Value>(&fr.stdout) {
                    if let serde_json::Value::Object(obj) = &mut v {
                        obj.insert("frames".into(), frjson);
                    }
                }
            }
        }
    }
    Ok(v)
}
