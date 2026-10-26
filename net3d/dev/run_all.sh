#!/usr/bin/env bash
# Runs the mock tests against ../scripts and renders the offline previews.
# Needs python3, node and Playwright with Chromium (require('playwright')).
set -euo pipefail
cd "$(dirname "$0")"
SCRIPTS="$(cd ../scripts && pwd)"
[ -d node_modules/three ] || npm install --silent
echo "== mock tests"
python3 -I test_dive.py "$SCRIPTS" x.json | grep -v '^focus'
python3 -I test_ui.py "$SCRIPTS" x.json | grep -v '^focus'
python3 -I test_type.py "$SCRIPTS" x.json | grep -v '^focus'
echo "== previews"
python3 -I export_scene.py "$SCRIPTS" scene.json
python3 -m http.server 8765 --bind 127.0.0.1 >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER' EXIT
sleep 1
node shoot.js
python3 -I dive_frames.py "$SCRIPTS" x.json && node shoot_dive.js
python3 -I type_frames.py "$SCRIPTS" x.json && node shoot_type.js
rm -rf "$SCRIPTS/__pycache__"
ls -1 *.png
