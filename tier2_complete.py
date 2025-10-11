# tier2_complete.py
from pathlib import Path
import re

root = Path(".")
cli = root / "mmx-cli/src/main.rs"
core_lib = root / "mmx-core/src/lib.rs"
core_backend = root / "mmx-core/src/backend.rs"
core_gst = root / "mmx-core/src/backend_gst.rs"
ladder_rs = root / "mmx-core/src/ladder.rs"
packager_rs = root / "mmx-core/src/packager.rs"

# ---------- 1) mmx-core/src/backend.rs: ensure RunOptions.hardware ----------
if core_backend.exists():
    s = core_backend.read_text()
    if "pub struct RunOptions" in s and "hardware:" not in s:
        s = re.sub(
            r"(pub\s+struct\s+RunOptions\s*\{)",
            r"\1\n    /// Hardware encoder (vt|nvenc|qsv|vaapi|cpu)\n    pub hardware: Option<String>,",
            s,
            count=1,
        )
        core_backend.write_text(s)

# ---------- 2) mmx-core/src/backend_gst.rs: use hardware for encoder ----------
if core_gst.exists():
    g = core_gst.read_text()

    # case A: single push with x264 + mp4mux in one string
    pattern_a = 'chain.push("x264enc tune=zerolatency ! mp4mux".into());'
    # case B: older style where encoder and mp4mux may be separate pushes — try to find the encoder push
    pattern_b = r'chain\.push\("x264enc[^"]*"\.into\(\)\);\s*chain\.push\("mp4mux"\.into\(\)\);'

    if "let enc =" not in g and (pattern_a in g or re.search(pattern_b, g)):
        if pattern_a in g:
            g = g.replace(
                pattern_a,
                'let enc = match run_opts.hardware.as_deref() {\n'
                '    Some("vt") => "vtenc_h264",\n'
                '    Some("nvenc") => "nvh264enc",\n'
                '    Some("qsv") => "msdkh264enc",\n'
                '    Some("vaapi") => "vaapih264enc",\n'
                '    _ => "x264enc tune=zerolatency",\n'
                '};\n'
                'chain.push(format!("{} ! mp4mux", enc));',
                1,
            )
        else:
            g = re.sub(
                pattern_b,
                'let enc = match run_opts.hardware.as_deref() {\n'
                '    Some("vt") => "vtenc_h264",\n'
                '    Some("nvenc") => "nvh264enc",\n'
                '    Some("qsv") => "msdkh264enc",\n'
                '    Some("vaapi") => "vaapih264enc",\n'
                '    _ => "x264enc",\n'
                '};\n'
                'chain.push(enc.into());\n'
                'chain.push("mp4mux".into());',
                g,
                count=1,
            )
        core_gst.write_text(g)

# ---------- 3) mmx-core/src/lib.rs: export ladder & packager ----------
if core_lib.exists():
    s = core_lib.read_text()
    changed = False
    if "pub mod ladder;" not in s:
        s = s.rstrip() + "\n\npub mod ladder;\n"
        changed = True
    if "pub mod packager;" not in s:
        s = s.rstrip() + "\n\npub mod packager;\n"
        changed = True
    if changed:
        core_lib.write_text(s)

