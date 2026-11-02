#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path
import numpy as np
import colour
from filmforge import Vulkan, physical, write_exr, srgb_encode

root=Path(__file__).resolve().parents[1]
os.chdir(root)
os.environ['VK_ICD_FILENAMES']='/usr/share/vulkan/icd.d/nvidia_icd.json'
os.environ['SPEKTRAFILM_VULKAN_DEVICE_INDEX']='1'
cfg=dict(backend='vulkan',film='kodak_portra_400',paper='kodak_portra_endura',grain=0,halation=0,diffusion=0,seed=1234)
v=Vulkan()
try:
    # Scene-linear Rec.709, 17 stops including deep shadows and high highlights.
    ramp=np.geomspace(1e-4,16,256).astype(np.float32)
    image=np.broadcast_to(ramp[None,:,None],(32,256,3)).copy()
    patches=np.array([[.18,.18,.18],[.42,.22,.13],[.1,.2,.55],[.1,.45,.12],[.9,.02,.02],[1,1,1],[8,8,8],[.001,.001,.001]],np.float32)
    image[16:32]=np.repeat(patches,32,axis=0)[None,:,:]
    a=v.render(image,cfg)
    b=physical(image,{**cfg,'backend':'cpu-physical'})
    write_exr('examples/quality-vulkan.exr',a)
    write_exr('examples/quality-python.exr',b)
    rmse=float(np.sqrt(np.mean((a-b)**2)))
    lab_a=colour.XYZ_to_Lab(colour.sRGB_to_XYZ(srgb_encode(np.clip(a,0,1))))
    lab_b=colour.XYZ_to_Lab(colour.sRGB_to_XYZ(srgb_encode(np.clip(b,0,1))))
    delta=colour.delta_E(lab_a,lab_b,method='CIE 2000')
    report={'comparison':'diagnostic only: same profile names, linear Rec.709 IO, exposure=0, grain/halation/diffusion disabled; remaining upstream defaults, data and reference-white calibrations differ. NOT validated parity.',
       'linear_rmse':rmse,'linear_psnr_peak1_db':float(-20*np.log10(rmse)),
       'deltaE2000_D65_srgb_clipped_mean':float(delta.mean()),'deltaE2000_D65_srgb_clipped_max':float(delta.max()),
       'vulkan_gray_channel_spread_max':float(np.ptp(a[:16],axis=-1).max()),'python_gray_channel_spread_max':float(np.ptp(b[:16],axis=-1).max()),
       'vulkan_min':float(a.min()),'vulkan_max':float(a.max()),'python_min':float(b.min()),'python_max':float(b.max()),
       'vulkan_outside_sdr_fraction':float(((a<0)|(a>1)).mean()),'scene_input_stops':float(np.log2(16/1e-4)),
       'color_patches':'synthetic diagnostic RGB swatches, not a calibrated measured ColorChecker'}
    for w,h in [(1280,720),(1920,1080),(3840,2160)]:
        frame=np.full((h,w,3),.18,np.float32)
        begin=time.perf_counter(); result=v.render(frame,{**cfg,'grain':.35,'halation':.3,'diffusion':.1})
        report[f'{h}p_single_frame_seconds']=time.perf_counter()-begin
        assert np.isfinite(result).all()
    Path('benchmarks/quality.json').write_text(json.dumps(report,indent=2))
finally: v.close()
