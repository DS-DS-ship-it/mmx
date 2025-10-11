# tier2_finish.py
from pathlib import Path
import re, json, textwrap

root = Path(".")

cli_rs        = root/"mmx-cli/src/main.rs"
cli_toml      = root/"mmx-cli/Cargo.toml"
core_lib_rs   = root/"mmx-core/src/lib.rs"
core_toml     = root/"mmx-core/Cargo.toml"
backend_gst   = root/"mmx-core/src/backend_gst.rs"
packager_rs   = root/"mmx-core/src/packager.rs"
ladder_rs     = root/"mmx-core/src/ladder.rs"

# ---------------- mmx-core: Cargo deps (serde_json for ffprobe parsing)
ct = core_toml.read_text()
if "[dependencies]" not in ct: ct += "\n[dependencies]\n"
need = {
  "serde":       'serde = { version = "1", features = ["derive"] }',
  "serde_json":  'serde_json = "1"',
}
for k, line in need.items():
    if re.search(rf'(?m)^\s*{re.escape(k)}\b', ct) is None:
        ct += line + "\n"
core_toml.write_text(ct)

# ---------------- mmx-core: export ladder + packager modules
lib_s = core_lib_rs.read_text()
changed = False
for decl in ["pub mod packager;", "pub mod ladder;"]:
    if decl not in lib_s:
        lib_s = lib_s.rstrip() + "\n" + decl + "\n"
        changed = True
if changed:
    core_lib_rs.write_text(lib_s)

# ---------------- mmx-core: ladder.rs (auto ABR builder)
ladder_rs.write_text(textwrap.dedent(r'''
    // 0BSD
    use serde::{Deserialize, Serialize};

    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct LadderItem {
        pub w: u32,
        pub h: u32,
        /// video bitrate in kbps
        pub v_bitrate_k: u32,
        /// audio bitrate in kbps (per-variant; 0 means shared audio later)
        pub a_bitrate_k: u32,
        pub name: String,
    }

    #[derive(Debug, Clone, Serialize, Deserialize)]
    pub struct Ladder {
        pub items: Vec<LadderItem>,
    }

    impl Ladder {
        pub fn fixed_360_720_1080() -> Self {
            Self {
                items: vec![
                    LadderItem{ w:640,  h:360,  v_bitrate_k:  700, a_bitrate_k:128, name:"360p".into() },
                    LadderItem{ w:1280, h:720,  v_bitrate_k: 2200, a_bitrate_k:128, name:"720p".into() },
                    LadderItem{ w:1920, h:1080, v_bitrate_k: 4500, a_bitrate_k:192, name:"1080p".into() },
                ]
            }
        }

        pub fn from_string(spec: &str) -> Option<Self> {
            // Example: "426x240@400k,640x360@800k,1280x720@2500k"
            let mut items = Vec::new();
            for part in spec.split(',') {
                let p = part.trim();
                let re = regex::Regex::new(r"^(\d+)x(\d+)@(\d+)k(?:/(\d+)k)?(?::(\w+))?$").ok()?;
                let caps = re.captures(p)?;
                let w: u32 = caps.get(1)?.as_str().parse().ok()?;
                let h: u32 = caps.get(2)?.as_str().parse().ok()?;
                let vb: u32 = caps.get(3)?.as_str().parse().ok()?;
                let ab: u32 = caps.get(4).map(|m| m.as_str().parse().ok()).flatten().unwrap_or(128);
                let name = caps.get(5).map(|m| m.as_str().to_string()).unwrap_or(format!("{}p", h));
                items.push(LadderItem{ w, h, v_bitrate_k: vb, a_bitrate_k: ab, name });
            }
            if items.is_empty() { None } else { Some(Self{ items }) }
        }
    }

    pub fn suggest_ladder_from_dims(w: u32, h: u32) -> Ladder {
        // Simple heuristic: target <= source height; taper bitrates
        let mut base = vec![(640,360,700u32,128u32), (1280,720,2200,128), (1920,1080,4500,192)];
        if h <= 480 { base = vec![(640,360,800,128)]; }
        if h >= 1440 {
            base.push((2560,1440,8000,256));
        }
        if h >= 2160 {
            base.push((3840,2160,14000,320));
        }
        base.retain(|&(_, hh, _, _)| hh <= h);
        Ladder { items: base.into_iter().map(|(w,h,v,a)| LadderItem{w,h,v_bitrate_k:v,a_bitrate_k:a,name:format!("{}p",h)}).collect() }
    }
'''))

