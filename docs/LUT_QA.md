# Official Python LUT export and QA

Executed in the isolated Python 3.13.7 environment, at spektrafilm SHA
3bb2c2d2801ff68b92019cf1dbcbb133d60832bc, package 0.3.4:

```bash
spektrafilm-lut list film
spektrafilm-lut list print
spektrafilm-lut build --film kodak_portra_400 --print kodak_portra_endura \
  --input srgb --output srgb --resolution 33 --qa --out examples/luts
spektrafilm-lut build --film kodak_portra_400 --print kodak_portra_endura \
  --input srgb --output srgb --resolution 65 --qa --out examples/luts65
```

Both commands exited 0 and produced .cube, bundle.json, README, full unchanged
CC BY-SA notice and full HTML/Markdown QA reports. The CLI exits 0 even with QA
failures, so success must be read from the report, not only the process exit code.
Input/output for this comparison is encoded sRGB; reference samples use the
builder's deterministic physical configuration and transfer/gamut processing.
The QA off-grid identity test uses CIEDE2000 and reports DeltaITP separately;
it is interpolation error against the live reference, not image-grain parity.

| Measured metric | 33³ | 65³ |
|---|---:|---:|
| Trilinear CIEDE2000 maximum | 0.9254 | 0.2700 |
| Trilinear CIEDE2000 p99 | 0.2491 | 0.08303 |
| Trilinear CIEDE2000 median | 0.02779 | 0.008408 |
| Tetrahedral CIEDE2000 maximum | 0.7166 | 0.2560 |
| Tetrahedral CIEDE2000 p99 | 0.2104 | 0.07230 |
| Monotonicity violations | 7 | 157 |
| Worst negative monotonic step | -0.0000591 | -0.000384 |
| Gamut fold fraction | 0.1610 | 0.1597 |

Both reports: **2 pass, 2 fail, 12 info**. Failures are monotonicity and output
gamut compression. Their flags remain unresolved; increasing cube resolution
alone is not a fix. Full reports:

* 33³ local report: `examples/luts/spektrafilm_v034_portra400_portraendura_1lut_srgb_srgb/qa/portra400_portraendura/report.md`
* 65³ local report: `examples/luts65/spektrafilm_v034_portra400_portraendura_1lut_srgb_srgb/qa/portra400_portraendura/report.md`

These reports and their profile-derived assets are generated locally by the
commands above; they are intentionally excluded from the published repository.

3D LUTs cannot express grain, halation, diffusion, spatial DIR or image-aware
auto exposure. The official builder uses lut_mode to disable spatial,
stochastic and image-global operators. These LUTs are a color-transform-only
alternative, not equivalent to full video rendering. This project's video
Vulkan backend does not substitute these LUTs for the actual OFX renderer.

License: generated assets retain Andrea Volpato credit, canonical source URL
and original profile/LUT notice. Original root and packaged data/license copies
are byte-identical (SHA256 76d629501783ae52e8d63aee1e054c1e1a9713b9fe7d36fb306e25b1d14b24e9).
OFX exported LUT restrictions are separate; these are not OFX-exported LUTs.
