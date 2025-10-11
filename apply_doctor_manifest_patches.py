#!/usr/bin/env python3
import argparse, json, os, re, sys
from pathlib import Path

def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")

def write(p: Path, s: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")
    print(f"[write]  {p}")

def patch_file(path: Path, transform):
    if not path.exists():
        print(f"[skip ] {path} (missing)")
        return False
    old = read(path)
    new = transform(old)
    if new != old:
        write(path, new)
        return True
    else:
        print(f"[keep ] {path} (already up to date)")
        return False

def ensure_dep(cargo_toml: Path, dep_line: str, section="[dependencies]"):
    if not cargo_toml.exists():
        print(f"[skip ] {cargo_toml} (missing)")
        return
    txt = read(cargo_toml)
    if dep_line in txt:
        print(f"[keep ] {cargo_toml} already has: {dep_line.strip()}")
        return
    # ensure section exists
    if section not in txt:
        txt += f"\n{section}\n"
    # append line at end of deps section
    parts = txt.split(section)
    head = parts[0]
    tail = section.join(parts[1:])
    # insert after the first occurrence of section header
    idx = txt.index(section) + len(section)
    # find end of that section (next '[' or EOF)
    m = re.search(r"\n\[", txt[idx:])
    if m:
        insert_at = idx + m.start()
        new = txt[:insert_at] + f"\n{dep_line}\n" + txt[insert_at:]
    else:
        new = txt + f"\n{dep_line}\n"
    write(cargo_toml, new)

def add_mod(lib_rs: Path, mod_line: str):
    if not lib_rs.exists():
        print(f"[skip ] {lib_rs} (missing)")
        return
    txt = read(lib_rs)
    if mod_line in txt:
        print(f"[keep ] {lib_rs} has {mod_line.strip()}")
        return
    # insert after existing pub mod lines if any, else at top
    lines = txt.splitlines()
    inserted = False
    for i, ln in enumerate(lines):
        # after the last pub mod ...; line near the top
        pass
    # simple: append at end to avoid breaking order
    txt2 = txt.rstrip() + "\n" + mod_line + "\n"
    write(lib_rs, txt2)

def upsert_run_fields(backend_rs: Path):
    def transform(s: str):
        # Add manifest & progress_json fields in RunOptions (mmx-core/src/backend.rs)
        if "pub struct RunOptions" not in s:
            return s
        # If fields already exist, keep
        if "pub manifest: Option<PathBuf>" in s and "pub progress_json: bool" in s:
            return s
        s = re.sub(
            r"(pub execute:\s*bool,)\s*([\r\n]+)",
            r"\1\n    /// If set, write/update a job manifest JSON file\n    pub manifest: Option<PathBuf>,\n    /// Emit progress as JSON lines on stdout\n    pub progress_json: bool,\n\2",
            s,
            count=1,
        )
        return s
    patch_file(backend_rs, transform)

def patch_cli_main(main_rs: Path):
    def transform(s: str):
        orig = s
        # import doctor
        if "doctor::doctor_inspect" not in s:
            s = re.sub(
                r"(probe::\{[^\}]+\})",
                r"\1,\n    doctor::doctor_inspect",
                s,
                count=1,
            )

        # Commands enum: add Doctor
        if re.search(r"\bDoctor\s*\(DoctorArgs\)", s) is None:
            s = re.sub(
                r"(pub enum Commands\s*\{[^\}]*?\bQc\s*\(QcArgs\),)",
                r"\1\n    /// Diagnose environment and print fix hints\n    Doctor(DoctorArgs),",
                s,
                flags=re.S,
                count=1,
            )

        # Add DoctorArgs and cmd_doctor
        if "pub struct DoctorArgs" not in s:
            insert_after = re.search(r"fn cmd_probe\s*\([^\)]*\)\s*->\s*Result<\(\)>\s*\{.*?\}\s*", s, re.S)
            if insert_after:
                idx = insert_after.end()
                block = """
#[derive(Args)]
pub struct DoctorArgs {
    /// Print extra details
    #[arg(long, default_value_t=false)]
    pub inspect: bool,
}

fn cmd_doctor(a: DoctorArgs) -> Result<()> {
    let rep = doctor_inspect()?;
    println!("{}", serde_json::to_string_pretty(&rep)?);
    if a.inspect {
        eprintln!("\\nHints:");
        for h in rep.hints.iter() {
            eprintln!("  - {h}");
        }
    }
    Ok(())
}
"""
                s = s[:idx] + block + s[idx:]

        # Wire match arm
        if re.search(r"Commands::Doctor\s*\(", s) and "cmd_doctor" in s:
            if re.search(r"Commands::Doctor\(a\) => cmd_doctor\(a\)", s) is None:
                s = re.sub(
                    r"(match\s+cli\.command\s*\{\s*[^}]*?)\n\s*\}",
                    r"\1\n        Commands::Doctor(a) => cmd_doctor(a),\n    }",
                    s,
                    flags=re.S,
                    count=1
                )

        # RunArgs: add manifest/progress_json flags
        if "pub manifest: Option<PathBuf>" not in s:
            s = re.sub(
                r"(pub struct RunArgs\s*\{[^\}]*?pub\s+execute:\s*bool,)",
                r"\1\n    /// Write/update a job manifest JSON here\n    #[arg(long, value_hint=ValueHint::FilePath)]\n    pub manifest: Option<PathBuf>,\n    /// Emit progress as JSON lines\n    #[arg(long, default_value_t=false)]\n    pub progress_json: bool,",
                s,
                flags=re.S,
                count=1
            )
        # cmd_run wiring for new fields
        if "opts.manifest = a.manifest;" not in s:
            s = re.sub(
                r"(opts\.execute\s*=\s*a\.execute;\s*)",
                r"\1opts.manifest = a.manifest;\n    opts.progress_json = a.progress_json;\n",
                s,
                count=1
            )

        return s
    patch_file(main_rs, transform)

def patch_gst_backend(gst_rs: Path):
    def transform(s: str):
        orig = s
        # Ensure serde::Serialize imported
        if "use serde::Serialize;" not in s:
            s = re.sub(r"(use\s+std::time::Duration;[^\n]*\n)", r"\1use serde::Serialize;\n", s, count=1)
        # Insert manifest/progress support into run()
        if "schema_version: \"mmx.manifest.v1\"" in s and "\"event\":\"progress\"" in s:
            return s  # already patched

        # Insert after "executing with pipeline" banner
        s = re.sub(
            r'(\[gst\] executing with pipeline:\n\s*\{\s*plan\s*\}\);\s*)',
            r"""\1

        // Minimal manifest structure
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

        // Write manifest bootstrap
        if let Some(p) = &opts.manifest {
            let started = time::OffsetDateTime::now_utc()
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
            s,
            flags=re.S
        )

        # Add progress loop bits: duration query + JSON lines
        if "position_ns" not in s:
            s = re.sub(
                r"(let\s+bus\s*=\s*pipeline\.bus\(\)\.ok_or_else\(\|\|\s*anyhow!\(\"no bus\"\)\)\?\s*;\s*pipeline\.set_state\(gst::State::Playing\)\?\s*;\s*)",
                r"""\
\1
        // progress support
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

        # Emit progress in bus loop
        if '"event":"progress"' not in s:
            s = re.sub(
                r"(\}\s*// end match\s*\}\s*// end Some\(\)\s*Else/None handlers.*?\}\s*// end loop case)",
                r"\1",
                s,
                flags=re.S
            )
        # simpler: inject after the bus.poll block before EOS check timings
        if "serde_json::json!({" not in s:
            s = re.sub(
                r"(match\s+bus\.timed_pop\(gst::ClockTime::from_mseconds\(200\)\)\s*\{[^}]*\}\s*;?\s*)",
                r"""\1
            // periodic progress emit
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
                s,
                flags=re.S
            )

        # Completion update: rewrite manifest with completion/size
        if "completed_utc" not in s:
            s = re.sub(
                r"(pipeline\.set_state\(gst::State::Null\)\?\s*;\s*)",
                r"""\
\1
        if let Some(p) = &opts.manifest {
            if let Ok(bytes) = std::fs::read(p) {
                if let Ok(mut v) = serde_json::from_slice::<serde_json::Value>(&bytes) {
                    if let Some(obj) = v.as_object_mut() {
                        obj.insert("completed_utc".into(),
                            serde_json::Value::String(
                                time::OffsetDateTime::now_utc()
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
    patch_file(gst_rs, transform)

def write_doctor_rs(doctor_rs: Path):
    if doctor_rs.exists():
        print(f"[keep ] {doctor_rs} (exists)")
        return
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
        // Common Homebrew location
        p.join("Cellar/gstreamer").read_dir().ok()
            .and_then(|mut rd| rd.next())
            .map(|e| e.ok().map(|e| e.path())).flatten()
            .unwrap_or_else(|| p.join("libexec/gstreamer-1.0"))
            .join("gst-plugin-scanner")
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
    write(doctor_rs, code)

def ensure_lib_rs_mods(lib_rs: Path):
    txt = read(lib_rs) if lib_rs.exists() else ""
    changed = False
    if "pub mod doctor;" not in txt:
        txt += "\npub mod doctor;\n"
        changed = True
    # keep qc mod if you already have it; otherwise don't add a bogus line
    if changed:
        write(lib_rs, txt)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="path to repo root (contains mmx/)")
    args = ap.parse_args()

    root = Path(args.dir).expanduser().resolve()
    core = root / "mmx" / "mmx-core"
    cli = root / "mmx" / "mmx-cli"

    # 1) Add doctor.rs and wire it
    write_doctor_rs(core / "src" / "doctor.rs")
    ensure_dep(core / "Cargo.toml", 'which = "6"')
    ensure_lib_rs_mods(core / "src" / "lib.rs")

    # 2) Add manifest/progress fields to RunOptions
    upsert_run_fields(core / "src" / "backend.rs")

    # 3) Patch gst backend to support manifest + progress
    patch_gst_backend(core / "src" / "backend_gst.rs")

    # 4) Patch CLI for Doctor command + run flags wiring
    patch_cli_main(cli / "src" / "main.rs")

    print("\n[ok] Doctor command, manifest & progress-json have been patched in.")
    print("Next:")
    print("  cargo build")
    print("  cargo build -p mmx-cli -F mmx-core/gst")
    print("  target/debug/mmx doctor --inspect")
    print("  target/debug/mmx run --backend gst --input in.mp4 --output out_exec.mp4 --cfr --fps 30 --execute --manifest job.mmx.json --progress-json | tee progress.jsonl")

if __name__ == "__main__":
    main()
