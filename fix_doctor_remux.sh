#!/usr/bin/env bash
set -euo pipefail

# -------- Config (override MAIN via env if your CLI lives elsewhere) --------
ROOT="$(pwd)"
MAIN="${MAIN:-mmx-cli/src/main.rs}"
TOML="${TOML:-mmx-cli/Cargo.toml}"

[[ -f "$MAIN" ]] || { echo "!! $MAIN not found (set MAIN=path/to/cli.rs)"; exit 1; }

echo "[1/7] Normalize clap imports (repair broken line)…"
# Remove ALL existing 'use clap::...' lines, then insert a clean one under the top 'use' block.
perl -0777 -i -pe '
  s/^[ \t]*use[ \t]+clap::[^\n]*\n//mg;
  s{
     (\A(?:[ \t]*use[ \t]+[^\n]+\n)+)
   }{$1use clap::{Args, Parser, Subcommand};\n}xms
' "$MAIN"

echo "[2/7] Inject which_path() (no external `which` crate)…"
if ! grep -q 'fn which_path(' "$MAIN"; then
  perl -0777 -i -pe '
    s{
      (use\s+[^\n]+\n(?:use\s+[^\n]+\n)*)
    }{$1
fn which_path(bin: &str) -> Option<String> {
    if let Ok(p) = std::env::var(bin.to_uppercase()) {
        let p = p.trim();
        if !p.is_empty() { return Some(p.to_string()); }
    }
    let path = match std::env::var("PATH") { Ok(x) => x, Err(_) => return None };
    let sep = if cfg!(windows) { \x27;\x27 } else { \x27:\x27 };
    for dir in path.split(sep) {
        if dir.is_empty() { continue; }
        let cand = if cfg!(windows) {
            let exts = ["", ".exe", ".bat", ".cmd"];
            let mut pick = None;
            for e in &exts {
                let c = std::path::Path::new(dir).join(format!("{bin}{e}"));
                if c.is_file() { pick = Some(c); break; }
            }
            if let Some(p) = pick { p } else { continue }
        } else {
            std::path::Path::new(dir).join(bin)
        };
        if cand.is_file() { return Some(cand.to_string_lossy().to_string()); }
    }
    None
}
}ms' "$MAIN"
fi

