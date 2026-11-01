#!/usr/bin/env bash
# Build the game's zip (for Kolibri Games' Setup page) into dist/, with a checksum.
# Needs kolibri-games installed (its kolibri-games-pack checks the game).
set -euo pipefail
cd "$(dirname "$0")/.."
version="$(python -c 'import beacon_pack; print(beacon_pack.__version__)')"
rm -rf dist && mkdir -p dist
kolibri-games-pack game -o "dist/beacon-hunt-$version.zip"
kolibri-games-pack --check "dist/beacon-hunt-$version.zip"
(cd dist && sha256sum *.zip > SHA256SUMS)
ls -la dist
