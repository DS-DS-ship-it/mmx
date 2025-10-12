use anyhow::{anyhow, Context, Result};
use regex::Regex;
use serde_json::{json, Value};
use std::{env, path::Path, process::{Command, Stdio}};

fn main() -> Result<()> {
    if let Err(e) = real_main() {
        eprintln!("{}", e);
        std::process::exit(1);
    }
    Ok(())
}

fn real_main() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    let invoked_as = Path::new(&args[0]).file_name().and_then(|s| s.to_str()).unwrap_or("");

    match invoked_as {
        "ffprobe" => return ffprobe_compat(&args[1..]),
        "ffmpeg"  => return ffmpeg_compat(&args[1..]),
        _ => {}
    }
    if args.len() >= 2 {
        match args[1].as_str() {
            "ffprobe" => return ffprobe_compat(&args[2..]),
            "ffmpeg"  => return ffmpeg_compat(&args[2..]),
            _ => {}
        }
    }
    eprintln!("usage:\n  mmx-compat ffprobe [args]\n  mmx-compat ffmpeg [args]\n  (or symlink as ffprobe/ffmpeg)");
    Ok(())
}

/* ---------------- ffprobe JSON compatibility ---------------- */
fn ffprobe_compat(argv: &[String]) -> Result<()> {
    let input = argv.iter().rev().find(|s| !s.starts_with('-'))
        .ok_or_else(|| anyhow!("ffprobe: missing input"))?;

    which::which("gst-discoverer-1.0")
        .context("gst-discoverer-1.0 not found; install GStreamer tools")?;

    let out = Command::new("gst-discoverer-1.0")
        .arg(input)
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .output()
        .context("failed to run gst-discoverer-1.0")?;

    let text = String::from_utf8_lossy(&out.stdout);
    let dur_re = Regex::new(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)").unwrap();
    let vid_re = Regex::new(r"video:\s*.+?codec=(\w+).*?width=(\d+), height=(\d+)").unwrap();
    let aud_re = Regex::new(r"audio:\s*.+?codec=(\w+).*?rate=(\d+), channels=(\d+)").unwrap();
    let ctn_re = Regex::new(r"container:\s*(.+)$").unwrap();

    let mut duration_sec: f64 = 0.0;
    if let Some(c) = dur_re.captures(&text) {
        let h: f64 = c[1].parse().unwrap_or(0.0);
        let m: f64 = c[2].parse().unwrap_or(0.0);
        let s: f64 = c[3].parse().unwrap_or(0.0);
        duration_sec = h*3600.0 + m*60.0 + s;
    }
    let mut format_name = "unknown".to_string();
    if let Some(c) = ctn_re.captures_iter(&text).last() {
        format_name = c[1].trim().to_string();
    }

    let mut streams: Vec<Value> = vec![];
    for cap in vid_re.captures_iter(&text) {
        let codec = cap[1].to_lowercase();
        let w: i64 = cap[2].parse().unwrap_or(0);
        let h: i64 = cap[3].parse().unwrap_or(0);
        streams.push(json!({
          "index": streams.len(),
          "codec_type":"video",
          "codec_name": codec,
          "width": w,
          "height": h,
          "r_frame_rate":"0/0",
          "avg_frame_rate":"0/0",
          "pix_fmt": Value::Null,
          "tags": {}
        }));
    }
    for cap in aud_re.captures_iter(&text) {
        let codec = cap[1].to_lowercase();
        let rate: i64 = cap[2].parse().unwrap_or(0);
        let ch: i64 = cap[3].parse().unwrap_or(0);
        streams.push(json!({
          "index": streams.len(),
          "codec_type":"audio",
          "codec_name": codec,
          "sample_rate": rate.to_string(),
          "channels": ch,
          "channel_layout": Value::Null,
          "tags": {}
        }));
    }

    let out_json = json!({
      "streams": streams,
      "format": {
        "filename": input,
        "nb_streams": streams.len(),
        "format_name": format_name,
        "duration": format!("{:.3}", duration_sec),
        "size": Value::Null,
        "bit_rate": Value::Null,
        "tags": {}
      }
    });
    println!("{}", serde_json::to_string_pretty(&out_json)?);
    Ok(())
}

/* ---------------- ffmpeg remux/trim (copy codecs) ---------------- */
#[derive(Default, Debug)]
struct FfmpegOpts {
    input: Option<String>,
    output: Option<String>,
    ss: Option<String>,
    t: Option<String>,
    to_: Option<String>,
    copy_video: bool,
    copy_audio: bool,
    faststart: bool,
    maps: Vec<String>,
}

