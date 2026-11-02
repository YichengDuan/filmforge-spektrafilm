#!/usr/bin/env python3
"""A2000 parity/timing for the native CUDA spectral color chain, not a LUT."""
import json
import os
from pathlib import Path
import sys
import time
import numpy as np

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
from filmforge import Vulkan,make_engine,srgb_decode

cfg=dict(film='kodak_vision3_500t',paper='kodak_2383',grain=0,halation=0,diffusion=0,
         seed=1234,temporal_grain_correlation=0,exposure=0)
v=Vulkan();c=make_engine('cuda-spectral')
report={'gpu':'NVIDIA RTX A2000 Laptop GPU','config':cfg,'native_cuda':True,
        'final_rgb_3d_lut':False,'wavelengths':81,'spatial_effects_ported':True,
        'conditions':'Other user GPU work remained running; timings are provisional under contention.',
        'samples':[]}
try:
    x=np.zeros((32,64,4),np.float32);x[...,:3]=.18;x[...,3]=np.linspace(0,1,64)
    a=c.render(x,cfg);b=c.render(x,cfg)
    np.testing.assert_array_equal(a,b);np.testing.assert_array_equal(a[...,3],x[...,3])
    report['repeat_and_alpha_exact']=True
    for key in ('grain','halation','diffusion'):
        assert np.isfinite(c.render(x,{**cfg,key:.1})).all()
    report['spatial_effects_finite']=True
    for w,h in [(1280,720),(1920,1080)]:
        frame=np.broadcast_to(srgb_decode(np.linspace(0,1,w,dtype=np.float32))[None,:,None],(h,w,3)).copy()
        results={}
        for mode in ('vulkan-tiled','vulkan-full-frame','cuda-spectral'):
            engine=c if mode=='cuda-spectral' else v
            os.environ['SPEKTRAFILM_VULKAN_TILE_MODE']='legacy' if mode=='vulkan-full-frame' else 'tiled'
            for i in range(3): engine.render(frame,cfg,i)
            times=[];gpu=[]
            for i in range(20):
                begin=time.perf_counter();out=engine.render(frame,cfg,i);times.append(time.perf_counter()-begin)
                assert np.isfinite(out).all()
                if mode=='cuda-spectral': gpu.append(c.kernel_ms())
            results[mode]={'frames':20,'median_ms':float(np.median(times)*1000),'p95_ms':float(np.quantile(times,.95)*1000),'mean_fps':20/sum(times)}
            if gpu: results[mode]['median_cuda_kernel_ms']=float(np.median(gpu))
        row={'width':w,'height':h,'results':results}
        report['samples'].append(row)
        print(json.dumps(row),flush=True)
    (root/'benchmarks/cuda-spectral-a2000.json').write_text(json.dumps(report,indent=2))
finally:v.close();c.close()
