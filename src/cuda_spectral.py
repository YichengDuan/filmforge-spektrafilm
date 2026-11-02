"""Native CUDA spectral and spatial rendering; no PyTorch or final RGB LUT."""
import ctypes as C
import hashlib
import os
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


class CudaSpectral:
    def __init__(self):
        library=ROOT/'build/cuda-spectral/libfilmforge_cuda_spectral.so'
        if not library.is_file():
            raise RuntimeError('Native CUDA backend missing: run bash scripts/build_cuda_spectral.sh in the Filmforge workspace')
        self.lib=C.CDLL(str(library))
        self.lib.ff_cuda_create.argtypes=[C.c_int];self.lib.ff_cuda_create.restype=C.c_void_p
        self.lib.ff_cuda_destroy.argtypes=[C.c_void_p];self.lib.ff_cuda_destroy.restype=None
        self.lib.ff_cuda_error.restype=C.c_char_p
        self.lib.ff_cuda_prepare.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_char_p]
        self.lib.ff_cuda_render_effects.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_int,C.c_int]+[C.c_float]*4+[C.c_uint]*2
        self.lib.ff_cuda_render_channels.argtypes=self.lib.ff_cuda_render_effects.argtypes+[C.c_int]
        self.lib.ff_cuda_render_temporal.argtypes=self.lib.ff_cuda_render_channels.argtypes+[C.c_double]
        self.lib.ff_cuda_kernel_ms.argtypes=[C.c_void_p];self.lib.ff_cuda_kernel_ms.restype=C.c_double
        self.lib.ff_cuda_enable_profiling.argtypes=[C.c_void_p]
        self.lib.ff_cuda_stage_ms.argtypes=[C.c_void_p,C.c_int];self.lib.ff_cuda_stage_ms.restype=C.c_double
        self.lib.ff_cuda_diffusion_dispatches.argtypes=[C.c_void_p];self.lib.ff_cuda_diffusion_dispatches.restype=C.c_uint
        self.lib.ff_spectral_stock_count.argtypes=[C.c_int]
        self.lib.ff_spectral_stock.argtypes=[C.c_int,C.c_int];self.lib.ff_spectral_stock.restype=C.c_char_p
        self.ptr=self.lib.ff_cuda_create(int(os.environ.get('FILMFORGE_CUDA_DEVICE','0')))
        if not self.ptr: raise RuntimeError(self.lib.ff_cuda_error().decode())

    def profiles(self,paper=False):
        return [self.lib.ff_spectral_stock(paper,i).decode() for i in range(self.lib.ff_spectral_stock_count(paper))]

    def close(self):
        if self.ptr:
            self.lib.ff_cuda_destroy(self.ptr);self.ptr=None

    def render(self,rgb,config,frame=0):
        x=np.asarray(rgb,np.float32)
        if x.ndim!=3 or x.shape[-1] not in (3,4) or not np.isfinite(x).all() or np.any(x[...,:3]<0):
            raise ValueError('CUDA spectral input must be finite nonnegative HWC RGB(A)')
        h,w=x.shape[:2]
        if not (0<w<=16384 and 0<h<=16384): raise ValueError('Unsupported image dimensions')
        if not 0<=frame<=0xffffffff: raise ValueError('absolute frame index outside uint32')
        for key in ('exposure','grain','halation','diffusion','temporal_grain_correlation'):
            value=config.get(key,0)
            if not np.isfinite(value) or (key!='exposure' and value<0):
                raise ValueError('Invalid '+key)
        rho=config.get('temporal_grain_correlation',0)
        if not 0<=rho<=1: raise ValueError('temporal_grain_correlation must be in [0,1]')
        source=np.ascontiguousarray(x)
        render_buffer=np.empty_like(source)
        film=self.profiles().index(config['film']);paper=self.profiles(True).index(config['paper'])
        if not self.lib.ff_cuda_prepare(self.ptr,film,paper,str(ROOT/'build/ofx-Release').encode()):
            raise RuntimeError('CUDA profile preparation failed: '+self.lib.ff_cuda_error().decode())
        seed=int.from_bytes(hashlib.sha256(f"{config.get('seed',1234)}:{config['film']}".encode()).digest()[:4],'little')
        grain=config.get('grain',0)
        if not self.lib.ff_cuda_render_temporal(self.ptr,source.ctypes.data,render_buffer.ctypes.data,w,h,
            config.get('exposure',0),grain,config.get('halation',0),config.get('diffusion',0),seed,frame,source.shape[-1],rho):
            raise RuntimeError('CUDA spectral render failed: '+self.lib.ff_cuda_error().decode())
        destination=render_buffer
        if source.shape[-1]==4:destination[...,3]=source[...,3]
        if not np.isfinite(destination).all(): raise RuntimeError('Non-finite CUDA spectral output')
        return destination

    def kernel_ms(self):
        return self.lib.ff_cuda_kernel_ms(self.ptr)

    def enable_profiling(self):
        if not self.lib.ff_cuda_enable_profiling(self.ptr):
            raise RuntimeError(self.lib.ff_cuda_error().decode())

    def stage_ms(self):
        stages=('exposure','diffusion','halation','develop_grain','print_scan')
        return {name:self.lib.ff_cuda_stage_ms(self.ptr,i) for i,name in enumerate(stages)}
