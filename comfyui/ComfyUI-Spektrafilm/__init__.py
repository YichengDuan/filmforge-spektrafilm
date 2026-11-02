"""GPL-3.0-or-later. Subprocess nodes using a separate rendering environment.

Film modeling powered by spektrafilm (Andrea Volpato) and spektrafilm OFX (Aedan Diez).
Set FILMFORGE_ROOT to the independent workspace in the ComfyUI launch environment.
"""
import functools
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile


def local_config():
    path=Path(__file__).with_name('filmforge.local.json')
    return json.loads(path.read_text()) if path.is_file() else {}


def worker_environment():
    env=os.environ.copy()
    config=local_config()
    if 'vulkan_device_index' in config:
        env['SPEKTRAFILM_VULKAN_DEVICE_INDEX']=str(config['vulkan_device_index'])
    if 'vulkan_icd' in config:
        env['VK_ICD_FILENAMES']=config['vulkan_icd']
    if 'cuda_visible_devices' in config:
        env['CUDA_VISIBLE_DEVICES']=str(config['cuda_visible_devices'])
        env['FILMFORGE_CUDA_DEVICE']='0'
    return env


def root():
    value=os.environ.get('FILMFORGE_ROOT') or local_config().get('runtime_root')
    if not value:
        raise RuntimeError('Set FILMFORGE_ROOT to the isolated workspace before starting ComfyUI')
    path=Path(value).resolve()
    if not (path/'bin/filmforge-video').is_file():
        raise RuntimeError('FILMFORGE_ROOT does not contain bin/filmforge-video')
    return path


def worker_command():
    python=local_config().get('python_executable')
    if python:
        return [python,'-B',str(root()/'src/filmforge.py')]
    return [str(root()/'bin/filmforge-video')]


@functools.lru_cache(maxsize=2)
def profiles(backend='vulkan'):
    return json.loads(subprocess.check_output([*worker_command(),'--backend',backend,'--list-profiles'],text=True,timeout=60,env=worker_environment()))


def process_numpy(frames,preset,start_frame=0,input_transfer='srgb'):
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
        job.write_text(json.dumps({'input':str(inp),'output':str(out),'config':cfg,'start_frame':int(start_frame),'input_transfer':input_transfer}))
        subprocess.run([*worker_command(),'--worker-job',str(job)],check=True,env=worker_environment())
        return np.load(out,allow_pickle=False)


