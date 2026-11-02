# Offline media contract

Vulkan backend is the unchanged upstream OFX VulkanRenderer and compute shaders,
not a recreated final-RGB film filter. The C ABI only supplies frame buffers,
parameters and time. Profile names are enumerated from compiled profile tables.
Auto exposure stays off to avoid image-global temporal exposure changes.

Video path: FFprobe verifies SDR metadata and constant fps → FFmpeg decodes
YUV using Rec.709 matrix and source range into full-range RGB code values →
explicit inverse BT.709 OETF (or explicit --input-transfer srgb) → scene-linear
Rec.709 RGB → upstream spectral exposure / optional diffusion and halation /
development with grain / print / scan → linear Rec.709 output → BT.709 OETF →
explicit SDR clipping, quantization to 8-bit RGB → FFmpeg Rec.709 limited-range
YUV 4:2:0 → H.264 or H.265. Primaries, transfer, matrix and range are tagged.
Clipped-channel fraction is reported. This is OETF-based SDR transport; it is
not a calibrated display EOTF/BT.1886 or HDR mastering workflow.

PNG/TIFF image defaults are **encoded sRGB**, EXR defaults **linear Rec.709**.
Use --input-transfer to override explicitly. An arbitrary ICC/wide-gamut image
must be converted before this bridge; no embedded ICC inference is claimed.
Read_image scales integer channels to float via OpenImageIO, and the selected
transfer is decoded once. EXR retains scene-linear values above 1; negative or
non-finite spectral RGB input is rejected. Straight alpha is preserved in EXR,
never simulated; video output drops alpha explicitly through RGB encoding.
Premultiplied alpha is unsupported and must be unassociated by the caller.

--frames-dir writes float32 scene-linear EXR frames as a lossless validation
baseline. Atomic frame rename prevents a partially written EXR being reused.
--resume checks a manifest covering source path/size/mtime, parameters, start
index, transfer, dimensions, fps and hashes of bridge code/library/shaders and
float tables. It re-decodes source frames and reuses completed matching EXRs,
then re-encodes the movie. It does not resume inside a partly encoded MP4. A
modified source with artificially preserved stat metadata is not detected.

The adapter holds one frame (plus render/codec scratch) at a time. ComfyUI sends
an existing host batch via temporary memory-mapped NPY files; no model weights
are copied into the renderer process. No pinned-memory/double-buffer claims are
made. Backend selection is explicit: Vulkan or CPU physical. Vulkan failures
produce an error; use --backend cpu-physical for deterministic CPU color only.

## Temporal grain

Upstream grain is applied during film density development. Its animated frame
index is floor(time*24+0.5); the bridge passes absolute frame_index/24 so any media
fps gets the correct absolute grain frame index. Seed is a stable SHA-256-derived
uint32 of user seed and film profile. --start-frame controls the absolute grain
index; it does not seek in the source. Set it to the source segment's starting
frame when processing independent clips.

Default correlation=0 uses upstream grain without residual mixing. Optional
correlation rho>0 is a **bridge extension**, not OFX parity: render the upstream
grain-free base O, a fixed upstream grain realization Gs, and the frame-indexed
realization Gf; output O+sqrt(rho)*(Gs-O)+sqrt(1-rho)*(Gf-O) in linear scan RGB.
This gives a reproducible shared component; nonlinear scan/grain bias means rho
is a control, not an exact guarantee in every image. It needs three renders per
frame and can produce out-of-range values; SDR clipping is reported. It is not
an AR(1) decay model and correlation does not decay with long frame separation.
No grain noise is invented in final sRGB. Temporal tests are in benchmarks/temporal.json.

## Media restrictions

Only validated 8-bit SDR video pixel formats, Rec.709 primaries/matrix and CFR
are accepted. Missing transfer metadata requires an explicit override. PQ/HLG,
10-bit, VFR, rotated video, nonzero A/V stream starts and arbitrary timeline
offsets are rejected. Image sequences may carry floating HDR scene values as
input to the physical renderer, but HDR video output is not supported.

--audio maps the original optional audio stream and re-encodes AAC; video starts
at zero and retains CFR cadence. Aligned zero-start audio/video duration has
been tested. Original codec/packets, timecode, subtitle tracks, arbitrary source
timestamps and metadata are not preserved. Encoder defaults to CPU; --encoder
auto probes NVENC and falls back explicitly to CPU. Failure to encode leaves no
success report; inspect the accompanying FFmpeg log. User-supplied camera footage
has not yet been tested; valid synthetic moving MP4s have been processed end to end.
