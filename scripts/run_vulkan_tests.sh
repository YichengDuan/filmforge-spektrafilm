#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$FILMFORGE_ROOT"
export SPEKTRAFILM_VULKAN_DEVICE_INDEX=1
export VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/nvidia_icd.json
for config in Release Debug; do
  "build/ofx-$config/SpektraVulkanCopyHarness" --width 320 --height 180 --iterations 2 > "logs/vulkan-copy-$config.log" 2>&1
done
for pass in print-scan halation camera-diffusion print-diffusion dir scanner-post preview-grain production-grain; do
  set +e
  build/ofx-Release/SpektraVulkanCopyHarness --width 320 --height 180 --iterations 2 --float-only --print-scan-pass "--$pass-pass" > "logs/vulkan-$pass.log" 2>&1
  status=$?
  printf '\nexit=%s\n' "$status" >> "logs/vulkan-$pass.log"
  set -e
done
python -m pytest tests/test_bridge.py tests/test_comfy_bridge.py -v > logs/bridge-tests.log 2>&1
