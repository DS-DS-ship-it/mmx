# tier2_enable_hardware_and_packager.py
from pathlib import Path
import re

root = Path(".")
cli = root/"mmx-cli/src/main.rs"
core_lib = root/"mmx-core/src/lib.rs"
core_backend = root/"mmx-core/src/backend.rs"
core_gst = root/"mmx-core/src/backend_gst.rs"
core_packager = root/"mmx-core/src/packager.rs"

# ---------- mmx-core/src/backend.rs : ensure RunOptions.hardware ----------
if core_backend.exists():
    s = core_backend.read_text()
    if "pub struct RunOptions" in s and "hardware:" not in s:
        s = re.sub(
            r"(pub\s+struct\s+RunOptions\s*\{)",
            r"\1\n    /// Hardware encoder (vt|nvenc|qsv|vaapi|cpu)\n    pub hardware: Option<String>,",
            s, count=1
        )
        core_backend.write_text(s)

# ---------- mmx-core/src/backend_gst.rs : use hardware flag for encoder ----------
if core_gst.exists():
    g = core_gst.read_text()
    if "let enc =" not in g:
        g = re.sub(
            r'(chain\.push\("x264enc[^\n]*mp4mux".*?;)',
            (
                "let enc = match run_opts.hardware.as_deref() {\n"
                "            Some(\"vt\") => \"vtenc_h264\",\n"
                "            Some(\"nvenc\") => \"nvh264enc\",\n"
                "            Some(\"qsv\") => \"msdkh264enc\",\n"
                "            Some(\"vaapi\") => \"vaapih264enc\",\n"
                "            _ => \"x264enc tune=zerolatency\",\n"
                "        };\n"
                "        chain.push(format!(\"{} ! mp4mux\", enc));"
            ),
            g, count=1, flags=re.S
        )
        core_gst.write_text(g)

# ---------- mmx-core/src/lib.rs : export packager ----------
if core_lib.exists():
    s = core_lib.read_text()
    if "pub mod packager;" not in s:
        s = s.rstrip() + "\n\npub mod packager;\n"
        core_lib.write_text(s)

# ---------- mmx-core/src/packager.rs : ffmpeg HLS packager ----------
core_packager.parent.mkdir(parents=True, exist_ok=True)
core_packager.write_text("""\
// 0BSD — simple HLS packager with auto ladder (ffmpeg fallback)
use anyhow::{anyhow, Result};
use std::process::Command;
use std::path::Path;

pub fn pack_hls_auto(input: &Path, out_dir: &Path, segment_seconds: u32) -> Result<()> {
    if !out_dir.exists() {
        std::fs::create_dir_all(out_dir)?;
    }

    let ffmpeg = std::env::var("FFMPEG").unwrap_or_else(|_| "ffmpeg".to_string());

    let filter = "[v:0]split=3[v1][v2][v3];\
[v1]scale=w=640:h=360[v1out];\
[v2]scale=w=1280:h=720[v2out];\
[v3]scale=w=1920:h=1080[v3out]";

    let seg_tpl = out_dir.join("v%v_seg%d.ts");
    let out_tpl = out_dir.join("v%v.m3u8");

    let args = vec![
        "-y",
        "-i", input.to_str().ok_or_else(|| anyhow!("bad input path"))?,
        "-filter_complex", filter,
        "-map", "[v1out]", "-c:v:0", "libx264", "-b:v:0", "500k",
        "-map", "[v2out]", "-c:v:1", "libx264", "-b:v:1", "1500k",
        "-map", "[v3out]", "-c:v:2", "libx264", "-b:v:2", "3000k",
        "-f", "hls",
        "-hls_time", &segment_seconds.to_string(),
        "-hls_playlist_type", "vod",
        "-master_pl_name", "master.m3u8",
        "-hls_segment_filename", seg_tpl.to_str().ok_or_else(|| anyhow!("bad seg path"))?,
        "-var_stream_map", "v:0,name:360p v:1,name:720p v:2,name:1080p",
        out_tpl.to_str().ok_or_else(|| anyhow!("bad out path"))?,
    ];

    let status = Command::new(ffmpeg).args(&args).status()
        .map_err(|e| anyhow!("failed to run ffmpeg: {e}"))?;
    if !status.success() {
        return Err(anyhow!("ffmpeg failed with status: {:?}", status));
    }
    Ok(())
}
""")

# ---------- mmx-cli/src/main.rs : add --hardware on run; add pack subcommand ----------
cs = cli.read_text()

if "use mmx_core::packager" not in cs:
    cs = re.sub(r"(use\s+mmx_core::backend[^\n]*;)", r"\1\nuse mmx_core::packager;", cs, count=1)

if re.search(r"struct\s+RunArgs\s*\{", cs) and "hardware:" not in cs:
    cs = re.sub(
        r"(struct\s+RunArgs\s*\{)",
        r"\1\n    /// Hardware encoder (vt|nvenc|qsv|vaapi|cpu)\n    #[arg(long = \"hardware\")]\n    hardware: Option<String>,",
        cs, count=1
    )

if "opts.hardware" not in cs:
    cs = re.sub(
        r"(opts\.progress_json\s*=\s*a\.progress_json\s*;)",
        r"\1\n    opts.hardware = a.hardware.clone();",
        cs, count=1
    )

if "struct PackArgs" not in cs:
    cs += """

#[derive(clap::Args, Debug, Clone)]
pub struct PackArgs {
    /// Input media file
    #[arg(long)]
    input: String,
    /// Output directory for HLS
    #[arg(long = "hls-out")]
    hls_out: Option<String>,
    /// Segment duration (seconds)
    #[arg(long = "segment-duration", default_value_t = 4)]
    segment_duration: u32,
}
"""

if re.search(r"enum\s+Command\s*\{", cs) and "Pack(" not in cs:
    cs = re.sub(r"(enum\s+Command\s*\{\s*)", r"\1\n    Pack(PackArgs),", cs, count=1)

if "fn cmd_pack(" not in cs:
    cs += """

fn cmd_pack(a: PackArgs) -> anyhow::Result<()> {
    let out = a.hls_out.ok_or_else(|| anyhow::anyhow!("use --hls-out <dir>"))?;
    packager::pack_hls_auto(std::path::Path::new(&a.input),
                            std::path::Path::new(&out),
                            a.segment_duration)?;
    eprintln!("[pack] wrote HLS to {}", out);
    Ok(())
}
"""

if "Command::Pack(" not in cs:
    cs = re.sub(
        r"(match\s+cli\.cmd\s*\{\s*)",
        r"\1\n        Command::Pack(a) => cmd_pack(a)?,",
        cs, count=1
    )

cli.write_text(cs)

print("[ok] tier2 hardware flag + pack subcommand + ffmpeg HLS packager")
