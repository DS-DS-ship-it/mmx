#!/usr/bin/env python3
# 0BSD — tiny smoke tester for mmx --backend gst --execute
import argparse, os, subprocess, sys, pathlib, shutil

def sh(cmd, cwd=None, env=None):
    print("→", " ".join(cmd))
    p = subprocess.run(cmd, cwd=cwd, env=env, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    sys.stdout.write(p.stdout)
    return p.returncode == 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mmx", required=True, help="path to mmx binary")
    ap.add_argument("--dir", required=True, help="workspace dir (contains target, etc.)")
    args = ap.parse_args()

    root = pathlib.Path(args.dir).expanduser().resolve()
    mmx = pathlib.Path(args.mmx).expanduser().resolve()
    os.chdir(root)

    # env hints for Homebrew gst
    env = os.environ.copy()
    prefix = shutil.which("brew")
    if prefix:
        # rely on your exported variables from the shell, but try to help if unset
        env.setdefault("GST_PLUGIN_PATH", "/opt/homebrew/lib/gstreamer-1.0")
        env.setdefault("GI_TYPELIB_PATH", "/opt/homebrew/lib/girepository-1.0")
        env.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")

    # 1) create sample input if missing
    if not (root / "in.mp4").exists():
        ok = sh(["gst-launch-1.0","-q","videotestsrc","num-buffers=120",
                 "!", "video/x-raw,framerate=30/1",
                 "!", "x264enc",
                 "!", "mp4mux",
                 "!", "filesink","location=in.mp4"], cwd=root, env=env)
        if not ok:
            print("[err] failed to create in.mp4 with gst-launch-1.0")
            sys.exit(2)

    # 2) plan (no execute)
    sh([str(mmx),"run","--backend","gst","--input","in.mp4",
        "--output","out_plan.mp4","--cfr","--fps","30"], cwd=root, env=env)

    # 3) execute
    ok = sh([str(mmx),"run","--backend","gst","--input","in.mp4",
             "--output","out_exec.mp4","--cfr","--fps","30","--execute"], cwd=root, env=env)
    if not ok:
        print("[err] mmx run --execute failed")
        sys.exit(3)

    # 4) validate file exists and has content
    out = root / "out_exec.mp4"
    if not out.exists() or out.stat().st_size < 1024:
        print("[err] out_exec.mp4 missing or too small")
        sys.exit(4)

    print("[ok] execution succeeded; out_exec.mp4 =", out.stat().st_size, "bytes")

if __name__ == "__main__":
    main()
