// GPL-3.0-only. Shared-memory scheduling of the upstream Gaussian sum.
// Arithmetic derived from Aedan Diez / chaert-s/spektrafilm-ofx shaders.
#pragma once
#include "cuda_blur.cuh"

namespace ff_blur {
template<bool Vertical,unsigned Operation,class Shader> __global__ void halation_tiled(Shader shader){
  using namespace glm;
  constexpr int BX=Vertical?16:128,BY=Vertical?16:2,Halo=32;
  __shared__ vec4 pixels[Vertical?BX*(BY+2*Halo):(BX+2*Halo)*BY];
  __shared__ vec4 weights[Halo+1];
  const Kernel& kernel=shader.blurKernels[shader.blurKernel];
  const int radius=kernel.radius;
  if(radius>Halo){
    shader.params.operation=Operation;
    shader.run(uvec3(blockIdx.x*BX+threadIdx.x,blockIdx.y*BY+threadIdx.y,0));
    return;
  }
  const int tid=int(threadIdx.y)*BX+threadIdx.x;
  if(tid<=radius)weights[tid]=kernel.weights[tid];
  const int stride=BX+(Vertical?0:2*radius),rows=BY+(Vertical?2*radius:0);
  const int originX=int(blockIdx.x)*BX-(Vertical?0:radius),originY=int(blockIdx.y)*BY-(Vertical?radius:0);
  for(int i=tid;i<stride*rows;i+=BX*BY)pixels[i]=shader.sampleRaw(originX+i%stride,originY+i/stride);
  __syncthreads();
  const unsigned x=blockIdx.x*BX+threadIdx.x,y=blockIdx.y*BY+threadIdx.y;
  if(x>=shader.params.width||y>=shader.params.height)return;
  const int center=(int(threadIdx.y)+(Vertical?radius:0))*stride+threadIdx.x+(Vertical?0:radius);
  vec4 value=pixels[center];
  for(int offset=1;offset<=radius;++offset){
    int delta=Vertical?offset*stride:offset;
    vec4 pair=pixels[center-delta]+pixels[center+delta],weight=weights[offset];
    value.x+=pair.x*weight.x;value.y+=pair.y*weight.y;value.z+=pair.z*weight.z;value.w+=pair.w;
  }
  value/=kernel.denominator;
  const unsigned index=y*shader.params.width+x;
  if constexpr(Operation==1||Operation==2)shader.storeBuf1Pixel(index,value);
  if constexpr(Operation==3){
    float weight=shader.params.sigmaMode==2?pow(.5f,float(shader.params.component))/1.75f:shader.scatterTailWeight(shader.params.component);
    shader.storeBuf1Pixel(index,vec4(vec3(shader.loadBuf1Pixel(index))+weight*vec3(value),value.w));
  }
}

template<bool Vertical,unsigned Operation,class Shader> __global__ void diffusion_tiled(Shader shader){
  using namespace glm;
  constexpr int BX=Vertical?16:128,BY=Vertical?16:2,Halo=32;
  constexpr bool Grouped=Operation==5||Operation==6;
  __shared__ vec4 pixels[Vertical?BX*(BY+2*Halo):(BX+2*Halo)*BY];
  __shared__ vec4 weights[2][Halo+1];
  const unsigned groups=Grouped?max(shader.params._pad2,1u):1u;
  unsigned first=shader.params.componentIndex;
  int radius=0;
  for(unsigned group=0;group<groups;++group)radius=max(radius,shader.blurKernels[7+first+group].radius);
  if(radius>Halo||groups>2){
    shader.params.operation=Operation;
    shader.run(uvec3(blockIdx.x*BX+threadIdx.x,blockIdx.y*BY+threadIdx.y,0));return;
  }
  const int tid=int(threadIdx.y)*BX+threadIdx.x;
  for(unsigned i=tid;i<groups*(Halo+1);i+=BX*BY){
    unsigned group=i/(Halo+1),offset=i%(Halo+1);
    const Kernel& kernel=shader.blurKernels[7+first+group];
    weights[group][offset]=offset<=kernel.radius?kernel.weights[offset]:vec4(0.f);
  }
  const int stride=BX+(Vertical?0:2*radius),rows=BY+(Vertical?2*radius:0);
  const int originX=int(blockIdx.x)*BX-(Vertical?0:radius),originY=int(blockIdx.y)*BY-(Vertical?radius:0);
  const unsigned x=blockIdx.x*BX+threadIdx.x,y=blockIdx.y*BY+threadIdx.y;
  const bool valid=x<shader.params.width&&y<shader.params.height;
  const unsigned index=y*shader.params.width+x;
  const int center=(int(threadIdx.y)+(Vertical?radius:0))*stride+threadIdx.x+(Vertical?0:radius);
  vec3 accumulated(0.f);float alpha=1.f;
  if constexpr(Vertical)if(valid){accumulated=vec3(shader.loadAccumPixel(index));alpha=shader.loadSourcePixel(index).w;}
  if constexpr(!Vertical){
    for(int i=tid;i<stride*rows;i+=BX*BY)pixels[i]=shader.sampleSource(originX+i%stride,originY+i/stride);
  }
  for(unsigned group=0;group<groups;++group){
    if constexpr(Vertical){
      for(int i=tid;i<stride*rows;i+=BX*BY)pixels[i]=shader.sampleGroupedTemp(originX+i%stride,originY+i/stride,group);
    }
    __syncthreads();
    if(valid){
      const Kernel& kernel=shader.blurKernels[7+first+group];
      vec4 value=pixels[center];
      for(int offset=1;offset<=kernel.radius;++offset){
        int delta=Vertical?offset*stride:offset;
        vec4 pair=pixels[center-delta]+pixels[center+delta],weight=weights[group][offset];
        value.x+=pair.x*weight.x;value.y+=pair.y*weight.y;value.z+=pair.z*weight.z;value.w+=pair.w;
      }
      value/=kernel.denominator;
      if constexpr(Vertical){
        vec4 component=shader.components[first+group];
        accumulated+=vec3(value)*vec3(component.y,component.z,component.w);alpha=value.w;
      }else shader.tempPixels[group*shader.params.width*shader.params.height+index]=value;
    }
    __syncthreads();
  }
  if constexpr(Vertical)if(valid)shader.storeAccumPixel(index,vec4(accumulated,alpha));
}
} // namespace ff_blur