echo "[3/7] Add enum variants Doctor + Remux(RemuxArgs)…"
perl -0777 -i -pe '
  s{(pub\s+enum\s+Command\s*\{\s*)([^}]*)\}}{
     my($h,$b)=($1,$2);
     $b .= "    Doctor,\n" unless $b =~ /\bDoctor\b/;
     $b .= "    Remux(RemuxArgs),\n" unless $b =~ /Remux\s*\(/;
     "${h}${b}}"
  }gse
' "$MAIN"

echo "[4/7] Add RemuxArgs struct…"
grep -q 'struct RemuxArgs' "$MAIN" || cat >> "$MAIN" <<'RS'

#[derive(Args, Debug, Clone)]
pub struct RemuxArgs {
    /// Input file
    #[arg(long)]
    pub input: String,
    /// Output file
    #[arg(long)]
    pub output: String,
    /// Optional start seconds
    #[arg(long)]
    pub ss: Option<f64>,
    /// Optional end seconds
    #[arg(long)]
    pub to: Option<f64>,
    /// ffmpeg-like map, e.g. "0:v:0,0:a:0,0:s?"
    #[arg(long, default_value="0:v:0,0:a:0")]
    pub stream_map: String,
}
RS

echo "[5/7] Add cmd_doctor + cmd_remux…"
grep -q 'fn cmd_doctor(' "$MAIN" || cat >> "$MAIN" <<'RS'

fn cmd_doctor() -> anyhow::Result<()> {
    use std::process::Command;
    #[derive(serde::Serialize)]
    struct Tool { requested: &'static str, path: Option<String>, version: Option<String>, ok: bool }
    #[derive(serde::Serialize)]
    struct Report { ffmpeg: Tool, ffprobe: Tool, gst_launch: Tool }

    fn ver(cmd: &str) -> Option<String> {
        let out = Command::new(cmd).arg("-version").output().ok()?;
        if !out.status.success() { return None; }
        let mut s = String::from_utf8_lossy(&out.stdout).to_string();
        if s.is_empty() { s = String::from_utf8_lossy(&out.stderr).to_string(); }
        let first = s.lines().next().unwrap_or("").trim().to_string();
        if first.is_empty() { None } else { Some(first) }
    }

    let ff  = which_path("ffmpeg");
    let ffp = which_path("ffprobe");
    let gst = which_path("gst-launch-1.0");

    let rep = Report {
        ffmpeg: Tool { requested:"ffmpeg", path: ff.clone(),  version: ff.as_deref().and_then(ver),  ok: ff.is_some() },
        ffprobe: Tool{ requested:"ffprobe", path: ffp.clone(), version: ffp.as_deref().and_then(ver), ok: ffp.is_some() },
        gst_launch: Tool{
            requested:"gst-launch-1.0", path: gst.clone(),
            version: gst.as_deref().and_then(|p|{
                let out = Command::new(p).arg("--version").output().ok()?;
                if !out.status.success() { return None; }
                let s = String::from_utf8_lossy(&out.stdout).lines().next().unwrap_or("").trim().to_string();
                if s.is_empty() { None } else { Some(s) }
            }),
            ok: gst.is_some(),
        },
    };
    println!("{}", serde_json::to_string_pretty(&rep)?);
    Ok(())
}

fn cmd_remux(a: RemuxArgs) -> anyhow::Result<()> {
    use std::process::Command;
    let ff = which_path("ffmpeg")
        .ok_or_else(|| anyhow::anyhow!("ffmpeg not found in PATH (or FFMPEG env). Install ffmpeg."))?;

    let mut args: Vec<String> = vec!["-y".into(), "-hide_banner".into(), "-nostdin".into()];
    if let Some(ss) = a.ss { args.push("-ss".into()); args.push(format!("{ss}")); }
    args.push("-i".into()); args.push(a.input.clone());
    if let Some(to) = a.to { args.push("-to".into()); args.push(format!("{to}")); }

    for part in a.stream_map.split(',').map(|x| x.trim()).filter(|x| !x.is_empty()) {
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
}
RS

echo "[6/7] Wire dispatch arms…"
python3 - "$MAIN" <<'PY'
import sys, re, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text()

def find_dispatch(text:str):
    # Find a 'match' block that already references Command::Run/Probe/Qc/Pack
    for m in re.finditer(r'match\s+[^{}]+\{', text):
        start = m.end()-1
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{': depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    body = text[start+1:i]
                    if any(x in body for x in ("Command::Run", "Command::Probe", "Command::Qc", "Command::Pack")):
                        return start+1, i
                    break
    return None

loc = find_dispatch(s)
if loc:
    b0,b1 = loc
    body = s[b0:b1]
    if "Command::Doctor" not in body:
        body = body.rstrip()+"\n        Command::Doctor => cmd_doctor()?,"
    if "Command::Remux(" not in body:
        body = body.rstrip()+"\n        Command::Remux(a) => cmd_remux(a)?,"
    s = s[:b0] + body + s[b1:]
    p.write_text(s)
    print("WIRED")
else:
    print("NOTE: Dispatch block not found. If your enum/match lives in another file, run with MAIN=that/file.rs")
PY

echo "[7/7] Ensure serde deps + build…"
grep -q '^\[dependencies\]' "$TOML" || printf '\n[dependencies]\n' >> "$TOML"
grep -Eq '^[[:space:]]*serde[[:space:]]*='      "$TOML" || printf 'serde = { version = "1", features = ["derive"] }\n' >> "$TOML"
grep -Eq '^[[:space:]]*serde_json[[:space:]]*=' "$TOML" || printf 'serde_json = "1"\n' >> "$TOML"

cargo build -p mmx-cli -F mmx-core/gst --release

echo
echo "Smoke test:"
target/release/mmx --help | sed -n '1,120p' || true
echo
echo "Try:"
echo "  target/release/mmx doctor"
echo "  target/release/mmx remux --input in.mp4 --output out_copy.mp4 --ss 0 --to 2.5 --stream-map \"0:v:0,0:a:0,0:s?\""