# ---------------- mmx-core: packager.rs (unified HLS/DASH + per-shot + tone-map)
packager_rs.write_text(textwrap.dedent(r'''
    // 0BSD — unified packager (ffmpeg fallback)
    use anyhow::{anyhow, Result};
    use std::process::{Command, Stdio};
    use std::path::Path;
    use serde_json::Value;
    use crate::ladder::{Ladder, LadderItem};

    #[derive(Debug, Clone)]
    pub enum PackKind { Hls, Dash }

    fn have_cmd(name: &str) -> bool {
        which::which(name).is_ok()
    }

    fn ffprobe_dims(input: &Path) -> Option<(u32,u32)> {
        if !have_cmd("ffprobe") { return None; }
        let out = Command::new("ffprobe")
            .args(&["-v","error","-select_streams","v:0",
                    "-show_entries","stream=width,height",
                    "-of","json", input.to_str()?])
            .output().ok()?;
        let v: Value = serde_json::from_slice(&out.stdout).ok()?;
        let w = v["streams"][0]["width"].as_u64()? as u32;
        let h = v["streams"][0]["height"].as_u64()? as u32;
        Some((w,h))
    }

    fn compute_scene_cuts(input: &Path, thresh: f32) -> Result<Vec<f64>> {
        if !have_cmd("ffmpeg") {
            return Ok(vec![]);
        }
        let expr = format!("select='gt(scene,{})',metadata=print", thresh);
        let out = Command::new("ffmpeg")
            .args(&["-hide_banner","-nostats","-i", input.to_str().ok_or_else(||anyhow!("bad input path"))?,
                    "-filter_complex", &expr, "-f","null","-"])
            .stderr(Stdio::piped())
            .stdout(Stdio::null())
            .output()?;
        let text = String::from_utf8_lossy(&out.stderr);
        let mut ts = Vec::new();
        for ln in text.lines() {
            if let Some(i) = ln.find("pts_time:") {
                let rest = &ln[i+9..];
                if let Some(end) = rest.find(' ') {
                    if let Ok(t) = rest[..end].trim().parse::<f64>() {
                        ts.push(t);
                    }
                } else if let Ok(t) = rest.trim().parse::<f64>() {
                    ts.push(t);
                }
            }
        }
        // keep at most 200
        if ts.len() > 200 { ts.truncate(200); }
        Ok(ts)
    }

    fn tone_map_chain(preset: &str) -> Option<&'static str> {
        match preset {
            "off" => None,
            "reinhard" => Some("zscale=t=linear,tonemap=reinhard,zscale=primaries=bt709:transfer=bt709:matrix=bt709,format=yuv420p"),
            "hable" => Some("zscale=t=linear,tonemap=hable,zscale=primaries=bt709:transfer=bt709:matrix=bt709,format=yuv420p"),
            "mobius" => Some("zscale=t=linear,tonemap=mobius,zscale=primaries=bt709:transfer=bt709:matrix=bt709,format=yuv420p"),
            "auto" | _ => Some("zscale=t=linear,tonemap=reinhard,zscale=primaries=bt709:transfer=bt709:matrix=bt709,format=yuv420p"),
        }
    }

    pub fn pack_unified_auto(
        kind: PackKind,
        input: &Path,
        out_dir: &Path,
        segment_seconds: u32,
        auto_ladder: bool,
        ladder_spec: Option<&str>,
        per_shot: bool,
        tone_map: &str,
    ) -> Result<()> {
        if !have_cmd("ffmpeg") { return Err(anyhow!("ffmpeg not found")); }
        if !out_dir.exists() { std::fs::create_dir_all(out_dir)?; }

        let ladder = if let Some(spec) = ladder_spec {
            if let Some(l) = crate::ladder::Ladder::from_string(spec) { l } else { crate::ladder::Ladder::fixed_360_720_1080() }
        } else if auto_ladder {
            let dims = ffprobe_dims(input);
            match dims {
                Some((w,h)) => crate::ladder::suggest_ladder_from_dims(w,h),
                None => crate::ladder::Ladder::fixed_360_720_1080(),
            }
        } else {
            crate::ladder::Ladder::fixed_360_720_1080()
        };

        let mut args: Vec<String> = Vec::new();
        args.extend(["-y".into(), "-i".into(), input.to_str().ok_or_else(||anyhow!("bad input path"))?.into()]);

        // build filter_complex: split + scale (+ tone-map)
        let n = ladder.items.len();
        let split = format!("[v:0]split={}{outs}", n, outs = (0..n).map(|i| format!("[v{i}]")).collect::<Vec<_>>().join(""));
        let mut chain_parts = vec![split];
        let tm = tone_map_chain(tone_map);
        for (i, it) in ladder.items.iter().enumerate() {
            let sc = if let Some(tmchain) = tm {
                format!("[v{i}]{} ,scale=w={}:h={}:flags=lanczos [v{i}o]", tmchain, it.w, it.h)
            } else {
                format!("[v{i}]scale=w={}:h={}:flags=lanczos,format=yuv420p [v{i}o]", it.w, it.h)
            };
            chain_parts.push(sc);
        }
        let filter_complex = chain_parts.join(";");

        args.extend(["-filter_complex".into(), filter_complex]);

        // per-shot: force keyframes at detected scene cuts
        if per_shot {
            let cuts = compute_scene_cuts(input, 0.40).unwrap_or_default();
            if !cuts.is_empty() {
                let list = cuts.iter().map(|t| format!("{:.3}", t)).collect::<Vec<_>>().join(",");
                args.extend(["-force_key_frames".into(), list]);
            }
            args.extend(["-sc_threshold".into(), "0".into()]);
        }

        // map video encodes
        for (i, it) in ladder.items.iter().enumerate() {
            args.extend(["-map".into(), format!("[v{}o]", i)]);
            args.extend([format!("-c:v:{}", i), "libx264".into()]);
            args.extend([format!("-b:v:{}", i), format!("{}k", it.v_bitrate_k)]);
            args.extend([format!("-maxrate:v:{}", i), format!("{}k", (it.v_bitrate_k as f32*1.07) as u32)]);
            args.extend([format!("-bufsize:v:{}", i), format!("{}k", it.v_bitrate_k*2)]);
            args.extend(["-profile:v".into(), "high".into()]);
            args.extend(["-g".into(), "60".into(), "-keyint_min".into(), "60".into()]);
        }

        // single shared audio mapped to all variants
        args.extend(["-map".into(), "a:0".into(), "-c:a".into(), "aac".into(), "-b:a".into(), "128k".into()]);

        match kind {
            PackKind::Hls => {
                args.extend(["-f".into(), "hls".into()]);
                args.extend(["-hls_time".into(), segment_seconds.to_string()]);
                args.extend(["-hls_playlist_type".into(), "vod".into()]);
                args.extend(["-hls_segment_type".into(), "fmp4".into()]);
                args.extend(["-master_pl_name".into(), "master.m3u8".into()]);
                args.extend(["-hls_segment_filename".into(), out_dir.join("v%v_seg%05d.m4s").to_str().ok_or_else(||anyhow!("bad seg path"))?.into()]);
                // build var_stream_map with audio
                let vmap = (0..n).map(|i| format!("v:{},a:0,name:{}", i, ladder.items[i].name)).collect::<Vec<_>>().join(" ");
                args.extend(["-var_stream_map".into(), vmap]);
                args.push(out_dir.join("v%v.m3u8").to_str().ok_or_else(||anyhow!("bad out path"))?.into());
            }
            PackKind::Dash => {
                args.extend(["-f".into(), "dash".into()]);
                args.extend(["-seg_duration".into(), segment_seconds.to_string()]);
                args.extend(["-use_template".into(), "1".into(), "-use_timeline".into(), "1".into()]);
                args.extend(["-init_seg_name".into(), "init_$RepresentationID$.mp4".into()]);
                args.extend(["-media_seg_name".into(), "chunk_$RepresentationID$_$Number%05d$.m4s".into()]);
                args.push(out_dir.join("manifest.mpd").to_str().ok_or_else(||anyhow!("bad out path"))?.into());
            }
        }

        let status = Command::new("ffmpeg").args(args.iter().map(|s| s.as_str())).status()
            .map_err(|e| anyhow!("failed to run ffmpeg: {e}"))?;
        if !status.success() { return Err(anyhow!("ffmpeg failed, status: {:?}", status)); }
        Ok(())
    }
'''))

