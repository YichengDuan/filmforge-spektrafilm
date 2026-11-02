#!/usr/bin/env python3
"""Compare current CUDA/Vulkan adapters with rotating order and identical frames."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from filmforge import Vulkan
from cuda_spectral import CudaSpectral


def snapshot():
    return subprocess.check_output(['nvidia-smi','--query-gpu=index,name,memory.used,utilization.gpu,clocks.sm,clocks.mem,pstate,pcie.link.gen.current,pcie.link.width.current','--format=csv'],text=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline-dir',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--frames',type=int,default=12)
    p.add_argument('--rounds',type=int,default=3)
    p.add_argument('--warmup',type=int,default=5)
    p.add_argument('--include-4k',action='store_true',help='Adds timed 4K frames, not a long-video test')
    args=p.parse_args()
    if args.output.exists():p.error('Preserve the existing report: select a new path')
    if min(args.frames,args.rounds,args.warmup)<1:p.error('Sampling counts must be positive')
    report={'gpu_start':snapshot(),'python':sys.version.split()[0],
            'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES'),
            'vulkan_device_index':os.environ.get('SPEKTRAFILM_VULKAN_DEVICE_INDEX'),
            'vulkan_tile_mode':os.environ.get('SPEKTRAFILM_VULKAN_TILE_MODE'),
            'cuda_blur':os.environ.get('FILMFORGE_CUDA_BLUR','tiled'),
            'warmup':args.warmup,'rounds':args.rounds,'frames_per_round':args.frames,
            'timer_scope':'Python adapter, validation, host/device transfers and rendering; excludes media decoding/encoding and first profile preparation',
            'order':'Rotate engine order each round; same absolute frame indices and static linear Rec.709 input',
            'upstream':json.loads((ROOT/'upstream/lock.json').read_text()),
            'optimized_library_sha256':hashlib.sha256((ROOT/'build/cuda-spectral/libfilmforge_cuda_spectral.so').read_bytes()).hexdigest(),
            'rows':[]}
    engines={'vulkan':Vulkan()}
    if args.baseline_dir:
        spec=importlib.util.spec_from_file_location('saved_cuda_baseline',args.baseline_dir/'src/cuda_spectral.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        engines['cuda-before']=module.CudaSpectral()
        report['baseline_library_sha256']=hashlib.sha256((args.baseline_dir/'build/cuda-spectral/libfilmforge_cuda_spectral.so').read_bytes()).hexdigest()
    engines['cuda-optimized']=CudaSpectral();engines['cuda-optimized'].enable_profiling()
    pairs=[('kodak_portra_400','kodak_portra_endura'),('kodak_vision3_500t','kodak_2383')]
    sizes=[(1280,720),(1920,1080)]+([(3840,2160)] if args.include_4k else [])
    try:
        for width,height in sizes:
            image=np.random.default_rng(19).uniform(0,2,(height,width,3)).astype('f4')
            for film,paper in pairs:
                for mode in ('color','full','temporal'):
                    cfg=dict(film=film,paper=paper,exposure=0,grain=0,halation=0,diffusion=0,seed=1234,temporal_grain_correlation=0)
                    if mode!='color':cfg.update(grain=.35,halation=.3,diffusion=.1)
                    if mode=='temporal':cfg['temporal_grain_correlation']=.7
                    samples={name:[] for name in engines};gpu=[];stages=[];outputs={}
                    for engine in engines.values():
                        for i in range(args.warmup):engine.render(image,cfg,i)
                    names=list(engines)
                    for trial in range(args.rounds):
                        order=names[trial%len(names):]+names[:trial%len(names)]
                        for name in order:
                            engine=engines[name]
                            for i in range(args.frames):
                                begin=time.perf_counter();out=engine.render(image,cfg,trial*args.frames+i)
                                samples[name].append((time.perf_counter()-begin)*1000)
                                if name=='cuda-optimized':gpu.append(engine.kernel_ms());stages.append(engine.stage_ms())
                            outputs[name]=out
                    row={'width':width,'height':height,'mode':mode,'config':cfg,'results':{}}
                    for name,values in samples.items():
                        row['results'][name]={'frames':len(values),'mean_ms':float(np.mean(values)),
                            'std_ms':float(np.std(values,ddof=1)) if len(values)>1 else 0.,
                            'min_ms':float(np.min(values)),'max_ms':float(np.max(values)),
                            'median_ms':float(np.median(values)),
                            'p95_ms':float(np.quantile(values,.95)),'mean_fps':1000/float(np.mean(values)),
                            'sample_ms':values}
                    row['cuda_gpu_ms']=float(np.median(gpu))
                    row['cuda_stage_ms']={k:float(np.median([s[k] for s in stages])) for k in stages[0]}
                    row['speedup_vs_vulkan']=row['results']['vulkan']['median_ms']/row['results']['cuda-optimized']['median_ms']
                    row['mean_speedup_vs_vulkan']=row['results']['vulkan']['mean_ms']/row['results']['cuda-optimized']['mean_ms']
                    row['beats_vulkan_mean']=row['mean_speedup_vs_vulkan']>1
                    if 'cuda-before' in outputs:
                        np.testing.assert_array_equal(outputs['cuda-before'],outputs['cuda-optimized'])
                        row['baseline_cuda_bitwise_equal']=True
                    e=np.abs(outputs['vulkan'].astype('f8')-outputs['cuda-optimized'])
                    row['vulkan_difference']={'rmse':float(np.sqrt(np.mean(e*e))),'max_abs':float(e.max()),'p99':float(np.quantile(e,.99))}
                    report['rows'].append(row);args.output.write_text(json.dumps(report,indent=2))
                    print(json.dumps({k:v for k,v in row.items() if k!='results'}|{'mean_ms':{name:r['mean_ms'] for name,r in row['results'].items()},'median_ms':{name:r['median_ms'] for name,r in row['results'].items()}}),flush=True)
        report['gpu_end']=snapshot()
        passed=all(row['beats_vulkan_mean'] for row in report['rows'])
        report['speed_target']='passed' if passed else 'not_met'
        report['status']='passed' if passed else 'speed_target_not_met'
        args.output.write_text(json.dumps(report,indent=2))
        if not passed:raise SystemExit(2)
    finally:
        for engine in engines.values():engine.close()


if __name__=='__main__':main()
