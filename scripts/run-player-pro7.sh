#!/usr/bin/env bash
set -euo pipefail
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -r MMXHydra/requirements.txt
python3 MMXHydra/video_gui_pro7.py
