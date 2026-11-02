# Ubuntu measured results

## CUDA adapter optimization — A2000, 2026-11-02

100 paired rotating rounds per configuration, one frame per backend per round,
10 warmup frames, same A2000 and same FP32 spectral/spatial settings. Mean wall
time includes the Python adapter and transfers, excludes codecs. Background display/video
work and a ComfyUI task on the other GPU continued; these are shared-workstation results.

| Portra 400 / Endura | Vulkan mean ms | Optimized CUDA mean ms | Speedup |
|---|---:|---:|---:|
| 720p color | 42.219 | 19.938 | 2.12x |
| 720p full | 52.582 | 36.857 | 1.43x |
| 720p temporal | 203.030 | 44.767 | 4.54x |
| 1080p color | 87.538 | 39.263 | 2.23x |
| 1080p full | 132.127 | 88.671 | 1.49x |
| 1080p temporal | 467.214 | 101.138 | 4.62x |

All 12 cases (including Vision3 500T/2383) beat Vulkan by mean time, and the
saved original CUDA output is bitwise equal in each compared final frame.
Full statistical samples, SD/P95, timer scope, quality checks and complete MP4 timings
are in [CUDA_OPTIMIZATION.md](../docs/CUDA_OPTIMIZATION.md).
The complete 250-frame MP4 commands took Vulkan/CUDA 43.442/33.220 s at 720p
and 99.383/76.871 s at 1080p, with matching codec/audio/color tags.
The existing ComfyUI Python 3.12.11/NumPy 2.5.4 installed-node bridge passes a
three-frame repeated temporal-grain test. No host dependencies or startup script changed.
Compute Sanitizer injection did not complete; no memcheck pass is claimed.


## Native CUDA follow-up — 2026-11-02

Current CLI/node controls now have a native CUDA spectral/spatial implementation.
The comparison below uses the **same RTX A2000 Laptop GPU**, identical input/config,
2 warmup frames and 12 samples, including NumPy/host transfer and excluding codec.
Vulkan is explicitly full-frame. The workstation has concurrent user GPU work;
these are measured samples, not a controlled idle-GPU hardware limit.

| Resolution | Full-effects Vulkan median ms | Initial CUDA ms | Grouped CUDA ms | Grouped CUDA GPU ms |
|---|---:|---:|---:|---:|
| 720p | 39.619 | 48.242 | 42.871 | 20.809 |
| 1080p | 89.931 | 109.282 | 95.928 | 48.087 |

The initial CUDA/Vulkan values were sampled in the preceding run; initial Vulkan
medians were 39.672/90.512 ms. Grouped CUDA uses the upstream default two-component
diffusion groups. CUDA events locate diffusion+halation at 10.253+6.775 ms (720p)
and 22.088+18.453 ms (1080p), about 82%/84% of CUDA GPU time. The unprofiled grouped
validation independently measured 1080p 96.068 ms CUDA / 89.923 ms Vulkan.

Color-only initial medians: 720p CUDA 24.977 / Vulkan 27.483 ms;
1080p CUDA 54.200 / Vulkan 61.207 ms. Native CUDA is currently faster for the color
chain and slower for full effects. No speedup is inferred from API name alone.

Initial full-effects CUDA CLI with CPU H.264/AAC, each 250 frames at 25fps:

| Resolution | Render/decode/encode s | fps | Whole command s | Video/audio s |
|---|---:|---:|---:|---|
| 720p | 33.910 | 7.373 | 34.592 | 10.000 / 10.005 |
| 1080p | 74.939 | 3.336 | 75.537 | 10.000 / 10.005 |

Both videos have BT.709 primaries/transfer/matrix and limited range. No new peak
VRAM/RSS measurements were collected for CUDA. These A2000 results are not compared
as a speed ratio against the older 3070 Ti table below.

Validation: all 160 film/print pairs pass, 100-frame CUDA repeat and independent
segments are exact, rho=.7 measured .69822. High-resolution cross-API grain cell
hashes can differ at float boundaries; see [CUDA_BACKEND.md](../docs/CUDA_BACKEND.md).
The grouped implementation passed the same validation and six local tests.
Live ComfyUI existing-Python image execution passes; a separate 320×180, 250-frame,
25fps native CUDA/AAC workflow passes with matching 10-second A/V duration.
Public numeric evidence: cuda-native-*.json under evidence/. No Resolve test.

## Original Vulkan benchmark — 2026-11-01

Measured 2026-11-01 (America/New_York). Source SHAs are in upstream/lock.json.

