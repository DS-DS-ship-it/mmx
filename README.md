# MMX — Hybrid Media Engine (Open Core)

Open-core multimedia stack in Rust:
- `mmx-core` — engine & APIs (MIT)
- `mmx-cli` — CLI (MIT)
- `mmx-pro` — commercial add-ons (GPU/GUI/Cloud)

## Install (from source)
```bash
cargo build -p mmx-cli -F mmx-core/gst --release
./target/release/mmx --help
```

## Pricing
| Tier     | Includes                                     | Price |
|----------|----------------------------------------------|-------|
| Community| mmx-core + mmx-cli (MIT)                     | Free  |
| Indie    | GPU accel + ABR presets + error aide         | $49  |
| Studio   | GUI + Cloud scheduler + priority support     | $499 |

**Buy Pro:** https://example.com/buy

## Telemetry
Opt-in only: set `MMX_TELEMETRY=on`. Captures command, exit, duration (no paths).

## License
Core is MIT. Pro is commercial.
