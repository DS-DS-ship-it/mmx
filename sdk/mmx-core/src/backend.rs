//! Backend selection + thin wrappers

use anyhow::Result;
use std::path::PathBuf;

use crate::probe;
use crate::qc;

/// Common interface all backends must implement.
pub trait Backend: Send + Sync {
    fn name(&self) -> &'static str;
    fn run(&self, opts: &RunOptions) -> Result<()>;
    fn probe(&self, path: &str) -> Result<probe::ProbeReport>;
    fn qc(&self, opts: &QcOptions) -> Result<qc::QcReport>;
}

/// Options for `run` — kept in sync with mmx-cli flags.
#[derive(Debug, Clone, Default)]
pub struct RunOptions {
    pub backend: String,
    pub input: String,
    pub output: String,
    pub cfr: bool,
    pub fps: Option<u32>,
    pub execute: bool,
    pub progress_json: bool,
    pub manifest: Option<PathBuf>,
    pub hardware: Option<String>,
}

/// Options for quality check.
#[derive(Debug, Clone, Default)]
pub struct QcOptions {
    pub ref_path: String,
    pub dist_path: String,
    pub vmaf_model: Option<String>,
}

/// Pick a backend by name. Currently only "gst".
fn select_backend(name: &str) -> Result<Box<dyn Backend>> {
    match name {
        "gst" | _ => {
            #[cfg(feature = "gst")]
            {
                Ok(Box::new(crate::backend_gst::GstBackend))
            }
            #[cfg(not(feature = "gst"))]
            {
                Err(anyhow!("gst backend not built; enable feature `gst` on mmx-core"))
            }
        }
    }
}

/// Thin wrapper so mmx-cli can call `backend::run(opts)`.
pub fn run(opts: RunOptions) -> Result<()> {
    let b = select_backend(opts.backend.as_str())?;
    b.run(&opts)
}

/// Thin wrapper so mmx-cli can call `backend::probe(path)`.
pub fn probe(path: &str) -> Result<probe::ProbeReport> {
    // default to gst for now
    let b = select_backend("gst")?;
    b.probe(path)
}

/// Thin wrapper so mmx-cli can call `backend::qc(opts)`.
pub fn qc(opts: &QcOptions) -> Result<qc::QcReport> {
    let b = select_backend("gst")?;
    b.qc(opts)
}
