#!/usr/bin/env python3
# 0BSD — Repair build: add shell_escape.rs and simplify gst backend to compile cleanly.

import argparse, pathlib, shutil

SHELL_ESCAPE_RS = r"""// 0BSD — tiny shell escaper (not a full implementation)
pub fn escape(s: &str) -> String {
    if s.chars().all(|c| c.is_ascii_alphanumeric() || c=='_' || c=='-' || c=='/' || c=='.' || c==':') {
        return s.to_string();
    }
    let mut out = String::from("\"");
    for ch in s.chars() {
        match ch {
            '"' => { out.push('\\'); out.push('"'); }
            '\\' => { out.push('\\'); out.push('\\'); }
            _ => out.push(ch),
        }
    }
    out.push('"');
    out
}
"""

BACKEND_GST_RS_MIN = r#"
// 0BSD — GStreamer backend (feature-gated, minimal-safe)
#![cfg(feature = "gst")]

use anyhow::{anyhow, Result};
use gstreamer as gst;
use gstreamer::prelude::*;
use gstreamer_pbutils as pbutils;

use crate::backend::{Backend, RunOptions, QcOptions};
use crate::probe::{self, ProbeReport, FormatInfo, StreamInfo};
use std::collections::BTreeMap;

pub struct GstBackend;

impl GstBackend {
    fn ensure_inited() -> Result<()> {
        // gst::init() is idempotent enough for our purposes; avoid is_initialized() pitfalls
        gst::init()?;
        Ok(())
    }

    fn discover(path: &str) -> Result<ProbeReport> {
        Self::ensure_inited()?;
        // 15s discoverer timeout
        let disc = pbutils::Discoverer::new(gst::ClockTime::from_seconds(15))
            .map_err(|e| anyhow!("{e:?}"))?;

        // Best-effort file:// URI; if discoverer cannot parse, we still return a minimal report
        let info = match disc.discover_uri(&format!("file://{}", path)) {
            Ok(i) => i,
            Err(e) => {
                return Ok(ProbeReport{
                    schema_version: probe::PROBE_SCHEMA_VERSION.to_string(),
                    path: path.to_string(),
                    format: FormatInfo{
                        format_name: "unknown".into(),
                        duration_sec: None,
                        size_bytes: None,
                        bit_rate: None,
                        tags: {
                            let mut t=BTreeMap::new(); t.insert("error".into(), format!("discoverer: {e}")); t
                        },
                    },
                    streams: vec![],
                    chapters: vec![],
                    warnings: vec!["gstreamer-discoverer failed; returning minimal info".into()],
                })
            }
        };

        // Traits for these methods live in pbutils prelude in newer releases; to avoid
        // cross-version instability we only pull safe fields here.
        let uri = info.uri().map(|u| u.to_string()).unwrap_or_else(|| path.to_string());
        let duration = info.duration().map(|d| d.nseconds() as f64 / 1_000_000_000.0);

        let mut tags = BTreeMap::new();
        tags.insert("source".into(), "gstreamer-discoverer".into());

        let rep = ProbeReport {
            schema_version: probe::PROBE_SCHEMA_VERSION.to_string(),
            path: uri,
            format: FormatInfo {
                format_name: "unknown".into(), // container name requires caps() trait; keep minimal
                duration_sec: duration,
                size_bytes: None,
                bit_rate: None,
                tags,
            },
            streams: Vec::<StreamInfo>::new(), // stream parsing can be added once traits/downcasts are stabilized
            chapters: vec![],
            warnings: vec![],
        };
        Ok(rep)
    }

    fn build_pipeline_string(opts: &RunOptions) -> String {
        let mut chain = vec![format!("filesrc location={} ! decodebin", crate::shell_escape::escape(&opts.input))];
        if opts.cfr || opts.fps.is_some() {
            let fps = opts.fps.unwrap_or(30);
            chain.push(format!("videorate ! video/x-raw,framerate={}/1", fps));
        }
        chain.push("x264enc tune=zerolatency ! mp4mux ! filesink".into());
        chain.push(format!("location={}", crate::shell_escape::escape(&opts.output)));
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

    fn probe(&self, path: &str) -> Result<crate::probe::ProbeReport> {
        Self::discover(path)
    }

    fn qc(&self, _opts: &QcOptions) -> Result<crate::qc::QcReport> {
        Ok(crate::qc::QcReport{ psnr: None, ssim: None, vmaf: None, details: "QC via gst not implemented yet".into() })
    }
}
"#  # end

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()
    root = pathlib.Path(args.dir).resolve()
    core = root / "mmx-core" / "src"

    # 1) Ensure shell_escape.rs exists
    (core / "shell_escape.rs").write_text(SHELL_ESCAPE_RS, encoding="utf-8")
    print(f"[write] {core/'shell_escape.rs'}")

    # 2) Replace backend_gst.rs with minimal, compile-safe version
    gst_path = core / "backend_gst.rs"
    if gst_path.exists():
        shutil.copy2(gst_path, gst_path.with_suffix(".bak_prev"))
    gst_path.write_text(BACKEND_GST_RS_MIN, encoding="utf-8")
    print(f"[write] {gst_path}")

    print("\n[ok] Files written. Now rebuild:")
    print("  cd", root)
    print("  cargo build")
    print("  cargo build -p mmx-cli -F mmx-core/gst")
    print("  target/debug/mmx probe --backend gst --input ./LICENSE")
    print("  target/debug/mmx run --backend gst --input in.mp4 --output out.mp4 --cfr --fps 30")

if __name__ == "__main__":
    main()
