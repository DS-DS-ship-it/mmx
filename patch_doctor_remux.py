cat > patch_doctor_remux.py <<'PY'
#!/usr/bin/env python3
import re, sys, json
from pathlib import Path

ROOT = Path.cwd()
MAIN = ROOT/"mmx-cli/src/main.rs"
TOML = ROOT/"mmx-cli/Cargo.toml"

def read(p:Path)->str:
    if not p.exists(): sys.exit(f"!! missing: {p}")
    return p.read_text(encoding="utf-8")

def write(p:Path, s:str)->None:
    p.write_text(s, encoding="utf-8")

def normalize_clap_imports(src:str)->str:
    # Remove any broken/duplicated clap imports and make one clean line
    lines = src.splitlines()
    out=[]
    inserted=False
    for ln in lines:
        if re.match(r'^\s*use\s+clap::', ln):
            if not inserted:
                out.append("use clap::{Args, Parser, Subcommand};")
                inserted=True
            # drop all other clap imports
        else:
            out.append(ln)
    if not inserted:
        # Insert after the first 'use ...;' group
        for i,(ln) in enumerate(list(enumerate(out))):
            pass
        i = 0
        while i < len(out) and not re.match(r'^\s*use\s+.*;\s*$', out[i]): i+=1
        while i < len(out) and re.match(r'^\s*use\s+.*;\s*$', out[i]): i+=1
        out.insert(i, "use clap::{Args, Parser, Subcommand};")
    return "\n".join(out)

def ensure_which_path_helper(src:str)->str:
    if "fn which_path(" in src:
        return src
    helper = r'''
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
'''.strip()+"\n"
    # Insert after the last use; statement block near the top
    m = list(re.finditer(r'^\s*use\s+.+?;\s*$', src, flags=re.M))
    if m:
        end = m[-1].end()
        return src[:end] + "\n\n" + helper + src[end:]
    else:
        return helper + "\n" + src

def add_enum_variants(src:str)->str:
    # Find pub enum Command { ... }
    m = re.search(r'pub\s+enum\s+Command\s*\{', src)
    if not m: return src
    i = m.end()
    depth=1
    j=i
    while j < len(src) and depth>0:
        if src[j] == '{': depth+=1
        elif src[j] == '}': depth-=1
        j+=1
    body = src[i:j-1]
    changed=False
    if "Doctor" not in body:
        body = body.rstrip() + "\n    Doctor,\n"
        changed=True
    if "Remux(" not in body:
        body = body.rstrip() + "    Remux(RemuxArgs),\n"
        changed=True
    if not changed: return src
    return src[:i] + body + src[j-1:]

def ensure_remux_args(src:str)->str:
    if "struct RemuxArgs" in src:
        return src
    block = r'''
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
'''.strip()+"\n"
    return src + ("\n\n" + block)

def ensure_cmd_doctor(src:str)->str:
    if re.search(r'\bfn\s+cmd_doctor\s*\(', src): return src
    fn = r'''
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
'''.strip()+"\n"
    return src + ("\n\n" + fn)

def ensure_cmd_remux(src:str)->str:
    if re.search(r'\bfn\s+cmd_remux\s*\(', src): return src
    fn = r'''
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
'''.strip()+"\n"
    return src + ("\n\n" + fn)

def wire_dispatch(src:str)->str:
    # Find a match-arm handling existing commands and add ours.
    # Heuristic: find the first 'match ' whose body mentions Command::Run / Probe / Qc / Pack
    for m in re.finditer(r'match\s+([^\{]+)\{', src):
        start = m.end()-1
        depth = 0
        i = start
        while i < len(src):
            c = src[i]
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    b0 = start+1; b1 = i
                    body = src[b0:b1]
                    if any(x in body for x in ("Command::Run", "Command::Probe", "Command::Qc", "Command::Pack")):
                        new = body
                        if "Command::Doctor" not in new:
                            new = new.rstrip() + "\n        Command::Doctor => cmd_doctor()?,"
                        if "Command::Remux(" not in new:
                            new = new.rstrip() + "\n        Command::Remux(a) => cmd_remux(a)?,"
                        return src[:b0] + new + src[b1:]
                    break
            i += 1
    # If not found, leave unchanged
    return src

def replace_which_calls(src:str)->str:
    return re.sub(r'\bwhich::which\(', 'which_path(', src)

def ensure_serde_deps(toml:str)->str:
    if "[dependencies]" not in toml:
        toml += "\n[dependencies]\n"
    def has(name): return re.search(rf'(?m)^\s*{re.escape(name)}\s*=', toml) is not None
    if not has("serde"):
        toml += 'serde = { version = "1", features = ["derive"] }\n'
    if not has("serde_json"):
        toml += 'serde_json = "1"\n'
    # remove stray which dep and bad bin.0.* lines
    toml = re.sub(r'(?m)^\s*which\s*=.*\n', '', toml)
    toml = re.sub(r'(?m)^\s*bin\.0\.(axum|regex|tokio|which).*?\n', '', toml)
    return toml

def main():
    print("[1/6] Load files…")
    src = read(MAIN)
    toml = read(TOML)

    print("[2/6] Fix/ensure clap imports…")
    src = normalize_clap_imports(src)

    print("[3/6] Add which_path helper + replace which::which…")
    src = ensure_which_path_helper(src)
    src = replace_which_calls(src)

    print("[4/6] Extend enums/args and add commands…")
    src = add_enum_variants(src)
    src = ensure_remux_args(src)
    src = ensure_cmd_doctor(src)
    src = ensure_cmd_remux(src)

    print("[5/6] Wire dispatch…")
    src = wire_dispatch(src)

    print("[6/6] Ensure serde deps…")
    toml = ensure_serde_deps(toml)

    write(MAIN, src)
    write(TOML, toml)
    print("\n[ok] Doctor & Remux patched.")
    print("\nNext:")
    print("  cargo build -p mmx-cli -F mmx-core/gst --release")
    print("Then try:")
    print("  target/release/mmx doctor")
    print('  target/release/mmx remux --input in.mp4 --output out_copy.mp4 --ss 0 --to 2.5 --stream-map "0:v:0,0:a:0,0:s?"')

if __name__ == "__main__":
    main()
PY
