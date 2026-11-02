#!/usr/bin/env python3
"""Measure CUDA-LUT against the identical Vulkan color-only configuration."""
import json
from pathlib import Path
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from filmforge import Vulkan,make_engine,srgb_decode,srgb_encode
import torch

cfg=dict(film='kodak_portra_400',paper='kodak_portra_endura',grain=0,halation=0,
         diffusion=0,seed=1234,temporal_grain_correlation=0,exposure=0)
v=Vulkan()
begin=time.perf_counter(); c=make_engine('cuda-lut'); init=time.perf_counter()-begin
report={'cuda_device':torch.cuda.get_device_name(c.device),'torch':torch.__version__,
        'python':sys.version.split()[0],'config':cfg,'cuda_init_seconds':init,
        'mode':'65^3 LUT, color only; not a full CUDA spectral/spatial port',
        'test_conditions':'A2000 requested while the user runs other GPU work. Timings may include contention.',
        'source_reference':'unchanged OFX VulkanRenderer, identical profile names/parameters/IO'}
try:
    rng=np.random.default_rng(1234)
    encoded=rng.random((100,100,3),dtype=np.float32)
    encoded[:16,:64]=np.linspace(0,1,64,dtype=np.float32)[None,:,None]
    rgb=srgb_decode(encoded)
    begin=time.perf_counter(); approximate=c.render(rgb,cfg); report['first_lut_call_seconds']=time.perf_counter()-begin
    reference=v.render(rgb,cfg)
    np.savez(ROOT/'benchmarks/cuda-lut-qa-samples.npz',encoded_input=encoded,reference=reference,approximate=approximate)
    error=approximate-reference
    rmse=float(np.sqrt(np.mean(error**2)))
    report.update(linear_rmse=rmse,linear_psnr_peak1_db=float(-20*np.log10(rmse)),
                  linear_abs_max=float(np.abs(error).max()),
                  linear_abs_p99=float(np.quantile(np.abs(error),.99)),
                  lut_bake_seconds=c.bake_seconds)
    # Full lattice corners and neutral values check axis ordering and alpha.
    rgba=np.ones((4,8,4),np.float32)*.18
    rgba[...,3]=np.linspace(0,1,8)[None,:]
    alpha=c.render(rgba,cfg)
    np.testing.assert_array_equal(alpha[...,3],rgba[...,3])
    np.testing.assert_array_equal(alpha,c.render(rgba,cfg))
    try: c.render(rgba,{**cfg,'grain':.2})
    except ValueError: report['spatial_effects_rejected']=True
    else: raise AssertionError('CUDA must not silently omit requested grain')
    try: c.render(rgba*8,cfg)
    except ValueError: report['hdr_rejected']=True
    else: raise AssertionError('CUDA must not silently clamp HDR')
    report['alpha_exact']=True; report['repeat_exact']=True
    report['performance']=[]
    for w,h in [(1280,720),(1920,1080)]:
        x=np.broadcast_to(srgb_decode(np.linspace(0,1,w,dtype=np.float32))[None,:,None],(h,w,3)).copy()
        for engine in (v,c):
            for i in range(3): engine.render(x,cfg,i)
        timings={'vulkan':[],'cuda-lut':[]}
        # Interleave blocks; both include CPU input, GPU transfer, render and CPU output.
        for block in range(3):
            for name,engine in [('vulkan',v),('cuda-lut',c)]:
                for i in range(10):
                    begin=time.perf_counter(); output=engine.render(x,cfg,i)
                    timings[name].append(time.perf_counter()-begin)
                    assert np.isfinite(output).all()
        row={'width':w,'height':h}
        for name,values in timings.items():
            row[name]={'frames':len(values),'median_ms':float(np.median(values)*1000),
                       'p95_ms':float(np.quantile(values,.95)*1000),'mean_fps':len(values)/sum(values)}
        row['median_speedup']=row['vulkan']['median_ms']/row['cuda-lut']['median_ms']
        report['performance'].append(row)
        print(json.dumps(row),flush=True)
    (ROOT/'benchmarks/cuda-lut-a2000.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
finally:
    v.close();c.close()
