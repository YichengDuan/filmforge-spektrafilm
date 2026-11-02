#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$FILMFORGE_ROOT"
test -s build/ofx-Release/generated/SpektraGeneratedProfileCurves.cpp || { echo 'Build OFX Release first' >&2; exit 1; }
cmake -S . -B build/bridge -G Ninja -DCMAKE_BUILD_TYPE=Release 2>&1 | tee logs/bridge-configure.log
cmake --build build/bridge --parallel "${BUILD_JOBS:-4}" 2>&1 | tee logs/bridge-build.log
