#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== Boris quality tests =="
python -m unittest discover -s tests/boris_quality -v
