#!/usr/bin/env bash
set -euo pipefail

MAIN="mmx-cli/src/main.rs"
TOML="mmx-cli/Cargo.toml"

[[ -f "$MAIN" ]] || { echo "!! $MAIN not found (run from repo root)"; exit 1; }

# ---------- Python patcher ----------
python3 - "$MAIN" "$TOML" <<'PY'
import sys, re, pathlib, datetime
main = pathlib.Path(sys.argv[1]); tomlp = pathlib.Path(sys.argv[2])

src = main.read_text(encoding="utf-8")
toml = tomlp.read_text(encoding="utf-8") if tomlp.exists() else ""

# Backup once
bak = main.with_suffix(main.suffix + f".bak-doctor-remux-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}")
bak.write_text(src, encoding="utf-8")

def normalize_clap(s:str)->str:
    lines = s.splitlines()
    out, inserted = [], False
    for ln in lines:
        # drop any clap import (even mangled)
        if re.match(r'^\s*use\s+clap::', ln):
            if not inserted:
                out.append("use clap::{Args, Parser, Subcommand};")
                inserted = True
        else:
            # also drop any broken fragments we’ve seen
            if "Subcommand}, {Args" in ln: 
                continue
            out.append(ln)
    if not inserted:
        # insert after last "use" block or at top
        i = 0
        while i < len(out) and not re.match(r'^\s*use\s+\S+;\s*$', out[i]): i += 1
        while i < len(out) and re.match(r'^\s*use\s+\S+;\s*$', out[i]): i += 1
        out.insert(i, "use clap::{Args, Parser, Subcommand};")
    return "\n".join(out)

def strip_which_imports(s:str)->str:
    # Remove any "use which::which;" lines and replace calls
    s = re.sub(r'(?m)^\s*use\s+which::which\s*;\s*\n', '', s)
    s = re.sub(r'\bwhich::which\(', 'which_path(', s)
    return s

def ensure_which_path(s:str)->str:
    if "fn which_path(" in s: return s
    helper = '''
fn which_path(bin: &str) -> Option<String> {
    if let Ok(p) = std::env::var(bin.to_uppercase()) {
        let p = p.trim();
        if !p.is_empty() { return Some(p.to_string()); }
    }
    let path = match std::env::var("PATH") { Ok(x) => x, Err(_) => return None };
    #[cfg(windows)] let sep = ';';
    #[cfg(not(windows))] let sep = ':';
    for dir in path.split(sep) {
        if dir.is_empty() { continue; }
        #[cfg(windows)]
        {
            for ext in ["", ".exe", ".bat", ".cmd"] {
                let cand = std::path::Path::new(dir).join(format!("{bin}{ext}"));
                if cand.is_file() { return Some(cand.to_string_lossy().to_string()); }
            }
        }
        #[cfg(not(windows))]
        {
            let cand = std::path::Path::new(dir).join(bin);
            if cand.is_file() { return Some(cand.to_string_lossy().to_string()); }
        }
    }
    None
}
'''.strip() + "\n"
    # place after last use; else top
    m = list(re.finditer(r'^\s*use\s+\S+;\s*$', s, flags=re.M))
    return (s[:m[-1].end()] + "\n\n" + helper + s[m[-1].end():]) if m else (helper + "\n" + s)

def extend_command_enum(s:str)->str:
    m = re.search(r'pub\s+enum\s+Command\s*\{', s)
    if not m: return s
    i, depth, j = m.end(), 1, m.end()
    while j < len(s) and depth:
        depth += (s[j] == '{') - (s[j] == '}')
        j += 1
    body = s[i:j-1]
    changed = False
    if not re.search(r'\bDoctor\b', body):
        body = body.rstrip() + "\n    Doctor,\n"; changed = True
    if not re.search(r'Remux\s*\(', body):
        body = body.rstrip() + "    Remux(RemuxArgs),\n"; changed = True
    return s if not changed else (s[:i] + body + s[j-1:])

def ensure_remux_args_and_cmds(s:str)->str:
    add = []
    if "struct RemuxArgs" not in s:
        add.append('''
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
'''.strip())
    if not re.search(r'\bfn\s+cmd_doctor\s*\(', s):
        add.append('''
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
'''.strip())
    if not re.search(r'\bfn\s+cmd_remux\s*\(', s):
        add.append('''
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
'''.strip())
    return s if not add else (s.rstrip() + "\n\n" + "\n\n".join(add) + "\n")

def wire_dispatch(s:str)->str:
    # Find a match block that already dispatches known commands; add our two.
    for m in re.finditer(r'match\s+([^\{]+)\{', s):
        start = m.end()-1
        depth = 0; i = start
        while i < len(s):
            c = s[i]
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    b0, b1 = start+1, i
                    body = s[b0:b1]
                    if any(k in body for k in ("Command::Run", "Command::Probe", "Command::Qc", "Command::Pack")):
                        new = body
                        if "Command::Doctor" not in new:
                            new = new.rstrip() + "\n        Command::Doctor => cmd_doctor()?,"
                        if "Command::Remux(" not in new:
                            new = new.rstrip() + "\n        Command::Remux(a) => cmd_remux(a)?,"
                        return s[:b0] + new + s[b1:]
                    break
            i += 1
    return s

# Apply transforms
src = normalize_clap(src)
src = strip_which_imports(src)
src = ensure_which_path(src)
src = extend_command_enum(src)
src = ensure_remux_args_and_cmds(src)
src = wire_dispatch(src)

# TOML: add serde deps; remove stray which/bin.0.*
if "[dependencies]" not in toml:
    toml += "\n[dependencies]\n"
def has(name): return re.search(rf'(?m)^\s*{re.escape(name)}\s*=', toml) is not None
if not has("serde"): toml += 'serde = { version = "1", features = ["derive"] }\n'
if not has("serde_json"): toml += 'serde_json = "1"\n'
toml = re.sub(r'(?m)^\s*which\s*=.*\n', '', toml)
toml = re.sub(r'(?m)^\s*bin\.0\.(axum|regex|tokio|which).*?\n', '', toml)

main.write_text(src, encoding="utf-8")
tomlp.write_text(toml, encoding="utf-8")

print("[ok] Patched: Doctor + Remux + which_path; dispatch wired; Cargo.toml normalized.")
PY

echo "Building (gst feature)…"
cargo build -p mmx-cli -F mmx-core/gst --release

echo
echo "Run:"
echo "  target/release/mmx doctor"
echo "  target/release/mmx remux --input in.mp4 --output out_copy.mp4 --ss 0 --to 2.5 --stream-map \"0:v:0,0:a:0,0:s?\""
