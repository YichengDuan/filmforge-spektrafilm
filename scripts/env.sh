#!/usr/bin/env bash
# Source this file; all mutable caches and dependencies stay in this workspace.
FILMFORGE_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
export FILMFORGE_ROOT
export PATH="$FILMFORGE_ROOT/.venv/bin:$FILMFORGE_ROOT/.deps/root/usr/bin:$FILMFORGE_ROOT/bin:$PATH"
export LD_LIBRARY_PATH="$FILMFORGE_ROOT/.deps/root/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export UV_CACHE_DIR="$FILMFORGE_ROOT/.cache/uv"
export UV_PYTHON_INSTALL_DIR="$FILMFORGE_ROOT/.python"
export XDG_CACHE_HOME="$FILMFORGE_ROOT/.cache"
export XDG_CONFIG_HOME="$FILMFORGE_ROOT/.config"
export XDG_DATA_HOME="$FILMFORGE_ROOT/.local/share"
export NUMBA_CACHE_DIR="$FILMFORGE_ROOT/.cache/numba"
export MPLCONFIGDIR="$FILMFORGE_ROOT/.cache/matplotlib"
export PYTHONPATH="$FILMFORGE_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR="$FILMFORGE_ROOT/.cache/tmp"
export CUDA_CACHE_PATH="$FILMFORGE_ROOT/.cache/cuda"
export __GL_SHADER_DISK_CACHE_PATH="$FILMFORGE_ROOT/.cache/nvidia"
mkdir -p "$TMPDIR"
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-8}
export NUMBA_NUM_THREADS=${NUMBA_NUM_THREADS:-8}
export OPENBLAS_NUM_THREADS=8