def process_cuda(images,preset,input_transfer='srgb'):
    import torch
    cfg=json.loads(preset)
    if images.ndim!=4 or images.shape[-1] not in (3,4):
        raise ValueError('Expected [B,H,W,3 or 4]')
    if not torch.isfinite(images).all() or torch.any(images<0) or torch.any(images>1):
        raise ValueError('CUDA-LUT input must be finite SDR values in [0,1]')
    config=local_config()
    physical=str(config.get('cuda_visible_devices',0))
    visibility=os.environ.get('CUDA_VISIBLE_DEVICES')
    if visibility:
        visible=[v.strip() for v in visibility.split(',')]
        if physical not in visible:
            raise RuntimeError('Configured CUDA GPU is not visible in this ComfyUI process')
        ordinal=visible.index(physical)
    else:
        ordinal=int(physical)
    device=torch.device(f'cuda:{ordinal}')
    base=root(); scratch=base/'.cache/comfyui-jobs'
    scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        preset_file=Path(directory)/'preset.json'
        preset_file.write_text(json.dumps(cfg))
        prepared=json.loads(subprocess.check_output([*worker_command(),'--prepare-lut',str(preset_file)],text=True,env=worker_environment()))
    spec=importlib.util.spec_from_file_location('_filmforge_cuda_lut',base/'src/cuda_lut.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    table=module.load_cuda_table(prepared['cache'],device)
    result=torch.empty(images.shape,dtype=torch.float32,device='cpu')
    def encode(rgb):
        return torch.where(rgb<=.0031308,12.92*rgb,1.055*rgb.clamp(min=0).pow(1/2.4)-.055)
    for i,frame in enumerate(images):
        frame=frame.to(device=device,dtype=torch.float32)
        rgb=frame[...,:3]
        if input_transfer=='bt709':
            rgb=encode(torch.where(rgb<.081,rgb/4.5,((rgb+.099)/1.099).pow(1/.45)))
        elif input_transfer=='linear-rec709': rgb=encode(rgb)
        elif input_transfer!='srgb': raise ValueError('Unknown input transfer')
        rendered=encode(module.sample_cuda_table(table,rgb)).clamp(0,1)
        result[i,...,:3]=rendered.cpu()
        if images.shape[-1]==4: result[i,...,3]=frame[...,3].cpu()
    return result


class SpektrafilmPreset:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'film':(profiles()['film'],),'print_profile':(profiles()['print'],),
                'backend':(local_config().get('backends',['vulkan','cpu-physical']),),
                'grain':('FLOAT',{'default':0.0,'min':0.0,'max':2.0}),
                'halation':('FLOAT',{'default':0.0,'min':0.0,'max':2.0}),
                'diffusion':('FLOAT',{'default':0.0,'min':0.0,'max':2.0}),
                'seed':('INT',{'default':1234,'min':0,'max':0xffffffff}),
                'temporal_grain_correlation':('FLOAT',{'default':0.0,'min':0.0,'max':1.0})},
                'optional':{'exposure':('FLOAT',{'default':0.0,'min':-5.0,'max':5.0,'step':.1})}}
    RETURN_TYPES=('STRING',)
    RETURN_NAMES=('preset_json',)
    FUNCTION='make'
    CATEGORY='image/spektrafilm (isolated)'
    def make(self,film,print_profile,backend,grain,halation,diffusion,seed,temporal_grain_correlation,exposure=0.0):
        if backend=='cuda-lut' and any((grain,halation,diffusion,temporal_grain_correlation)):
            raise ValueError('cuda-lut only processes color: set grain, halation, diffusion and temporal correlation to 0; use cuda-spectral or vulkan for these effects')
        registry=profiles(backend)
        if film not in registry['film'] or print_profile not in registry['print']:
            raise ValueError('Selected profile unavailable for this backend')
        return (json.dumps(dict(film=film,paper=print_profile,backend=backend,grain=grain,
                halation=halation,diffusion=diffusion,exposure=exposure,seed=seed,
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
        if json.loads(preset_json).get('backend')=='cuda-lut':
            return (process_cuda(images,preset_json),)
        result=process_numpy(images.detach().cpu().numpy(),preset_json)
        # ComfyUI IMAGE transport is bounded SDR. EXR offline CLI retains floats.
        return (torch.from_numpy(result.clip(0,1)),)


class SpektrafilmVideoFrames(SpektrafilmImage):
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'images':('IMAGE',),'preset_json':('STRING',{'multiline':True}),
                'fps':('FLOAT',{'default':25.0,'min':0.001,'max':240.0}),
                'start_frame':('INT',{'default':0,'min':0,'max':0xffffffff})},
                'optional':{'input_transfer':(['srgb','bt709','linear-rec709'],)}}
    RETURN_TYPES=('IMAGE','FLOAT')
    RETURN_NAMES=('images','fps')
    def process(self,images,preset_json,fps,start_frame,input_transfer='srgb'):
        import torch
        if json.loads(preset_json).get('backend')=='cuda-lut':
            return (process_cuda(images,preset_json,input_transfer),fps)
        result=process_numpy(images.detach().cpu().numpy(),preset_json,start_frame,input_transfer)
        return (torch.from_numpy(result.clip(0,1)),fps)


NODE_CLASS_MAPPINGS={c.__name__:c for c in (SpektrafilmPreset,SpektrafilmImage,SpektrafilmVideoFrames)}
NODE_DISPLAY_NAME_MAPPINGS={name:name+' (isolated)' for name in NODE_CLASS_MAPPINGS}
