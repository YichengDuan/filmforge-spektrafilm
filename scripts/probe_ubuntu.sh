#!/usr/bin/env bash
set -uo pipefail
source "$(dirname "$0")/env.sh"
mkdir -p "$FILMFORGE_ROOT/logs"
{
  date -Is
  for command in 'uname -a' 'lsb_release -a' 'lspci -nn' 'nvidia-smi' 'vulkaninfo --summary' 'python3 --version' 'cmake --version' 'ffmpeg -version' 'which glslc' 'which glslangValidator' 'df -h .' 'free -h'; do
    printf '\n$ %s\n' "$command"
    bash -c "$command"; printf 'exit=%s\n' "$?"
  done
  printf '\nDISPLAY=%s\nWAYLAND_DISPLAY=%s\n' "${DISPLAY-}" "${WAYLAND_DISPLAY-}"
  for repo in spektrafilm spektrafilm-ofx openfx; do
    printf '\n%s SHA: ' "$repo"
    git -C "$FILMFORGE_ROOT/upstream/$repo" rev-parse HEAD
  done
  printf '\nResolve executable: '; command -v resolve || true
  test ! -e /opt/resolve/bin/resolve || printf '/opt/resolve/bin/resolve exists\n'
} 2>&1 | tee "$FILMFORGE_ROOT/logs/environment.txt"
