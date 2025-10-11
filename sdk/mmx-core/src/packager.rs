
// 0BSD — Tier-2 minimal packager (ffmpeg fallback)
use anyhow::{anyhow, Result};
use std::process::Command;
use std::path::Path;

#[derive(Clone, Copy, Debug)]
pub enum PackKind { Hls, Dash }

pub fn pack_unified_auto(
    kind: PackKind,
    input: &Path,
    out_dir: &Path,
    segment_seconds: u32,
    _auto_ladder: bool,
    _ladder_spec: Option<&str>,
    _per_shot: bool,
    _tone_map: &str,
) -> Result<()> {
    match kind {
        PackKind::Hls => pack_hls_auto(input, out_dir, segment_seconds),
        PackKind::Dash => pack_dash_auto(input, out_dir, segment_seconds),
    }
}

pub fn pack_hls_auto(input: &Path, out_dir: &Path, segment_seconds: u32) -> Result<()> {
    if !out_dir.exists() { std::fs::create_dir_all(out_dir)?; }
    let ffmpeg = std::env::var("FFMPEG").unwrap_or_else(|_| "ffmpeg".to_string());

    let filter = concat!(
        "[v:0]split=3[v1][v2][v3];",
        "[v1]scale=w=640:h=360:flags=bicubic[v1out];",
        "[v2]scale=w=1280:h=720:flags=bicubic[v2out];",
        "[v3]scale=w=1920:h=1080:flags=bicubic[v3out]"
    );

    let seg_tpl = out_dir.join("v%v_seg%d.ts");
    let out_tpl = out_dir.join("v%v.m3u8");
    let seg_s = seg_tpl.to_str().ok_or_else(|| anyhow!("bad seg path"))?;
    let out_s = out_tpl.to_str().ok_or_else(|| anyhow!("bad out path"))?;
    let segd = segment_seconds.to_string();

    let args = [
        "-y",
        "-i", input.to_str().ok_or_else(|| anyhow!("bad input path"))?,
        "-filter_complex", filter,
        "-map", "[v1out]", "-c:v:0", "libx264", "-b:v:0", "500k",
        "-map", "[v2out]", "-c:v:1", "libx264", "-b:v:1", "1500k",
        "-map", "[v3out]", "-c:v:2", "libx264", "-b:v:2", "3000k",
        "-f", "hls",
        "-hls_time", &segd,
        "-hls_playlist_type", "vod",
        "-master_pl_name", "master.m3u8",
        "-hls_segment_filename", seg_s,
        "-var_stream_map", "v:0,name:360p v:1,name:720p v:2,name:1080p",
        out_s,
    ];

    let st = Command::new(ffmpeg).args(&args).status()
        .map_err(|e| anyhow!("failed to run ffmpeg: {e}"))?;
    if !st.success() { return Err(anyhow!("ffmpeg failed (HLS), status: {:?}", st)); }
    Ok(())
}

pub fn pack_dash_auto(input: &Path, out_dir: &Path, segment_seconds: u32) -> Result<()> {
    if !out_dir.exists() { std::fs::create_dir_all(out_dir)?; }
    let ffmpeg = std::env::var("FFMPEG").unwrap_or_else(|_| "ffmpeg".to_string());

    let filter = concat!(
        "[v:0]split=3[v1][v2][v3];",
        "[v1]scale=w=640:h=360:flags=bicubic[v1out];",
        "[v2]scale=w=1280:h=720:flags=bicubic[v2out];",
        "[v3]scale=w=1920:h=1080:flags=bicubic[v3out]"
    );

    let mpd = out_dir.join("stream.mpd");
    let mpd_s = mpd.to_str().ok_or_else(|| anyhow!("bad out path"))?;
    let segd = segment_seconds.to_string();

    let args = [
        "-y",
        "-i", input.to_str().ok_or_else(|| anyhow!("bad input path"))?,
        "-filter_complex", filter,
        "-map", "[v1out]", "-c:v:0", "libx264", "-b:v:0", "500k",
        "-map", "[v2out]", "-c:v:1", "libx264", "-b:v:1", "1500k",
        "-map", "[v3out]", "-c:v:2", "libx264", "-b:v:2", "3000k",
        "-f", "dash",
        "-seg_duration", &segd,
        "-use_template", "1",
        "-use_timeline", "1",
        "-init_seg_name", "init_$RepresentationID$.m4s",
        "-media_seg_name", "chunk_$RepresentationID$_$Number$.m4s",
        mpd_s,
    ];

    let st = Command::new(ffmpeg).args(&args).status()
        .map_err(|e| anyhow!("failed to run ffmpeg: {e}"))?;
    if !st.success() { return Err(anyhow!("ffmpeg failed (DASH), status: {:?}", st)); }
    Ok(())
}
