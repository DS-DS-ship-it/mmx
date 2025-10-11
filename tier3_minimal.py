# tier3_minimal.py
from pathlib import Path
import re, json

root = Path(".")
cli = root/"mmx-cli/src/main.rs"
cli_toml = root/"mmx-cli/Cargo.toml"
core_pack = root/"mmx-core/src/packager.rs"
core_lib = root/"mmx-core/src/lib.rs"

# --- mmx-core: add live_hls (ffmpeg fallback) ---
core_pack.parent.mkdir(parents=True, exist_ok=True)
if core_pack.exists():
    s = core_pack.read_text()
else:
    s = ""

if "pub fn live_hls(" not in s:
    s += r'''
use anyhow::{anyhow, Result};
use std::path::Path;
use std::process::Command;

pub fn live_hls(input: &Path, out_dir: &Path, low_latency: bool) -> Result<()> {
    if !out_dir.exists() { std::fs::create_dir_all(out_dir)?; }
    let ffmpeg = std::env::var("FFMPEG").unwrap_or_else(|_| "ffmpeg".to_string());

    // Very simple LL-HLS preset: fMP4 segments, ~1s duration, short playlist.
    let mut args = vec![
        "-re",
        "-i", input.to_str().ok_or_else(|| anyhow!("bad input path"))?,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-g", "30", "-keyint_min", "30",
        "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", "128k",
        "-f", "hls",
        "-hls_segment_type", "fmp4",
        "-master_pl_name", "master.m3u8",
        "-hls_list_size", "6",
        "-hls_flags", "independent_segments+append_list+delete_segments+program_date_time",
    ];
    if low_latency {
        args.extend([
            "-hls_time", "1",
        ]);
    } else {
        args.extend([
            "-hls_time", "4",
        ]);
    }
    args.push(out_dir.join("index.m3u8").to_str().ok_or_else(|| anyhow!("bad out path"))?);

    let status = Command::new(ffmpeg).args(&args).status()
        .map_err(|e| anyhow!("failed to run ffmpeg: {e}"))?;
    if !status.success() {
        return Err(anyhow!("ffmpeg failed (live HLS), status: {:?}", status));
    }
    Ok(())
}
'''
    core_pack.write_text(s)

# export packager module if needed
lib_s = core_lib.read_text()
if "pub mod packager;" not in lib_s:
    core_lib.write_text(lib_s.rstrip() + "\n\npub mod packager;\n")

# --- mmx-cli: deps for HTTP server (axum), serde ----
t = cli_toml.read_text()
if "[dependencies]" not in t: t += "\n[dependencies]\n"
need = {
    "axum": 'axum = "0.7"',
    "tokio": 'tokio = { version = "1", features = ["rt-multi-thread","macros","signal"] }',
    "serde": 'serde = { version = "1", features = ["derive"] }',
    "serde_json": 'serde_json = "1"',
}
for k, line in need.items():
    if re.search(rf'(?m)^\s*{re.escape(k)}\b', t) is None:
        t += line + "\n"
cli_toml.write_text(t)

# --- mmx-cli: add LiveArgs, ServeArgs, wiring ---
cs = cli.read_text()

# imports
if "use mmx_core::packager" not in cs:
    cs = re.sub(r'(use\s+mmx_core::backend[^\n]*;)', r'\1\nuse mmx_core::packager;', cs, count=1)

# structs
if "struct LiveArgs" not in cs:
    cs += r'''
#[derive(clap::Args, Debug, Clone)]
pub struct LiveArgs {
    /// Input (file, device, or URL)
    #[arg(long)]
    input: String,
    /// Output directory for HLS
    #[arg(long = "out")]
    out: String,
    /// Low latency HLS
    #[arg(long = "ll", default_value_t = true)]
    low_latency: bool,
}
'''

if "struct ServeArgs" not in cs:
    cs += r'''
#[derive(clap::Args, Debug, Clone)]
pub struct ServeArgs {
    /// Bind address, e.g. 0.0.0.0:8080
    #[arg(long, default_value = "0.0.0.0:8080")]
    bind: String,
}
'''

# enum variants
if re.search(r"enum\s+Command\s*\{", cs) and "Live(" not in cs:
    cs = re.sub(r"(enum\s+Command\s*\{\s*)", r"\1\n    Live(LiveArgs),", cs, count=1)
if re.search(r"enum\s+Command\s*\{", cs) and "Serve(" not in cs:
    cs = re.sub(r"(enum\s+Command\s*\{\s*)", r"\1\n    Serve(ServeArgs),", cs, count=1)

# cmd handlers
if "fn cmd_live(" not in cs:
    cs += r'''
fn cmd_live(a: LiveArgs) -> anyhow::Result<()> {
    packager::live_hls(std::path::Path::new(&a.input),
                       std::path::Path::new(&a.out),
                       a.low_latency)?;
    Ok(())
}
'''
if "async fn cmd_serve(" not in cs:
    cs += r'''
async fn cmd_serve(a: ServeArgs) -> anyhow::Result<()> {
    use axum::{Router, routing::{get, post}, extract::Json};
    use serde::Deserialize;
    use std::sync::Arc;

    #[derive(Deserialize)]
    struct RunReq {
        backend: String, input: String, output: String,
        cfr: Option<bool>, fps: Option<u32>, execute: Option<bool>,
        hardware: Option<String>,
    }
    async fn health() -> &'static str { "ok" }

    async fn run(Json(req): Json<RunReq>) -> Json<serde_json::Value> {
        use mmx_core::backend::{self, RunOptions};
        let mut opts = RunOptions {
            backend: req.backend,
            input: req.input,
            output: req.output,
            cfr: req.cfr.unwrap_or(false),
            fps: req.fps,
            execute: req.execute.unwrap_or(true),
            manifest: None,
            progress_json: true,
            hardware: req.hardware,
        };
        match backend::run(opts) {
            Ok(_) => Json(serde_json::json!({"ok":true})),
            Err(e) => Json(serde_json::json!({"ok":false,"error":e.to_string()})),
        }
    }

    let app = Router::new()
        .route("/health", get(health))
        .route("/run", post(run));

    let listener = tokio::net::TcpListener::bind(&a.bind).await?;
    axum::serve(listener, app.into_make_service()).await?;
    Ok(())
}
'''

# main match arms
if "Command::Live(" not in cs:
    cs = re.sub(r"(match\s+cli\.cmd\s*\{\s*)",
                r"\1\n        Command::Live(a) => cmd_live(a)?,", cs, count=1)
if "Command::Serve(" not in cs:
    cs = re.sub(r"(match\s+cli\.cmd\s*\{\s*)",
                r"\1\n        Command::Serve(a) => { tokio::runtime::Runtime::new().unwrap().block_on(cmd_serve(a))?; },",
                cs, count=1)

cli.write_text(cs)
print("[ok] Tier-3 minimal: live + serve added (Axum HTTP, LL-HLS)")
