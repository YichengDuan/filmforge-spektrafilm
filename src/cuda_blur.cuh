// GPL-3.0-only. Cached coefficients for the unchanged OFX Gaussian recurrence.
// Arithmetic derived from Aedan Diez / chaert-s/spektrafilm-ofx shaders.
#pragma once
#include "cuda_glsl_compat.cuh"

namespace ff_blur {
struct Kernel {
  glm::vec4 weights[257];
  glm::vec4 denominator;
  int radius;
};

__device__ inline void prepare(Kernel& kernel,glm::vec3 sigma){
  using namespace glm;
  float maxSigma=max(max(sigma.x,sigma.y),sigma.z);
  kernel.radius=maxSigma<=1e-4f?0:min(int(ceil(3.f*maxSigma)),256);
  vec3 safeSigma=max(sigma,vec3(1e-6f));
  vec3 invSigma2=1.f/max(safeSigma*safeSigma,vec3(1e-8f));
  vec3 weight=exp(-.5f*invSigma2),ratio=exp(-1.5f*invSigma2),ratioStep=exp(-invSigma2);
  vec3 sum(1.f);
  kernel.weights[0]=vec4(1.f);
  for(int offset=1;offset<=kernel.radius;++offset){
    kernel.weights[offset]=vec4(weight,1.f);
    sum+=2.f*weight;weight*=ratio;ratio*=ratioStep;
  }
  kernel.denominator=vec4(max(sum,vec3(1e-8f)),float(kernel.radius*2+1));
}

template<int Source,class Shader> __device__ inline glm::vec4 sample(
    Shader& shader,int x,int y,unsigned plane,unsigned width,unsigned height){
  if constexpr(Source==0)return shader.sampleRaw(x,y);
  if constexpr(Source==1)return shader.sampleSource(x,y);
  if constexpr(Source==2)return shader.sampleTemp(x,y);
  if constexpr(Source==3)return shader.sampleGroupedTemp(x,y,plane);
  if constexpr(Source==4)return shader.sampleDownsampleSource(x,y,width,height);
  if constexpr(Source==5)return shader.sampleDownsampleTemp(x,y,plane,width,height);
}

template<int Source,bool Vertical,class Shader> __device__ inline glm::vec4 gaussian(
    Shader& shader,glm::uvec2 gid,const Kernel& kernel,unsigned plane=0,unsigned width=0,unsigned height=0){
  using namespace glm;
  const int x=int(gid.x),y=int(gid.y);
  vec4 value=sample<Source>(shader,x,y,plane,width,height);
  // Preserve accumulation order, radius, edge clamping and final division.
  for(int offset=1;offset<=kernel.radius;++offset){
    int dx=Vertical?0:offset,dy=Vertical?offset:0;
    vec4 pair=sample<Source>(shader,x-dx,y-dy,plane,width,height)+sample<Source>(shader,x+dx,y+dy,plane,width,height);
    vec4 weight=kernel.weights[offset];
    value.x+=pair.x*weight.x;value.y+=pair.y*weight.y;value.z+=pair.z*weight.z;value.w+=pair.w;
  }
  return value/kernel.denominator;
}
} // namespace ff_blur
