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
