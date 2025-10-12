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
