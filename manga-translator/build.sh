#!/bin/sh
# Packages the extension into dist/manga-lens-translator.zip, ready to upload to
# addons.mozilla.org for free signing.
set -e
cd "$(dirname "$0")"
mkdir -p dist
rm -f dist/manga-lens-translator.zip
zip -q -r -X dist/manga-lens-translator.zip manifest.json background.js content.js content.css popup.html popup.css popup.js icons
echo "Built dist/manga-lens-translator.zip"
