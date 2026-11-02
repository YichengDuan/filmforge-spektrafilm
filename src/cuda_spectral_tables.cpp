// GPL-3.0-only. Reuse Aedan Diez's exact CPU spectral preparation helpers.
// Include the public source in this translation unit; no private-field access,
// upstream edits, or Vulkan device creation is needed for these helper calls.
#include "cuda_spectral_tables.h"
#include "../upstream/spektrafilm-ofx/src/SpektraVulkanRenderer.cpp"

namespace {
struct Owner {
  SpectralTables view{};
  std::vector<float> response,printWeights,scanWeights;
};
thread_local std::string tableError;
}
extern "C" {
int ff_spectral_stock_count(int paper) {return paper?spektrafilm::kSpektraPaperCount:spektrafilm::kSpektraFilmCount;}
const char* ff_spectral_stock(int paper,int index) {
  if(index<0 || index>=ff_spectral_stock_count(paper)) return nullptr;
  auto* p=paper?spektrafilm::paperProfileCurves(index):spektrafilm::filmProfileCurves(index);
  return p?p->stock:nullptr;
}
const char* ff_spectral_tables_error(){return tableError.c_str();}
void* ff_spectral_tables_create(int film,int paper,const char* resourceDir) {
  using namespace spektrafilm;
  try {
    if(!ff_spectral_stock(0,film)||!ff_spectral_stock(1,paper)) {tableError="Invalid profile index";return nullptr;}
    auto owner=std::make_unique<Owner>(); auto& t=owner->view;
    auto* f=filmProfileCurves(film);auto* p=paperProfileCurves(paper);
    if(f->wavelengthCount!=p->wavelengthCount || f->wavelengthCount!=81u) {tableError="Experimental CUDA requires matching 81-wavelength profiles";return nullptr;}
    const auto& h=hanatosSpectraLutInfo();
    auto spectra=readFloatResourceFile(std::filesystem::path(resourceDir)/"SpektraHanatos2025Spectra.f32",h.elementCount,tableError);
    if(spectra.empty()) return nullptr;
    owner->response=makeHanatosRawResponse(*f,makeLinearSensitivity(f->logSensitivity,f->wavelengthCount),spectra,h,RgbToRawMethod::Hanatos2026);
    t.wavelengths=f->wavelengthCount;t.film_exposures=f->exposureCount;t.paper_exposures=p->exposureCount;
    t.hanatos_width=h.width;t.hanatos_height=h.height;
    t.film_log_e=f->logExposure;t.film_curves=f->densityCurves;t.film_dyes=f->channelDensity;t.film_min=f->densityCurveMinimum;
    t.paper_log_e=p->logExposure;t.paper_curves=p->densityCurves;t.paper_dyes=p->channelDensity;
    std::copy_n(f->inputToReferenceXyz+15*9,9,t.input_xyz);
    std::copy_n(f->inputToReferenceXyz+17*9,9,t.gray_xyz);
    std::copy_n(p->scanToOutputRgb+15*9,9,t.output_rgb);
    RenderParams params{};params.film=film;params.paper=paper;
    auto sensitivity=makeLinearSensitivity(p->logSensitivity,p->wavelengthCount);
    owner->printWeights.resize(t.wavelengths*3);owner->scanWeights.resize(t.wavelengths*3);
    float normalization=0;
    const float* cmfs=standardObserverCmfs();
    for(int w=0;w<t.wavelengths;++w) {
      float negativeBase=std::pow(10.f,-f->baseDensity[w]);
      float illuminant=filteredEnlargerIlluminantCpu(w,params,0,0,0);
      float printBase=std::pow(10.f,-p->baseDensity[w]);
      if(!std::isfinite(negativeBase))negativeBase=0;
      if(!std::isfinite(illuminant))illuminant=0;
      if(!std::isfinite(printBase))printBase=0;
      for(int c=0;c<3;++c) {
        owner->printWeights[w*3+c]=negativeBase*illuminant*sensitivity[w*3+c];
        owner->scanWeights[w*3+c]=printBase*p->scanIlluminant[w]*cmfs[w*3+c];
      }
      normalization+=p->scanIlluminant[w]*cmfs[w*3+1];
    }
    t.scan_normalization=1.f/std::max(normalization,1e-10f);
    t.response=owner->response.data();t.print_weights=owner->printWeights.data();t.scan_weights=owner->scanWeights.data();
    return owner.release();
  } catch(const std::exception& e) {tableError=e.what();return nullptr;}
}
const SpectralTables* ff_spectral_tables_view(void* owner){return &static_cast<Owner*>(owner)->view;}
void ff_spectral_tables_destroy(void* owner){delete static_cast<Owner*>(owner);}
int ff_spectral_spatial_params(int film,int width,int height,float grain,float halation,float diffusion,
                              unsigned seed,unsigned frame,SpatialParams* output) {
  using namespace spektrafilm;
  try {
    if(!output || width<1 || height<1 || !ff_spectral_stock(0,film)) {
      tableError="Invalid spatial parameter arguments"; return 0;
    }
    *output={}; auto& o=*output; auto& f=o.floats; auto& u=o.ints;
    RenderParams p{}; p.grainAmount=grain; p.halationAmount=halation;
    p.cameraDiffusionStrength=diffusion;
    auto* profile=filmProfileCurves(film);
    auto maximum=densityCurveMaximums(*profile);
    const float pixelSize=filmFormatLongEdgeMm(p.filmFormat)*1000.f/std::max(width,height)/resolvedEnlargerScale(p);
    for(int i=0;i<3;++i) {
      f[16+i]=maximum[i];
      f[34+i]=profile->halationStrength ? profile->halationStrength[i] : (i==0?p.halationStrengthR:i==1?p.halationStrengthG:p.halationStrengthB);
      f[37+i]=profile->halationFirstSigmaUm ? profile->halationFirstSigmaUm[i] : 65.f;
    }
    f[29]=pixelSize; f[30]=p.scatterAmount; f[31]=p.scatterScale;
    f[32]=halation; f[33]=p.halationScale;
    f[49]=grain; f[50]=p.grainSaturation; f[51]=p.grainParticleAreaUm2;
    f[52]=p.grainParticleScaleR; f[53]=p.grainParticleScaleG; f[54]=p.grainParticleScaleB;
    f[55]=p.grainParticleScaleLayer0; f[56]=p.grainParticleScaleLayer1; f[57]=p.grainParticleScaleLayer2;
    f[58]=p.grainDensityMinR; f[59]=p.grainDensityMinG; f[60]=p.grainDensityMinB;
    f[61]=p.grainUniformityR; f[62]=p.grainUniformityG; f[63]=p.grainUniformityB;
    const float formatScale=std::pow(std::max(filmFormatLongEdgeMm(p.filmFormat)/35.f,1e-6f),.62f);
    f[64]=std::max(p.grainFinalBlurUm,0.f)*formatScale/std::max(pixelSize,1e-6f);
    f[65]=p.grainBlurDyeCloudsUm; f[66]=p.grainMicroStructureScale;
    f[67]=p.grainMicroStructureSigmaNm*.001f/std::max(pixelSize,1e-6f);
    f[68]=resolvedEnlargerScale(p); f[69]=p.enlargerOffsetXPercent; f[70]=p.enlargerOffsetYPercent; f[71]=pixelSize;
    f[75]=p.halationBoostEv; f[76]=p.halationBoostRange; f[77]=p.halationProtectEv;
    u[10]=profile->type && std::string(profile->type)=="positive" ? 1u : 0u;
    u[16]=seed; u[17]=p.grainSublayersEnabled; u[18]=std::max(p.grainSubLayerCount,1); u[19]=frame;
    u[26]=1;
    if(diffusion>0) {
      VulkanDiffusionInfo info{};
      auto components=makeDiffusionComponents(
        {p.cameraDiffusionFamily,p.cameraDiffusionStrength,p.cameraDiffusionSpatialScale,
         p.cameraDiffusionHaloWarmth,p.cameraDiffusionCoreIntensity,p.cameraDiffusionCoreSize,
         p.cameraDiffusionHaloIntensity,p.cameraDiffusionHaloSize,p.cameraDiffusionBloomIntensity,
         p.cameraDiffusionBloomSize},pixelSize,info,.10f);
      o.diffusion_count=info.componentCount; o.diffusion_scatter=info.scatterFraction;
      std::memcpy(o.diffusion_components,components.data(),components.size()*sizeof(VulkanDiffusionComponent));
    }
    return 1;
  } catch(const std::exception& e) {tableError=e.what();return 0;}
}
}
