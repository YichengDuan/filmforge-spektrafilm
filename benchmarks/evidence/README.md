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

Full local working logs are excluded from Git. The original upstream suite was
829 passed / 5 failed; that outcome is reported in docs/KNOWN_LIMITATIONS.md.
