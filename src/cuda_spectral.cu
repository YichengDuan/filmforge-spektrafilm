// GPL-3.0-only. Native CUDA port of the default OFX spectral color chain.
// Hanatos reconstruction -> film curves -> 81-band print exposure -> print
// curves -> 81-band scan -> linear RGB. No final RGB 3D LUT is used.
#include "cuda_spectral_tables.h"
#include <cuda_runtime.h>
#include <vector>
#include <string>
#include <cmath>
#include <algorithm>
#include <cstdlib>
#include "cuda_effects.cuh"
#include "cuda_tiled_blur.cuh"

namespace {
thread_local std::string error;
struct Context {
  int device,film=-1,paper=-1;
  SpectralTables table{};
  std::vector<void*> allocations;
  float4 *input=nullptr,*output=nullptr;
  float3 *packedInput=nullptr,*packedOutput=nullptr;
  float4* scratch[8]{};
  float* frameFloats=nullptr;
  unsigned* frameInts=nullptr;
  glm::vec4* components=nullptr;
  ff_blur::Kernel* blurKernels=nullptr;
  bool cachedBlur=true;
  bool tiledBlur=true;
  SpatialParams spatial{};
  size_t capacity=0;
  cudaStream_t stream{};
  cudaEvent_t begin{},end{};
  cudaEvent_t stageEvents[4]{};
  bool profiling=false;
  float stageMs[5]{};
  unsigned diffusionDispatches=0;
  float kernelMs=0;
};
bool check(cudaError_t code) {
  if(code==cudaSuccess) return true;
  error=cudaGetErrorString(code);return false;
}
__device__ float3 add(float3 a,float3 b){return make_float3(a.x+b.x,a.y+b.y,a.z+b.z);}
__device__ float3 scale(float3 a,float b){return make_float3(a.x*b,a.y*b,a.z*b);}
__device__ float3 matrix(const float* m,float3 x){return make_float3(m[0]*x.x+m[1]*x.y+m[2]*x.z,m[3]*x.x+m[4]*x.y+m[5]*x.z,m[6]*x.x+m[7]*x.y+m[8]*x.z);}
__device__ float mitchell(float t){
  float x=fabsf(t),B=1.f/3.f,C=1.f/3.f;
  if(x<1) return ((12-9*B-6*C)*x*x*x+(-18+12*B+6*C)*x*x+(6-2*B))/6;
  if(x<2) return ((-B-6*C)*x*x*x+(6*B+30*C)*x*x+(-12*B-48*C)*x+(8*B+24*C))/6;
  return 0;
}
__device__ int mirror(int index,int count){int period=2*count-2;int m=index%period;if(m<0)m+=period;return m>=count?period-m:m;}
__device__ float3 hanatos(float3 xyz,const SpectralTables& t){
  float brightness=xyz.x+xyz.y+xyz.z;
  float x=fminf(fmaxf(xyz.x/fmaxf(brightness,1e-10f),0),1);
  float y=fminf(fmaxf(xyz.y/fmaxf(brightness,1e-10f),0),1);
  float xc=(1-x)*(1-x)*(t.hanatos_width-1),yc=fminf(y/fmaxf(1-x,1e-10f),1.f)*(t.hanatos_height-1);
  int xb=xc>=t.hanatos_width-1?t.hanatos_width-2:int(floorf(xc));
  int yb=yc>=t.hanatos_height-1?t.hanatos_height-2:int(floorf(yc));
  float xf=xc>=t.hanatos_width-1?1.f:xc-xb,yf=yc>=t.hanatos_height-1?1.f:yc-yb;
  float3 raw=make_float3(0,0,0);float sum=0;
  #pragma unroll
  for(int i=0;i<4;++i){
    int xi=mirror(xb-1+i,t.hanatos_width);float wx=mitchell(xf+1-i);
    #pragma unroll
    for(int j=0;j<4;++j){
      int yi=mirror(yb-1+j,t.hanatos_height);float weight=wx*mitchell(yf+1-j);
      const float* r=t.response+(xi*t.hanatos_height+yi)*3;
      raw=add(raw,scale(make_float3(r[0],r[1],r[2]),weight));sum+=weight;
    }
  }
  return scale(raw,fmaxf(brightness,0.f)/(sum!=0?sum:1));
}
__device__ float curve(float value,int channel,const float* xs,const float* ys,int count){
  if(value<=xs[0])return ys[channel];
  if(value>=xs[count-1])return ys[(count-1)*3+channel];
  int lo=0,hi=count-1;
  while(hi-lo>1){int mid=(lo+hi)>>1;if(xs[mid]<=value)lo=mid;else hi=mid;}
  float a=ys[lo*3+channel],b=ys[hi*3+channel];
  float weight=fminf(fmaxf((value-xs[lo])/fmaxf(xs[lo+1]-xs[lo],1e-9f),0.f),1.f);
  return a+(b-a)*weight;
}
__device__ float3 develop(float3 raw,const float* xs,const float* ys,int count){return make_float3(curve(log10f(fmaxf(raw.x,0.f)+1e-10f),0,xs,ys,count),curve(log10f(fmaxf(raw.y,0.f)+1e-10f),1,xs,ys,count),curve(log10f(fmaxf(raw.z,0.f)+1e-10f),2,xs,ys,count));}
__device__ float3 spectral_integral(float3 density,const float* dyes,const float* weights,int count){
  float3 sums[3]={make_float3(0,0,0),make_float3(0,0,0),make_float3(0,0,0)};
  for(int w=0;w<count;w+=3){
    #pragma unroll
    for(int k=0;k<3;++k){
      int i=(w+k)*3;float transmittance=powf(10.f,-(density.x*dyes[i]+density.y*dyes[i+1]+density.z*dyes[i+2]));
      if(!isfinite(transmittance))transmittance=0;
      sums[k]=add(sums[k],scale(make_float3(weights[i],weights[i+1],weights[i+2]),transmittance));
    }
  }
  return add(add(sums[0],sums[1]),sums[2]);
}
__global__ void frame_constants(SpectralTables t){
  float3 raw=hanatos(matrix(t.gray_xyz,make_float3(.184f,.184f,.184f)),t);
  float3 density=develop(raw,t.film_log_e,t.film_curves,t.film_exposures);
  density=add(density,make_float3(t.film_min[0],t.film_min[1],t.film_min[2]));
  float3 printRaw=spectral_integral(density,t.film_dyes,t.print_weights,t.wavelengths);
  *t.print_scale=1.f/fmaxf(expf((logf(fmaxf(printRaw.x,1e-10f))+logf(fmaxf(printRaw.y,1e-10f))+logf(fmaxf(printRaw.z,1e-10f)))/3.f),1e-10f);
}
__global__ void render_spectral(const float4* source,float4* destination,int width,int height,float exposure,SpectralTables t){
  int x=blockIdx.x*blockDim.x+threadIdx.x,y=blockIdx.y*blockDim.y+threadIdx.y;
  if(x>=width||y>=height)return;
  int i=y*width+x;float4 pixel=source[i];
  float3 raw=scale(hanatos(matrix(t.input_xyz,make_float3(pixel.x,pixel.y,pixel.z)),t),exp2f(exposure));
  float3 density=develop(raw,t.film_log_e,t.film_curves,t.film_exposures);
  density=make_float3(fmaxf(density.x,0.f),fmaxf(density.y,0.f),fmaxf(density.z,0.f));
  float3 printRaw=scale(spectral_integral(density,t.film_dyes,t.print_weights,t.wavelengths),*t.print_scale);
  float3 paperDensity=develop(printRaw,t.paper_log_e,t.paper_curves,t.paper_exposures);
  float3 xyz=scale(spectral_integral(paperDensity,t.paper_dyes,t.scan_weights,t.wavelengths),t.scan_normalization);
  float3 rgb=matrix(t.output_rgb,xyz);destination[i]=make_float4(rgb.x,rgb.y,rgb.z,pixel.w);
}
__global__ void expose_raw(const float4* source,float4* destination,int width,int height,float exposure,SpectralTables t){
  int x=blockIdx.x*blockDim.x+threadIdx.x,y=blockIdx.y*blockDim.y+threadIdx.y;
  if(x>=width||y>=height)return;
  int i=y*width+x;float4 pixel=source[i];
  float3 raw=scale(hanatos(matrix(t.input_xyz,make_float3(pixel.x,pixel.y,pixel.z)),t),exp2f(exposure));
  destination[i]=make_float4(raw.x,raw.y,raw.z,pixel.w);
}
__global__ void unpack_rgb(const float3* source,float4* destination,size_t count){
  size_t i=size_t(blockIdx.x)*blockDim.x+threadIdx.x;
  if(i<count){auto p=source[i];destination[i]=make_float4(p.x,p.y,p.z,1.f);}
}
__global__ void pack_rgb(const float4* source,float3* destination,size_t count){
  size_t i=size_t(blockIdx.x)*blockDim.x+threadIdx.x;
  if(i<count){auto p=source[i];destination[i]=make_float3(p.x,p.y,p.z);}
}
__global__ void shared_grain_seed(unsigned* ints){ints[16]^=0x9e3779b9u;ints[19]=0;}
__global__ void correlate_grain(float4* current,const float4* base,const float4* shared,size_t count,double independent,double common){
  size_t i=size_t(blockIdx.x)*blockDim.x+threadIdx.x;
  if(i>=count)return;
  float4 a=current[i],b=base[i],s=shared[i];
  // Match NumPy's FP32 residual subtraction followed by FP64 scalar mixing.
  float dx=a.x-b.x,dy=a.y-b.y,dz=a.z-b.z;
  float sx=s.x-b.x,sy=s.y-b.y,sz=s.z-b.z;
  current[i]=make_float4(float((double(b.x)+independent*double(dx))+common*double(sx)),
    float((double(b.y)+independent*double(dy))+common*double(sy)),
    float((double(b.z)+independent*double(dz))+common*double(sz)),a.w);
}
__global__ void develop_image(const float4* source,float4* destination,int width,int height,bool logInput,SpectralTables t){
  int x=blockIdx.x*blockDim.x+threadIdx.x,y=blockIdx.y*blockDim.y+threadIdx.y;
  if(x>=width||y>=height)return;
  int i=y*width+x;float4 p=source[i];float3 density;
  if(logInput) density=make_float3(curve(p.x,0,t.film_log_e,t.film_curves,t.film_exposures),
    curve(p.y,1,t.film_log_e,t.film_curves,t.film_exposures),curve(p.z,2,t.film_log_e,t.film_curves,t.film_exposures));
  else density=develop(make_float3(p.x,p.y,p.z),t.film_log_e,t.film_curves,t.film_exposures);
  destination[i]=make_float4(fmaxf(density.x,0.f),fmaxf(density.y,0.f),fmaxf(density.z,0.f),p.w);
}
__global__ void scan_image(const float4* source,float4* destination,const float4* original,int width,int height,SpectralTables t){
  int x=blockIdx.x*blockDim.x+threadIdx.x,y=blockIdx.y*blockDim.y+threadIdx.y;
  if(x>=width||y>=height)return;
  int i=y*width+x;float4 p=source[i];
  float3 printRaw=scale(spectral_integral(make_float3(p.x,p.y,p.z),t.film_dyes,t.print_weights,t.wavelengths),*t.print_scale);
  float3 paperDensity=develop(printRaw,t.paper_log_e,t.paper_curves,t.paper_exposures);
  float3 xyz=scale(spectral_integral(paperDensity,t.paper_dyes,t.scan_weights,t.wavelengths),t.scan_normalization);
  float3 rgb=matrix(t.output_rgb,xyz);destination[i]=make_float4(rgb.x,rgb.y,rgb.z,original[i].w);
}
template<class Shader,unsigned Operation> __global__ void effect(Shader shader){
  shader.params.operation=Operation;
  shader.run(glm::uvec3(blockIdx.x*blockDim.x+threadIdx.x,blockIdx.y*blockDim.y+threadIdx.y,blockIdx.z));
}
template<class Shader> void launch_effect(Shader shader,dim3 grid,dim3 threads,cudaStream_t stream){
  // Specialize operations at compile time: a preview grain dispatch must not
  // inherit register/local-memory pressure from the stochastic synthesis path.
  switch(shader.params.operation){
    case 0:effect<Shader,0><<<grid,threads,0,stream>>>(shader);break;
    case 1:effect<Shader,1><<<grid,threads,0,stream>>>(shader);break;
    case 2:effect<Shader,2><<<grid,threads,0,stream>>>(shader);break;
    case 3:effect<Shader,3><<<grid,threads,0,stream>>>(shader);break;
    case 4:effect<Shader,4><<<grid,threads,0,stream>>>(shader);break;
    case 5:effect<Shader,5><<<grid,threads,0,stream>>>(shader);break;
    case 6:effect<Shader,6><<<grid,threads,0,stream>>>(shader);break;
    case 7:effect<Shader,7><<<grid,threads,0,stream>>>(shader);break;
    case 8:effect<Shader,8><<<grid,threads,0,stream>>>(shader);break;
    case 9:effect<Shader,9><<<grid,threads,0,stream>>>(shader);break;
    case 10:effect<Shader,10><<<grid,threads,0,stream>>>(shader);break;
    case 11:effect<Shader,11><<<grid,threads,0,stream>>>(shader);break;
    case 12:effect<Shader,12><<<grid,threads,0,stream>>>(shader);break;
    case 13:effect<Shader,13><<<grid,threads,0,stream>>>(shader);break;
    default:break;
  }
}
template<class Shader> void setup_shader(Shader& s,int width,int height){
  s.params.width=width;s.params.height=height;s.params.fullWidth=width;s.params.fullHeight=height;
  s.params.activeWidth=width;s.params.activeHeight=height;
}
__global__ void prepare_blur(ff_blur::Kernel* kernels,const float* floats,const glm::vec4* components,unsigned count){
  unsigned index=threadIdx.x+blockIdx.x*blockDim.x;
  if(index<7){
    ff_effects::Halation h{};h.frameFloats=floats;
    h.params.sigmaMode=index==0?0:index<4?1:2;
    h.params.component=index==0?0:index<4?index-1:index-4;
    ff_blur::prepare(kernels[index],h.sigmaForMode());
  }else if(index<7+count){
    float sigma=components[index-7].x;
    float scale=sigma>=48?8.f:sigma>=24?4.f:sigma>=12?2.f:1.f;
    ff_blur::prepare(kernels[index],glm::vec3(fmaxf(sigma/scale,1e-6f)));
  }
}
// The ordering and bindings follow VulkanRenderer::renderCore, full-frame mode.
// All GPU work below uses CUDA kernels; Vulkan is never initialized here.
void render_effects(Context& c,int width,int height,float exposure,float grain,float halation,float diffusion,double rho){
  using glm::vec4;
  dim3 blocks((width+31)/32,(height+7)/8),threads(32,8);
  if(c.cachedBlur)prepare_blur<<<2,32,0,c.stream>>>(c.blurKernels,c.frameFloats,c.components,c.spatial.diffusion_count);
  expose_raw<<<blocks,threads,0,c.stream>>>(c.input,c.scratch[0],width,height,exposure,c.table);
  if(c.profiling)cudaEventRecord(c.stageEvents[0],c.stream);
  c.diffusionDispatches=0;
  float4* raw=c.scratch[0];
  if(diffusion>0 && c.spatial.diffusion_count>0){
    auto sequence=[&](auto d){
    setup_shader(d,width,height);d.blurKernels=c.blurKernels;
    d.sourcePixels=reinterpret_cast<vec4*>(raw);
    d.tempPixels=reinterpret_cast<vec4*>(c.scratch[1]);
    d.accumPixels=reinterpret_cast<vec4*>(c.scratch[2]);
    d.destinationPixels=reinterpret_cast<vec4*>(c.scratch[3]);
    d.downsampleSourcePixels=reinterpret_cast<vec4*>(c.scratch[4]);
    d.downsampleTempPixels=reinterpret_cast<vec4*>(c.scratch[5]);
    d.downsampleBlurPixels=reinterpret_cast<vec4*>(c.scratch[6]);
    d.components=c.components;d.diffusionInfo.componentCount=c.spatial.diffusion_count;
    d.diffusionInfo.scatterFraction=c.spatial.diffusion_scatter;
    auto dispatch=[&](unsigned op,unsigned component,unsigned packed,dim3 grid){
      d.params.operation=op;d.params.componentIndex=component;d.params._pad2=packed;
      if(c.tiledBlur&&(op==1||op==2||op==5||op==6)){
        dim3 horizontal((width+127)/128,(height+1)/2),vertical((width+15)/16,(height+15)/16);
        if(op==1)ff_blur::diffusion_tiled<false,1><<<horizontal,dim3(128,2),0,c.stream>>>(d);
        if(op==2)ff_blur::diffusion_tiled<true,2><<<vertical,dim3(16,16),0,c.stream>>>(d);
        if(op==5)ff_blur::diffusion_tiled<false,5><<<horizontal,dim3(128,2),0,c.stream>>>(d);
        if(op==6)ff_blur::diffusion_tiled<true,6><<<vertical,dim3(16,16),0,c.stream>>>(d);
        ++c.diffusionDispatches;return;
      }
      launch_effect(d,grid,threads,c.stream);
      ++c.diffusionDispatches;
    };
    dispatch(d.kOpClear,0,0,blocks);
    // Match the upstream default two-component groups and automatic downsample
    // thresholds. Keep the accumulation order identical to the shader path.
    auto downsample=[&](unsigned i){
      float sigma=c.spatial.diffusion_components[i*4];
      return sigma>=48?8u:sigma>=24?4u:sigma>=12?2u:1u;
    };
    for(unsigned i=0;i<c.spatial.diffusion_count;){
      unsigned scale=downsample(i),group=1;
      if(i+1<c.spatial.diffusion_count && downsample(i+1)==scale)group=2;
      if(scale==1){
        dispatch(group==1?d.kOpBlurX:d.kOpGroupBlurX,i,group,blocks);
        dispatch(group==1?d.kOpBlurYAccumulate:d.kOpGroupBlurYAccumulate,i,group,blocks);
      }
      else {
        dim3 reduced(((width+scale-1)/scale+31)/32,((height+scale-1)/scale+7)/8);
        unsigned packed=(scale<<16)|group;
        dispatch(d.kOpDownsample,scale,0,reduced);
        dispatch(group==1?d.kOpDownsampleBlurX:d.kOpDownsampleGroupBlurX,i,packed,reduced);
        dispatch(group==1?d.kOpDownsampleBlurY:d.kOpDownsampleGroupBlurY,i,packed,reduced);
        dispatch(group==1?d.kOpDownsampleUpsampleAccumulate:d.kOpDownsampleGroupUpsampleAccumulate,i,packed,blocks);
      }
      i+=group;
    }
    dispatch(d.kOpResolve,0,0,blocks);raw=c.scratch[3];
    };
    if(c.cachedBlur)sequence(ff_effects::DiffusionCached{});else sequence(ff_effects::Diffusion{});
  }
  if(c.profiling)cudaEventRecord(c.stageEvents[1],c.stream);
  bool logInput=false;
  if(halation>0){
    auto sequence=[&](auto h){
    setup_shader(h,width,height);h.frameFloats=c.frameFloats;h.blurKernels=c.blurKernels;
    // scratch[3] may hold diffusion output; keep it live throughout halation.
    auto dispatch=[&](unsigned op,unsigned sigma,unsigned component,float4* in,float4* one,float4* two,float4* out){
      h.params.operation=op;h.params.sigmaMode=sigma;h.params.component=component;
      h.blurKernel=sigma==0?0:sigma==1?1+component:4+component;
      h.in0=reinterpret_cast<vec4*>(in);h.buf1=reinterpret_cast<vec4*>(one);
      h.in2=reinterpret_cast<vec4*>(two);h.buf3=reinterpret_cast<vec4*>(out);
      if(c.tiledBlur){
        dim3 horizontal((width+127)/128,(height+1)/2),vertical((width+15)/16,(height+15)/16);
        if(op==1){ff_blur::halation_tiled<false,1><<<horizontal,dim3(128,2),0,c.stream>>>(h);return;}
        if(op==2){ff_blur::halation_tiled<true,2><<<vertical,dim3(16,16),0,c.stream>>>(h);return;}
        if(op==3){ff_blur::halation_tiled<true,3><<<vertical,dim3(16,16),0,c.stream>>>(h);return;}
      }
      launch_effect(h,blocks,threads,c.stream);
    };
    auto a=c.scratch[1],b=c.scratch[2],tail=c.scratch[4],scattered=c.scratch[5],log=c.scratch[6];
    dispatch(h.kOpBlurX,h.kSigmaScatterCore,0,raw,a,a,a);
    dispatch(h.kOpBlurYStore,h.kSigmaScatterCore,0,a,b,a,b);
    dispatch(h.kOpClear,0,0,raw,tail,a,tail);
    for(unsigned i=0;i<3;++i){
      dispatch(h.kOpBlurX,h.kSigmaScatterTail,i,raw,a,a,a);
      dispatch(h.kOpBlurYAccumulate,h.kSigmaScatterTail,i,a,tail,a,tail);
    }
    dispatch(h.kOpScatterResolve,0,0,raw,b,tail,scattered);
    dispatch(h.kOpClear,0,0,scattered,tail,a,tail);
    for(unsigned i=0;i<3;++i){
      dispatch(h.kOpBlurX,h.kSigmaBounce,i,scattered,a,a,a);
      dispatch(h.kOpBlurYAccumulate,h.kSigmaBounce,i,a,tail,a,tail);
    }
    dispatch(h.kOpBounceResolveLog,0,0,scattered,tail,a,log);
    raw=log;logInput=true;
    };
    if(c.cachedBlur)sequence(ff_effects::HalationCached{});else sequence(ff_effects::Halation{});
  }
  if(c.profiling)cudaEventRecord(c.stageEvents[2],c.stream);
  develop_image<<<blocks,threads,0,c.stream>>>(raw,c.scratch[7],width,height,logInput,c.table);
  float4* density=c.scratch[7];
  if(grain>0){
    ff_effects::Grain g{};setup_shader(g,width,height);
    g.params.exposureCount=c.table.film_exposures;g.params.operation=g.kOpPreview;
    g.frameFloats=c.frameFloats;g.frameInts=c.frameInts;
    g.sourcePixels=reinterpret_cast<vec4*>(density);g.destinationPixels=reinterpret_cast<vec4*>(c.scratch[0]);
    effect<ff_effects::Grain,0><<<blocks,threads,0,c.stream>>>(g);density=c.scratch[0];
  }
  if(c.profiling)cudaEventRecord(c.stageEvents[3],c.stream);
  scan_image<<<blocks,threads,0,c.stream>>>(density,c.output,c.input,width,height,c.table);
  if(grain>0&&rho>0){
    // Exposure/spatial processing and development are shared by all three
    // temporal residual renders. Preserve the previous public mixing equation.
    scan_image<<<blocks,threads,0,c.stream>>>(c.scratch[7],c.scratch[2],c.input,width,height,c.table);
    shared_grain_seed<<<1,1,0,c.stream>>>(c.frameInts);
    ff_effects::Grain g{};setup_shader(g,width,height);
    g.params.exposureCount=c.table.film_exposures;g.params.operation=g.kOpPreview;
    g.frameFloats=c.frameFloats;g.frameInts=c.frameInts;
    g.sourcePixels=reinterpret_cast<vec4*>(c.scratch[7]);g.destinationPixels=reinterpret_cast<vec4*>(c.scratch[0]);
    effect<ff_effects::Grain,0><<<blocks,threads,0,c.stream>>>(g);
    scan_image<<<blocks,threads,0,c.stream>>>(c.scratch[0],c.scratch[3],c.input,width,height,c.table);
    size_t count=size_t(width)*height;
    correlate_grain<<<(count+255)/256,256,0,c.stream>>>(c.output,c.scratch[2],c.scratch[3],count,std::sqrt(1.0-rho),std::sqrt(rho));
  }
}
bool upload(Context& c,const float*& target,const float* source,size_t count){
  void* data=nullptr;if(!check(cudaMalloc(&data,count*sizeof(float))))return false;
  c.allocations.push_back(data);target=static_cast<float*>(data);
  return check(cudaMemcpyAsync(data,source,count*sizeof(float),cudaMemcpyHostToDevice,c.stream));
}
void clear_tables(Context& c){for(void* p:c.allocations)cudaFree(p);c.allocations.clear();c.film=c.paper=-1;}
}
extern "C" {
const char* ff_cuda_error(){return error.c_str();}
void* ff_cuda_create(int device){
  auto* c=new Context;c->device=device;
  const char* blur=std::getenv("FILMFORGE_CUDA_BLUR");
  c->cachedBlur=!blur||std::string(blur)!="reference";
  c->tiledBlur=!blur||std::string(blur)=="tiled";
  if(!check(cudaSetDevice(device))||!check(cudaStreamCreateWithFlags(&c->stream,cudaStreamNonBlocking))||!check(cudaEventCreate(&c->begin))||!check(cudaEventCreate(&c->end))){delete c;return nullptr;}
  return c;
}
void ff_cuda_destroy(void* handle){
  if(!handle)return;auto& c=*static_cast<Context*>(handle);cudaSetDevice(c.device);cudaStreamSynchronize(c.stream);
  clear_tables(c);cudaFree(c.input);cudaFree(c.output);
  cudaFree(c.packedInput);cudaFree(c.packedOutput);
  for(auto p:c.scratch)cudaFree(p);
  cudaFree(c.frameFloats);cudaFree(c.frameInts);cudaFree(c.components);
  cudaFree(c.blurKernels);
  for(auto event:c.stageEvents)if(event)cudaEventDestroy(event);
  cudaEventDestroy(c.begin);cudaEventDestroy(c.end);cudaStreamDestroy(c.stream);delete &c;
}
int ff_cuda_prepare(void* handle,int film,int paper,const char* resources){
  auto& c=*static_cast<Context*>(handle);if(!check(cudaSetDevice(c.device)))return 0;
  if(c.film==film&&c.paper==paper)return 1;
  void* owner=ff_spectral_tables_create(film,paper,resources);if(!owner){error=ff_spectral_tables_error();return 0;}
  clear_tables(c);c.table=*ff_spectral_tables_view(owner);auto& t=c.table;int w=t.wavelengths;
  bool ok=upload(c,t.film_log_e,t.film_log_e,t.film_exposures)&&upload(c,t.film_curves,t.film_curves,t.film_exposures*3)&&
    upload(c,t.film_dyes,t.film_dyes,w*3)&&upload(c,t.film_min,t.film_min,3)&&upload(c,t.paper_log_e,t.paper_log_e,t.paper_exposures)&&
    upload(c,t.paper_curves,t.paper_curves,t.paper_exposures*3)&&upload(c,t.paper_dyes,t.paper_dyes,w*3)&&
    upload(c,t.response,t.response,t.hanatos_width*t.hanatos_height*3)&&upload(c,t.print_weights,t.print_weights,w*3)&&upload(c,t.scan_weights,t.scan_weights,w*3);
  float* scale=nullptr;
  if(ok&&check(cudaMalloc(&scale,sizeof(float)))){c.allocations.push_back(scale);t.print_scale=scale;frame_constants<<<1,1,0,c.stream>>>(t);ok=check(cudaGetLastError())&&check(cudaStreamSynchronize(c.stream));}else ok=false;
  // Host source buffers must outlive asynchronous H2D copies, even on failure.
  cudaStreamSynchronize(c.stream);ff_spectral_tables_destroy(owner);
  if(ok){c.film=film;c.paper=paper;}return ok;
}
int ff_cuda_render_temporal(void* handle,const void* source,void* output,int width,int height,float exposure,
                           float grain,float halation,float diffusion,unsigned seed,unsigned frame,int channels,double rho){
  if(!handle||!source||!output){error="Null CUDA render argument";return 0;}
  auto& c=*static_cast<Context*>(handle);if(!check(cudaSetDevice(c.device)))return 0;
  size_t count=size_t(width)*height;
  if(width<1||height<1||width>16384||height>16384||c.film<0||(channels!=3&&channels!=4)||!std::isfinite(exposure)||
     !std::isfinite(grain)||!std::isfinite(halation)||!std::isfinite(diffusion)||grain<0||halation<0||diffusion<0||
     !std::isfinite(rho)||rho<0||rho>1){
    error="Invalid spectral render arguments";return 0;
  }
  if(count>c.capacity){cudaStreamSynchronize(c.stream);cudaFree(c.input);cudaFree(c.output);c.input=c.output=nullptr;c.capacity=0;
    cudaFree(c.packedInput);cudaFree(c.packedOutput);c.packedInput=c.packedOutput=nullptr;
    for(auto& p:c.scratch){cudaFree(p);p=nullptr;}
    if(!check(cudaMalloc(&c.input,count*sizeof(float4)))||!check(cudaMalloc(&c.output,count*sizeof(float4))))return 0;c.capacity=count;}
  if(channels==3){
    if(!c.packedInput&&!check(cudaMalloc(&c.packedInput,c.capacity*sizeof(float3))))return 0;
    if(!c.packedOutput&&!check(cudaMalloc(&c.packedOutput,c.capacity*sizeof(float3))))return 0;
  }
  bool effects=grain>0||halation>0||diffusion>0;
  if(effects){
    for(unsigned i=0;i<8;++i){
      unsigned planes=(i==1||i==5||i==6)?2:1;
      if(!c.scratch[i]&&!check(cudaMalloc(&c.scratch[i],c.capacity*sizeof(float4)*planes)))return 0;
    }
    if(!c.frameFloats&&!check(cudaMalloc(&c.frameFloats,sizeof(c.spatial.floats))))return 0;
    if(!c.frameInts&&!check(cudaMalloc(&c.frameInts,sizeof(c.spatial.ints))))return 0;
    if(!c.components&&!check(cudaMalloc(&c.components,sizeof(c.spatial.diffusion_components))))return 0;
    if(c.cachedBlur&&!c.blurKernels&&!check(cudaMalloc(&c.blurKernels,39*sizeof(ff_blur::Kernel))))return 0;
    if(!ff_spectral_spatial_params(c.film,width,height,grain,halation,diffusion,seed,frame,&c.spatial)){
      error=ff_spectral_tables_error();return 0;
    }
    if(!check(cudaMemcpyAsync(c.frameFloats,c.spatial.floats,sizeof(c.spatial.floats),cudaMemcpyHostToDevice,c.stream))||
       !check(cudaMemcpyAsync(c.frameInts,c.spatial.ints,sizeof(c.spatial.ints),cudaMemcpyHostToDevice,c.stream))||
       !check(cudaMemcpyAsync(c.components,c.spatial.diffusion_components,sizeof(c.spatial.diffusion_components),cudaMemcpyHostToDevice,c.stream)))return 0;
  }
  c.diffusionDispatches=0;
  if(!check(cudaMemcpyAsync(channels==3?static_cast<void*>(c.packedInput):c.input,source,
            count*channels*sizeof(float),cudaMemcpyHostToDevice,c.stream)))return 0;
  cudaEventRecord(c.begin,c.stream);
  if(channels==3)unpack_rgb<<<(count+255)/256,256,0,c.stream>>>(c.packedInput,c.input,count);
  if(effects)render_effects(c,width,height,exposure,grain,halation,diffusion,rho);
  else render_spectral<<<dim3((width+31)/32,(height+7)/8),dim3(32,8),0,c.stream>>>(c.input,c.output,width,height,exposure,c.table);
  if(channels==3)pack_rgb<<<(count+255)/256,256,0,c.stream>>>(c.output,c.packedOutput,count);
  cudaEventRecord(c.end,c.stream);
  if(!check(cudaGetLastError())||!check(cudaMemcpyAsync(output,channels==3?static_cast<void*>(c.packedOutput):c.output,
      count*channels*sizeof(float),cudaMemcpyDeviceToHost,c.stream))||!check(cudaStreamSynchronize(c.stream)))return 0;
  cudaEventElapsedTime(&c.kernelMs,c.begin,c.end);
  if(c.profiling){
    std::fill_n(c.stageMs,5,0.f);
    if(effects){
      cudaEvent_t previous=c.begin;
      for(unsigned i=0;i<4;++i){cudaEventElapsedTime(&c.stageMs[i],previous,c.stageEvents[i]);previous=c.stageEvents[i];}
      cudaEventElapsedTime(&c.stageMs[4],previous,c.end);
    }else c.stageMs[4]=c.kernelMs;
  }
  return 1;
}
int ff_cuda_render_channels(void* handle,const void* source,void* output,int width,int height,float exposure,
                           float grain,float halation,float diffusion,unsigned seed,unsigned frame,int channels){
  return ff_cuda_render_temporal(handle,source,output,width,height,exposure,grain,halation,diffusion,seed,frame,channels,0);
}
int ff_cuda_render_effects(void* handle,const float4* source,float4* output,int width,int height,float exposure,
                          float grain,float halation,float diffusion,unsigned seed,unsigned frame){
  return ff_cuda_render_channels(handle,source,output,width,height,exposure,grain,halation,diffusion,seed,frame,4);
}
// Keep the initial color-only ABI for existing clients.
int ff_cuda_render(void* handle,const float4* source,float4* output,int width,int height,float exposure){
  return ff_cuda_render_effects(handle,source,output,width,height,exposure,0,0,0,0,0);
}
double ff_cuda_kernel_ms(void* handle){return static_cast<Context*>(handle)->kernelMs;}
int ff_cuda_enable_profiling(void* handle){
  if(!handle){error="Null CUDA context";return 0;}
  auto& c=*static_cast<Context*>(handle);if(!check(cudaSetDevice(c.device)))return 0;
  for(auto& event:c.stageEvents)if(!event&&!check(cudaEventCreate(&event)))return 0;
  c.profiling=true;return 1;
}
double ff_cuda_stage_ms(void* handle,int stage){
  return stage>=0&&stage<5?static_cast<Context*>(handle)->stageMs[stage]:0;
}
unsigned ff_cuda_diffusion_dispatches(void* handle){return static_cast<Context*>(handle)->diffusionDispatches;}
}
