#!/usr/bin/env bash
# One-time setup per machine: Python packages and the Kokoro voice model (~350 MB).
# Needs ffmpeg, Node and Playwright with Chromium already installed.
set -euo pipefail
MODELS="${FACELESS_REEL_MODELS:-$HOME/.cache/faceless-reel}"
mkdir -p "$MODELS"
pip install -q kokoro-onnx soundfile faster-whisper pillow
REL=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
[ -s "$MODELS/kokoro.onnx" ] || curl -sSL -o "$MODELS/kokoro.onnx" "$REL/kokoro-v1.0.onnx"
[ -s "$MODELS/voices.bin" ]  || curl -sSL -o "$MODELS/voices.bin"  "$REL/voices-v1.0.bin"
for t in ffmpeg ffprobe node; do command -v "$t" >/dev/null || { echo "missing: $t"; exit 1; }; done
node -e "require('playwright')" || { echo "missing: playwright (npm i playwright)"; exit 1; }
echo "ready: models in $MODELS"
