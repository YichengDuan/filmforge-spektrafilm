#!/usr/bin/env python3
"""Opt-in CUDA event timings for the five native pipeline stages."""
import argparse
import json
from pathlib import Path
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from filmforge import Vulkan,make_engine


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'benchmarks/cuda-native-profile-new.json')
    parser.add_argument('--frames',type=int,default=12)
    args=parser.parse_args()
    if args.frames<1:parser.error('--frames must be positive')
    if args.output.exists():parser.error('Output exists; select a new report path')
    cfg=dict(film='kodak_portra_400',paper='kodak_portra_endura',exposure=0,
             grain=.35,halation=.3,diffusion=.1,seed=1234,temporal_grain_correlation=0)
    cuda=make_engine('cuda-spectral');vulkan=Vulkan();cuda.enable_profiling();rows=[]
    try:
        for width,height in ((1280,720),(1920,1080)):
            image=np.random.default_rng(16).uniform(0,2,(height,width,3)).astype('f4')
            results={}
            for name,engine in (('vulkan',vulkan),('cuda-spectral',cuda)):
                for i in range(2):engine.render(image,cfg,i)
                timings=[];kernels=[];stages=[]
                for i in range(args.frames):
                    begin=time.perf_counter();engine.render(image,cfg,i);timings.append((time.perf_counter()-begin)*1000)
                    if name=='cuda-spectral':kernels.append(cuda.kernel_ms());stages.append(cuda.stage_ms())
                row={'median_ms':float(np.median(timings)),'p95_ms':float(np.quantile(timings,.95))}
                if stages:
                    row['kernel_ms']=float(np.median(kernels))
                    row['stage_ms']={key:float(np.median([s[key] for s in stages])) for key in stages[0]}
                    row['diffusion_dispatches']=cuda.lib.ff_cuda_diffusion_dispatches(cuda.ptr)
                results[name]=row
            rows.append({'width':width,'height':height,'config':cfg,'results':results})
            args.output.write_text(json.dumps(rows,indent=2));print(json.dumps(rows[-1]),flush=True)
    finally:cuda.close();vulkan.close()


if __name__=='__main__':main()
