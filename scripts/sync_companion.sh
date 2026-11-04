#!/usr/bin/env sh
# Copies the standalone recorder and SSRF guard into the companion so it ships without the backend.
set -eu
cd "$(dirname "$0")/.."
mkdir -p desktop/companion/vendor
cp backend/app/browser/recorder.py desktop/companion/vendor/recorder.py
cp backend/app/services/ssrf.py desktop/companion/vendor/ssrf.py
touch desktop/companion/vendor/__init__.py
echo "Synced vendor files."
