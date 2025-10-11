use anyhow::{bail, Result};
use clap::{Args, Parser, Subcommand};
use mmx_core::backend::{self, QcOptions, RunOptions};
use mmx_core::packager::{self, PackKind};

fn which_path(bin: &str) -> Option<String> {
    // ENV override: FFMPEG/FFPROBE/GST-LAUNCH-1.0 or variants
    let env_key = bin.to_uppercase().replace('-', "_").replace('.', "_");
    if let Ok(p) = std::env::var(&env_key) {
        let p = p.trim();
        if !p.is_empty() && std::path::Path::new(p).is_file() {
            return Some(p.to_string());
        }
    }
    // PATH search
    let path = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path) {
        if dir.as_os_str().is_empty() { continue; }
        #[cfg(windows)]
        {
            for ext in ["", ".exe", ".bat", ".cmd"] {
                let cand = dir.join(format!("{bin}{ext}"));
                if cand.is_file() { return Some(cand.to_string_lossy().to_string()); }
            }
        }
        #[cfg(not(windows))]
        {
            let cand = dir.join(bin);
            if cand.is_file() { return Some(cand.to_string_lossy().to_string()); }
        }
    }
    None
}

#[derive(Parser, Debug)]
#[command(name = "mmx")]
#[command(about = "MMX — media swiss-army CLI")]
struct Cli {
    #[command(subcommand)]
    cmd: Command,
}

#[derive(Subcommand, Debug)]
pub enum Command {
    /// Copy container/streams quickly (ffmpeg)
    Remux(RemuxArgs),
    /// Run a transcode with a chosen backend
    Run(RunArgs),
    /// Probe input media (add --enhanced to use ffprobe JSON)
    Probe(ProbeArgs),
    /// Quality check between two files (PSNR/SSIM; falls back to ffmpeg if needed)
    Qc(QcArgs),
    /// Package for streaming (HLS/DASH)
    Pack(PackArgs),
    /// Environment + dependency health check
    Doctor(DoctorArgs),
}

#[derive(Args, Debug, Clone)]
pub struct RunArgs {
    /// Backend name (gst)
    #[arg(long = "backend")]
    backend: String,
    /// Input path
    #[arg(long = "input")]
    input: String,
    /// Output path
    #[arg(long = "output")]
    output: String,
    /// Constant frame rate
    #[arg(long, default_value_t = false)]
    cfr: bool,
    /// Output FPS (when CFR)
    #[arg(long)]
    fps: Option<u32>,
    /// Execute the graph
    #[arg(long, default_value_t = false)]
    execute: bool,
    /// Job manifest path (optional)
    #[arg(long)]
    manifest: Option<String>,
    /// Stream JSON Lines progress to stdout
    #[arg(long = "progress-json", default_value_t = false)]
    progress_json: bool,
    /// Hardware encoder (vt|nvenc|qsv|vaapi|cpu)
    #[arg(long = "hardware")]
    hardware: Option<String>,
}

#[derive(Args, Debug, Clone)]
pub struct ProbeArgs {
    /// Input media file
    #[arg(long)]
    input: String,
    /// Use ffprobe and print the full JSON (format + streams)
    #[arg(long, default_value_t = false)]
    enhanced: bool,
}

#[derive(Args, Debug, Clone)]
pub struct QcArgs {
    /// Reference file
    #[arg(long = "ref-path")]
    ref_path: String,
    /// Distorted/comparison file
    #[arg(long = "dist-path")]
    dist_path: String,
    /// Compute PSNR
    #[arg(long, default_value_t = false)]
    psnr: bool,
    /// Compute SSIM
    #[arg(long, default_value_t = false)]
    ssim: bool,
    /// Optional VMAF model path (passthrough to core; ignored by ffmpeg fallback)
    #[arg(long = "vmaf-model")]
    vmaf_model: Option<String>,
}

