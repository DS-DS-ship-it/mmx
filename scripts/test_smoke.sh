#!/bin/bash
set -e
echo "🧪 Running: doctor"
cargo run --bin doctor
echo "🧪 Simulating remux (input.mp4 → output.mp4)"
touch input.mp4
cargo run --bin remux input.mp4 output.mp4 || true