# ---------- 4) mmx-core/src/ladder.rs ----------
ladder_rs.parent.mkdir(parents=True, exist_ok=True)
ladder_rs.write_text(
    """
// 0BSD — ABR ladder helper (ffprobe-based)
use anyhow::{anyhow, Result};
use std::process::Command;
use std::path::Path;

#[derive(Clone, Debug)]
pub struct LadderRung {
    pub width: u32,
    pub height: u32,
    pub bitrate_k: u32,
    pub name: String,
}

fn probe_dims(input: &Path) -> Result<(u32, u32)> {
    // ffprobe: WIDTHxHEIGHT as a single CSV cell
    let out = Command::new(std::env::var("FFPROBE").unwrap_or_else(|_| "ffprobe".to_string()))
        .args([
            "-v","error",
            "-select_streams","v:0",
            "-show_entries","stream=width,height",
            "-of","csv=s=x:p=0",
            input.to_str().ok_or_else(|| anyhow!("bad input path"))?,
        ])
        .output()
        .map_err(|e| anyhow!("failed to run ffprobe: {e}"))?;
    if !out.status.success() {
        return Err(anyhow!("ffprobe failed"));
    }
    let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
    let mut it = s.split('x');
    let w: u32 = it.next().ok_or_else(|| anyhow!("bad ffprobe width"))?.parse()?;
    let h: u32 = it.next().ok_or_else(|| anyhow!("bad ffprobe height"))?.parse()?;
    Ok((w,h))
}

pub fn auto_for_input_path(input: &Path) -> Result<Vec<LadderRung>> {
    let (_w, h) = probe_dims(input)?;
    let mut rungs: Vec<LadderRung> = vec![];
    if h >= 360 {
        rungs.push(LadderRung{ width: 640, height: 360, bitrate_k: 600, name: "360p".into() });
    }
    if h >= 720 {
        rungs.push(LadderRung{ width: 1280, height: 720, bitrate_k: 1800, name: "720p".into() });
    }
    if h >= 1080 {
        rungs.push(LadderRung{ width: 1920, height: 1080, bitrate_k: 3500, name: "1080p".into() });
    }
    if rungs.is_empty() {
        rungs.push(LadderRung{ width: 426, height: 240, bitrate_k: 400, name: "240p".into() });
    }
    Ok(rungs)
}
""".lstrip()
)

