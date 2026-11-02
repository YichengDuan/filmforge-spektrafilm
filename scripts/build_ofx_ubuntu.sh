#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
config=${1:-Release}
[[ "$config" == Release || "$config" == Debug ]] || { echo 'Expected Release or Debug' >&2; exit 2; }
mkdir -p "$FILMFORGE_ROOT/logs"
build="$FILMFORGE_ROOT/build/ofx-$config"
cmake -S "$FILMFORGE_ROOT/upstream/spektrafilm-ofx" -B "$build" -G Ninja \
  -DCMAKE_BUILD_TYPE="$config" \
  -DPython3_EXECUTABLE="$FILMFORGE_ROOT/.venv/bin/python" \
  -DSPEKTRAFILM_OFX_ROOT="$FILMFORGE_ROOT/upstream/openfx" \
  -DVulkan_INCLUDE_DIR="$FILMFORGE_ROOT/.deps/root/usr/include" \
  -DVulkan_LIBRARY=/usr/lib/x86_64-linux-gnu/libvulkan.so.1 \
  -DCMAKE_INSTALL_PREFIX="$FILMFORGE_ROOT/install" \
  2>&1 | tee "$FILMFORGE_ROOT/logs/ofx-$config-configure.log"
cmake --build "$build" --parallel "${BUILD_JOBS:-4}" 2>&1 | tee "$FILMFORGE_ROOT/logs/ofx-$config-build.log"
