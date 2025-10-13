# MMX Remux — Contributor Training (Quick)

## The one-liner prompt
Use this with your AI assistant:

> “Act as a senior Rust + GStreamer engineer pairing on MMX Remux.  
> I’m working on issue #NNN: <title>.  
> Propose the **smallest** patch that compiles on macOS + Linux, passes `cargo clippy -- -D warnings`, adds/updates a smoke test, and hides risky parts under the `experimental` Cargo feature.  
> Return: a diff (or full files), test updates, and a conventional commit message.”

## Expectations
- Small PRs (< 500 changed lines).  
- Green CI before merge.  
- No secrets in issues/PRs.  
- If in doubt: put code behind `--features experimental`.

## Local dev
```bash
# build
cargo build

# format + lint
cargo fmt --all
cargo clippy --all-targets -- -D warnings

# run smoke tests (add more in scripts/)
scripts/smoke_gen_fixture_mp4.sh
scripts/smoke_remux_mp4_to_mkv.sh

---

# Market Focus & Customer Personas (MMX Remux)

## What MMX Is
**MMX = Native Rust-based multimedia engine built on GStreamer (no FFmpeg).**
- Safer and leaner than FFmpeg (no GPL baggage).
- Embeddable (Rust crate/binary/API), cloud-friendly, cross-platform.

## Who Needs It Most (ranked by profit potential)
1. **Cloud Media Infrastructure** (AWS MediaConvert–style, Mux, Vimeo, Cloudflare Stream)  
   *Why:* Large transcoding spend, GPL risk, need reliability and cost/perf gains.  
   *Pitch:* “Cut encoding cost, remove GPL risk, container-native, Rust-safe.”  
   *Model:* Enterprise license + SLA.

2. **AI/ML Media Companies** (Runway, Synthesia, Pika, ElevenLabs)  
   *Why:* Petabyte-scale I/O, GPU/zero-copy, FFmpeg subprocess pain.  
   *Pitch:* “FFmpeg-free, embeddable Rust core for GPU/AI pipelines.”  
   *Model:* Per-seat SDK + support.

3. **Pro Tools & Engines** (DaVinci/Resolve, Reaper, OBS, Unreal, Blender)  
   *Why:* Need legal-safe import/export, App Store/Steam-friendly.  
   *Pitch:* “Drop-in media backend — one binary, no GPL, cross-platform.”  
   *Model:* Dual license (MIT/Apache for OSS, commercial for proprietary).

4. **Indie Devs & Automation** (YouTube ops, internal tools)  
   *Why:* Scriptable, predictable media ops without FFmpeg flag hell.  
   *Model:* Freemium CLI + paid “Pro” features.

5. **Gov/Broadcast/Secure**  
   *Why:* Auditable, hardened, C-free builds; FFmpeg cannot pass some audits.  
   *Model:* Hardened builds + LT support.

## Packaging & Pricing Ladder
- **CLI Core (OSS)**: Free (MIT/Apache).  
- **MMX Pro SDK**: $99–$499 per dev (parallel remux, HLS/DASH, GPU QC).  
- **Enterprise Server**: $5k–$50k/yr (REST control plane, scaling, SLA).  
- **Hardened/Secure Edition**: custom (> $100k + support).

## Messaging Cheat Sheet
- **Value:** “FFmpeg-free. Safer Rust core. Lower cost. Cloud-native.”  
- **Proof:** Universal2 macOS builds, clean CI, reproducible tarballs, smoke tests.  
- **CTA:** “Send us failing samples; we fix + optimize under SLA.”

## Execution for New Contributors
- Prioritize: reliability (Tier 0), build/pkgs (Tier 1), Pro features gated behind `--features pro`.  
- Every PR: smallest change, green CI, adds/updates a smoke test.  
- Sensitive code behind `experimental` or `pro` feature flags.

