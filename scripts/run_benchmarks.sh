#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$FILMFORGE_ROOT"
exec python scripts/benchmark_ubuntu.py
