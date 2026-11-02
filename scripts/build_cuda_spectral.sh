#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$FILMFORGE_ROOT"
if ! command -v nvcc >/dev/null; then
  echo 'CUDA toolkit nvcc is missing. This script does not install system packages.' >&2
  exit 1
fi
glm_sha=0af55ccecd98d4e5a8d1fad7de25ba429d60e863
if [[ ! -d .deps/glm ]]; then
  git clone --depth 1 --branch 1.0.1 https://github.com/g-truc/glm.git .deps/glm
fi
if [[ $(git -C .deps/glm rev-parse HEAD) != "$glm_sha" ]] || [[ -n $(git -C .deps/glm status --porcelain) ]]; then
  echo 'GLM must be the clean pinned 1.0.1 commit; existing files were preserved.' >&2
  exit 1
fi
cmake -S . -B build/cuda-spectral -G Ninja -DCMAKE_BUILD_TYPE=Release -DFILMFORGE_BUILD_CUDA=ON 2>&1 | tee logs/cuda-spectral-configure.log
cmake --build build/cuda-spectral --target filmforge_cuda_spectral --parallel 3 2>&1 | tee logs/cuda-spectral-build.log
cp .deps/glm/copying.txt build/cuda-spectral/GLM-LICENSE.txt
