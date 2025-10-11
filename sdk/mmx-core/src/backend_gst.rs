// 0BSD — GStreamer backend (feature=gst)
#![cfg(feature = "gst")]
use time::OffsetDateTime;
use anyhow::{anyhow, Result};
use gstreamer as gst;
use gstreamer::prelude::*;
use crate::backend::{Backend, RunOptions, QcOptions};

pub struct GstBackend;

impl GstBackend {
    fn ensure_inited() -> Result<()> { gst::init()?; Ok(()) }

    fn build_pipeline_string(run_opts: &RunOptions) -> String {
        let mut chain = vec![format!("filesrc location={} ! decodebin", crate::shell_escape::escape(&run_opts.input))];
        if run_opts.cfr || run_opts.fps.is_some() {
            let fps = run_opts.fps.unwrap_or(30);
            chain.push(format!("videorate ! video/x-raw,framerate={}/1", fps));
        }
        let enc = match run_opts.hardware.as_deref() {
    Some("vt") => "vtenc_h264",
    Some("nvenc") => "nvh264enc",
    Some("qsv") => "qsvh264enc",
    Some("vaapi") => "vaapih264enc",
    _ => "x264enc tune=zerolatency",
};
        chain.push(format!("{} ! mp4mux", enc));
        chain.push(format!("filesink location={}", crate::shell_escape::escape(&run_opts.output)));
        chain.join(" ! ")
    }

