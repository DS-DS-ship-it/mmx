// 0BSD — environment doctor
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
