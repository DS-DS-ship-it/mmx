#!/usr/bin/env bash
set -euo pipefail

mkdir -p sdk dist
rm -rf sdk/*

for dir in mmx-core mmx-cli mmx-ui; do
  [[ -d "$dir" ]] && cp -R "$dir" "sdk/$dir"
done

tar -czf dist/mmx-sdk.tar.gz -C sdk .
echo "dist/mmx-sdk.tar.gz"
