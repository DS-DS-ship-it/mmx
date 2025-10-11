#!/usr/bin/env python3
import argparse, os, re, sys, json, subprocess
from pathlib import Path

def msg(kind, p): print(f"[{kind:<5}] {p}")

def read(p: Path): return p.read_text(encoding="utf-8")
def write(p: Path, s: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")
    msg("write", p)

def find_workspace(root: Path):
    # support both: ~/mmx/{mmx-core,mmx-cli} and ~/mmx/mmx/{mmx-core,mmx-cli}
    candidates = [
        (root/"mmx-core", root/"mmx-cli"),
        (root/"mmx"/"mmx-core", root/"mmx"/"mmx-cli"),
    ]
    for core, cli in candidates:
        if (core/"Cargo.toml").exists() and (cli/"Cargo.toml").exists():
            return core, cli
    # last resort: search by name
    core = next((p for p in root.rglob("mmx-core/Cargo.toml")), None)
    cli = next((p for p in root.rglob("mmx-cli/Cargo.toml")), None)
    if core and cli:
        return core.parent, cli.parent
    raise SystemExit("Could not locate mmx-core and mmx-cli; please pass --dir pointing at repo root (that contains mmx-core/ and mmx-cli/).")

def ensure_dep(cargo: Path, crate_line: str):
    t = read(cargo)
    if crate_line in t:
        msg("keep", f"{cargo} already has {crate_line.strip()}")
        return
    if "\n[dependencies]" not in t:
        t += "\n[dependencies]\n"
    # append at end
    t2 = t.rstrip()+"\n"+crate_line+"\n"
    write(cargo, t2)

def upsert_mod_lib(lib_rs: Path, mod_line: str):
    t = read(lib_rs)
    if mod_line in t:
        msg("keep", f"{lib_rs} has {mod_line.strip()}")
        return
    write(lib_rs, t.rstrip()+"\n"+mod_line+"\n")

def patch_file(p: Path, f):
    if not p.exists(): msg("skip", f"{p} (missing)"); return
    old = read(p)
    new = f(old)
    if new != old: write(p, new)
    else: msg("keep", f"{p} (up to date)")

def add_run_options_fields(backend_rs: Path):
    def tf(s: str):
        if "pub struct RunOptions" not in s: return s
        # only add if missing
        if "pub manifest:" in s and "pub progress_json:" in s: return s
        s = re.sub(
            r"(pub struct RunOptions\s*\{[^}]*?pub\s+execute\s*:\s*bool\s*,)",
            r"\1\n    /// Optional manifest path\n    pub manifest: Option<std::path::PathBuf>,\n    /// Emit JSONL progress on stdout\n    pub progress_json: bool,",
            s, flags=re.S, count=1
        )
        return s
    patch_file(backend_rs, tf)

def patch_cli_main(main_rs: Path):
    def tf(s: str):
        orig=s
        # bring in imports we might need
        if "use clap::{" in s and "ValueHint" not in s:
            s = s.replace("use clap::{", "use clap::{ValueHint, ")
        # add doctor import from core
        if "doctor::doctor_inspect" not in s:
            s = re.sub(r"(use\s+mmx_core::\{[^\}]+)",
                       r"\1,\n    doctor::doctor_inspect",
                       s, count=1)
        # add RunArgs flags
        if re.search(r"pub struct RunArgs\s*\{", s):
            if "manifest:" not in s:
                s = re.sub(r"(pub struct RunArgs\s*\{[^}]*?pub\s+execute\s*:\s*bool\s*,)",
                           r"""\1
    /// Write/update a job manifest JSON here
    #[arg(long, value_hint=ValueHint::FilePath)]
    pub manifest: Option<std::path::PathBuf>,
    /// Emit progress as JSON lines
    #[arg(long, default_value_t=false)]
    pub progress_json: bool,""",
                           s, flags=re.S, count=1)
        # wire in cmd_run: opts.manifest / opts.progress_json
        if "opts.manifest = a.manifest;" not in s and "cmd_run(" in s:
            s = re.sub(r"(opts\.execute\s*=\s*a\.execute\s*;\s*)",
                       r"\1opts.manifest = a.manifest;\n    opts.progress_json = a.progress_json;\n",
                       s, count=1)

        # add DoctorArgs & cmd_doctor if not present
        if "struct DoctorArgs" not in s:
            # add Clap subcommand in enum Commands
            if re.search(r"enum\s+Commands\s*\{", s) and "Doctor(" not in s:
                s = re.sub(r"(enum\s+Commands\s*\{[^}]*?)\}",
                           r"""\1
    /// Diagnose environment and print fix hints
    Doctor(DoctorArgs),
}""",
                           s, flags=re.S, count=1)
            # append args + handler (place after cmd_probe or at end)
            block = r"""
#[derive(clap::Args)]
pub struct DoctorArgs {
    /// Print extra details
    #[arg(long, default_value_t=false)]
    pub inspect: bool,
}

fn cmd_doctor(a: DoctorArgs) -> anyhow::Result<()> {
    let rep = doctor_inspect()?;
    println!("{}", serde_json::to_string_pretty(&rep)?);
    if a.inspect {
        eprintln!("\nHints:");
        for h in rep.hints.iter() { eprintln!("  - {}", h); }
    }
    Ok(())
}
"""
            if "fn cmd_probe(" in s:
                s = s + block
            else:
                s = s + block

        # wire match arm
        if "Commands::Doctor(" in s and "cmd_doctor" in s and "=> cmd_doctor(" not in s:
            s = re.sub(r"(match\s+cli\.command\s*\{[^}]*)(\})",
                       r"\1\n        Commands::Doctor(a) => cmd_doctor(a),\n    \2",
                       s, flags=re.S, count=1)

        return s
    patch_file(main_rs, tf)

def patch_gst_backend(gst_rs: Path):
    def tf(s: str):
        need_time_import = "time::OffsetDateTime" not in s
        need_serde_imp = "use serde::Serialize;" not in s
        if need_serde_imp:
            s = re.sub(r"(use\s+std::time::Duration;[^\n]*\n)",
                       r"\1use serde::Serialize;\nuse std::io::Write;\nuse time::OffsetDateTime;\n",
                       s, count=1)
        if "schema_version: \"mmx.manifest.v1\"" in s and '"event":"progress"' in s:
            return s

        # after printing executing banner, write manifest skeleton if requested
        s = re.sub(
            r'(\[\s*gst\s*\]\s*executing with pipeline:\s*\n\s*{\s*plan\s*}\s*\)\s*;)',
            r"""\1

        #[derive(Serialize)]
        struct Manifest<'a> {
            schema_version: &'static str,
            backend: &'static str,
            input: String,
            output: String,
            fps: Option<u32>,
            cfr: bool,
            planned: &'a str,
            started_utc: String,
        }

        if let Some(p) = &opts.manifest {
            let started = OffsetDateTime::now_utc()
                .format(&time::format_description::well_known::Rfc3339)
                .unwrap_or_default();
            let m = Manifest {
                schema_version: "mmx.manifest.v1",
                backend: self.name(),
                input: opts.input.display().to_string(),
                output: opts.output.display().to_string(),
                fps: opts.fps,
                cfr: opts.cfr,
                planned: &plan,
                started_utc: started,
            };
            std::fs::write(p, serde_json::to_vec_pretty(&m)?)?;
        }
""",
            s, flags=re.S
        )

        # add progress scaffolding right after set_state(Playing)
        if "duration_ns:" not in s:
            s = re.sub(
                r"(pipeline\.set_state\(gst::State::Playing\)\?\s*;)",
                r"""\1
        let mut last_emit = std::time::Instant::now();
        let mut duration_ns: Option<u128> = None;
        if opts.progress_json {
            if let Ok((dur, _fmt)) = pipeline.query_duration::<gst::ClockTime>() {
                duration_ns = dur.map(|d| d.nseconds() as u128);
            }
        }
""",
                s
            )

        # periodically emit progress inside the poll loop
        if '"event":"progress"' not in s:
            s = re.sub(
                r"(match\s+bus\.timed_pop\(gst::ClockTime::from_mseconds\(200\)\)\s*\{[^}]*\}\s*;?)",
                r"""\1
        if opts.progress_json && last_emit.elapsed() >= std::time::Duration::from_millis(250) {
            last_emit = std::time::Instant::now();
            if let Ok((pos, _fmt)) = pipeline.query_position::<gst::ClockTime>() {
                let pos_ns = pos.map(|p| p.nseconds() as u128).unwrap_or(0);
                let pct = if let Some(dn) = duration_ns {
                    if dn > 0 { (pos_ns as f64 / dn as f64 * 100.0).clamp(0.0, 100.0) } else { 0.0 }
                } else { 0.0 };
                println!("{}", serde_json::json!({
                    "event":"progress",
                    "position_ns": pos_ns,
                    "percent": (pct*10.0).round()/10.0
                }));
                std::io::stdout().flush().ok();
            }
        }
""",
                s, flags=re.S
            )

        # completion: atomically update manifest with completion and size
        if "completed_utc" not in s:
            s = re.sub(
                r"(pipeline\.set_state\(gst::State::Null\)\?\s*;)",
                r"""\1
        if let Some(p) = &opts.manifest {
            if let Ok(bytes) = std::fs::read(p) {
                if let Ok(mut v) = serde_json::from_slice::<serde_json::Value>(&bytes) {
                    if let Some(obj) = v.as_object_mut() {
                        obj.insert("completed_utc".into(),
                            serde_json::Value::String(
                                OffsetDateTime::now_utc()
                                  .format(&time::format_description::well_known::Rfc3339)
                                  .unwrap_or_default()
                            )
                        );
                        let size = std::fs::metadata(&opts.output).ok().map(|m| m.len()).unwrap_or(0);
                        obj.insert("output_size".into(), serde_json::json!(size));
                        let tmp = p.with_extension("json.tmp");
                        if let Ok(buf) = serde_json::to_vec_pretty(&v) {
                            let _ = std::fs::write(&tmp, buf);
                            let _ = std::fs::rename(&tmp, p);
                        }
                    }
                }
            }
        }
""",
                s
            )
        return s
    patch_file(gst_rs, tf)

def write_doctor_rs(dst: Path):
    if dst.exists(): msg("keep", f"{dst} (exists)"); return
    code = r'''// 0BSD — environment doctor
use anyhow::Result;
use serde::Serialize;
use std::{env, path::PathBuf};

#[derive(Debug, Serialize)]
pub struct DoctorReport {
    pub gst_version: Option<String>,
    pub gst_plugin_scanner: Option<PathBuf>,
    pub gi_typelib_path_ok: bool,
    pub pkg_config_path_set: bool,
    pub homebrew_prefix: Option<PathBuf>,
    pub hints: Vec<String>,
}

#[cfg(feature="gst")]
fn gst_ver() -> Option<String> {
    if gstreamer::is_initialized() || gstreamer::init().is_ok() {
        Some(format!("{}", gstreamer::version_string()))
    } else { None }
}
#[cfg(not(feature="gst"))]
fn gst_ver() -> Option<String> { None }

pub fn doctor_inspect() -> Result<DoctorReport> {
    let mut hints = vec![];

    let brew_prefix = std::process::Command::new("brew")
        .arg("--prefix")
        .output()
        .ok()
        .and_then(|o| if o.status.success() {
            let s = String::from_utf8_lossy(&o.stdout).trim().to_string();
            if s.is_empty() { None } else { Some(PathBuf::from(s)) }
        } else { None });

    // gst-plugin-scanner
    let from_env = env::var_os("GST_PLUGIN_SCANNER").map(PathBuf::from);
    let guess = brew_prefix.as_ref().map(|p| {
        // prefer libexec path; fall back to typical Cellar path
        let libexec = p.join("libexec/gstreamer-1.0/gst-plugin-scanner");
        if libexec.exists() { libexec } else {
            p.join("Cellar/gstreamer").read_dir().ok()
                .and_then(|mut rd| rd.next())
                .map(|e| e.ok().map(|e| e.path())).flatten()
                .unwrap_or_else(|| p.join("libexec/gstreamer-1.0"))
                .join("gst-plugin-scanner")
        }
    });
    let scanner = from_env.clone()
        .or_else(|| which::which("gst-plugin-scanner").ok())
        .or(guess);
    if scanner.is_none() {
        hints.push("GST plugin scanner not found. If using Homebrew: `brew reinstall gstreamer` and export GST_PLUGIN_SCANNER from `brew --prefix gstreamer`/libexec/gstreamer-1.0/gst-plugin-scanner".into());
    }

    // GI_TYPELIB_PATH
    let gi_ok = env::var_os("GI_TYPELIB_PATH").is_some();
    if !gi_ok {
        hints.push("GI_TYPELIB_PATH not set. On macOS/Homebrew: export GI_TYPELIB_PATH=\"$(brew --prefix)/lib/girepository-1.0:$GI_TYPELIB_PATH\"".into());
    }

    // PKG_CONFIG_PATH (build-time)
    let pkg_ok = env::var_os("PKG_CONFIG_PATH").is_some();
    if !pkg_ok {
        hints.push("PKG_CONFIG_PATH not set. Export Homebrew paths for GStreamer .pc files before building.".into());
    }

    Ok(DoctorReport{
        gst_version: gst_ver(),
        gst_plugin_scanner: scanner,
        gi_typelib_path_ok: gi_ok,
        pkg_config_path_set: pkg_ok,
        homebrew_prefix: brew_prefix,
        hints,
    })
}
'''
    write(dst, code)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="repo root (contains mmx-core/ and mmx-cli/)")
    args = ap.parse_args()
    root = Path(args.dir).expanduser().resolve()

    core_dir, cli_dir = find_workspace(root)
    core_src = core_dir/"src"
    cli_src  = cli_dir/"src"

    # 1) doctor.rs
    write_doctor_rs(core_src/"doctor.rs")
    # 2) wire mod in lib.rs
    lib_rs = core_src/"lib.rs"
    if lib_rs.exists(): upsert_mod_lib(lib_rs, "pub mod doctor;")
    else: msg("skip", f"{lib_rs} (missing)")

    # 3) deps
    ensure_dep(core_dir/"Cargo.toml", 'which = "6"')
    ensure_dep(core_dir/"Cargo.toml", 'time = { version = "0.3", features = ["formatting"] }')

    # 4) RunOptions add fields
    add_run_options_fields(core_src/"backend.rs")

    # 5) patch gst backend
    patch_gst_backend(core_src/"backend_gst.rs")

    # 6) patch CLI: add doctor + flags + wiring
    patch_cli_main(cli_src/"main.rs")

    print("\n[ok] Patches applied. Build with:")
    print("  cargo build")
    print("  cargo build -p mmx-cli -F mmx-core/gst")
    print("\nThen try:")
    print("  target/debug/mmx doctor --inspect")
    print("  gst-launch-1.0 -q videotestsrc num-buffers=150 ! video/x-raw,framerate=30/1 ! x264enc ! mp4mux ! filesink location=in.mp4")
    print("  target/debug/mmx run --backend gst --input in.mp4 --output out_exec.mp4 --cfr --fps 30 --execute --manifest job.mmx.json --progress-json | tee progress.jsonl")

if __name__ == "__main__":
    main()
