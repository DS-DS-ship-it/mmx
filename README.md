# MMX Remux (alpha)
**Native Rust remuxer on GStreamer (no FFmpeg).**

MMX Remux stream-copies (remuxes) audio/video from one container to another using the GStreamer media stack via Rust bindings. No transcoding, no FFmpeg dependency.

> ⚠️ Alpha quality. Expect rough edges. Please file issues with sample files that break.

## Features
- Remux **MP4 ⇄ MKV ⇄ WebM** (depends on installed GStreamer plugins)
- Zero re-encode (stream copy)
- Auto input detection via demuxers
- Simple CLI (`mmx-remux in.mp4 out.mkv`)
- Cross-platform builds (macOS universal2, Linux x86_64)

## Install

### Homebrew (after first release)
```bash
brew tap DS-DS-ship-it/mmx-remux
brew install mmx-remux

---

## Get paid to contribute

We’re running a small paid-contributors program for MMX Remux.

1) **Create a Stripe account** (free):  
   👉 https://dashboard.stripe.com/register  
   (Learn more: https://stripe.com/docs/connect)

2) **Open the “Join paid contributor program” issue** (Issue Forms).  
   We’ll review, approve, and email onboarding details.

3) **Payment**: approved tasks are paid via Stripe.  
   *Never paste secrets or private keys into GitHub.*

---

## Training quickstart (1-liner to use with any AI assistant)

Copy/paste this:

> *“Act as a senior Rust + GStreamer engineer pairing on MMX Remux (repo: https://github.com/DS-DS-ship-it/mmx).  
> I’m working on issue #NNN: <title>.  
> Please propose the **smallest** patch that: (1) builds on macOS and Linux, (2) passes `cargo clippy -- -D warnings`, (3) includes a smoke test or update to `scripts/`, and (4) hides risky code behind the `experimental` Cargo feature.  
> Return: a diff (or file drops), test updates, and a conventional commit message.”*

Replace `DS-DS-ship-it/mmx` and issue number, then paste the patch into a PR.

---

## Safe intake (samples & ideas)

- **Samples / failing files:** open the “Sample intake” issue (drag-and-drop files or link to cloud storage).  
- **Feature requests:** open the “Feature request” issue.  
- CI ensures **main (master) always works**; unstable work lives behind the `experimental` Cargo feature or on branches.

## Further reading
- [Training](docs/TRAINING.md)
- [Go To Market](docs/GO_TO_MARKET.md)

---

Want to help build a native Rust remuxer (no FFmpeg) and get paid for merged work?
**[Apply here →](https://github.com/DS-DS-ship-it/mmx/issues/new?template=join_program.yml)**

# mmx video player

A lightweight PyQt6 video player with a hex background, filter panel, and a **frame-accurate timeline**.

## Run from source
```bash
python3 -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python video_gui_pro8.py

Video Player:
Linux (AppImage-like single file)
python3 -m pip install -r requirements.txt
pyinstaller --onefile --windowed --name mmx-video-player video_gui_pro8.py

Windows (.exe)
py -3 -m pip install -r requirements.txt
pyinstaller --onefile --windowed --name mmx-video-player --icon icons\mmx.ico video_gui_pro8.py

