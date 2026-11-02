"""GPL-3.0-or-later. Optional subprocess nodes; never install into an existing host.

Film modeling powered by spektrafilm (Andrea Volpato) and spektrafilm OFX (Aedan Diez).
Set FILMFORGE_ROOT to the independent workspace in the ComfyUI launch environment.
"""
import functools
import json
import os
from pathlib import Path
import subprocess
import tempfile


def root():
    value=os.environ.get('FILMFORGE_ROOT')
    if not value:
        raise RuntimeError('Set FILMFORGE_ROOT to the isolated workspace before starting ComfyUI')
    path=Path(value).resolve()
    if not (path/'bin/filmforge-video').is_file():
        raise RuntimeError('FILMFORGE_ROOT does not contain bin/filmforge-video')
    return path


@functools.lru_cache(maxsize=2)
def profiles(backend='vulkan'):
    return json.loads(subprocess.check_output([str(root()/'bin/filmforge-video'),'--backend',backend,'--list-profiles'],text=True,timeout=60))


def process_numpy(frames,preset,start_frame=0):
    # NumPy and torch are imported only in the host runtime. No Qt, colour,
    # Vulkan Python package or original simulation dependencies enter the host.
    import numpy as np
    frames=np.asarray(frames,dtype=np.float32)
    if frames.ndim!=4 or frames.shape[-1] not in (3,4):
        raise ValueError('Expected [B,H,W,3 or 4] sRGB encoded straight RGB(A)')
    if not np.isfinite(frames).all() or np.any(frames<0) or np.any(frames>1):
        raise ValueError('ComfyUI IMAGE must contain finite sRGB values in [0,1]')
    cfg=json.loads(preset) if isinstance(preset,str) else dict(preset)
    base=root()
    scratch=base/'.cache'/'comfyui-jobs'
    scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        directory=Path(directory)
        inp=directory/'input.npy'; out=directory/'output.npy'; job=directory/'job.json'
        np.save(inp,frames,allow_pickle=False)
        job.write_text(json.dumps({'input':str(inp),'output':str(out),'config':cfg,'start_frame':int(start_frame)}))
        subprocess.run([str(base/'bin/filmforge-video'),'--worker-job',str(job)],check=True)
        return np.load(out,allow_pickle=False)


class SpektrafilmPreset:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'film':(profiles()['film'],),'print_profile':(profiles()['print'],),
                'backend':(['vulkan','cpu-physical'],),
                'grain':('FLOAT',{'default':0.0,'min':0.0,'max':2.0}),
                'halation':('FLOAT',{'default':0.0,'min':0.0,'max':2.0}),
                'diffusion':('FLOAT',{'default':0.0,'min':0.0,'max':2.0}),
                'seed':('INT',{'default':1234,'min':0,'max':0xffffffff}),
                'temporal_grain_correlation':('FLOAT',{'default':0.0,'min':0.0,'max':1.0})}}
    RETURN_TYPES=('STRING',)
    RETURN_NAMES=('preset_json',)
    FUNCTION='make'
    CATEGORY='image/spektrafilm (isolated)'
    def make(self,film,print_profile,backend,grain,halation,diffusion,seed,temporal_grain_correlation):
        registry=profiles(backend)
        if film not in registry['film'] or print_profile not in registry['print']:
            raise ValueError('Selected profile unavailable for this backend')
        return (json.dumps(dict(film=film,paper=print_profile,backend=backend,grain=grain,
                halation=halation,diffusion=diffusion,exposure=0,seed=seed,
                temporal_grain_correlation=temporal_grain_correlation)),)


class SpektrafilmImage:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'images':('IMAGE',),'preset_json':('STRING',{'multiline':True})}}
    RETURN_TYPES=('IMAGE',)
    FUNCTION='process'
    CATEGORY=SpektrafilmPreset.CATEGORY
    def process(self,images,preset_json):
        import torch
        result=process_numpy(images.detach().cpu().numpy(),preset_json)
        # ComfyUI IMAGE transport is bounded SDR. EXR offline CLI retains floats.
        return (torch.from_numpy(result.clip(0,1)),)


class SpektrafilmVideoFrames(SpektrafilmImage):
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'images':('IMAGE',),'preset_json':('STRING',{'multiline':True}),
                'fps':('FLOAT',{'default':25.0,'min':0.001,'max':240.0}),
                'start_frame':('INT',{'default':0,'min':0,'max':0xffffffff})}}
    RETURN_TYPES=('IMAGE','FLOAT')
    RETURN_NAMES=('images','fps')
    def process(self,images,preset_json,fps,start_frame):
        import torch
        result=process_numpy(images.detach().cpu().numpy(),preset_json,start_frame)
        return (torch.from_numpy(result.clip(0,1)),fps)


NODE_CLASS_MAPPINGS={c.__name__:c for c in (SpektrafilmPreset,SpektrafilmImage,SpektrafilmVideoFrames)}
NODE_DISPLAY_NAME_MAPPINGS={name:name+' (isolated)' for name in NODE_CLASS_MAPPINGS}
