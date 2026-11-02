# Published validation evidence

These are measured test outputs from the original Ubuntu workstation. Absolute
workspace paths were replaced with `<workspace>`; test-temp account names are
redacted. Numeric measurements and failures are unchanged. No raw nvidia-smi
process inventory, credentials, personal configuration or generated LUTs are
included. JSON files preserve the recorded commands, parameters and media metadata.

* local-tests.txt: six bridge, node subprocess and still-IO tests pass.
* ofx-transfer-tests.txt: eleven upstream SDR transfer tests pass.
* vulkan-copy-*.txt: actual half/float copies pass in Debug and Release.
* vulkan-print-scan.txt and vulkan-camera-diffusion.txt: examples of unresolved
  upstream harness assertion failures, retained without suppressing them.
* video-results.json: 720p/1080p measurements, stream metadata and A/V durations.
* video-*.metrics.json: sampled device-total VRAM and parent-process RSS.
* media-verification.json: lossless segment alignment, resume, fallback and errors.
* cuda-native-validation.json: initial CUDA 160-pair, effect, temporal and timing tests.
* cuda-native-grouped-validation.json: regression after two-component diffusion grouping.
* cuda-native-grouped-profile.json: opt-in CUDA events and same-GPU Vulkan timings.
* cuda-native-video.json: 720p/1080p 250-frame CUDA MP4/AAC and color metadata validation.
* cuda-native-comfyui-*.json: sanitized live host image and 320×180 video workflow results.
* cuda-opt-a2000-100rounds.json: final 100-round means, sample SD/P95 and raw samples;
  same-GPU rotating-order comparison, all 12 configurations beat Vulkan by mean time.
* cuda-opt-baseline-qa.json: exact original/optimized CUDA checks for geometry, alpha,
  noncontiguous arrays, temporal mixing, profiles and buffer ownership.
* cuda-opt-validation.json: 160 profile, effects and stateless temporal regressions.
* cuda-opt-video-a2000.json: full 250-frame MP4 comparisons with CPU H.264/AAC.
* cuda-opt-host-node.json: existing-host Python installed-node repeat test.

Full local working logs are excluded from Git. The original upstream suite was
829 passed / 5 failed; that outcome is reported in docs/KNOWN_LIMITATIONS.md.