#[derive(Args, Debug, Clone)]
pub struct PackArgs {
    /// Input media file
    #[arg(long)]
    input: String,
    /// Packager kind: hls | dash
    #[arg(long, default_value = "hls")]
    packager: String,
    /// Output directory for HLS
    #[arg(long = "hls-out")]
    hls_out: Option<String>,
    /// Output directory for DASH
    #[arg(long = "dash-out")]
    dash_out: Option<String>,
    /// Segment duration (seconds)
    #[arg(long = "segment-duration", default_value_t = 4)]
    segment_duration: u32,
    /// Suggest a ladder automatically
    #[arg(long = "auto-ladder", default_value_t = true)]
    auto_ladder: bool,
    /// Explicit ladder spec
    #[arg(long = "ladder")]
    ladder: Option<String>,
    /// Enable per-shot analysis (placeholder)
    #[arg(long = "per-shot", default_value_t = false)]
    per_shot: bool,
    /// Tone-map policy: auto|off (placeholder)
    #[arg(long = "tone-map", default_value = "auto")]
    tone_map: String,
}

#[derive(Args, Debug, Clone)]
pub struct DoctorArgs {
    /// Print JSON (machine-readable)
    #[arg(long, default_value_t = false)]
    json: bool,
}

#[derive(clap::Args, Debug, Clone)]
pub struct RemuxArgs {
    /// Input file
    #[arg(long)]
    pub input: String,
    /// Output file
    #[arg(long)]
    pub output: String,
    /// Optional start seconds (trim-in)
    #[arg(long)]
    pub ss: Option<f64>,
    /// Optional end seconds (trim-out)
    #[arg(long)]
    pub to: Option<f64>,
    /// ffmpeg-like mapping (e.g. "0:v:0,0:a?,0:s?")
    #[arg(long, default_value = "0:v:0,0:a?,0:s?")]
    pub stream_map: String,
}

/* ---------- Commands ---------- */

fn cmd_run(a: RunArgs) -> Result<()> {
    let mut opts = RunOptions::default();
    opts.backend = a.backend;
    opts.input = a.input;
    opts.output = a.output;
    opts.cfr = a.cfr;
    opts.fps = a.fps;
    opts.execute = a.execute;
    opts.manifest = a.manifest.map(std::path::PathBuf::from);
    opts.progress_json = a.progress_json;
    opts.hardware = a.hardware;
    backend::run(opts)
}

fn ffprobe_json(input: &str) -> Result<String> {
    let ffprobe = which_path("ffprobe")
        .or_else(|| std::env::var("FFPROBE").ok())
        .ok_or_else(|| anyhow::anyhow!("ffprobe not found in PATH (or FFPROBE env)"))?;
    let out = std::process::Command::new(&ffprobe)
        .args(["-v","error","-show_format","-show_streams","-print_format","json", input])
        .output()
        .map_err(|e| anyhow::anyhow!("failed to run ffprobe: {e}"))?;
    if !out.status.success() {
        bail!("ffprobe failed with status {}", out.status);
    }
    Ok(String::from_utf8_lossy(&out.stdout).to_string())
}

fn cmd_probe(a: ProbeArgs) -> Result<()> {
    if a.enhanced {
        let js = ffprobe_json(&a.input)?;
        println!("{js}");
        return Ok(());
    }
    let rep = backend::probe(&a.input)?;
    println!("{}", serde_json::to_string_pretty(&rep)?);
    Ok(())
}

