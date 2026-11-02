#!/usr/bin/env python3
"""Check optimized CUDA against a saved original implementation and reference kernels."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from cuda_spectral import CudaSpectral


def baseline_module(directory):
    spec=importlib.util.spec_from_file_location('cuda_baseline',directory/'src/cuda_spectral.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,default=ROOT/'benchmarks/cuda-optimization-qa.json')
    args=p.parse_args()
    old=baseline_module(args.baseline_dir).CudaSpectral()
    os.environ['FILMFORGE_CUDA_BLUR']='reference';reference=CudaSpectral()
    os.environ['FILMFORGE_CUDA_BLUR']='tiled';optimized=CudaSpectral()
    cfg=dict(film='kodak_portra_400',paper='kodak_portra_endura',grain=.35,halation=.3,diffusion=.1,
             exposure=0,seed=1234,temporal_grain_correlation=0)
    report={'geometry':[],'temporal':[]}
    rng=np.random.default_rng(31)
    def metric(a,b):
        error=np.abs(a.astype('f8')-b)
        return {'max_abs':float(error.max()),'rmse':float(np.sqrt(np.mean(error*error)))}
    try:
        for width,height in ((1,1),(33,1),(1,17),(129,33),(513,257),(8193,1),(1280,720),(1920,1080)):
            for channels in (3,4):
                image=rng.uniform(0,4,(height,width,channels)).astype('f4')
                if channels==4:image[...,3]=rng.uniform(0,1,(height,width))
                a=old.render(image,cfg,27);b=optimized.render(image,cfg,27)
                difference=metric(a,b)
                np.testing.assert_array_equal(a,b)
                if channels==4:np.testing.assert_array_equal(image[...,3],b[...,3])
                # Returned arrays must own independent storage across renders.
                saved=b.copy();optimized.render(image,cfg,28);np.testing.assert_array_equal(saved,b)
                report['geometry'].append({'width':width,'height':height,'channels':channels,**difference})
        for rho in (0,.3,.7,1):
            for channels in (3,4):
                image=rng.uniform(0,2,(129,257,channels)).astype('f4')
                config={**cfg,'temporal_grain_correlation':rho}
                a=old.render(image,config,45);b=optimized.render(image,config,45)
                difference=metric(a,b)
                np.testing.assert_array_equal(a,b)
                np.testing.assert_array_equal(b,reference.render(image,config,45))
                report['temporal'].append({'rho':rho,'channels':channels,**difference})
        # Noncontiguous arrays and independently sliced frame batches.
        image=rng.uniform(0,1,(33,130,4)).astype('f4')[:,::2,:3]
        assert not image.flags.c_contiguous
        np.testing.assert_array_equal(old.render(image,cfg,3),optimized.render(image,cfg,3))
        for film,paper in [('kodak_vision3_500t','kodak_2383'),('fuji_pro_400h','kodak_portra_endura')]:
            if film not in optimized.profiles():continue
            config={**cfg,'film':film,'paper':paper,'exposure':-1,'temporal_grain_correlation':.7}
            np.testing.assert_array_equal(old.render(image,config,99),optimized.render(image,config,99))
        report['noncontiguous_and_profile_changes']='passed'
        report['status']='passed'
        args.output.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:old.close();reference.close();optimized.close()


if __name__=='__main__':main()
