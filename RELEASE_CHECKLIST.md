# Release checklist — MMX Remux

## Preflight
- [ ] `cargo build --release` succeeds on macOS + Linux
- [ ] `mmx-remux --help` looks correct
- [ ] `README.md` install examples match tap and version
- [ ] Version bumped in `mmx-cli/Cargo.toml` (e.g. 0.1.0-alpha.1)

## Tag & GitHub Release
- [ ] Tag: `git tag vX.Y.Z && git push --tags`
- [ ] CI artifacts appear on the tag (universal2 macOS, linux x86_64)
- [ ] Create GitHub Release from the tag and attach binaries

## Homebrew (tap)
- [ ] Update `Formula/mmx-remux.rb` with new version, SHA256, URL
- [ ] `brew tap <your-username>/mmx-remux`
- [ ] `brew install mmx-remux`
- [ ] `mmx-remux --version` prints vX.Y.Z

## Verify
- [ ] Remux sanity: `mmx-remux in.mp4 out.mkv`
- [ ] Validate: `gst-discoverer-1.0 out.mkv` (streams, duration OK)

## Announce
- [ ] Changelog entry
- [ ] Open an Issue for next milestone (bugs/requests collected)
