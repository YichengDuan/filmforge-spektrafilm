# Known limitations and unresolved validation

* Upstream Python suite: 829 pass, 5 fail. One GUI fake has the wrong addWidget
  signature; one LUT-mode test references removed GrainParams.mult_usm_amount;
  three committed print RGB baseline images differ (max absolute differences
  include 0.007131 gray ramp and 0.05176 green patch). Baselines were not changed.
* Official Python LUT QA: both 33³ and 65³ builds finish, but monotonicity and
  output gamut compression fail. Smaller interpolation error does not settle
  those model/QA failures.
* OFX copy succeeds on actual GPU in float16 and float32. Core/spatial harness
  tests reach finite pixels/alpha checks but then fail outdated expected-pass
  counts: print+scan expects 3, gets 4; halation expects 21, gets 22; optimized
  diffusion has substantially different counts. The original tests are not
  silently bypassed. Independent bridge effect/temporal tests pass.
* Source builds three flavors: spektrafilm, flow, dev. It does not build the
  website's diffuse and lens flavors. Source Linux version is 0.1.9, not the
  website's advertised 0.3.12. Official binaries were not downloaded or executed.
* No Resolve found at checked locations; no host plugin recognition/export test.
  Live ComfyUI registration and image/video API workflows were subsequently
  tested on the user's existing Python 3.12.11/NumPy 2.5.4 without package changes.
  VHS/manual UI interactions remain untested. Original GUI only constructed offscreen; Qt warned that
  QOpenGLWidget is unsupported on that offscreen platform.
* CPU and Vulkan differ with shared profile names: diagnostic RMSE and DeltaE
  are reported in benchmarks/quality.json. Defaults/data/calibration are not
  fully aligned, so no CPU/OFX parity, neutral-grade accuracy or fair speedup
  claim is made. Synthetic swatches are not a measured ColorChecker.
* 4K only single-frame smoke, not a sustained throughput/VRAM guarantee. GPU
  memory samples are whole-device usage and include other processes. Parent
  RSS excludes codec child processes; a whole-process-tree peak is not reported.
* Offline MVP exposes exposure, preview density grain, halation, camera
  diffusion and film/print choice. DIR tuning, print diffusion, production grain
  controls, scanner options, LUT export from OFX, gate weave and flicker are not
  exposed. Gate weave/flicker are not present in this checkout's RenderParams.
* Native CUDA now covers the current CLI/node controls, not all OFX controls.
  Production/synthesis grain, DIR, print diffusion, scanner tuning and HDR are
  not exposed in this CUDA path. Cross-API grain cells can differ at float
  boundaries; within-CUDA repeated and segmented output is exact. Initial CUDA
  full-effects rendering was slower; current optimizations and same-GPU timed
  comparisons are documented in CUDA_OPTIMIZATION.md. No GPU tensor interop or
  asynchronous frame overlap is claimed.
* Compute Sanitizer failed to inject before the first instrumented CUDA API on
  this workstation, so memory instrumentation is unverified. Numeric A/B,
  geometry/fallback/alpha, 100-frame temporal, live host bridge and media tests
  pass. Nsight Compute did not collect kernel counters; reported GPU stage
  timings use CUDA events. No system profiler permissions or drivers were changed.
* Optional CUDA LUT interpolation is color-only, not a spectral/spatial port;
  its nonzero grain/spatial settings are rejected. CPU mode is deterministic physical color, with unsupported
  spatial/grain amounts rejected. CPU fallback must be explicitly selected.
* Correlated grain is optional linear residual mixing of upstream renders, not
  a native OFX temporal mode or AR(1) model. See VIDEO_COLOR_PIPELINE.md.
* 8-bit SDR CFR video only; no validated HDR/10-bit/VFR/rotation/nonzero stream
  starts, ICC conversion, subtitles/timecode or arbitrary original timestamps.
  Audio is optional AAC transcoding, not bit-exact passthrough.
* Input sequences are lexically sorted image directories with uniform geometry
  and caller-provided fps. There is no image-sequence pattern expansion or gap
  reconstruction. EXR output is lossless float; TIFF output is bounded 16-bit
  from test_still.py. For non-RGB EXRs convert to explicit RGB first.
* Resume re-decodes from the beginning and re-encodes the movie; it reuses EXR
  renders, not partially encoded MP4 packets. Source path/size/mtime and runtime
  hashes are checked; maliciously preserved source stat metadata is not detected.
* Current CMake bridge is Ubuntu x86_64-specific (system Vulkan loader path).
  Read-only preinstalled OS libraries are used; the project is dependency-isolated,
  not a fully hermetic VM/container. No global package or driver changes were made.