RTX 3070 Ti 8GB, NVIDIA 615.71.09, Vulkan-only ICD, Vulkan device index 1.
Ubuntu 24.04.4, Python 3.13.7, CMake 3.28.3, GCC 13.3.
Each input is a valid 10-second, 25fps, 250-frame moving MP4 with synthetic color
patterns, skin-like swatch, shadow/highlight patches and 440Hz AAC audio. These
are engineering test patterns, not calibrated chart or user camera footage.
Effects: upstream preview grain=.35, halation=.3, camera diffusion=.1; Portra 400
and Portra Endura; CPU libx264 encode, 8-bit limited-range Rec.709 YUV420 output.

| Resolution | Frames | Render/encode timer (s) | fps | Whole command (s) | Python peak RSS (MiB) | 3070 Ti peak total VRAM (MiB) | SDR clipped channels |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1280×720 | 250 | 49.790 | 5.021 | 53.686 | 448.4 | 454 | 5.385% |
| 1920×1080 | 250 | 84.803 | 2.948 | 85.508 | 666.5 | 684 | 5.405% |

The render timer includes reading frames, transfer conversions, render, encode
and encoder drain, but excludes imports, initialization and initial decoder/encoder
creation. Whole command timing includes those costs. VRAM is sampled device-total
usage every 0.2 seconds, including desktop/other processes, not isolated allocation.
3070 Ti baseline was 183 MiB; observed increases were 271 MiB and 501 MiB. RSS is
Python parent high-water sampling and excludes codec child processes. No aggregate
whole-process-tree memory peak or isolated GPU allocation peak is claimed.

| Resolution | Video duration (s) | Audio duration (s) | A/V difference (s) |
|---|---:|---:|---:|
| 720p | 10.000000 | 10.005000 | 0.005000 |
| 1080p | 10.000000 | 10.005000 | 0.005000 |

Both output streams were inspected with FFprobe, all 250 video frames present;
video tags are bt709 primaries/transfer/matrix and tv range. Full stream metadata
is retained in rendered-720p.ffprobe.json and rendered-1080p.ffprobe.json.

## Single-frame 4K smoke and color diagnostic

Single-frame timings with the same effects: 720p 0.0721s, 1080p 0.1687s, 4K 0.6596s. These are single-frame smoke measurements, not sustained fps or a 4K long-video validation.

CPU Python versus OFX Vulkan diagnostic, linear Rec.709 with spatial/grain disabled: RMSE=0.047607, peak-1 PSNR=26.447dB; clipped sRGB D65 CIEDE2000 mean=2.3115, max=8.2118.
Shared profile names and exposure do not align all data, calibration and defaults.
These differences are unresolved. This is not a strict parity acceptance or a fair
CPU-vs-GPU speed benchmark. Gray-channel spread and scene-range values are in
quality.json; no neutral-grade accuracy claim is made.

## Temporal verification

Fixed-seed 100-frame repeats and independent segment overlaps were exactly equal
in float output. Default upstream animated grain:
variance=1.1949781e-07, adjacent correlation=-0.009580, frame-mean std=4.953582e-06.
Bridge rho=.7 residual mixing produced measured adjacent spatial correlation 0.705239; repeated output was exactly equal.
EXR full-versus-split equality and resume/config rejection passed actual CLI tests.

## NVENC

The initial 64×64 HEVC capability probe failed because those dimensions are below
NVENC minimum. The adapter now probes the actual requested dimensions. A 256×256
probe succeeds. A separately processed 720p short clip used hevc_nvenc and retained
audio (examples/nvenc-720p.mp4 and logs/video-nvenc.log). The 10-second performance
table above deliberately reports the original CPU-encoder runs. Small-frame HEVC
testing exercised explicit auto fallback to libx265. No driver installation occurred.

## Test boundaries

* Original Python: 829 passed / 5 failed; raw log logs/python-full-tests.log.
* OFX Python SDR transfer: 11 passed.
* Original Vulkan half/float copy: passes in Debug and Release.
* Original core harness: fixed pass-count assertions fail; raw logs retained.
* New bridge + isolated node subprocess tests: 4 passed.
* Still-image IO/straight-alpha/TIFF16/negative-input checks: 2 passed; final local suite: 6 passed.
* Official LUT exports completed, each QA: 2 pass / 2 fail / 12 info.
* GUI constructed offscreen; no visual desktop or OFX-host validation.
* No real camera footage, full 4K clip, live ComfyUI, or Resolve benchmark yet.
