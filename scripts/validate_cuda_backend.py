#!/usr/bin/env python3
"""Validate native CUDA spectral/spatial rendering against the pinned Vulkan path.

Run on an idle GPU where possible. Selection is explicit through
CUDA_VISIBLE_DEVICES/FILMFORGE_CUDA_DEVICE and SPEKTRAFILM_VULKAN_DEVICE_INDEX.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from filmforge import Vulkan,make_engine


def errors(a,b):
    e=np.abs(a[...,:3].astype('f8')-b[...,:3])
    return dict(rmse=float(np.sqrt(np.mean(e*e))),max_abs=float(e.max()),
                p99=float(np.quantile(e,.99)),fraction_over_1e_4=float(np.mean(e>1e-4)))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'benchmarks/cuda-native-validation.json')
    p.add_argument('--timing-frames',type=int,default=12)
    args=p.parse_args()
    if args.timing_frames<1:p.error('--timing-frames must be positive')
    cfg=dict(film='kodak_portra_400',paper='kodak_portra_endura',exposure=0,grain=0,
             halation=0,diffusion=0,seed=1234,temporal_grain_correlation=0)
    report={'scope':'Current Filmforge CLI/node features, not all OFX advanced controls',
            'gpu_snapshot':subprocess.check_output(['nvidia-smi','--query-gpu=index,name,memory.used,utilization.gpu','--format=csv'],text=True),
            'conditions':'Live workstation; other user GPU work may cause contention. No CUDA speed guarantee.',
            'profiles':[],'effects':[],'timings':[]}
    def save():
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2))
    v=Vulkan(); c=make_engine('cuda-spectral')
    rng=np.random.default_rng(16)
    try:
        # Every generated profile pairing, mixed black/midgray/HDR/colored patches.
        patches=rng.uniform(0,4,(8,16,4)).astype('f4')
        patches[0,:,:3]=0;patches[1,:,:3]=.184;patches[2,:,:3]=16
        patches[...,3]=rng.uniform(0,1,(8,16))
        for film in c.profiles():
            for paper in c.profiles(True):
                config={**cfg,'film':film,'paper':paper}
                a=v.render(patches,config);b=c.render(patches,config)
                assert np.isfinite(b).all()
                np.testing.assert_array_equal(b[...,3],patches[...,3])
                metric=errors(a,b)
                # Very dark/bright patches exercise endpoints and out-of-gamut
                # scan RGB. Keep the absolute tolerance explicit and meaningful.
                assert metric['max_abs']<2e-4,(film,paper,metric)
                report['profiles'].append({'film':film,'paper':paper,**metric})
        report['profile_pairings_passed']=len(report['profiles']);save()
        print('profile pairings:',report['profile_pairings_passed'],flush=True)
        # Strong edges, moving-style detail, HDR highlights and a grayscale ramp.
        x=rng.uniform(0,1,(257,513,4)).astype('f4')
        x[64:180,220:230,:3]=24;x[190:240,:,:3]=np.linspace(0,4,513)[None,:,None]
        x[...,3]=np.linspace(0,1,513)
        for delta in ({},{'halation':.5},{'diffusion':.4},{'grain':.5},
                      {'halation':.5,'diffusion':.4,'grain':.5},
                      {'halation':.5,'diffusion':.4,'grain':.5,'temporal_grain_correlation':.7}):
            config={**cfg,**delta};a=v.render(x,config,27);b=c.render(x,config,27)
            metric=errors(a,b)
            assert np.isfinite(b).all()
            np.testing.assert_array_equal(b[...,3],x[...,3])
            np.testing.assert_array_equal(b,c.render(x,config,27))
            # Grain cell hashes can differ at a float rounding boundary between
            # APIs. Do not demand texture pixel identity across backends.
            assert metric['rmse']<(0.003 if config['grain'] else 2e-5),metric
            if delta:
                assert np.max(np.abs(b-c.render(x,cfg,27)))>1e-6,'Effect silently ignored'
            report['effects'].append({'config_delta':delta,**metric});save()
        # Same 100 frames twice and independent chunks must align exactly.
        small=np.full((48,80,4),.184,np.float32);small[...,3]=.37
        config={**cfg,'grain':.5,'halation':.4,'diffusion':.2}
        sequence=[c.render(small,config,i) for i in range(100)]
        for i in range(100):np.testing.assert_array_equal(sequence[i],c.render(small,config,i))
        for lo,hi in ((0,37),(37,74),(74,100)):
            for i in range(lo,hi):np.testing.assert_array_equal(sequence[i],c.render(small,config,i))
        residual=np.stack(sequence)[...,:3]-c.render(small,cfg)[None,...,:3]
        adjacent=np.corrcoef(residual[:-1].ravel(),residual[1:].ravel())[0,1]
        report['temporal']={'frames':100,'repeat_exact':True,'segments_exact':True,
                            'variance':float(residual.var()),'adjacent_correlation':float(adjacent)}
        assert residual.var()>0
        correlated={**config,'temporal_grain_correlation':.7}
        seq=np.stack([c.render(small,correlated,i)[...,:3] for i in range(30)])
        base=c.render(small,{**config,'grain':0})[...,:3]
        r=seq-base
        rho=float(np.corrcoef(r[:-1].ravel(),r[1:].ravel())[0,1])
        report['temporal']['rho_0_7_observed']=rho
        assert .5<rho<.9,rho
        # Reject malformed frames/parameters, invalid device and invalid profiles.
        rejected=[]
        for name,image,delta,index in [('nan',small*np.nan,{},0),('negative',-small,{},0),
            ('bad_profile',small,{'film':'missing'},0),('bad_correlation',small,{'temporal_grain_correlation':2},0),
            ('bad_frame',small,{},-1)]:
            try:c.render(image,{**cfg,**delta},index)
            except (ValueError,RuntimeError):rejected.append(name)
            else:raise AssertionError('Invalid input accepted: '+name)
        report['rejected']=rejected;save()
        for width,height in ((1280,720),(1920,1080)):
            frame=rng.uniform(0,2,(height,width,3)).astype('f4')
            for effects in (False,True):
                config={**cfg,**({'grain':.35,'halation':.3,'diffusion':.1} if effects else {})}
                outputs={}
                for name,engine in (('vulkan',v),('cuda-spectral',c)):
                    for i in range(2):engine.render(frame,config,i)
                    samples=[];kernels=[]
                    for i in range(args.timing_frames):
                        begin=time.perf_counter();out=engine.render(frame,config,i);samples.append(time.perf_counter()-begin)
                        if name=='cuda-spectral':kernels.append(c.kernel_ms())
                    row={'width':width,'height':height,'effects':effects,'backend':name,
                         'frames':len(samples),'median_ms':float(np.median(samples)*1000),'p95_ms':float(np.quantile(samples,.95)*1000),
                         'mean_fps':len(samples)/sum(samples),'config':config}
                    if kernels:row['median_cuda_kernel_ms']=float(np.median(kernels))
                    report['timings'].append(row);outputs[name]=out
                    print(json.dumps(row),flush=True);save()
                report.setdefault('resolution_parity',[]).append({'width':width,'height':height,'effects':effects,**errors(*outputs.values())})
        report['status']='passed';save()
    finally:v.close();c.close()


if __name__=='__main__':main()