# which crate for have_cmd
ct = core_toml.read_text()
if re.search(r'(?m)^\s*which\b', ct) is None:
    ct += 'which = "6"\n'
core_toml.write_text(ct)

# ---------------- gst backend: map more hardware encoders (simple swap)
if backend_gst.exists():
    g = backend_gst.read_text()
    if "match run_opts.hardware.as_deref()" in g:
        # replace block conservatively
        g = re.sub(
            r'match\s+run_opts\.hardware\.as_deref\(\)\s*\{[^\}]+\}',
            'match run_opts.hardware.as_deref() {\n'
            '    Some("vt") => "vtenc_h264",\n'
            '    Some("nvenc") => "nvh264enc",\n'
            '    Some("qsv") => "qsvh264enc",\n'
            '    Some("vaapi") => "vaapih264enc",\n'
            '    _ => "x264enc tune=zerolatency",\n'
            '}',
            g, flags=re.S
        )
    else:
        # add minimal mapping where x264enc is used
        g = g.replace(
            'chain.push("x264enc tune=zerolatency ! mp4mux".to_string());',
            'let enc = match run_opts.hardware.as_deref() {'
            '    Some("vt") => "vtenc_h264",'
            '    Some("nvenc") => "nvh264enc",'
            '    Some("qsv") => "qsvh264enc",'
            '    Some("vaapi") => "vaapih264enc",'
            '    _ => "x264enc tune=zerolatency",'
            '};'
            'chain.push(format!("{} ! mp4mux", enc));'
        )
    backend_gst.write_text(g)

