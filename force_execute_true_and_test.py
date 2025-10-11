#!/usr/bin/env python3
# 0BSD — force-wire --execute end-to-end, rebuild with gst, smoke-test execution.

import argparse, pathlib, re, shutil, subprocess, sys, os, textwrap

def sh(cmd, cwd=None, env=None, check=True):
    print("→", " ".join(cmd))
    p = subprocess.run(cmd, cwd=cwd, env=env, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    sys.stdout.write(p.stdout)
    if check and p.returncode != 0:
        raise RuntimeError(f"command failed: {cmd}")
    return p

def backup(p: pathlib.Path):
    if p.exists():
        b = p.with_suffix(p.suffix + ".prepatch")
        if not b.exists():
            shutil.copy2(p, b)
            print(f"[backup] {p} → {b}")

def write(p: pathlib.Path, s: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    backup(p)
    p.write_text(s, encoding="utf-8")
    print(f"[write]  {p}")

def patch_runoptions_execute(core_backend_rs: pathlib.Path):
    txt = core_backend_rs.read_text(encoding="utf-8")
    changed = False

    # Ensure field in struct
    if "pub struct RunOptions" in txt and "execute: bool" not in txt:
        txt = re.sub(r"(pub\s+struct\s+RunOptions\s*{\s*[^}]*?)\n}",
                     r"\1\n    pub execute: bool,\n}", txt, flags=re.S)
        print("[add ] RunOptions.execute")
        changed = True

    # Ensure default false
    if "impl Default for RunOptions" in txt and "execute:" not in txt:
        txt = re.sub(
            r"(impl\s+Default\s+for\s+RunOptions\s*{\s*fn\s+default\(\)\s*->\s*Self\s*{\s*Self\s*{\s*[^}]*?)\n\s*}\s*}\s*",
            r"\1\n            execute: false,\n            }\n        }\n", txt, flags=re.S)
        print("[add ] RunOptions.execute default=false")
        changed = True

    if changed:
        write(core_backend_rs, txt)

def patch_cli_execute(cli_main_rs: pathlib.Path):
    t = cli_main_rs.read_text(encoding="utf-8")
    changed = False

    # Add --execute flag in RunArgs
    if re.search(r"struct\s+RunArgs\s*{", t) and "--execute" not in t:
        t = re.sub(r"(struct\s+RunArgs\s*{\s*[^}]*?)\n}",
                   r"\1\n    #[arg(long)]\n    execute: bool,\n}", t, flags=re.S)
        print("[add ] CLI --execute")
        changed = True

    # Wire into RunOptions
    if "opts.execute = a.execute" not in t:
        t = re.sub(r"(let\s+mut\s+opts\s*=\s*RunOptions::default\(\);\s*.*?)\n(\s*let\s+backend_name|\s*let\s+b\s*=|\s*if\s+let\s+)",
                   r"\1\n    opts.execute = a.execute;\n\2", t, flags=re.S)
        print("[wire] opts.execute <- a.execute")
        changed = True

    # Add a debug print so we can see the value
    if "Run planning:" in t and "execute=" not in t:
        t = re.sub(r'(Run planning:\\"\\n\\"\s*\),\s*',
                   r'Run planning:\\"\\n\\"\s*),\n        println!("  execute={}", opts.execute);\n        ',
                   t)
        changed = True

    if changed:
        write(cli_main_rs, t)

def patch_backend_gst_execute(core_backend_gst_rs: pathlib.Path):
    # Replace content with a safe version that executes when execute=true and prints execute flag.
    CONTENT = r"""// 0BSD — GStreamer backend (feature=gst)
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

    fn element_to_pipeline(el: gst::Element) -> Result<gst::Pipeline> {
        if let Ok(p) = el.clone().downcast::<gst::Pipeline>() { return Ok(p); }
        let p = gst::Pipeline::new();
        p.add(&el)?;
        Ok(p)
    }

    fn run_execute(pipe_str: &str) -> Result<()> {
        let el = gst::parse::launch(pipe_str)?;
        let pipeline = Self::element_to_pipeline(el)?;
        let bus = pipeline.bus().ok_or_else(|| anyhow!("no bus on pipeline"))?;
        pipeline.set_state(gst::State::Playing)?;
        loop {
            match bus.timed_pop(gst::ClockTime::from_seconds(1)) {
                Some(msg) => match msg.view() {
                    gst::MessageView::Eos(..) => { pipeline.set_state(gst::State::Null)?; println!("[gst] EOS"); break; }
                    gst::MessageView::Error(e) => {
                        let err = e.error(); let dbg = e.debug().unwrap_or_default();
                        pipeline.set_state(gst::State::Null)?;
                        return Err(anyhow!("[gst] ERROR: {err:?} debug={dbg}"));
                    }
                    gst::MessageView::StateChanged(s) => {
                        if let Some(src) = s.src() {
                            if src.downcast_ref::<gst::Pipeline>().is_some() {
                                println!("[gst] state: {:?} → {:?}", s.old(), s.current());
                            }
                        }
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
        println!("[gst] executing (execute=true) with pipeline:\n  {}", pipe);
        Self::run_execute(&pipe)
    }
    fn probe(&self, path: &str) -> Result<crate::probe::ProbeReport> { crate::probe::cheap_probe(path) }
    fn qc(&self, _opts: &QcOptions) -> Result<crate::qc::QcReport> {
        Ok(crate::qc::QcReport{ psnr: None, ssim: None, vmaf: None, details: "QC via gst not implemented yet".into() })
    }
}
"""
    write(core_backend_gst_rs, CONTENT)

def brew_prefix():
    try:
        return sh(["brew","--prefix"], check=False).stdout.strip() or "/opt/homebrew"
    except Exception:
        return "/opt/homebrew"

def ensure_env():
    env = os.environ.copy()
    prefix = brew_prefix()
    env["PATH"] = f"{prefix}/bin:" + env.get("PATH","")
    # Help dynamic loader & GI
    env.setdefault("DYLD_FALLBACK_LIBRARY_PATH", f"{prefix}/lib")
    env.setdefault("GI_TYPELIB_PATH", f"{prefix}/lib/girepository-1.0")
    env.setdefault("GST_PLUGIN_PATH", f"{prefix}/lib/gstreamer-1.0")
    # Scanner path
    cand = f"{prefix}/libexec/gstreamer-1.0/gst-plugin-scanner"
    if os.path.exists(cand):
        env["GST_PLUGIN_SCANNER"] = cand
    return env

def build(root: pathlib.Path, env):
    # full rebuild to be safe
    sh(["cargo","build"], cwd=root, env=env)
    sh(["cargo","build","-p","mmx-cli","-F","mmx-core/gst"], cwd=root, env=env)

def smoke(root: pathlib.Path, env):
    mmx = root / "target" / "debug" / "mmx"
    # create sample if missing
    if not (root/"in.mp4").exists():
        sh(["gst-launch-1.0","-q",
            "videotestsrc","num-buffers=120",
            "!", "video/x-raw,framerate=30/1",
            "!", "x264enc",
            "!", "mp4mux",
            "!", "filesink","location=in.mp4"], cwd=root, env=env)
    # plan
    sh([str(mmx),"run","--backend","gst","--input","in.mp4",
        "--output","out_plan.mp4","--cfr","--fps","30"], cwd=root, env=env)
    # execute
    sh([str(mmx),"run","--backend","gst","--input","in.mp4",
        "--output","out_exec.mp4","--cfr","--fps","30","--execute"], cwd=root, env=env, check=False)
    out = root/"out_exec.mp4"
    if out.exists() and out.stat().st_size >= 100*1024:
        print(f"[ok] execute produced {out.name} ({out.stat().st_size} bytes)")
    else:
        print("[warn] execute didn’t produce a large file; printing fallback hints:\n"
              "  - Ensure you’re running the gst-enabled binary you just built.\n"
              "  - Re-run: cargo build -p mmx-cli -F mmx-core/gst && target/debug/mmx run ... --execute\n"
              "  - Check GST env vars (GST_PLUGIN_SCANNER, DYLD_FALLBACK_LIBRARY_PATH, GI_TYPELIB_PATH, GST_PLUGIN_PATH)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="path to mmx workspace")
    args = ap.parse_args()
    root = pathlib.Path(args.dir).expanduser().resolve()
    core = root/"mmx-core"/"src"
    cli  = root/"mmx-cli"/"src"

    # 1) force wiring
    patch_runoptions_execute(core/"backend.rs")
    patch_cli_execute(cli/"main.rs")
    patch_backend_gst_execute(core/"backend_gst.rs")

    # 2) build & smoke
    env = ensure_env()
    try:
        build(root, env)
    except Exception as e:
        print(f"[warn] build failed once: {e}\n→ retry after clean")
        sh(["cargo","clean"], cwd=root, env=env, check=False)
        build(root, env)

    # 3) smoke test
    try:
        smoke(root, env)
    except Exception as e:
        print(f"[warn] smoke test failed: {e}")

    # 4) echo exports for convenience
    prefix = brew_prefix()
    exports = f"""
# Add to your shell profile (~/.zprofile) if needed:
export HOMEBREW_PREFIX="{prefix}"
export PATH="$HOMEBREW_PREFIX/bin:$PATH"
export GST_PLUGIN_SCANNER="$HOMEBREW_PREFIX/libexec/gstreamer-1.0/gst-plugin-scanner"
export DYLD_FALLBACK_LIBRARY_PATH="$HOMEBREW_PREFIX/lib${{DYLD_FALLBACK_LIBRARY_PATH+:$DYLD_FALLBACK_LIBRARY_PATH}}"
export GI_TYPELIB_PATH="$HOMEBREW_PREFIX/lib/girepository-1.0${{GI_TYPELIB_PATH+:$GI_TYPELIB_PATH}}"
export GST_PLUGIN_PATH="$HOMEBREW_PREFIX/lib/gstreamer-1.0${{GST_PLUGIN_PATH+:$GST_PLUGIN_PATH}}"
""".strip()
    print("\n[env] Suggested exports:\n" + exports + "\n")

if __name__ == "__main__":
    main()