fn ffmpeg_compat(argv: &[String]) -> Result<()> {
    let mut i = 0usize;
    let mut o = FfmpegOpts::default();
    while i < argv.len() {
        match argv[i].as_str() {
            "-y" => { i+=1; }
            "-i" => { o.input = argv.get(i+1).cloned(); i+=2; }
            "-ss" => { o.ss = argv.get(i+1).cloned(); i+=2; }
            "-t"  => { o.t  = argv.get(i+1).cloned(); i+=2; }
            "-to" => { o.to_ = argv.get(i+1).cloned(); i+=2; }
            "-map" => { if let Some(m)=argv.get(i+1){ o.maps.push(m.clone()); } i+=2; }
            "-c:v" => { let v=argv.get(i+1).map(|s|s.as_str()).unwrap_or(""); o.copy_video = v=="copy"; i+=2; }
            "-c:a" => { let v=argv.get(i+1).map(|s|s.as_str()).unwrap_or(""); o.copy_audio = v=="copy"; i+=2; }
            "-movflags" => { let v=argv.get(i+1).cloned().unwrap_or_default(); if v.contains("+faststart"){ o.faststart=true; } i+=2; }
            s if s.starts_with('-') => {
                if i+1<argv.len() && !argv[i+1].starts_with('-') { i+=2; } else { i+=1; }
            }
            _ => { o.output = Some(argv[i].clone()); i+=1; }
        }
    }
    let input = o.input.ok_or_else(|| anyhow!("ffmpeg: missing -i input"))?;
    let output= o.output.ok_or_else(|| anyhow!("ffmpeg: missing output"))?;

    which::which("gst-launch-1.0").context("gst-launch-1.0 not found; install GStreamer")?;

    // Build a simple copy-codec remux pipeline (MP4/MOV). Trim is best-effort via splitmux.
    let faststart = if o.faststart { "faststart=true" } else { "" };

    // If no trim, use qtmux remux
    if o.ss.is_none() && o.t.is_none() && o.to_.is_none() {
        let pipeline = format!(
            "filesrc location={} ! qtdemux name=d \
             d.video_0 ! queue ! identity ! qtmux {} name=mux ! filesink location={} \
             d.audio_0 ! queue ! identity ! mux.",
            shq(&input), faststart, shq(&output)
        );
        let status = Command::new("gst-launch-1.0").arg("-q").arg(pipeline).status()
            .context("failed to run gst-launch-1.0")?;
        if !status.success() {
            return Err(anyhow!("ffmpeg-compat: remux failed (gst-launch exit {:?})", status.code()));
        }
        return Ok(());
    }

    // With trim: use decode+encode passthrough where needed (still copy by default).
    // Best-effort: trim using mp4split-ish approach via splitmuxsink start/stop times.
    let (ss_sec, end_sec) = {
        let parse_ts = |s: &str| -> f64 {
            if s.contains(':') {
                let parts: Vec<f64> = s.split(':').map(|x| x.parse::<f64>().unwrap_or(0.0)).collect();
                match parts.len() {
                    3 => parts[0]*3600.0 + parts[1]*60.0 + parts[2],
                    2 => parts[0]*60.0 + parts[1],
                    _ => parts.iter().sum(),
                }
            } else { s.parse::<f64>().unwrap_or(0.0) }
        };
        let ss = o.ss.as_deref().map(parse_ts).unwrap_or(0.0);
        let t  = o.t.as_deref().map(parse_ts);
        let to = o.to_.as_deref().map(parse_ts);
        let end = if let Some(tt)=t { ss + tt } else { to.unwrap_or(0.0) };
        (ss, end)
    };

    // Pipeline: decode -> (trim) -> encode copy/identity -> mux
    // NOTE: for strict copy without re-encode, precise trim on keyframes only.
    let mut args: Vec<String> = vec!["-q".into()];
    let mut pipe = format!(
        "filesrc location={} ! qtdemux name=d ",
        shq(&input)
    );

    // Video
    pipe.push_str("d.video_0 ! queue ! ");
    if ss_sec > 0.0 {
        pipe.push_str(&format!("videorate ! identity timestamp-offset={}000000000 ! ", (ss_sec * -1e9f64) as i64));
    }
    pipe.push_str("identity ! ");

    // Audio
    pipe.push_str("d.audio_0 ! queue ! identity ! ");

    pipe.push_str(&format!("qtmux {} name=mux ! filesink location={} ", faststart, shq(&output)));
    // Join pads
    pipe.push_str("d.audio_0 ! mux.");

    args.push(pipe);

    let status = Command::new("gst-launch-1.0").args(args).status()
        .context("failed to run gst-launch-1.0 (trim pipeline)")?;
    if !status.success() {
        return Err(anyhow!("ffmpeg-compat: trim failed (gst-launch exit {:?})", status.code()));
    }

    Ok(())
}

fn shq(s: &str) -> String {
    let t = s.replace('\'', "'\"'\"'");
    format!("'{}'", t)
}
