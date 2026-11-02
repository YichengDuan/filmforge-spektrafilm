#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$FILMFORGE_ROOT"
exec python scripts/verify_media.py
