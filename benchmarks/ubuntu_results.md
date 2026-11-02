# Ubuntu measured results

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
