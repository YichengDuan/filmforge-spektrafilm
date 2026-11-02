#!/usr/bin/env bash
# Workspace-only staging. No system plugin installation by design.
set -euo pipefail
source "$(dirname "$0")/env.sh"
dry=0
destination="$FILMFORGE_ROOT/install/OFX/Plugins"
while (($#)); do
  case "$1" in
    --dry-run) dry=1; shift;;
    --destination) destination=$2; shift 2;;
    *) echo 'Usage: install_ofx_ubuntu.sh [--dry-run] [--destination WORKSPACE_PATH]' >&2; exit 2;;
  esac
done
destination=$(realpath -m "$destination")
[[ "$destination" == "$FILMFORGE_ROOT/"* ]] || { echo 'Isolation policy: destination must be inside this workspace' >&2; exit 2; }
shopt -s nullglob
bundles=("$FILMFORGE_ROOT"/build/ofx-Release/*.ofx.bundle)
((${#bundles[@]})) || { echo 'Build Release first' >&2; exit 1; }
for bundle in "${bundles[@]}"; do
  target="$destination/$(basename "$bundle")"
  printf '%s -> %s\n' "$bundle" "$target"
  if ((dry)); then continue; fi
  if [[ -e "$target" ]]; then
    [[ -f "$target/.filmforge-owned" ]] || { echo "Refusing unowned $target" >&2; exit 1; }
    mv "$target" "$target.backup-$(date +%Y%m%d%H%M%S%N)"
  fi
  mkdir -p "$destination"
  cp -a "$bundle" "$target"
  touch "$target/.filmforge-owned"
done
