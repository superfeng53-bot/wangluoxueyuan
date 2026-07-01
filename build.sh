#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv .build-venv 2>/dev/null || true
source .build-venv/bin/activate
pip install -q -r requirements.txt -r requirements-build.txt
python scripts/build.py "$@"
