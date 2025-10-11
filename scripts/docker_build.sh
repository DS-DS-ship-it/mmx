#!/usr/bin/env bash
set -euo pipefail
docker build -t mmx:local .
docker run --rm mmx:local --help
