// GPL-3.0-or-later. Thin ABI over Aedan Diez's unchanged GPL Vulkan renderer.
#include "SpektraVulkanRenderer.h"
#include "SpektraProfileCurves.h"
#include <string>
#include <exception>
#include <memory>
#include <cmath>
#include <limits>

namespace {
thread_local std::string error;
struct Context { spektrafilm::VulkanRenderer renderer; };
}
extern "C" {
const char* ff_error() { return error.c_str(); }
void* ff_create() {
  try { return new Context; }
  catch (const std::exception& e) { error=e.what(); return nullptr; }
}
void ff_destroy(void* ptr) { delete static_cast<Context*>(ptr); }
int ff_count(int paper) { return paper ? spektrafilm::kSpektraPaperCount : spektrafilm::kSpektraFilmCount; }
const char* ff_stock(int paper, int index) {
  if(index<0 || index>=ff_count(paper)) return nullptr;
  auto* p = paper ? spektrafilm::paperProfileCurves(index) : spektrafilm::filmProfileCurves(index);
  return p ? p->stock : nullptr;
}
int ff_render(void* ptr, const float* input, float* output, int w, int h,
              int film, int paper, int input_space, int output_space,
              float exposure, float grain, float halation, float diffusion,
              unsigned seed, unsigned frame) {
  try {
    if(!ptr || !input || !output || w<1 || h<1 || w>16384 || h>16384 ||
       !ff_stock(0, film) || !ff_stock(1, paper)) { error="Invalid render arguments"; return 0; }
    spektrafilm::RenderParams params{};
    params.film=film; params.paper=paper;
    params.inputColorSpace=static_cast<spektrafilm::ColorSpace>(input_space);
    params.outputColorSpace=static_cast<spektrafilm::ColorSpace>(output_space);
    params.filmExposureEv=exposure;
    params.grainEnabled=grain>0; params.grainAmount=grain;
    params.grainSeed=seed; params.grainAnimate=true;
    params.halationEnabled=halation>0; params.halationAmount=halation;
    params.cameraDiffusionEnabled=diffusion>0; params.cameraDiffusionStrength=diffusion;
    params.gpuRenderTiling=spektrafilm::GpuRenderTilingMode::Tiled;
    spektrafilm::ImageView src{input,0,0,w,h,w*16,4,4};
    spektrafilm::MutableImageView dst{output,0,0,w,h,w*16,4,4};
    auto& renderer=static_cast<Context*>(ptr)->renderer;
    // Upstream grain animation quantizes time at 24 Hz. Supplying index/24
    // produces the requested absolute frame index regardless of media fps.
    if(!renderer.render(src,dst,{0,0,w,h},params,double(frame)/24.0)) {
      error=renderer.lastError(); return 0;
    }
    for(size_t i=0;i<size_t(w)*h*4;i++) if(!std::isfinite(output[i])) {
      error="Non-finite Vulkan output"; return 0;
    }
    return 1;
  } catch(const std::exception& e) { error=e.what(); return 0; }
}
}