# ---------------- CLI: add pack flags, unify call
crs = cli_rs.read_text()

if "use mmx_core::packager" not in crs:
    crs = re.sub(r'(use\s+mmx_core::backend[^\n]*;)', r'\1\nuse mmx_core::packager;', crs, count=1)
if "use mmx_core::ladder" not in crs:
    crs = re.sub(r'(use\s+mmx_core::backend[^\n]*;)', r'\1\nuse mmx_core::ladder;', crs, count=1)

# Ensure PackArgs has unified flags
if "pub struct PackArgs" in crs:
    crs = re.sub(r'(?s)pub\s+struct\s+PackArgs\s*\{.*?\}',
                 textwrap.dedent(r'''
                 #[derive(clap::Args, Debug, Clone)]
                 pub struct PackArgs {
                     #[arg(long)]
                     input: String,
                     #[arg(long, default_value="hls")]
                     packager: String, // hls|dash
                     #[arg(long = "hls-out")]
                     hls_out: Option<String>,
                     #[arg(long = "dash-out")]
                     dash_out: Option<String>,
                     #[arg(long = "segment-duration", default_value_t = 4)]
                     segment_duration: u32,
                     #[arg(long = "auto-ladder", default_value_t = true)]
                     auto_ladder: bool,
                     #[arg(long = "ladder")]
                     ladder: Option<String>,
                     #[arg(long = "per-shot", default_value_t = false)]
                     per_shot: bool,
                     #[arg(long = "tone-map", default_value = "auto")]
                     tone_map: String,
                 }
                 ''').strip(),
                 crs, count=1)

# cmd_pack implementation
if "fn cmd_pack(" in crs:
    crs = re.sub(r'(?s)fn\s+cmd_pack\s*\([^\)]*\)\s*->\s*anyhow::Result<\(\)>\s*\{.*?\}\s*',
                 textwrap.dedent(r'''
                 fn cmd_pack(a: PackArgs) -> anyhow::Result<()> {
                     use mmx_core::packager::PackKind;
                     let kind = match a.packager.as_str() {
                         "hls" => PackKind::Hls,
                         "dash" => PackKind::Dash,
                         other => anyhow::bail!("unknown --packager {}", other),
                     };
                     let out = match kind {
                         PackKind::Hls => a.hls_out.ok_or_else(|| anyhow::anyhow!("--hls-out is required for HLS"))?,
                         PackKind::Dash => a.dash_out.ok_or_else(|| anyhow::anyhow!("--dash-out is required for DASH"))?,
                     };
                     mmx_core::packager::pack_unified_auto(
                         kind,
                         std::path::Path::new(&a.input),
                         std::path::Path::new(&out),
                         a.segment_duration,
                         a.auto_ladder,
                         a.ladder.as_deref(),
                         a.per_shot,
                         &a.tone_map,
                     )?;
                     eprintln!("[pack] wrote to {}", out);
                     Ok(())
                 }
                 ''').strip(),
                 crs, count=1)

# CLI Cargo deps for regex (ladder parser) + which for CLI too (not strictly needed here)
ct = cli_toml.read_text()
if "[dependencies]" not in ct: ct += "\n[dependencies]\n"
for dep in ["serde_json = \"1\"","regex = \"1\"","which = \"6\""]:
    if dep.split("=",1)[0].strip() not in ct:
        ct += dep + "\n"
cli_toml.write_text(ct)

cli_rs.write_text(crs)

print("[ok] Tier-2 finish: auto ladder, unified packager (HLS/DASH), per-shot, tone-map, HW map extended")