fn qc_via_ffmpeg(refp: &str, distp: &str, want_psnr: bool, want_ssim: bool) -> Result<()> {
    let ff = which_path("ffmpeg")
        .or_else(|| std::env::var("FFMPEG").ok())
        .ok_or_else(|| anyhow::anyhow!("ffmpeg not found in PATH (or FFMPEG env)"))?;
    if !want_psnr && !want_ssim {
        bail!("qc: specify at least one of --psnr or --ssim");
    }
    // Build lavfi chain
    let mut filters = Vec::new();
    if want_ssim { filters.push("[0:v][1:v]ssim"); }
    if want_psnr { filters.push("[0:v][1:v]psnr"); }
    let chain = filters.join(";");
    let out = std::process::Command::new(&ff)
        .args([
            "-hide_banner","-nostdin","-v","error",
            "-i", refp, "-i", distp,
            "-lavfi", &chain,
            "-f","null","-"
        ])
        .output()
        .map_err(|e| anyhow::anyhow!("failed to run ffmpeg: {e}"))?;

    let stdout = String::from_utf8_lossy(&out.stdout);
    let stderr = String::from_utf8_lossy(&out.stderr);
    let text = format!("{stdout}\n{stderr}");

    // Very light parse (best-effort)
    let mut psnr_all = None::<f64>;
    let mut ssim_all = None::<f64>;
    for line in text.lines() {
        // PSNR lines often contain "average:" or "all:"
        if want_psnr && line.to_lowercase().contains("psnr") && line.to_lowercase().contains("all:") {
            // try to find "all:XX.XXX"
            if let Some(idx) = line.to_lowercase().find("all:") {
                let rest = &line[idx+4..];
                let num: String = rest.chars().take_while(|c| c.is_ascii_digit() || *c=='.' || *c=='-').collect();
                if let Ok(v) = num.parse::<f64>() { psnr_all = Some(v); }
            }
        }
        // SSIM lines often contain "All:"
        if want_ssim && (line.contains("SSIM") || line.contains("ssim")) && line.contains("All:") {
            if let Some(idx) = line.find("All:") {
                let rest = &line[idx+4..];
                let num: String = rest.chars().take_while(|c| c.is_ascii_digit() || *c=='.').collect();
                if let Ok(v) = num.parse::<f64>() { ssim_all = Some(v); }
            }
        }
    }

    let mut rep = serde_json::json!({});
    if let Some(v) = psnr_all { rep["psnr_all"] = serde_json::json!(v); }
    if let Some(v) = ssim_all { rep["ssim_all"] = serde_json::json!(v); }
    if rep.as_object().unwrap().is_empty() {
        // If parsing failed, still show raw tool output to help users
        bail!("qc(ffmpeg) completed but could not parse summary.\n{}", text);
    }
    println!("{}", serde_json::to_string_pretty(&rep)?);
    Ok(())
}

fn cmd_qc(a: QcArgs) -> Result<()> {
    // Try core first; if not implemented or errors, fall back to ffmpeg
    match backend::qc(&QcOptions {
        ref_path: a.ref_path.clone(),
        dist_path: a.dist_path.clone(),
        vmaf_model: a.vmaf_model.clone(),
    }) {
        Ok(rep) => {
            println!("{}", serde_json::to_string_pretty(&rep)?);
            Ok(())
        }
        Err(_) => {
            qc_via_ffmpeg(&a.ref_path, &a.dist_path, a.psnr, a.ssim)
        }
    }
}

fn cmd_pack(a: PackArgs) -> Result<()> {
    let kind = match a.packager.as_str() {
        "hls" => PackKind::Hls,
        "dash" => PackKind::Dash,
        other => bail!("unknown --packager {}", other),
    };
    let out_dir = match kind {
        PackKind::Hls => a
            .hls_out
            .ok_or_else(|| anyhow::anyhow!("--hls-out <dir> is required for --packager hls"))?,
        PackKind::Dash => a
            .dash_out
            .ok_or_else(|| anyhow::anyhow!("--dash-out <dir> is required for --packager dash"))?,
    };
    packager::pack_unified_auto(
        kind,
        std::path::Path::new(&a.input),
        std::path::Path::new(&out_dir),
        a.segment_duration,
        a.auto_ladder,
        a.ladder.as_deref(),
        a.per_shot,
        &a.tone_map,
    )?;
    eprintln!("[pack] wrote to {}", out_dir);
    Ok(())
}

