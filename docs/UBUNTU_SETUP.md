# Workspace-only setup

All project downloads, caches, Python, .deb extraction, build outputs, plugin
staging and temporary node jobs live below this directory. Scripts never invoke
sudo, install system packages, change drivers, run remote installers, or modify an
existing ComfyUI. The existing Ubuntu C++ compiler, CMake, NVIDIA Vulkan driver
and other preinstalled shared libraries are read-only runtime prerequisites.
The workspace is about 2.5 GB at first validation; disk had 43 GB free initially.

Test host: Ubuntu 24.04.4 x86_64, kernel 7.0.0-38-generic, GCC 13.3, CMake 3.28.3,
Python 3.13.7 (downloaded locally by uv). NVIDIA 615.71.09, RTX 3070 Ti 8 GB and
RTX A2000 Laptop 8 GB. CUDA toolkit 12.0 was detected but is not used by this
project. Vulkan loader/headers 1.3.275; NVIDIA advertises Vulkan 1.4.351.
Glslang 15.1, Ninja 1.11.1, FFmpeg 6.1.1. DISPLAY=:0, WAYLAND_DISPLAY unset.

```bash
bash scripts/setup_ubuntu.sh
bash scripts/probe_ubuntu.sh
bash scripts/build_ofx_ubuntu.sh Release
bash scripts/build_ofx_ubuntu.sh Debug
bash scripts/build_bridge.sh
bash scripts/install_ofx_ubuntu.sh --dry-run
bash scripts/install_ofx_ubuntu.sh
```

setup uses the already installed `uv` executable. On a fresh host lacking uv,
install uv through your chosen trusted package source; the script deliberately
does not download and execute an installer. Python dependencies are pinned in
requirements.lock; Ubuntu package versions in .deps/package-versions.txt and
download checksums in .deps/packages.sha256. Sources are pinned in
upstream/lock.json. Existing source trees are only checked, never reset.
Package download availability depends on the Ubuntu archive retaining versions.
No system-wide Python or site-packages changes are required.

Separate OFX checkout layout works by passing an explicit OpenFX SDK root and
Python executable to CMake. It does not require modifying the original tree or
nesting a second clone in OFX/SpektraFilm. Sources remain clean (`git status`).
Release/Debug build configs and all output are in logs/. Shader compilation is
part of the actual build. There is no assumption that copying a prebuilt bundle
is equivalent to compiling the source.

## GPU selection

On this machine, NVIDIA-only Vulkan enumeration is A2000 at index 0 and
RTX 3070 Ti at index 1. This differs from nvidia-smi (3070 Ti at index 0).
Do not transplant that index to a different machine without checking:

```bash
source scripts/env.sh
VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json vulkaninfo --summary
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json
export SPEKTRAFILM_VULKAN_DEVICE_INDEX=1
bash scripts/run_vulkan_tests.sh
```

A restricted sandbox initially hid /dev/nvidia and /dev/dri and caused nvidia-smi
to fail; host-side read-only detection confirmed working GPUs. No driver repair
was necessary. GPU tests need device access in their execution environment.

## Local plugin staging only

install_ofx_ubuntu.sh stages bundles at install/OFX/Plugins inside this workspace.
It supports --dry-run, refuses destinations outside the workspace, refuses to
replace unowned directories, and backs up owned previous copies. It does not
write /usr/OFX/Plugins. A future explicitly chosen host can use OFX_PLUGIN_PATH
if that host supports it; this has not been host-tested. Resolve was not found
in PATH or at /opt/resolve/bin/resolve. No Resolve was installed.

## Verification

```bash
source scripts/env.sh
python scripts/test_still.py --input-space linear-rec709
python scripts/test_still.py --input-space linear-rec709 --output examples/test-float.exr
python -m pytest upstream/spektrafilm/tests -q
python -m pytest upstream/spektrafilm-ofx/tests -v
bash scripts/run_vulkan_tests.sh
bash scripts/run_media_tests.sh
python scripts/quality_ubuntu.py
```

Upstream test failures are documented, not hidden or replaced with new baselines.
GUI construction was checked offscreen using scripts/gui_smoke.py; actual
desktop/OpenGL interaction remains unverified.