# ---------- 5) mmx-core/src/packager.rs ----------
packager_rs.write_text(
    """
// 0BSD — Unified packager (HLS/DASH) via ffmpeg fallback + auto ladder
use anyhow::{anyhow, Result};
use std::process::Command;
use std::path::Path;

use crate::ladder::{self, LadderRung};

fn ffmpeg_cmd() -> String {
    std::env::var("FFMPEG").unwrap_or_else(|_| "ffmpeg".to_string())
}

fn push<S: Into<String>>(v: &mut Vec<String>, s: S) { v.push(s.into()); }

fn build_filter_and_maps(rungs: &[LadderRung]) -> (String, Vec<(String, usize)>) {
    let n = rungs.len();
    let mut filter = String::new();
    if n == 1 {
        filter.push_str("[v:0]scale=w=");
        filter.push_str(&rungs[0].width.to_string());
        filter.push_str(":h=");
        filter.push_str(&rungs[0].height.to_string());
        filter.push_str("[v0out]");
        return (filter, vec![("v0out".into(), 0)]);
    }

    filter.push_str("[v:0]split=");
    filter.push_str(&n.to_string());
    for i in 0..n {
        filter.push_str(&format!("[v{idx}]", idx=i));
    }
    filter.push(';');
    for i in 0..n {
        let r = &rungs[i];
        filter.push_str(&format!("[v{idx}]scale=w={w}:h={h}[v{idx}out];", idx=i, w=r.width, h=r.height));
    }
    if filter.ends_with(';') { filter.pop(); }

    let mut maps = Vec::with_capacity(n);
    for i in 0..n {
        maps.push((format!("v{}out", i), i));
    }
    (filter, maps)
}

fn build_hls_args(input: &Path, out_dir: &Path, segment_seconds: u32, rungs: &[LadderRung]) -> Result<Vec<String>> {
    if !out_dir.exists() { std::fs::create_dir_all(out_dir)?; }

    let (filter, maps) = build_filter_and_maps(rungs);
    let seg_tpl = out_dir.join("v%v_seg%d.ts");
    let out_tpl = out_dir.join("v%v.m3u8");

    let mut args: Vec<String> = Vec::new();
    push(&mut args, "-y");
    push(&mut args, "-i"); push(&mut args, input.to_str().ok_or_else(|| anyhow!("bad input path"))?);
    push(&mut args, "-filter_complex"); push(&mut args, filter);

    for (label, idx) in &maps {
        push(&mut args, "-map"); push(&mut args, format!("[{}]", label));
        push(&mut args, format!("-c:v:{}", idx)); push(&mut args, "libx264");
        let br = format!(\"{}k\", rungs[*idx].bitrate_k);
        push(&mut args, format!("-b:v:{}", idx)); push(&mut args, br);
    }

    let seg = segment_seconds.to_string();
    push(&mut args, "-f"); push(&mut args, "hls");
    push(&mut args, "-hls_time"); push(&mut args, seg);
    push(&mut args, "-hls_playlist_type"); push(&mut args, "vod");
    push(&mut args, "-master_pl_name"); push(&mut args, "master.m3u8");
    push(&mut args, "-hls_segment_filename"); push(&mut args, seg_tpl.to_str().ok_or_else(|| anyhow!("bad seg path"))?);

    let mut vmap = String::new();
    for (i, r) in rungs.iter().enumerate() {
        if i > 0 { vmap.push(' '); }
        vmap.push_str(&format!("v:{},name:{}", i, r.name));
    }
    push(&mut args, "-var_stream_map"); push(&mut args, vmap);

    push(&mut args, out_tpl.to_str().ok_or_else(|| anyhow!("bad out path"))?);
    Ok(args)
}

fn build_dash_args(input: &Path, out_dir: &Path, segment_seconds: u32, rungs: &[LadderRung]) -> Result<Vec<String>> {
    if !out_dir.exists() { std::fs::create_dir_all(out_dir)?; }

    let (filter, maps) = build_filter_and_maps(rungs);
    let mpd = out_dir.join("master.mpd");
    let seg = segment_seconds.to_string();

    let mut args: Vec<String> = Vec::new();
    push(&mut args, "-y");
    push(&mut args, "-i"); push(&mut args, input.to_str().ok_or_else(|| anyhow!("bad input path"))?);
    push(&mut args, "-filter_complex"); push(&mut args, filter);

    for (label, idx) in &maps {
        push(&mut args, "-map"); push(&mut args, format!("[{}]", label));
        push(&mut args, format!("-c:v:{}", idx)); push(&mut args, "libx264");
        let br = format!(\"{}k\", rungs[*idx].bitrate_k);
        push(&mut args, format!("-b:v:{}", idx)); push(&mut args, br);
    }

    push(&mut args, "-f"); push(&mut args, "dash");
    push(&mut args, "-use_template"); push(&mut args, "1");
    push(&mut args, "-use_timeline"); push(&mut args, "1");
    push(&mut args, "-seg_duration"); push(&mut args, seg);
    push(&mut args, "-init_seg_name"); push(&mut args, "init_$RepresentationID$.m4s");
    push(&mut args, "-media_seg_name"); push(&mut args, "chunk_$RepresentationID$_$Number$.m4s");
    push(&mut args, mpd.to_str().ok_or_else(|| anyhow!("bad mpd path"))?);

    Ok(args)
}

pub fn pack_hls_auto(input: &Path, out_dir: &Path, segment_seconds: u32) -> Result<()> {
    let rungs = ladder::auto_for_input_path(input)?;
    let args = build_hls_args(input, out_dir, segment_seconds, &rungs)?;
    let status = Command::new(ffmpeg_cmd()).args(args.iter().map(|s| s.as_str())).status()
        .map_err(|e| anyhow!("failed to run ffmpeg: {e}"))?;
    if !status.success() { return Err(anyhow!("ffmpeg HLS failed: {:?}", status)); }
    Ok(())
}

pub fn pack_dash_auto(input: &Path, out_dir: &Path, segment_seconds: u32) -> Result<()> {
    let rungs = ladder::auto_for_input_path(input)?;
    let args = build_dash_args(input, out_dir, segment_seconds, &rungs)?;
    let status = Command::new(ffmpeg_cmd()).args(args.iter().map(|s| s.as_str())).status()
        .map_err(|e| anyhow!("failed to run ffmpeg: {e}"))?;
    if !status.success() { return Err(anyhow!("ffmpeg DASH failed: {:?}", status)); }
    Ok(())
}
""".lstrip()
)

