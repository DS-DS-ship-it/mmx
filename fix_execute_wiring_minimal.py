#!/usr/bin/env python3
# 0BSD — fix --execute wiring for 'run' only, clean builds, smoke test gst

import argparse, pathlib, re, shutil, subprocess, sys, os

def sh(cmd, cwd=None, env=None, check=True):
    print("→", " ".join(cmd))
    p = subprocess.run(cmd, cwd=cwd, env=env, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    sys.stdout.write(p.stdout)
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed: {cmd}")
    return p

def backwrite(path: pathlib.Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_suffix(path.suffix + ".prepatch")
    if not backup.exists() and path.exists():
        shutil.copy2(path, backup)
        print(f"[backup] {path} → {backup}")
    path.write_text(content, encoding="utf-8")
    print(f"[write]  {path}")

def ensure_runoptions_execute(core_backend_rs: pathlib.Path):
    s = core_backend_rs.read_text(encoding="utf-8")
    changed = False

    # add execute: bool in RunOptions
    if "pub struct RunOptions" in s and "execute:" not in s:
        s = re.sub(r"(pub\s+struct\s+RunOptions\s*{\s*[^}]*?)\n}",
                   r"\1\n    pub execute: bool,\n}", s, flags=re.S)
        print("[add ] RunOptions.execute")
        changed = True

    # default false
    if "impl Default for RunOptions" in s and re.search(r"execute\s*:", s) is None:
        s = re.sub(
            r"(impl\s+Default\s+for\s+RunOptions\s*{\s*fn\s+default\(\)\s*->\s*Self\s*{\s*Self\s*{\s*[^}]*?)\n\s*}\s*}\s*",
            r"\1\n            execute: false,\n            }\n        }\n", s, flags=re.S)
        print("[add ] RunOptions.execute default=false")
        changed = True

    if changed:
        backwrite(core_backend_rs, s)

def fix_cli_main(cli_main_rs: pathlib.Path):
    s = cli_main_rs.read_text(encoding="utf-8")

    # 1) Ensure --execute exists only in RunArgs (run subcommand)
    # Find RunArgs struct
    m = re.search(r"(struct\s+RunArgs\s*{[^}]*})", s, flags=re.S)
    if not m:
        print("[warn] RunArgs not found; skipping execute add.")
    else:
        block = m.group(1)
        # Remove any duplicate 'execute' lines inside RunArgs block, then add one clean field
        block_no_dups = re.sub(r"\n\s*#\[arg\(long\)\]\s*\n\s*execute\s*:\s*bool,\s*", "\n", block)
        if "execute:" not in block_no_dups:
            block_no_dups = re.sub(r"}\s*$",
                                   "\n    #[arg(long)]\n    execute: bool,\n}", block_no_dups)
            print("[add ] CLI --execute on RunArgs")
        # Put back
        s = s.replace(block, block_no_dups)

    # 2) Remove any 'execute' field from PackArgs entirely (should not exist)
    s = re.sub(r"(struct\s+PackArgs\s*{[^}]*?)\n\s*#\[arg\(long\)\]\s*\n\s*execute\s*:\s*bool,\s*", r"\1\n", s, flags=re.S)

    # 3) In the run handler, wire opts.execute = a.execute;
    # Find the function that handles run (look for "fn cmd_run" or the match arm)
    if "fn cmd_run" in s:
        # make sure assignment exists exactly once in cmd_run
        s = re.sub(
            r"(fn\s+cmd_run\s*\([^{]*\)\s*->\s*Result<\(\),\s*anyhow::Error>\s*{\s*[^}]*?let\s+mut\s+opts\s*=\s*RunOptions::default\(\);\s*)",
            r"\1\n    opts.execute = a.execute;\n", s, flags=re.S)
        print("[wire] opts.execute <- a.execute (cmd_run)")
    else:
        # If using match arms, try to insert near RunOptions::default inside run arm
        s = re.sub(
            r"(Command::Run\(\s*a\s*\)\s*=>\s*{\s*[^}]*?let\s+mut\s+opts\s*=\s*RunOptions::default\(\);\s*)",
            r"\1\n            opts.execute = a.execute;\n", s, flags=re.S)
        print("[wire] opts.execute <- a.execute (match arm)")

    # 4) Remove any stray 'opts.execute = a.execute;' inside *pack* handler
    s = re.sub(r"(fn\s+cmd_pack\s*\([^{]*\)\s*->\s*Result<\(\),\s*anyhow::Error>\s*{[^}]*?)\n\s*opts\.execute\s*=\s*a\.execute\s*;\s*",
               r"\1\n", s, flags=re.S)
    s = re.sub(r"(Command::Pack\(\s*a\s*\)\s*=>\s*{[^}]*?)\n\s*opts\.execute\s*=\s*a\.execute\s*;\s*",
               r"\1\n", s, flags=re.S)

    backwrite(cli_main_rs, s)

def ensure_gst_backend_exec(core_backend_gst_rs: pathlib.Path):
    # Minimal backend: executes when execute=true; plans otherwise.
    CONTENT = r'''// 0BSD — GStreamer backend (feature=gst)
#![cfg(feature = "gst")]
use anyhow::{anyhow, Result};
use gstreamer as gst;
use gstreamer::prelude::*;
use crate::backend::{Backend, RunOptions, QcOptions};

pub struct GstBackend;

impl GstBackend {
    fn ensure_inited() -> Result<()> { gst::init()?; Ok(()) }

    fn build_pipeline_string(opts: &RunOptions) -> String {
        let mut chain = vec![format!("filesrc location={} ! decodebin", crate::shell_escape::escape(&opts.input))];
        if opts.cfr || opts.fps.is_some() {
            let fps = opts.fps.unwrap_or(30);
            chain.push(format!("videorate ! video/x-raw,framerate={}/1", fps));
        }
        chain.push("x264enc tune=zerolatency ! mp4mux".into());
        chain.push(format!("filesink location={}", crate::shell_escape::escape(&opts.output)));
        chain.join(" ! ")
    }

    fn run_execute(pipe_str: &str) -> Result<()> {
        let el = gst::parse::launch(pipe_str)?;
        // If parse::launch returned a plain Element, put it into a Pipeline
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
        loop {
            match bus.timed_pop(gst::ClockTime::from_seconds(1)) {
                Some(msg) => match msg.view() {
                    gst::MessageView::Eos(..) => { pipeline.set_state(gst::State::Null)?; break; }
                    gst::MessageView::Error(e) => {
                        let err = e.error(); let dbg = e.debug().unwrap_or_default();
                        pipeline.set_state(gst::State::Null)?;
                        return Err(anyhow!("[gst] ERROR: {err:?} debug={dbg}"));
                    }
                    _ => {}
                },
                None => {}
            }
        }
        Ok(())
    }
}

impl Backend for GstBackend {
    fn name(&self) -> &'static str { "gst" }
    fn run(&self, opts: &RunOptions) -> Result<()> {
        Self::ensure_inited()?;
        let pipe = Self::build_pipeline_string(opts);
        if !opts.execute {
            println!("[gst] planned pipeline:\n  {}", pipe);
            return Ok(());
        }
        println!("[gst] executing with pipeline:\n  {}", pipe);
        Self::run_execute(&pipe)
    }
    fn probe(&self, path: &str) -> Result<crate::probe::ProbeReport> { crate::probe::cheap_probe(path) }
    fn qc(&self, _opts: &QcOptions) -> Result<crate::qc::QcReport> {
        Ok(crate::qc::QcReport{ psnr: None, ssim: None, vmaf: None, details: "QC via gst not implemented yet".into() })
    }
}
'''
    backwrite(core_backend_gst_rs, CONTENT)

def ensure_env():
    env = os.environ.copy()
    prefix = "/opt/homebrew"
    try:
        out = sh(["brew","--prefix"], check=False)
        if out.returncode == 0 and out.stdout.strip():
            prefix = out.stdout.strip()
    except Exception:
        pass
    env["PATH"] = f"{prefix}/bin:" + env.get("PATH","")
    env.setdefault("DYLD_FALLBACK_LIBRARY_PATH", f"{prefix}/lib")
    env.setdefault("GI_TYPELIB_PATH", f"{prefix}/lib/girepository-1.0")
    env.setdefault("GST_PLUGIN_PATH", f"{prefix}/lib/gstreamer-1.0")
    scanner = f"{prefix}/libexec/gstreamer-1.0/gst-plugin-scanner"
    if os.path.exists(scanner):
        env["GST_PLUGIN_SCANNER"] = scanner
    return env

def build_all(root, env):
    sh(["cargo","build"], cwd=root, env=env)
    sh(["cargo","build","-p","mmx-cli","-F","mmx-core/gst"], cwd=root, env=env)

def smoke(root, env):
    mmx = root / "target" / "debug" / "mmx"
    if not (root/"in.mp4").exists():
        sh(["gst-launch-1.0","-q",
            "videotestsrc","num-buffers=90",
            "!", "video/x-raw,framerate=30/1",
            "!", "x264enc",
            "!", "mp4mux",
            "!", "filesink","location=in.mp4"], cwd=root, env=env)
    # Plan
    sh([str(mmx),"run","--backend","gst","--input","in.mp4",
        "--output","out_plan.mp4","--cfr","--fps","30"], cwd=root, env=env)
    # Execute
    sh([str(mmx),"run","--backend","gst","--input","in.mp4",
        "--output","out_exec.mp4","--cfr","--fps","30","--execute"], cwd=root, env=env, check=False)
    out = root / "out_exec.mp4"
    if out.exists() and out.stat().st_size >= 100*1024:
        print(f"[ok] out_exec.mp4 generated ({out.stat().st_size} bytes)")
    else:
        print("[warn] out_exec.mp4 missing or too small. Ensure you're running target/debug/mmx just built.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    args = ap.parse_args()
    root = pathlib.Path(args.dir).expanduser().resolve()

    # Core edits
    ensure_runoptions_execute(root/"mmx-core"/"src"/"backend.rs")
    fix_cli_main(root/"mmx-cli"/"src"/"main.rs")
    ensure_gst_backend_exec(root/"mmx-core"/"src"/"backend_gst.rs")

    env = ensure_env()
    try:
        build_all(root, env)
    except Exception as e:
        print(f"[warn] build failed once: {e}\n→ retry after clean")
        sh(["cargo","clean"], cwd=root, env=env, check=False)
        build_all(root, env)

    try:
        smoke(root, env)
    except Exception as e:
        print(f"[warn] smoke test failed: {e}")

if __name__ == "__main__":
    main()
