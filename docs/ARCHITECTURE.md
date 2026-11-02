# Architecture audit (checked-out sources)

## Observed facts

The original repository and OFX are separate implementations. The original installed
package is 0.3.4 and requires Python ~=3.13. At this SHA `create_params` is NOT
exported: use `init_params`, `digest_params`, `Simulator`, `simulate`. The online
README/API examples can differ from this checkout.

Python call chain: GUI (`spektrafilm_gui/app.py`, controller) or LUT builder
(`spektrafilm_lut_creator/builders.py`) → runtime/process.py →
SimulationPipeline (runtime/pipeline.py) → topology:

```mermaid
flowchart LR
  RGB --> Preprocess --> FilmExpose --> FilmDevelop --> PrintExpose --> PrintDevelop --> Scan
  FilmDevelop --> NegativeScan
```

FilmExpose performs spectral upsampling, camera exposure, diffusion and halation
before development. FilmDevelop applies density curves, couplers and grain.
PrintExpose projects negative transmittance onto print media; PrintDevelop forms
print density; Scan integrates spectral light and converts to output RGB.
See runtime/stages/{filming,printing,scanning}.py; model/{develop,couplers,
density_curves,grain,diffusion}.py; utils spectral conversion helpers.
Spectral tensors/einsum, spatial convolution, stochastic grain and Numba first-run
compilation are expected expensive operations (cost attribution requires measured timings).

OFX: host image/parameter plumbing in C++ → `VulkanRenderer::render(ImageView,
MutableImageView, RenderWindow, RenderParams, double time)` → format conversion,
spectral FilmExposure, Halation/Diffusion, CurveDevelop/DIR/Grain, PrintScan,
ScannerPost GLSL compute shaders. Generated profile curves and spectral tables are
build-time Python products in the build directory. VulkanRenderer has no OFX
host dependency in its public API. The existing VulkanCopyHarness calls it directly
and also validates core, print/scan and spatial passes, with float/half cases.
The other Perf/Evaluation/Parity harness targets are inside the Apple branch.
The Vulkan harness is a synthetic test runner, not a general media renderer.

Minimal offline integration: compile the unchanged VulkanRenderer.cpp and generated
profile C++ into a separate library, expose a narrow float RGBA C ABI, and handle
FFmpeg/media/streaming in a separate Python process. Keep all upstream data,
profile indices and shader code authoritative. Do not add a new film algorithm.
Use separate build directories with an explicit SDK path, so the README's nested
OFX/SpektraFilm layout is unnecessary. Upstream worktrees remain unmodified.

## Verification boundary

Successful compilation or harness rendering is not verification inside Resolve.
CPU Python and OFX ship different profile registries and defaults; their numeric
outputs cannot be claimed identical without matched settings and reference tests.
The standalone bridge, temporal semantics and media behavior require their own tests.

## Function matrix (updated after local tests)

| Feature | Python upstream | OFX upstream | Offline CLI | ComfyUI bridge |
|---|---|---|---|---|
| Spectral film/print/scan | runtime tested | GPU bridge tested; host untested | Vulkan + CPU physical tested | subprocess tested; host untested |
| GUI | Qt/napari | OFX host | no | existing host only |
| LUT export | official 33³/65³ exports; QA has failures | host export untested | use official Python CLI separately | no LUT node |
| Halation/diffusion/grain | deterministic color + spatial API exists | Vulkan passes implemented; upstream harness count failures | upstream halation/camera diffusion/preview grain tested | Vulkan subprocess effects tested |
| General MP4 decode/encode | no media CLI | host provides | SDR H.264/H.265 + audio tested | no VideoFile/VHS node |
| Stateless segmented processing | CPU deterministic color tested | animation parameter quantizes 24 Hz | absolute grain index + EXR overlap exact | subprocess segment overlap exact |
| Runtime proof on this machine | TIFF/EXR, 829 tests pass, 5 fail; GUI offscreen | Debug/Release and float/half copy; no Resolve | 720p/1080p 250-frame streams; 4K one frame | 3 nodes defined; no existing host changed |

Optional rho>0 temporal correlation is an explicitly labeled bridge extension
that mixes upstream grain residuals in linear output. Default rho=0 uses upstream
grain directly. It is not native OFX temporal correlation or an AR(1) model.
