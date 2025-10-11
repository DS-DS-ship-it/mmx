use anyhow::Result;
use crate::backend::{Backend, RunOptions, QcOptions};

pub struct MockBackend;

impl Backend for MockBackend {
    fn name(&self) -> &'static str { "mock" }
    fn run(&self, run_opts: &RunOptions) -> Result<()> {
        eprintln!("[mock] RUN planning:0 (100.0 %)");
        eprintln!("  input={} output={}", run_opts.input, run_opts.output);
        eprintln!("  backend={} zero_copy=false gpu_preset=None", run_opts.backend);
        eprintln!("  cfr={} fps={:?}", run_opts.cfr, run_opts.fps);
        eprintln!("  resume=true progress={}", run_opts.progress_json);
        Ok(())
    }
    fn probe(&self, path: &str) -> Result<crate::probe::ProbeReport> {
        crate::probe::cheap_probe(path)
    }
    fn qc(&self, _opts: &QcOptions) -> Result<crate::qc::QcReport> {
        Ok(crate::qc::QcReport{ psnr: None, ssim: None, vmaf: None, details: "mock qc".into() })
    }
}
