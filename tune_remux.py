# tune_remux.py
from pathlib import Path
import re, sys

MAIN = Path("mmx-cli/src/main.rs")
if not MAIN.exists():
    print("!! mmx-cli/src/main.rs not found (run from repo root)")
    sys.exit(1)

src = MAIN.read_text()

def replace_struct(text: str) -> str:
    # Find the first 'struct RemuxArgs { ... }' block and replace its fields.
    m = re.search(r'(#[^\n]*derive[^\n]*\n\s*pub\s+struct\s+RemuxArgs\s*\{)', text)
    if not m:
        m = re.search(r'(pub\s+struct\s+RemuxArgs\s*\{)', text)
    if not m:
        print("!! Could not find RemuxArgs struct; aborting.")
        sys.exit(1)

    start = m.end()
    # Walk forward to find matching closing brace
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
        i += 1
    end = i  # position just after the closing '}'

    new_struct = r'''
#[derive(clap::Args, Debug, Clone)]
pub struct RemuxArgs {
    /// Input file
    #[arg(long)]
    pub input: String,

    /// Output file
    #[arg(long)]
    pub output: String,

    /// Optional start seconds (trim-in)
    #[arg(long)]
    pub ss: Option<f64>,

    /// Optional end seconds (trim-out)
    #[arg(long)]
    pub to: Option[f64], // clap allows Option<f64>; we’ll normalize [] to <> below
    // ffmpeg-like mapping: "0:v:0,0:a:0,0:s?"
    #[arg(long, default_value = "0:v:0,0:a:0,0:s?")]
    pub stream_map: String,
}
'''.lstrip()

    # Normalize an occasional [] -> <> typo if any previous patches did that
    new_struct = new_struct.replace("Option[f64]", "Option<f64>")

    return text[:m.start()] + new_struct + text[end:]

def replace_fn(text: str) -> str:
    m = re.search(r'(fn\s+cmd_remux\s*\(\s*a:\s*RemuxArgs\s*\)\s*->\s*anyhow::Result\s*<\s*\(\s*\)\s*>\s*\{)', text)
    if not m:
        m = re.search(r'(fn\s+cmd_remux\s*\(\s*a:\s*RemuxArgs\s*\)\s*->\s*anyhow::Result\s*<[^>]*>\s*\{)', text)
    if not m:
        m = re.search(r'(fn\s+cmd_remux\s*\(\s*a:\s*RemuxArgs\s*\)\s*->\s*anyhow::Result\s*\(\s*\)\s*\{)', text)
    if not m:
        m = re.search(r'(fn\s+cmd_remux\s*\(\s*a:\s*RemuxArgs\s*\)\s*->\s*anyhow::Result\s*<\s*\(\s*\)\s*>\s*\{)', text)
    if not m:
        print("!! Could not find fn cmd_remux(a: RemuxArgs) …; aborting.")
        sys.exit(1)

    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
        i += 1
    end = i

    body = r'''
    use std::process::Command;

    // Find ffmpeg (FFMPEG env or PATH)
    let ff = which_path("ffmpeg")
        .or_else(|| std::env::var("FFMPEG").ok())
        .ok_or_else(|| anyhow::anyhow!("ffmpeg not found in PATH (or FFMPEG env). Install ffmpeg."))?;

    let mut args: Vec<String> = vec!["-y".into(), "-hide_banner".into(), "-nostdin".into()];

    if let Some(ss) = a.ss { args.push("-ss".into()); args.push(format!("{ss}")); }
    args.push("-i".into()); args.push(a.input.clone());
    if let Some(to) = a.to { args.push("-to".into()); args.push(format!("{to}")); }

    // stream map: "0:v:0,0:a:0,0:s?"
    let smap = if a.stream_map.trim().is_empty() {
        "0:v:0,0:a:0".to_string()
    } else {
        a.stream_map.clone()
    };
    for part in smap.split(',').map(|x| x.trim()).filter(|x| !x.is_empty()) {
        let p = if part.ends_with('?') { &part[..part.len()-1] } else { part };
        args.push("-map".into()); args.push(p.into());
    }
    args.extend(["-c:v".into(),"copy".into(), "-c:a".into(),"copy".into(), "-c:s".into(),"copy".into()]);
    args.push(a.output.clone());

    let status = Command::new(&ff).args(&args).status()
        .map_err(|e| anyhow::anyhow!("failed to spawn ffmpeg: {e}"))?;
    if !status.success() {
        return Err(anyhow::anyhow!("ffmpeg remux failed (exit {status})"));
    }
    println!("[remux] wrote {}", a.output);
    Ok(())
'''.rstrip() + "\n"

    return text[:m.start()] + m.group(1) + body + text[end-1:]  # keep the final '}' we counted

# Patch struct and function
src2 = replace_struct(src)
src3 = replace_fn(src2)

# A couple of normalizations that have bitten earlier patches in this repo
src3 = src3.replace("Option[f64]", "Option<f64>")
# make sure we have clap::Args imported (harmless if already present)
if "use clap::" not in src3:
    src3 = "use clap::{Args, Parser, Subcommand};\n" + src3

MAIN.write_text(src3)
print("[ok] RemuxArgs upgraded and remux implementation normalized.")

print("Now build:\n  cargo build -p mmx-cli -F mmx-core/gst --release")
print("\nThen try:\n  target/release/mmx remux --help\n"
      "  target/release/mmx remux --input in.mp4 --output out_copy.mp4 --ss 0 --to 2.5 --stream-map \"0:v:0,0:a:0,0:s?\"")