fn cmd_remux(a: RemuxArgs) -> anyhow::Result<()> {
    use std::process::Command;

    let ff = which_path("ffmpeg")
        .or_else(|| std::env::var("FFMPEG").ok())
        .ok_or_else(|| anyhow::anyhow!("ffmpeg not found in PATH (or FFMPEG env). Install ffmpeg."))?;

    let mut args: Vec<String> = vec!["-y".into(), "-hide_banner".into(), "-nostdin".into()];
    if let Some(ss) = a.ss { args.push("-ss".into()); args.push(format!("{ss}")); }
    args.push("-i".into()); args.push(a.input.clone());
    if let Some(to) = a.to { args.push("-to".into()); args.push(format!("{to}")); }

    let smap = if a.stream_map.trim().is_empty() {
        "0:v:0,0:a?,0:s?".to_string()
    } else {
        a.stream_map.clone()
    };
    for part in smap.split(',').map(|x| x.trim()).filter(|x| !x.is_empty()) {
        args.push("-map".into()); args.push(part.into());
    }
    args.extend([
        "-c:v".into(),"copy".into(),
        "-c:a".into(),"copy".into(),
        "-c:s".into(),"copy".into()
    ]);
    args.push(a.output.clone());

    let status = Command::new(&ff).args(&args).status()
        .map_err(|e| anyhow::anyhow!("failed to spawn ffmpeg: {e}"))?;
    if !status.success() {
        return Err(anyhow::anyhow!("ffmpeg remux failed (exit {status})"));
    }
    println!("[remux] wrote {}", a.output);
    Ok(())
}

/* doctor */

fn version_of(bin: &str, flag: &str) -> Option<String> {
    let out = std::process::Command::new(bin).arg(flag).output().ok()?;
    if !out.status.success() { return None; }
    let s = String::from_utf8_lossy(&out.stdout);
    Some(s.lines().next().unwrap_or("").trim().to_string())
}

fn cmd_doctor(a: DoctorArgs) -> Result<()> {
    let ff  = std::env::var("FFMPEG").ok().filter(|s| !s.is_empty())
                .or_else(|| which_path("ffmpeg"));
    let ffp = std::env::var("FFPROBE").ok().filter(|s| !s.is_empty())
                .or_else(|| which_path("ffprobe"));
    let gst = which_path("gst-launch-1.0");

    let code = {
        let mut missing = 0;
        if ff.is_none()  { missing |= 0b001; }
        if ffp.is_none() { missing |= 0b010; }
        if gst.is_none() { missing |= 0b100; }
        match missing {
            0 => 0,
            0b001 => 2,
            0b010 => 3,
            0b100 => 4,
            _     => 5, // multiple missing
        }
    };

    let rep = serde_json::json!({
        "mmx": if code==0 { "ok" } else { "degraded" },
        "deps": {
            "ffmpeg": ff.clone().unwrap_or_else(|| "<missing>".into()),
            "ffprobe": ffp.clone().unwrap_or_else(|| "<missing>".into()),
            "gstreamer": gst.clone().unwrap_or_else(|| "<missing>".into()),
            "ffmpeg_version": ff.as_deref().and_then(|p| version_of(p, "-version")),
            "ffprobe_version": ffp.as_deref().and_then(|p| version_of(p, "-version")),
            "gstreamer_version": gst.as_deref().and_then(|p| version_of(p, "--version")),
        },
        "env": {
            "PATH": std::env::var("PATH").unwrap_or_default(),
            "FFMPEG": std::env::var("FFMPEG").unwrap_or_default(),
            "FFPROBE": std::env::var("FFPROBE").unwrap_or_default()
        }
    });

    if a.json {
        println!("{}", serde_json::to_string_pretty(&rep)?);
    } else {
        println!("{}", serde_json::to_string_pretty(&rep)?);
        if code != 0 {
            eprintln!("\n[doctor] problems found (exit code {code}) — tips:");
            if ff.is_none()  { eprintln!("  - Install ffmpeg (brew install ffmpeg)"); }
            if ffp.is_none() { eprintln!("  - Install ffprobe (part of ffmpeg)"); }
            if gst.is_none() { eprintln!("  - Install GStreamer (brew install gstreamer)"); }
        }
    }
    // CI-friendly exit codes
    std::process::exit(code);
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.cmd {
        Command::Run(a) => cmd_run(a)?,
        Command::Probe(a) => cmd_probe(a)?,
        Command::Qc(a) => cmd_qc(a)?,
        Command::Pack(a) => cmd_pack(a)?,
        Command::Doctor(a) => cmd_doctor(a)?,
        Command::Remux(a) => cmd_remux(a)?,
    }
    Ok(())
}
