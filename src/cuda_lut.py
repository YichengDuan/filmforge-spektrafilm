"""GPL-3.0-or-later. CUDA interpolation of a locally baked OFX color transform.

This is a color-only approximation, not a CUDA port of the spectral/spatial core.
Derived profile tables stay in the local cache with their upstream notices.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


class LutBaker:
    resolution=65

    def __init__(self,reference_class):
        self.reference_class=reference_class
        reference=reference_class()
        try:
            self.registry=[reference.profiles(),reference.profiles(True)]
        finally: reference.close()
        assets=[ROOT/'src/vulkan_bridge.cpp',ROOT/'build/bridge/libfilmforge_vulkan.so',
                *sorted((ROOT/'build/ofx-Release/shaders').glob('*.spv')),
                *sorted((ROOT/'build/ofx-Release').glob('*.f32'))]
        digest=hashlib.sha256()
        for asset in assets: digest.update(asset.read_bytes())
        self.source_hash=digest.hexdigest()
        self.table=None
        self.key=None
        self.last_cache=None
        self.bake_seconds=0

    def profiles(self,paper=False):
        return self.registry[int(paper)]

    def close(self):
        self.table=None
        self.key=None

    def prepare(self,config):
        for name in ('grain','halation','diffusion','temporal_grain_correlation'):
            if config.get(name,0)!=0:
                raise ValueError('cuda-lut is color-only: set grain, halation, diffusion and temporal_grain_correlation to 0, or use vulkan')
        if config['film'] not in self.registry[0] or config['paper'] not in self.registry[1]:
            raise ValueError('Unknown OFX profile')
        spec={'film':config['film'],'paper':config['paper'],'exposure':config.get('exposure',0),
              'resolution':self.resolution,'domain':'encoded sRGB [0,1] -> linear Rec.709',
              'renderer_source':self.source_hash,'version':1}
        key=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
        if key==self.key: return
        folder=ROOT/'.cache/cuda-lut'
        folder.mkdir(parents=True,exist_ok=True)
        path=folder/(key+'.npz')
        if path.is_file():
            with np.load(path,allow_pickle=False) as archive:
                cube=archive['cube']
                if json.loads(str(archive['spec']))!=spec: raise RuntimeError('CUDA LUT cache configuration mismatch')
        else:
            begin=time.perf_counter()
            axis=np.linspace(0,1,self.resolution,dtype=np.float32)
            # Volume D/H/W are B/G/R, matching grid_sample's x/y/z = R/G/B.
            b,g,r=np.meshgrid(axis,axis,axis,indexing='ij')
            encoded=np.stack([r,g,b],axis=-1).reshape(self.resolution,self.resolution**2,3)
            linear=np.where(encoded<=.04045,encoded/12.92,((encoded+.055)/1.055)**2.4)
            reference=self.reference_class()
            try:
                cube=reference.render(linear,config,0).reshape(self.resolution,self.resolution,self.resolution,3)
            finally: reference.close()
            if not np.isfinite(cube).all(): raise RuntimeError('Non-finite OFX LUT samples')
            temp=folder/(key+f'.{os.getpid()}.tmp.npz')
            np.savez(temp,cube=cube.astype(np.float32),spec=json.dumps(spec,sort_keys=True))
            temp.replace(path)
            self.bake_seconds=time.perf_counter()-begin
            for name,src in [('OFX_THIRD_PARTY_NOTICES.txt',ROOT/'upstream/spektrafilm-ofx/Legal/THIRD_PARTY_NOTICES.txt'),
                             ('SPEKTRAFILM_PROFILE_LICENSE.txt',ROOT/'upstream/spektrafilm/SPEKTRAFILM_LICENSE.txt'),
                             ('OFX_LUT_NOTICE.txt',ROOT/'upstream/spektrafilm-ofx/Legal/SPEKTRAFILM_OFX_LUT_LICENSE.txt')]:
                shutil.copy2(src,folder/name)
        if cube.shape!=(self.resolution,)*3+(3,) or not np.isfinite(cube).all():
            raise RuntimeError('Invalid CUDA LUT cache')
        self.key=key
        self.last_cache=path
        return cube


def load_cuda_table(path,device):
    import torch
    with np.load(path,allow_pickle=False) as archive:
        cube=archive['cube']
        spec=json.loads(str(archive['spec']))
    if cube.shape!=(spec['resolution'],)*3+(3,) or not np.isfinite(cube).all():
        raise RuntimeError('Invalid CUDA LUT cache')
    return torch.from_numpy(np.ascontiguousarray(cube.transpose(3,0,1,2))).unsqueeze(0).to(device)


def sample_cuda_table(table,encoded):
    import torch.nn.functional as F
    return F.grid_sample(table,(encoded*2-1)[None,None],mode='bilinear',padding_mode='border',align_corners=True)[0,:,0].permute(1,2,0)


class CudaLut(LutBaker):
    def __init__(self,reference_class):
        try:
            import torch
        except ImportError as e:
            raise RuntimeError('cuda-lut requires an existing CUDA-enabled PyTorch environment; no packages were installed') from e
        if not torch.cuda.is_available():
            raise RuntimeError('cuda-lut: CUDA is unavailable in this Python environment')
        self.torch=torch
        self.device=torch.device('cuda:'+os.environ.get('FILMFORGE_CUDA_DEVICE','0'))
        super().__init__(reference_class)

    def prepare(self,config):
        cube=super().prepare(config)
        if cube is not None:
            self.table=self.torch.from_numpy(np.ascontiguousarray(cube.transpose(3,0,1,2))).unsqueeze(0).to(self.device)

    def render(self,linear,config,frame=0):
        self.prepare(config)
        a=np.asarray(linear,dtype=np.float32)
        if a.ndim!=3 or a.shape[-1] not in (3,4) or not np.isfinite(a).all():
            raise ValueError('cuda-lut expects finite HWC RGB(A)')
        if np.any(a[...,:3]<0) or np.any(a[...,:3]>1.000001):
            raise ValueError('cuda-lut supports linear Rec.709 RGB in [0,1]; HDR requires vulkan')
        t=self.torch.from_numpy(np.ascontiguousarray(a)).to(self.device)
        rgb=t[...,:3]
        encoded=self.torch.where(rgb<=.0031308,rgb*12.92,1.055*rgb.clamp(min=0).pow(1/2.4)-.055)
        result=sample_cuda_table(self.table,encoded)
        if a.shape[-1]==4: result=self.torch.cat([result,t[...,3:4]],dim=-1)
        return result.contiguous().cpu().numpy()
