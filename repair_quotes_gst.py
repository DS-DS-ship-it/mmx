#!/usr/bin/env python3
# 0BSD — reset mmx-core/lib.rs, backend.rs, backend_gst.rs and mmx-cli/main.rs to a clean, compilable state.

import argparse, pathlib, shutil, subprocess, sys

def w(path: pathlib.Path, txt: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak_ok"))
    path.write_text(txt, encoding="utf-8")
    print(f"[write] {path}")

CORE_LIB_RS = r"""// 0BSD
pub mod probe;
pub mod backend;
pub mod qc;
pub mod shell_escape;
#[cfg(feature="gst")]
pub mod backend_gst;

use serde::{Deserialize, Serialize};

pub use probe::{ProbeReport, FormatInfo, Chapter, VideoStreamInfo, AudioStreamInfo, SubtitleStreamInfo, StreamInfo, PROBE_SCHEMA_VERSION};

#[derive(Debug, thiserror::Error)]
pub enum MmxError { #[error("{0}")] Msg(String) }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HlsVariant {
    pub name: String,
    pub bandwidth: u32,
    pub res: Option<(u32,u32)>,
    pub dir: String,
    pub codecs: Option<String>,
    pub vcodec: Option<String>,
    pub acodec: Option<String>,
    pub vbv_maxrate: Option<u32>,
    pub vbv_bufsize: Option<u32>,
    pub gop: Option<i32>,
    pub profile: Option<String>,
    pub encoder_family: Option<String>,
    pub abitrate: Option<u32>,
    pub cmaf: Option<bool>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AudioVariant {
    pub name: String, pub group: String, pub lang: String, pub dir: String,
    pub acodec: String, pub bandwidth: u32, pub default: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum Packager { #[serde(rename="hls-ts")] HlsTs, #[serde(rename="hls-cmaf")] HlsCmaf, #[serde(rename="dash-cmaf")] DashCmaf }
impl Default for Packager { fn default()->Self { Packager::HlsTs } }

pub fn codecs_tag(video: &str, audio: &str, profile: Option<&str>) -> String {
    let v = match video {
        "h265" | "hevc" => "hvc1.1.6.L123.B0".to_string(),
        "av1" => "av01.0.08M.08".to_string(),
        "vp9" => "vp09.00.50.08".to_string(),
        _ => match profile { Some("high")=>"avc1.64002A".into(), Some("main")=>"avc1.4D4029".into(), _=>"avc1.4D401F".into() }
    };
    let a = match audio { "opus"=>"opus", "ac3"=>"ac-3", "eac3"=>"ec-3", "flac"=>"fLaC", _=>"mp4a.40.2" };
    format!("{},{}", v, a)
}
pub fn derive_bandwidth(vbv_maxrate: Option<u32>, enc_bitrate: Option<u32>, abitrate: Option<u32>, res: Option<(u32,u32)>) -> u32 {
    let vbv = vbv_maxrate.or(enc_bitrate).unwrap_or_else(|| match res {
        Some((w,h)) if w>=1920 || h>=1080 => 5_000_000,
        Some((w,h)) if w>=1280 || h>=720  => 3_000_000,
        _ => 1_600_000,
    });
    let ab = abitrate.unwrap_or(128_000);
    ((vbv + ab) as f64 * 1.10) as u32
}
pub fn write_hls_master(path:&std::path::Path, variants:&[(String,u32,Option<(u32,u32)>,String,String,Option<String>)], audios:&[(String,String,String,bool,String,String)]) -> anyhow::Result<()> {
    use std::io::Write;
    if let Some(parent) = path.parent(){ std::fs::create_dir_all(parent)?; }
    let mut s=String::from("#EXTM3U\n#EXT-X-VERSION:7\n");
    for (group,name,lang,default,dir,file) in audios {
        let def=if *default {"YES"} else {"NO"};
        s.push_str(&format!(r#"#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="{group}",NAME="{name}",LANGUAGE="{lang}",DEFAULT={def},AUTOSELECT=YES,URI="{dir}/{file}""#));
        s.push('\n');
    }
    for (name,bw,res,dir,codecs,audio_group) in variants {
        let audio_attr = audio_group.as_ref().map(|g| format!(r#",AUDIO="{g}""#)).unwrap_or_default();
        let uri = format!("{dir}/{name}.m3u8");
        if let Some((w,h))=res {
            s.push_str(&format!(r#"#EXT-X-STREAM-INF:BANDWIDTH={bw},RESOLUTION={w}x{h},CODECS="{codecs}"{audio_attr}"#));
        } else {
            s.push_str(&format!(r#"#EXT-X-STREAM-INF:BANDWIDTH={bw},CODECS="{codecs}"{audio_attr}"#));
        }
        s.push('\n'); s.push_str(&uri); s.push('\n');
    }
    let mut f=std::fs::File::create(path)?; f.write_all(s.as_bytes())?; Ok(())
}
pub fn write_hls_variant_playlist(base_dir:&std::path::Path, name:&str, cmaf:bool)->anyhow::Result<()>{
    use std::io::Write; std::fs::create_dir_all(base_dir)?;
    let ext=if cmaf {"m4s"} else {"ts"};
    let mut s=String::from("#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-TARGETDURATION:4\n#EXT-X-PLAYLIST-TYPE:VOD\n");
    for i in 0..5u32 { s.push_str(&format!("#EXTINF:4.0,\n{n}_{i:05}.{ext}\n", n=name, i=i, ext=ext)); }
    let mut f=std::fs::File::create(base_dir.join(format!("{name}.m3u8")))?; f.write_all(s.as_bytes())?; Ok(())
}
pub fn write_audio_playlist(base_dir:&std::path::Path, name:&str)->anyhow::Result<()>{
    use std::io::Write; std::fs::create_dir_all(base_dir)?;
    let mut s=String::from("#EXTM3U\n#EXT-X-VERSION:7\n#EXT-X-TARGETDURATION:4\n#EXT-X-PLAYLIST-TYPE:VOD\n");
    for i in 0..5u32 { s.push_str(&format!("#EXTINF:4.0,\n{n}_{i:05}.m4s\n", n=name, i=i)); }
    let mut f=std::fs::File::create(base_dir.join(format!("{name}.m3u8")))?; f.write_all(s.as_bytes())?; Ok(())
}
pub fn write_dash_mpd(path:&std::path::Path, v_reps:&[(String,u32,Option<(u32,u32)>,String,String)], a_rep:Option<(String,u32,String)>) -> anyhow::Result<()> {
    use std::io::Write; if let Some(parent)=path.parent(){ std::fs::create_dir_all(parent)?; }
    let mut s=String::new();
    s.push_str(r#"<?xml version="1.0" encoding="UTF-8"?>"#);
    s.push_str(r#"<MPD xmlns="urn:mpeg:DASH:schema:MPD:2011" type="static" minBufferTime="PT2S" profiles="urn:mpeg:dash:profile:isoff-main:2011">"#);
    s.push_str(r#"<Period start="PT0S">"#);
    s.push_str(r#"<AdaptationSet contentType="video" mimeType="video/mp4" startWithSAP="1">"#);
    for (name,bw,res,dir,codecs) in v_reps {
        let (w,h)=res.unwrap_or((0,0));
        s.push_str(&format!(r#"<Representation id="{name}" bandwidth="{bw}" codecs="{codecs}" width="{w}" height="{h}">"#));
        s.push_str(&format!(r#"<BaseURL>{}/</BaseURL>"#, dir));
        s.push_str(r#"<SegmentTemplate media="$RepresentationID$_$Number$.m4s" initialization="$RepresentationID$_init.mp4" duration="4" startNumber="0"/>"#);
        s.push_str(r#"</Representation>"#);
    }
    s.push_str(r#"</AdaptationSet>"#);
    if let Some((name,bw,dir))=a_rep {
        s.push_str(r#"<AdaptationSet contentType="audio" mimeType="audio/mp4" startWithSAP="1">"#);
        s.push_str(&format!(r#"<Representation id="{name}" bandwidth="{bw}" codecs="mp4a.40.2">"#));
        s.push_str(&format!(r#"<BaseURL>{}/</BaseURL>"#, dir));
        s.push_str(r#"<SegmentTemplate media="$RepresentationID$_$Number$.m4s" initialization="$RepresentationID$_init.mp4" duration="4" startNumber="0"/>"#);
        s.push_str(r#"</Representation></AdaptationSet>"#);
    }
    s.push_str(r#"</Period></MPD>"#);
    let mut f=std::fs::File::create(path)?; f.write_all(s.as_bytes())?; Ok(())
}
"""

CORE_BACKEND_RS = r"""// 0BSD
use anyhow::Result;

#[derive(Debug, Clone)]
pub struct RunOptions {
    pub input: String,
    pub output: String,
    pub backend: String,          // "mock" | "gst" | "vt" | "vaapi" | "nvenc" | "qsv"
    pub graph: Option<String>,    // ffmpeg-like filtergraph
    pub graph_json: Option<String>,
    pub cfr: bool,
    pub fps: Option<u32>,
    pub propagate_color: bool,
    pub detect_bt2020_pq: bool,
    pub subtitles_mode: Option<String>, // "list"|"copy"|"convert:ass->webvtt"|"burn"
    pub streaming_mode: Option<String>, // "rtmp"|"srt"|"whip"|"hls-ll"|"dash-live"
    pub zero_copy: bool,
    pub gpu_preset: Option<String>,
    pub resume: bool,
    pub progress: bool,
}
impl Default for RunOptions {
    fn default() -> Self {
        Self {
            input: String::new(),
            output: String::new(),
            backend: "mock".into(),
            graph: None, graph_json: None,
            cfr: false, fps: None,
            propagate_color: true, detect_bt2020_pq: true,
            subtitles_mode: None, streaming_mode: None,
            zero_copy: false, gpu_preset: None,
            resume: true, progress: true,
        }
    }
}

#[derive(Debug, Clone)]
pub struct QcOptions {
    pub ref_path: String,
    pub dist_path: String,
    pub want_psnr: bool,
    pub want_ssim: bool,
    pub want_vmaf: bool,
}

pub trait Backend {
    fn name(&self) -> &'static str;
    fn run(&self, opts: &RunOptions) -> Result<()>;
    fn probe(&self, path: &str) -> Result<crate::probe::ProbeReport>;
    fn qc(&self, _opts: &QcOptions) -> Result<crate::qc::QcReport> {
        Ok(crate::qc::QcReport {
            psnr: None, ssim: None, vmaf: None,
            details: "QC not implemented for this backend; returning None".into()
        })
    }
}

pub struct MockBackend;

impl Backend for MockBackend {
    fn name(&self) -> &'static str { "mock" }
    fn run(&self, opts: &RunOptions) -> Result<()> {
        println!("[mock] RUN planning:");
        println!("  input={} output={}", opts.input, opts.output);
        println!("  backend={} zero_copy={} gpu_preset={:?}", opts.backend, opts.zero_copy, opts.gpu_preset);
        println!("  graph={:?} graph_json-len={}", opts.graph, opts.graph_json.as_ref().map(|s| s.len()).unwrap_or(0));
        println!("  cfr={} fps={:?}", opts.cfr, opts.fps);
        println!("  color_propagation={} detect_bt2020_pq={}", opts.propagate_color, opts.detect_bt2020_pq);
        println!("  subtitles_mode={:?} streaming_mode={:?}", opts.subtitles_mode, opts.streaming_mode);
        println!("  resume={} progress={}", opts.resume, opts.progress);
        println!("(No real media pipeline in 'mock' backend.)");
        Ok(())
    }
    fn probe(&self, path: &str) -> Result<crate::probe::ProbeReport> {
        crate::probe::cheap_probe(path)
    }
    fn qc(&self, opts: &QcOptions) -> Result<crate::qc::QcReport> {
        crate::qc::cheap_qc(opts)
    }
}

#[cfg(feature="gst")]
use crate::backend_gst::GstBackend;

pub fn find_backend(name: &str) -> Box<dyn Backend + Send> {
    match name {
        #[cfg(feature="gst")]
        "gst" => Box::new(GstBackend),
        _ => Box::new(MockBackend),
    }
}
"""

CORE_BACKEND_GST_RS = r"""// 0BSD — GStreamer backend (feature-gated)
#![cfg(feature = "gst")]

use anyhow::{anyhow, Result};
use gstreamer as gst;
use gstreamer::prelude::*;
use gstreamer_pbutils as pbutils;

use crate::backend::{Backend, RunOptions, QcOptions};
use crate::probe::{self, ProbeReport, FormatInfo, StreamInfo, VideoStreamInfo, AudioStreamInfo, SubtitleStreamInfo};
use std::collections::BTreeMap;

pub struct GstBackend;

impl GstBackend {
    fn ensure_inited() -> Result<()> {
        if gst::is_initialized() { return Ok(()); }
        gst::init()?;
        Ok(())
    }

    fn discover(path: &str) -> Result<ProbeReport> {
        Self::ensure_inited()?;
        let disc = pbutils::Discoverer::new(gst::ClockTime::from_seconds(15))
            .map_err(|e| anyhow!("{e:?}"))?;
        let info = disc.discover_uri(&format!("file://{}", path))?;
        let uri = info.uri().unwrap_or_default().to_string();

        let mut fmt_tags = BTreeMap::new();
        fmt_tags.insert("source".into(), "gstreamer-discoverer".into());

        let duration = info.duration().map(|d| d.nseconds() as f64 / 1_000_000_000.0);
        let container = info.container_info()
            .and_then(|c| c.get_caps())
            .and_then(|caps| caps.structure(0))
            .map(|s| s.name().to_string())
            .unwrap_or_else(|| "unknown".into());

        let mut streams = Vec::<StreamInfo>::new();
        for s in info.stream_info_list() {
            match s {
                pbutils::DiscovererStreamInfo::Video(vi) => {
                    let caps = vi.get_caps();
                    let codec = caps.as_ref()
                        .and_then(|c| c.structure(0))
                        .map(|st| st.name().to_string())
                        .unwrap_or_else(|| "video/unknown".into());
                    let mut w = 0u32;
                    let mut h = 0u32;
                    let mut fps = None;
                    if let Some(vinfo) = vi.video_info() {
                        w = vinfo.width();
                        h = vinfo.height();
                        if let Some(fr) = vinfo.fps() {
                            fps = Some(fr.numer() as f64 / fr.denom() as f64);
                        }
                    }
                    let tags_map = BTreeMap::new();
                    streams.push(StreamInfo::Video(VideoStreamInfo {
                        index: 0, codec, width: w, height: h,
                        fps, color_primaries: None, color_trc: None,
                        color_matrix: None, hdr: None, tags: tags_map,
                    }));
                }
                pbutils::DiscovererStreamInfo::Audio(ai) => {
                    let caps = ai.get_caps();
                    let codec = caps.as_ref()
                        .and_then(|c| c.structure(0))
                        .map(|st| st.name().to_string())
                        .unwrap_or_else(|| "audio/unknown".into());
                    let tags_map = BTreeMap::new();
                    streams.push(StreamInfo::Audio(AudioStreamInfo {
                        index: 0, codec,
                        sample_rate: 48000, channels: 2,
                        channel_layout: None, bit_rate: None,
                        tags: tags_map,
                    }));
                }
                pbutils::DiscovererStreamInfo::Subtitle(si) => {
                    let caps = si.get_caps();
                    let codec = caps.as_ref()
                        .and_then(|c| c.structure(0))
                        .map(|st| st.name().to_string())
                        .unwrap_or_else(|| "sub/unknown".into());
                    let tags_map = BTreeMap::new();
                    streams.push(StreamInfo::Subtitle(SubtitleStreamInfo {
                        index: 0, codec,
                        language: None, hearing_impaired: None,
                        tags: tags_map,
                    }));
                }
                _ => {}
            }
        }

        Ok(ProbeReport {
            schema_version: probe::PROBE_SCHEMA_VERSION.to_string(),
            path: uri,
            format: FormatInfo {
                format_name: container,
                duration_sec: duration,
                size_bytes: None,
                bit_rate: None,
                tags: fmt_tags,
            },
            streams,
            chapters: vec![],
            warnings: vec![],
        })
    }

    fn build_pipeline_string(opts: &RunOptions) -> String {
        let mut chain = vec![format!("filesrc location={} ! decodebin", opts.input)];
        if opts.cfr || opts.fps.is_some() {
            let fps = opts.fps.unwrap_or(30);
            chain.push(format!("videorate ! video/x-raw,framerate={}/1", fps));
        }
        chain.push("x264enc tune=zerolatency ! mp4mux ! filesink".into());
        chain.push(format!("location={}", opts.output));
        chain.join(" ! ")
    }
}

impl Backend for GstBackend {
    fn name(&self) -> &'static str { "gst" }
    fn run(&self, opts: &RunOptions) -> Result<()> {
        Self::ensure_inited()?;
        let pipe = Self::build_pipeline_string(opts);
        println!("[gst] planned pipeline:\n  {}", pipe);
        Ok(())
    }
    fn probe(&self, path: &str) -> Result<ProbeReport> {
        Self::discover(path)
    }
    fn qc(&self, _opts: &QcOptions) -> Result<crate::qc::QcReport> {
        Ok(crate::qc::QcReport {
            psnr: None, ssim: None, vmaf: None,
            details: "QC via gst not yet implemented".into(),
        })
    }
}
"""

CLI_MAIN_RS = r"""// 0BSD
use anyhow::{Context, Result};
use clap::{Parser, Subcommand, Args, ValueEnum};
use mmx_core::{
    HlsVariant, AudioVariant, Packager, codecs_tag, derive_bandwidth,
    write_hls_master, write_hls_variant_playlist, write_audio_playlist, write_dash_mpd,
    backend::{find_backend, RunOptions, QcOptions},
    probe::{ProbeReport, PROBE_SCHEMA_VERSION},
};

#[derive(Parser)]
#[command(name="mmx", version, about="Modern Multimedia eXchange — CLI")]
struct Cli {
    #[arg(long, default_value="info")]
    log: String,
    #[command(subcommand)]
    cmd: Command,
}

#[derive(Subcommand)]
enum Command {
    Pack(PackArgs),
    Ladder(LadderArgs),
    Probe(ProbeArgs),
    Run(RunArgs),
    Qc(QcArgs),
}

#[derive(Args)]
struct PackArgs {
    #[arg(long, default_value="out")] out_dir: String,
    #[arg(long, default_value="hls-ts")] packager: String,
    #[arg(long)] ladder: Option<String>,
    #[arg(long)] hls_variants_json: Option<String>,
    #[arg(long)] audio_variants_json: Option<String>,
}
#[derive(Args)] struct LadderArgs { #[arg(long)] ladder: String }
#[derive(Clone, ValueEnum)]
enum BackendKind { Gst, Vt, Vaapi, Nvenc, Qsv, Mock }
impl BackendKind {
    fn as_str(&self)->&'static str {
        match self { Self::Gst=>"gst", Self::Vt=>"vt", Self::Vaapi=>"vaapi", Self::Nvenc=>"nvenc", Self::Qsv=>"qsv", Self::Mock=>"mock" }
    }
}
#[derive(Args)] struct ProbeArgs { #[arg(long)] input: String, #[arg(long, value_enum, default_value="mock")] backend: BackendKind }

#[derive(Args)]
struct RunArgs {
    #[arg(long)] input: String,
    #[arg(long, default_value="out.mp4")] output: String,
    #[arg(long, value_enum, default_value="mock")] backend: BackendKind,
    #[arg(long)] graph: Option<String>,
    #[arg(long)] graph_json: Option<String>,
    #[arg(long)] cfr: bool,
    #[arg(long)] fps: Option<u32>,
    #[arg(long, default_value_t=true)] propagate_color: bool,
    #[arg(long, default_value_t=true)] detect_bt2020_pq: bool,
    #[arg(long)] subtitles_mode: Option<String>,
    #[arg(long)] streaming_mode: Option<String>,
    #[arg(long)] zero_copy: bool,
    #[arg(long)] gpu_preset: Option<String>,
    #[arg(long, default_value_t=true)] resume: bool,
    #[arg(long, default_value_t=true)] progress: bool,
}

#[derive(Args)]
struct QcArgs {
    #[arg(long, value_name="REF_PATH")] ref_path: String,
    #[arg(long, value_name="DIST_PATH")] dist_path: String,
    #[arg(long)] psnr: bool,
    #[arg(long)] ssim: bool,
    #[arg(long)] vmaf: bool,
}

fn parse_ladder(s: &str) -> Result<Vec<(String,(u32,u32),u32)>> {
    fn res(label:&str)->Option<(u32,u32)> {
        match label {
            "2160p" => Some((3840,2160)), "1440p" => Some((2560,1440)),
            "1080p" => Some((1920,1080)), "720p"  => Some((1280,720)),
            "540p"  => Some((960,540)),   "480p"  => Some((854,480)),
            "360p"  => Some((640,360)),   _ => None
        }
    }
    fn bw(v:&str)->Option<u32>{
        let u=v.to_uppercase();
        if u.ends_with('M'){ u[..u.len()-1].parse::<f32>().ok().map(|m| (m*1_000_000.0) as u32) }
        else if u.ends_with('K'){ u[..u.len()-1].parse::<f32>().ok().map(|k| (k*1_000.0) as u32) }
        else { v.parse::<u32>().ok() }
    }
    let mut out=vec![];
    for term in s.split(',') {
        let (label,b)=term.split_once(':').context("use label:bitrate")?;
        let r = res(label).context("unknown rung label")?;
        let bb = bw(b).context("bad bitrate")?;
        out.push((label.to_string(), r, bb));
    }
    Ok(out)
}

fn ladder_to_variants(ladder:&str)->Result<Vec<HlsVariant>>{
    let rows = parse_ladder(ladder)?;
    Ok(rows.into_iter().map(|(name,res,_bw)| HlsVariant{
        name, bandwidth: 0, res: Some(res), dir: format!("out/{}p", res.1),
        codecs: None, vcodec: None, acodec: None, vbv_maxrate: None, vbv_bufsize: None,
        gop: None, profile: None, encoder_family: None, abitrate: None, cmaf: None,
    }).collect())
}

fn parse_packager(s:&str)->mmx_core::Packager{
    match s {
        "hls-ts" => mmx_core::Packager::HlsTs,
        "hls-cmaf" => mmx_core::Packager::HlsCmaf,
        "dash-cmaf" => mmx_core::Packager::DashCmaf,
        _ => mmx_core::Packager::HlsTs
    }
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.cmd {
        Command::Pack(a) => cmd_pack(a),
        Command::Ladder(a) => cmd_ladder(a),
        Command::Probe(a) => cmd_probe(a),
        Command::Run(a) => cmd_run(a),
        Command::Qc(a) => cmd_qc(a),
    }
}

fn cmd_ladder(a: LadderArgs) -> Result<()> {
    let vars = ladder_to_variants(&a.ladder)?;
    println!("Expanded ladder:");
    for v in vars { println!("  {}  dir={}  res={:?}", v.name, v.dir, v.res); }
    Ok(())
}

fn cmd_probe(a: ProbeArgs) -> Result<()> {
    let be = find_backend(a.backend.as_str());
    let rep: ProbeReport = be.probe(&a.input)?;
    println!("{}", serde_json::to_string_pretty(&rep)?);
    Ok(())
}

fn cmd_run(a: RunArgs) -> Result<()> {
    let mut opts = RunOptions::default();
    opts.input = a.input; opts.output = a.output; opts.backend = a.backend.as_str().to_string();
    opts.graph = a.graph; opts.graph_json = a.graph_json; opts.cfr = a.cfr; opts.fps = a.fps;
    opts.propagate_color = a.propagate_color; opts.detect_bt2020_pq = a.detect_bt2020_pq;
    opts.subtitles_mode = a.subtitles_mode; opts.streaming_mode = a.streaming_mode;
    opts.zero_copy = a.zero_copy; opts.gpu_preset = a.gpu_preset; opts.resume = a.resume; opts.progress = a.progress;
    let be = find_backend(&opts.backend);
    be.run(&opts)
}

fn cmd_qc(a: QcArgs) -> Result<()> {
    let be = find_backend("mock");
    let rep = be.qc(&QcOptions{
        ref_path: a.ref_path, dist_path: a.dist_path,
        want_psnr: a.psnr, want_ssim: a.ssim, want_vmaf: a.vmaf,
    })?;
    println!("{}", serde_json::to_string_pretty(&rep)?);
    Ok(())
}

fn cmd_pack(a: PackArgs) -> Result<()> {
    let mut variants: Vec<HlsVariant> = if let Some(j) = a.hls_variants_json.as_ref() {
        serde_json::from_str(j).context("--hls-variants-json bad JSON")?
    } else if let Some(l) = a.ladder.as_ref() {
        ladder_to_variants(l)?
    } else {
        ladder_to_variants("720p:3M,480p:1.6M")?
    };
    let audios: Vec<AudioVariant> = if let Some(j) = a.audio_variants_json.as_ref() {
        serde_json::from_str(j).context("--audio-variants-json bad JSON")?
    } else { vec![] };

    let packager = parse_packager(&a.packager);

    let mut built_video: Vec<(String,u32,Option<(u32,u32)>,String,String,Option<String>,bool)> = vec![];
    for v in &mut variants {
        if let mmx_core::Packager::HlsCmaf = packager { if v.cmaf.is_none() { v.cmaf = Some(true); } }
        let vcodec = v.vcodec.clone().unwrap_or_else(|| "h264".into());
        let acodec = v.acodec.clone().unwrap_or_else(|| "aac".into());
        let abitrate = v.abitrate.unwrap_or(128_000);
        if v.bandwidth == 0 {
            let enc_bitrate = v.vbv_maxrate;
            v.bandwidth = mmx_core::derive_bandwidth(v.vbv_maxrate, enc_bitrate, Some(abitrate), v.res);
        }
        let codecs = v.codecs.clone().unwrap_or_else(|| mmx_core::codecs_tag(&vcodec, &acodec, v.profile.as_deref()));
        built_video.push((v.name.clone(), v.bandwidth, v.res, v.dir.clone(), codecs, None::<String>, v.cmaf.unwrap_or(false)));
    }
    let mut built_audio: Vec<(String,String,String,bool,String,String)> = vec![];
    if !audios.is_empty() {
        let group = audios.first().map(|a| a.group.clone()).unwrap_or_else(|| "aud_stereo".into());
        for b in &mut built_video { b.5 = Some(group.clone()); }
        for adef in &audios {
            let dir = std::path::Path::new(&adef.dir);
            mmx_core::write_audio_playlist(dir, &adef.name)?;
            built_audio.push((adef.group.clone(), adef.name.clone(), adef.lang.clone(), adef.default, adef.dir.clone(), format!("{}.m3u8", adef.name)));
        }
    }
    let out_root = std::path::Path::new(&a.out_dir);
    match packager {
        mmx_core::Packager::HlsTs => {
            for (name, _bw, _res, dir, _codecs, _ag, _cmaf) in &built_video {
                let vdir = out_root.join(dir); mmx_core::write_hls_variant_playlist(&vdir, name, false)?;
            }
            let master_path = out_root.join("master.m3u8");
            let shaped: Vec<_> = built_video.iter().map(|b| (b.0.clone(), b.1, b.2, b.3.clone(), b.4.clone(), b.5.clone())).collect();
            mmx_core::write_hls_master(&master_path, &shaped, &built_audio)?;
        }
        mmx_core::Packager::HlsCmaf => {
            for (name, _bw, _res, dir, _codecs, _ag, _cmaf) in &built_video {
                let vdir = out_root.join(dir); mmx_core::write_hls_variant_playlist(&vdir, name, true)?;
            }
            let master_path = out_root.join("master.m3u8");
            let shaped: Vec<_> = built_video.iter().map(|b| (b.0.clone(), b.1, b.2, b.3.clone(), b.4.clone(), b.5.clone())).collect();
            mmx_core::write_hls_master(&master_path, &shaped, &built_audio)?;
        }
        mmx_core::Packager::DashCmaf => {
            let v_reps: Vec<_> = built_video.iter().map(|b| (b.0.clone(), b.1, b.2, b.3.clone(), b.4.clone())).collect();
            for (_n,_bw,_r,dir,_c) in &v_reps { std::fs::create_dir_all(out_root.join(dir))?; }
            let a_rep = built_audio.first().map(|(_g,n,_lang,_def,dir,_file)| (n.clone(), 128_000u32, dir.clone()));
            let mpd = out_root.join("manifest.mpd");
            mmx_core::write_dash_mpd(&mpd, &v_reps, a_rep)?;
        }
    }
    println!("ABR validation report:");
    println!("  Packager: {}", a.packager);
    for (name, bw, res, dir, codecs, ag, cmaf) in &built_video {
        let res_s = res.map(|(w,h)| format!("{}x{}", w,h)).unwrap_or_else(|| "-".into());
        let ags = ag.clone().unwrap_or_else(|| "-".into());
        println!("  - {name:<8} bw={bw} res={res_s:<10} dir={dir:<20} codecs={codecs} audio_group={ags} cmaf={cmaf}");
    }
    if !built_audio.is_empty() {
        println!("  Audio groups:");
        for (g,n,lang,def,dir,file) in &built_audio {
            println!("  - group={g} name={n} lang={lang} default={} uri={}/{}", if *def {"YES"} else {"NO"}, dir, file);
        }
    }
    println!("Outputs written under: {}", out_root.display());
    Ok(())
}
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()
    root = pathlib.Path(args.dir).resolve()

    w(root/"mmx-core"/"src"/"lib.rs", CORE_LIB_RS)
    w(root/"mmx-core"/"src"/"backend.rs", CORE_BACKEND_RS)
    w(root/"mmx-core"/"src"/"backend_gst.rs", CORE_BACKEND_GST_RS)
    w(root/"mmx-cli"/"src"/"main.rs", CLI_MAIN_RS)

    print("\n[hint] Now rebuild:")
    print("  cd", root)
    print("  cargo build")
    print("  cargo build -p mmx-cli -F mmx-core/gst")
    print("  target/debug/mmx probe --backend gst --input ./LICENSE")
    print("  target/debug/mmx run --backend gst --input in.mp4 --output out.mp4 --cfr --fps 30")

if __name__ == "__main__":
    main()