# ---------- 6) mmx-cli/src/main.rs: add --hardware, and pack subcommand ----------
if cli.exists():
    cs = cli.read_text()

    # Import packager
    if "use mmx_core::packager" not in cs:
        cs = re.sub(
            r"(use\s+mmx_core::backend[^\n]*;)",
            r"\1\nuse mmx_core::packager;",
            cs,
            count=1,
        )

    # RunArgs.hardware
    if re.search(r"struct\s+RunArgs\s*\{", cs) and "hardware:" not in cs:
        cs = re.sub(
            r"(struct\s+RunArgs\s*\{)",
            r'\1\n    /// Hardware encoder (vt|nvenc|qsv|vaapi|cpu)\n'
            r'    #[arg(long = "hardware")]\n'
            r"    hardware: Option<String>,",
            cs,
            count=1,
        )

    # Pass hardware into opts (look for a durable anchor)
    if "opts.hardware" not in cs:
        cs = re.sub(
            r"(opts\.progress_json\s*=\s*a\.progress_json\s*;)",
            r"\1\n        opts.hardware = a.hardware.clone();",
            cs,
            count=1,
        )

    # PackArgs struct
    if "struct PackArgs" not in cs:
        cs += """
#[derive(clap::Args, Debug, Clone)]
pub struct PackArgs {
    /// Input media file
    #[arg(long)]
    input: String,
    /// Packager to use: hls|dash
    #[arg(long = "packager", default_value = "hls")]
    packager: String,
    /// HLS output directory (if packager=hls)
    #[arg(long = "hls-out")]
    hls_out: Option<String>,
    /// DASH output directory (if packager=dash)
    #[arg(long = "dash-out")]
    dash_out: Option<String>,
    /// Segment duration (seconds)
    #[arg(long = "segment-duration", default_value_t = 4)]
    segment_duration: u32,
}
"""

    # Command::Pack variant
    if re.search(r"enum\s+Command\s*\{", cs) and "Pack(" not in cs:
        cs = re.sub(r"(enum\s+Command\s*\{\s*)", r"\1\n    Pack(PackArgs),", cs, count=1)

    # cmd_pack handler
    if "fn cmd_pack(" not in cs:
        cs += """
fn cmd_pack(a: PackArgs) -> anyhow::Result<()> {
    match a.packager.as_str() {
        "dash" => {
            let out = a.dash_out.ok_or_else(|| anyhow::anyhow!("use --dash-out <dir>"))?;
            packager::pack_dash_auto(std::path::Path::new(&a.input),
                                     std::path::Path::new(&out),
                                     a.segment_duration)?;
            eprintln!("[pack] wrote DASH to {}", out);
        }
        _ => {
            let out = a.hls_out.ok_or_else(|| anyhow::anyhow!("use --hls-out <dir>"))?;
            packager::pack_hls_auto(std::path::Path::new(&a.input),
                                    std::path::Path::new(&out),
                                    a.segment_duration)?;
            eprintln!("[pack] wrote HLS to {}", out);
        }
    }
    Ok(())
}
"""

    # match branch for Command::Pack
    if "Command::Pack(" not in cs:
        cs = re.sub(
            r"(match\s+cli\.cmd\s*\{\s*)",
            r"\1\n        Command::Pack(a) => cmd_pack(a)?,",
            cs,
            count=1,
        )

    cli.write_text(cs)

print("[ok] Tier-2 complete: hardware flag, auto ladder, HLS+DASH packager, CLI wiring")