    fn write_manifest_completed(run_opts: &RunOptions) {
        if let Some(p) = &run_opts.manifest {
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
                        let size = std::fs::metadata(&run_opts.output).ok().map(|m| m.len()).unwrap_or(0);
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
    }

    fn run_execute(pipe_str: &str, run_opts: &RunOptions) -> Result<()> {
        let el = gst::parse::launch(pipe_str)?;
        let pipeline = match el.clone().downcast::<gst::Pipeline>() {
            Ok(p) => p,
            Err(e) => {
                let p = gst::Pipeline::new();
                p.add(&e).map_err(|_| anyhow!("failed to add element into pipeline"))?;
                p
            }
        };
        let bus = pipeline.bus().ok_or_else(|| anyhow!("no bus on pipeline"))?;
        pipeline.set_state(gst::State::Playing)?;
        let mut emitted_start = false;
        let mut done = false;
        if run_opts.progress_json && !emitted_start { if !emitted_start { println!("{}", serde_json::json!({"event":"start"})); emitted_start = true; } emitted_start = true; }

        if run_opts.progress_json { if run_opts.progress_json && !emitted_start {
            if run_opts.progress_json && !emitted_start { if run_opts.progress_json && !emitted_start { if !emitted_start {  emitted_start = true; } emitted_start = true; } emitted_start = true; }
            emitted_start = true;
        } }
        
        let start = std::time::Instant::now();
        let mut last_emit = std::time::Instant::now();

        // Periodic progress (every ~200ms)
        let mut maybe_emit_progress = |pos_ns: u128| {
            let now = std::time::Instant::now();
            if now.duration_since(last_emit).as_millis() >= 200 {
        let mut duration_ns: Option<u128> = None;
        let mut duration_ns: Option<u128> = None;
                let dur = duration_ns.unwrap_or_else(|| pos_ns.max(1));
                let pct = (pos_ns as f64 / dur as f64) * 100.0;
                println!("{}", serde_json::json!({
                    "event":"progress",
                    "position_ns": pos_ns as u64,
                    "duration_ns": dur as u64,
                    "pct": (pct.max(0.0).min(100.0))
                }));
                last_emit = now;
            }
        };

        let mut duration_ns: Option<u128> = None;
if run_opts.progress_json {
            if let Some(dur) = pipeline.query_duration::<gst::ClockTime>() {
                duration_ns = Some(dur.nseconds() as u128);
            }
            if run_opts.progress_json && !emitted_start {
            if run_opts.progress_json && !emitted_start { if run_opts.progress_json && !emitted_start { if !emitted_start {  emitted_start = true; } emitted_start = true; } emitted_start = true; }
            emitted_start = true;
        }
        }
let start = std::time::Instant::now();
        let mut last_emit = std::time::Instant::now();
        let mut duration_ns: Option<u128> = None;
        if run_opts.progress_json {
            if let Some(dur) = pipeline.query_duration::<gst::ClockTime>() {
                duration_ns = Some(dur.nseconds() as u128);
            }
        }

        loop {
            if run_opts.progress_json && last_emit.elapsed() >= std::time::Duration::from_millis(200) {
                let pos_ns = pipeline
                    .query_position::<gst::ClockTime>()
                    .map(|t| t.nseconds() as u128);
                let pct = match (pos_ns, duration_ns) {
                    (Some(p), Some(d)) if d > 0 => Some((p as f64 / d as f64) * 100.0),
                    _ => None,
                };
                if run_opts.progress_json && !done {
            if !done { if !done { if !done { if !done {  } } } }
        }
                last_emit = std::time::Instant::now();
            }

            match bus.timed_pop(gst::ClockTime::from_seconds(1)) {
                Some(msg) => match msg.view() {
                    gst::MessageView::Eos(..) => { if run_opts.progress_json && !done { println!("{}", serde_json::json!({"event":"end","pct":100.0,"position_ns":duration_ns})); done = true; }
                // final snapshot before tear-down
                let final_pos = pipeline
                    .query_position::<gst::ClockTime>()
                    .map(|t| t.nseconds() as u128);
                if duration_ns.is_none() {
                    if let Some(d) = pipeline.query_duration::<gst::ClockTime>() {
                        duration_ns = Some(d.nseconds() as u128);
                    }
                }
                let final_pct = match (final_pos, duration_ns) {
                    (Some(p), Some(d)) if d > 0 => Some((p as f64 / d as f64) * 100.0),
                    _ => Some(100.0),
                };
                if run_opts.progress_json {
                    { println!(
                        "{}",
                        serde_json::json!({
                            "event": "end",
                            "position_ns": final_pos,
                            "duration_ns": duration_ns,
                            "pct": final_pct
                        })
                    ); done = true; }
                }

                        pipeline.set_state(gst::State::Null)?;
                        if run_opts.progress_json {
                            let obj = serde_json::json!({
                                "event": "progress",
                                "position_ns": duration_ns,
                                "duration_ns": duration_ns,
                                "pct": 100.0
                            });
                            if !done { if !done { if !done { println!("{}", obj); } } }
}
                        Self::write_manifest_completed(run_opts);
                        break;
                    }
                    gst::MessageView::Error(e) => {
                        let err = e.error(); let dbg = e.debug().unwrap_or_default();
                        pipeline.set_state(gst::State::Null)?;
                        Self::write_manifest_completed(run_opts);
                        return Err(anyhow!("[gst] ERROR: {err:?} debug={dbg}"));
                    }
                    _ => {}
                },
                None => {
                    if run_opts.progress_json && last_emit.elapsed().as_millis() >= 250 {
                        let pos_ns = pipeline
                            .query_position::<gst::ClockTime>()
                            .map(|t| t.nseconds() as u128);
                        let pct = match (pos_ns, duration_ns) {
                            (Some(p), Some(d)) if d > 0 => Some((p as f64 / d as f64) * 100.0),
                            _ => None
                        };
                        let obj = serde_json::json!({
                            "event": "progress",
                            "position_ns": pos_ns,
                            "duration_ns": duration_ns,
                            "pct": pct
                        });
                        if !done { if !done { if !done { println!("{}", obj); } } }
last_emit = std::time::Instant::now();
                    }
                }
            }
        }
        Ok(())
    }
}

impl Backend for GstBackend {
    fn name(&self) -> &'static str { "gst" }
    fn run(&self, run_opts: &RunOptions) -> Result<()> {
        Self::ensure_inited()?;
        let pipe = Self::build_pipeline_string(run_opts);
        if !run_opts.execute {
            println!("[gst] planned pipeline:\n  {}", pipe);
            return Ok(());
        }
        println!("[gst] executing with pipeline:\n  {}", pipe);
        Self::run_execute(&pipe, run_opts)
    }
    fn probe(&self, path: &str) -> Result<crate::probe::ProbeReport> { crate::probe::cheap_probe(path) }
    fn qc(&self, _opts: &QcOptions) -> Result<crate::qc::QcReport> {
        Ok(crate::qc::QcReport{ psnr: None, ssim: None, vmaf: None, details: "QC via gst not implemented yet".into() })
    }
}
