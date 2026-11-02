"""GPL-3.0-or-later. Isolated media adapter; film modeling powered by spektrafilm."""
import argparse
import ctypes as C
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def srgb_decode(x):
    return np.where(x <= .04045, x/12.92, ((x+.055)/1.055)**2.4)


def srgb_encode(x):
    return np.where(x <= .0031308, 12.92*x, 1.055*np.maximum(x, 0)**(1/2.4)-.055)


def bt709_decode(x):
    return np.where(x < .081, x/4.5, ((x+.099)/1.099)**(1/.45))


def bt709_encode(x):
    return np.where(x < .018, x*4.5, 1.099*np.maximum(x, 0)**.45-.099)


class Vulkan:
    def __init__(self):
        os.environ.setdefault('SPEKTRAFILM_RESOURCE_DIR', str(ROOT/'build/ofx-Release'))
        self.lib = C.CDLL(str(ROOT/'build/bridge/libfilmforge_vulkan.so'))
        self.lib.ff_create.restype = C.c_void_p
        self.lib.ff_destroy.argtypes = [C.c_void_p]
        self.lib.ff_destroy.restype = None
        self.lib.ff_error.restype = C.c_char_p
        self.lib.ff_count.argtypes = [C.c_int]
        self.lib.ff_stock.argtypes = [C.c_int, C.c_int]
        self.lib.ff_stock.restype = C.c_char_p
        self.lib.ff_render.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p] + [C.c_int]*6 + [C.c_float]*4 + [C.c_uint]*2
        self.ptr = self.lib.ff_create()
        if not self.ptr:
            raise RuntimeError(self.lib.ff_error().decode())

    def close(self):
        if self.ptr:
            self.lib.ff_destroy(self.ptr)
            self.ptr = None

    def profiles(self, paper=False):
        return [self.lib.ff_stock(paper, i).decode() for i in range(self.lib.ff_count(paper))]

    def render(self, rgb, config, frame=0):
        rgb = np.asarray(rgb, np.float32)
        if rgb.ndim != 3 or rgb.shape[2] not in (3, 4):
            raise ValueError('Expected [H,W,3 or 4] straight RGB(A)')
        if not np.isfinite(rgb).all() or np.any(rgb[..., :3] < 0):
            raise ValueError('Negative or NaN/Inf RGB input rejected')
        if not 0 <= frame <= 0xffffffff:
            raise ValueError('absolute frame index outside uint32')
        h, w = rgb.shape[:2]
        rgba = np.ones((h,w,4), np.float32)
        rgba[...,:rgb.shape[2]] = rgb
        out = np.empty_like(rgba)
        film = self.profiles().index(config['film'])
        paper = self.profiles(True).index(config['paper'])
        # Include profile identity in the seed, independent of Python hash salt.
        seed = int.from_bytes(hashlib.sha256(f"{config['seed']}:{config['film']}".encode()).digest()[:4], 'little')
        def call(grain, index, salt=0):
            ok = self.lib.ff_render(self.ptr, rgba.ctypes.data, out.ctypes.data, w,h,film,paper,15,15,
                                   config.get('exposure',0),grain,config.get('halation',0),
                                   config.get('diffusion',0),seed ^ salt,index)
            if not ok:
                raise RuntimeError('Vulkan render failed: '+self.lib.ff_error().decode())
            return out.copy()
        grain = config.get('grain',0)
        rho = config.get('temporal_grain_correlation',0)
        if not 0 <= rho <= 1:
            raise ValueError('temporal_grain_correlation must be in [0,1]')
        result = call(grain, frame)
        if grain > 0 and rho > 0:
            # Correlate upstream texture residuals, never reimplement grain.
            # This optional bridge extension is not an OFX parity claim.
            base = call(0,frame)
            shared = call(grain,0,0x9e3779b9)
            result[...,:3] = base[...,:3] + np.sqrt(1-rho)*(result[...,:3]-base[...,:3]) + np.sqrt(rho)*(shared[...,:3]-base[...,:3])
        result[...,3] = rgba[...,3]
        return result[...,:rgb.shape[2]]


def physical(rgb, config):
    from spektrafilm import init_params, digest_params, Simulator
    if config.get('grain',0) or config.get('temporal_grain_correlation',0):
        raise ValueError('CPU physical bridge currently supports deterministic color/spatial processing only; choose vulkan for temporal grain')
    p = init_params(config['film'],config['paper'])
    p.io.input_color_space = p.io.output_color_space = 'sRGB'
    p.io.input_cctf_decoding = p.io.output_cctf_encoding = False
    p.io.crop=False
    p.io.upscale_factor=1
    p.camera.auto_exposure=False
    p.camera.exposure_compensation_ev=config.get('exposure',0)
    p.debug.deactivate_stochastic_effects=True
    p.debug.deactivate_spatial_effects=not bool(config.get('halation',0) or config.get('diffusion',0))
    if config.get('halation',0) or config.get('diffusion',0):
        raise ValueError('CPU bridge spatial amount mapping not verified; use vulkan or scripts/test_still.py --spatial')
    result = Simulator(digest_params(p)).process(rgb[...,:3])
    if rgb.shape[2] == 4:
        result=np.concatenate([result,rgb[...,3:4]],axis=2)
    return result.astype(np.float32)


def write_exr(path, frame):
    import OpenImageIO as oiio
    out=oiio.ImageOutput.create(str(path))
    spec=oiio.ImageSpec(frame.shape[1],frame.shape[0],frame.shape[2],oiio.FLOAT)
    spec.attribute('oiio:ColorSpace','Linear Rec.709 (sRGB primaries)')
    spec.attribute('oiio:UnassociatedAlpha',1)
    if not out or not out.open(str(path),spec):
        raise RuntimeError(oiio.geterror())
    try:
        if not out.write_image(np.asarray(frame,np.float32)):
            raise RuntimeError(out.geterror())
    finally:
        out.close()


def read_image(path):
    import OpenImageIO as oiio
    config=oiio.ImageSpec()
    config.attribute('oiio:UnassociatedAlpha',1)
    inp=oiio.ImageInput.open(str(path),config)
    if not inp:
        raise ValueError(oiio.geterror())
    try:
        return inp.read_image(format=oiio.FLOAT)
    finally:
        inp.close()


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))


def read_exact(stream,size):
    chunks=[]
    remaining=size
    while remaining:
        chunk=stream.read(remaining)
        if not chunk:
            if remaining != size:
                raise RuntimeError('Truncated decoded frame')
            return None
        chunks.append(chunk)
        remaining-=len(chunk)
    return b''.join(chunks)


def worker(job_path):
    job=json.loads(Path(job_path).read_text())
    frames=np.load(job['input'],allow_pickle=False,mmap_mode='r')
    if frames.ndim!=4:
        raise ValueError('Expected [B,H,W,C]')
    if not np.isfinite(frames).all() or np.any(frames<0) or np.any(frames>1):
        raise ValueError('Worker transport requires bounded finite sRGB frames')
    cfg=job['config']
    engine=Vulkan() if cfg['backend']=='vulkan' else None
    result=np.lib.format.open_memmap(job['output'],mode='w+',dtype=np.float32,shape=frames.shape)
    try:
        for i,frame in enumerate(frames):
            linear=srgb_decode(frame[...,:3])
            if frame.shape[2]==4:
                linear=np.concatenate([linear,frame[...,3:4]],axis=2)
            rendered=engine.render(linear,cfg,job.get('start_frame',0)+i) if engine else physical(linear,cfg)
            result[i,...,:3]=srgb_encode(rendered[...,:3])
            if frame.shape[2]==4:
                result[i,...,3]=frame[...,3]
        result.flush()
    finally:
        if engine: engine.close()


def main(argv=None):
    p=argparse.ArgumentParser(description='Offline adapter over the actual spektrafilm OFX Vulkan renderer. SDR only.')
    p.add_argument('--input',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--backend',choices=['vulkan','cpu-physical'],default='vulkan')
    p.add_argument('--film',default='kodak_portra_400')
    p.add_argument('--print',dest='paper',default='kodak_portra_endura')
    p.add_argument('--grain',type=float,default=0)
    p.add_argument('--halation',type=float,default=0)
    p.add_argument('--diffusion',type=float,default=0)
    p.add_argument('--exposure',type=float,default=0)
    p.add_argument('--seed',type=int,default=1234)
    p.add_argument('--temporal-grain-correlation',type=float,default=0)
    p.add_argument('--start-frame',type=int,default=0,help='Absolute grain frame index (not media seek)')
    p.add_argument('--fps',type=float,help='Required for image directories; videos must be constant fps')
    p.add_argument('--input-transfer',choices=['auto','bt709','srgb','linear'],default='auto')
    p.add_argument('--codec',choices=['h264','hevc'],default='h264')
    p.add_argument('--encoder',choices=['cpu','nvenc','auto'],default='cpu')
    p.add_argument('--audio',action='store_true',help='Mux original audio to AAC, timestamps normalized to zero')
    p.add_argument('--frames-dir',type=Path,help='Keep linear float32 EXR baseline; enables resume')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--preset',type=Path)
    p.add_argument('--save-preset',type=Path)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--benchmark',action='store_true')
    p.add_argument('--list-profiles',action='store_true')
    p.add_argument('--worker-job',type=Path,help=argparse.SUPPRESS)
    a=p.parse_args(argv)
    if a.worker_job:
        worker(a.worker_job); return
    if a.preset:
        cfg=json.loads(a.preset.read_text())
        allowed={'film','paper','backend','grain','halation','diffusion','exposure','seed','temporal_grain_correlation'}
        if set(cfg)-allowed: p.error('Unknown preset fields: '+str(set(cfg)-allowed))
        # Explicit flags override presets.
        for k,v in cfg.items():
            flag='--print' if k=='paper' else '--'+k.replace('_','-')
            if flag not in (argv if argv is not None else sys.argv[1:]): setattr(a,k,v)
    config={k:getattr(a,k) for k in ['film','paper','backend','grain','halation','diffusion','exposure','seed','temporal_grain_correlation']}
    if a.backend not in ('vulkan','cpu-physical'): p.error('Invalid backend')
    if not isinstance(a.seed,int) or not 0<=a.seed<=0xffffffff: p.error('seed must be uint32')
    for k in ('grain','halation','diffusion','exposure','temporal_grain_correlation'):
        if not isinstance(config[k],(int,float)) or not np.isfinite(config[k]): p.error('Invalid '+k)
    if min(a.grain,a.halation,a.diffusion)<0 or not 0<=a.temporal_grain_correlation<=1: p.error('Invalid effect amount')
    engine=Vulkan() if a.backend=='vulkan' else None
    if engine:
        stocks={'film':engine.profiles(),'print':engine.profiles(True)}
    else:
        from spektrafilm.model.stocks import FilmStocks, PrintPapers
        stocks={'film':[i.value for i in FilmStocks],'print':[i.value for i in PrintPapers]}
    if a.list_profiles:
        print(json.dumps(stocks,indent=2)); return
    if a.film not in stocks['film'] or a.paper not in stocks['print']: p.error('Unknown profile; use --list-profiles')
    if a.save_preset: a.save_preset.write_text(json.dumps(config,indent=2))
    if not a.input or not a.output: p.error('--input and --output required')
    if a.input.resolve()==a.output.resolve(): p.error('Input and output must differ')
    if a.output.exists() and not a.resume: p.error('Output exists; choose a new path')
    image_ext={'.png','.tiff','.tif','.exr'}
    still=a.input.suffix.lower() in image_ext
    sequence=a.input.is_dir()
    files=sorted(f for f in a.input.iterdir() if f.suffix.lower() in image_ext) if sequence else ([a.input] if still else [])
    if still or sequence:
        if not files: p.error('No image frames')
        sample=read_image(files[0]); h,w=sample.shape[:2]
        fps=a.fps or (1 if still else 0)
        if not fps: p.error('--fps required for frame directories')
        transfer=a.input_transfer if a.input_transfer!='auto' else ('linear' if files[0].suffix.lower()=='.exr' else 'srgb')
        meta={'frames':len(files),'fps':fps,'transfer':transfer,'shape':[h,w]}
    else:
        meta=probe(a.input)
        stream=next(s for s in meta['streams'] if s['codec_type']=='video')
        if stream.get('color_transfer') in ('smpte2084','arib-std-b67') or int(stream.get('bits_per_raw_sample') or 8)>8:
            p.error('HDR/10-bit video is not validated; convert explicitly to SDR first')
        if stream.get('pix_fmt') not in ('yuv420p','yuv422p','yuv444p','nv12','rgb24','bgr24'):
            p.error('Only validated 8-bit SDR video pixel formats are accepted')
        if any(s.get('rotation',0) for s in stream.get('side_data_list',[])):
            p.error('Rotated video requires explicit preprocessing')
        if stream.get('color_space') not in ('bt709',None,'unknown','unspecified'): p.error('Only Rec.709 primaries/matrix supported')
        if stream.get('color_primaries') not in ('bt709',None,'unknown','unspecified'): p.error('Only Rec.709 primaries supported')
        if stream.get('avg_frame_rate')!=stream.get('r_frame_rate'): p.error('Variable frame rate not supported')
        from fractions import Fraction
        fps=float(Fraction(stream['avg_frame_rate'])); w=int(stream['width']); h=int(stream['height'])
        transfer=a.input_transfer if a.input_transfer!='auto' else stream.get('color_transfer')
        if transfer not in ('bt709','srgb','linear'): p.error('Missing/unsupported transfer metadata: set --input-transfer bt709 or srgb explicitly')
        if a.audio:
            # Synchronization is only verified for streams with aligned zero start.
            starts=[float(s.get('start_time',0)) for s in meta['streams'] if s['codec_type'] in ('audio','video')]
            if any(abs(t)>0.001 for t in starts): p.error('Nonzero A/V start timestamps not supported')
    if a.output.suffix.lower()=='.exr' and not still: p.error('Single EXR output requires a still input')
    if a.output.suffix.lower() not in ('.mp4','.mov','.exr'): p.error('Output must be MP4/MOV or a still EXR')
    if a.output.suffix.lower()!='.exr' and (w%2 or h%2): p.error('4:2:0 video output requires even dimensions')
    report={'config':config,'input':str(a.input.resolve()),'input_metadata':meta,'output_transfer':'linear' if a.output.suffix.lower()=='.exr' else 'bt709', 'output_primaries':'bt709','output_matrix':'bt709','output_range':'full' if a.output.suffix.lower()=='.exr' else 'limited','fps':fps,'shape':[h,w]}
    if a.dry_run: print(json.dumps(report,indent=2)); return
    source_sig=[]
    for f in files or [a.input]:
        st=f.stat(); source_sig.append([str(f.resolve()),st.st_size,st.st_mtime_ns])
    runtime_signature={}
    if a.backend=='vulkan':
        assets=[ROOT/'build/bridge/libfilmforge_vulkan.so',*sorted((ROOT/'build/ofx-Release/shaders').glob('*.spv')),*sorted((ROOT/'build/ofx-Release').glob('*.f32'))]
    else:
        assets=[ROOT/'upstream/COMMITS.txt',ROOT/'requirements.lock']
    for asset in [Path(__file__),*assets]:
        runtime_signature[str(asset.relative_to(ROOT))]=hashlib.sha256(asset.read_bytes()).hexdigest()
    fingerprint=hashlib.sha256(json.dumps([config,source_sig,a.start_frame,transfer,w,h,fps,runtime_signature],sort_keys=True).encode()).hexdigest()
    report['runtime_signature']=runtime_signature
    if a.frames_dir:
        a.frames_dir.mkdir(parents=True,exist_ok=True)
        manifest=a.frames_dir/'manifest.json'
        if manifest.exists():
            if not a.resume or json.loads(manifest.read_text())['fingerprint']!=fingerprint: p.error('Frame cache exists or config/input changed; choose a new directory')
        elif any(a.frames_dir.iterdir()): p.error('Refusing nonempty unowned frame directory')
        manifest.write_text(json.dumps({'fingerprint':fingerprint,'report':report},indent=2))
    elif a.resume: p.error('--resume requires --frames-dir')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    decoder=None; encoder=None
    process_log=a.output.with_suffix(a.output.suffix+'.ffmpeg.log').open('w')
    if not still and not sequence:
        decoder=subprocess.Popen(['ffmpeg','-v','error','-noautorotate','-i',str(a.input),'-map','0:v:0','-vf','scale=in_color_matrix=bt709:in_range=auto:out_range=full','-pix_fmt','rgb24','-f','rawvideo','-vsync','0','pipe:1'],stdout=subprocess.PIPE,stderr=process_log)
    if a.output.suffix.lower()!='.exr':
        codec=('libx264' if a.codec=='h264' else 'libx265')
        if a.encoder in ('nvenc','auto'):
            nv='h264_nvenc' if a.codec=='h264' else 'hevc_nvenc'
            test=subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=s={w}x{h}:d=0.04','-c:v',nv,'-f','null','-'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            if test.returncode==0: codec=nv
            elif a.encoder=='nvenc': raise RuntimeError('NVENC unavailable: '+test.stderr.decode())
            else: print('NVENC unavailable; using CPU codec',file=sys.stderr)
        cmd=['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r',str(fps),'-i','pipe:0']
        if a.audio and not (still or sequence): cmd+=['-i',str(a.input),'-map','0:v:0','-map','1:a:0?','-c:a','aac','-b:a','192k']
        cmd+=['-vf','scale=in_range=full:out_range=limited:out_color_matrix=bt709','-pix_fmt','yuv420p','-c:v',codec]
        if codec=='libx265': cmd+=['-x265-params','pools=4:frame-threads=2:log-level=error']
        if codec.startswith('lib'): cmd+=['-crf','18','-preset','fast','-threads','4']
        cmd+=['-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv','-movflags','+faststart',str(a.output)]
        encoder=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=process_log)
        report['encoder']=codec
    start=time.perf_counter(); count=0; clipped=0; total=0
    try:
        while True:
            if files:
                if count==len(files): break
                frame=read_image(files[count])
            else:
                data=read_exact(decoder.stdout,w*h*3)
                if data is None: break
                frame=np.frombuffer(data,np.uint8).reshape(h,w,3).astype(np.float32)/255
            if frame.shape[:2]!=(h,w): raise ValueError('Frame shape changed')
            frame_path=a.frames_dir/f'{a.start_frame+count:08d}.exr' if a.frames_dir else None
            if frame_path and frame_path.exists() and a.resume:
                result=read_image(frame_path)
                if result.shape!=frame.shape or not np.isfinite(result).all(): raise ValueError('Invalid cached EXR')
            else:
                rgb=frame[...,:3]
                linear=bt709_decode(rgb) if transfer=='bt709' else (srgb_decode(rgb) if transfer=='srgb' else rgb)
                if frame.shape[2]==4: linear=np.concatenate([linear,frame[...,3:4]],axis=2)
                result=engine.render(linear,config,a.start_frame+count) if engine else physical(linear,config)
                if frame_path:
                    temp=frame_path.with_suffix('.partial.exr'); write_exr(temp,result); temp.replace(frame_path)
            if not np.isfinite(result).all(): raise RuntimeError('Non-finite output')
            if encoder:
                code=bt709_encode(result[...,:3]); clipped+=int(((code<0)|(code>1)).sum()); total+=code.size
                encoder.stdin.write(np.rint(np.clip(code,0,1)*255).astype(np.uint8).tobytes())
            else: write_exr(a.output,result)
            count+=1
            if count%25==0: print(f'frames={count} elapsed={time.perf_counter()-start:.2f}s',file=sys.stderr)
        if decoder and decoder.wait()!=0: raise RuntimeError('FFmpeg decoder failed; see ffmpeg log')
        if not count: raise RuntimeError('No frames decoded')
        if encoder:
            encoder.stdin.close()
            if encoder.wait()!=0: raise RuntimeError('FFmpeg encoder failed; see ffmpeg log')
    finally:
        if decoder and decoder.poll() is None: decoder.kill(); decoder.wait()
        if encoder and encoder.poll() is None: encoder.kill(); encoder.wait()
        if engine: engine.close()
        process_log.close()
    report.update(frames=count,seconds=time.perf_counter()-start,clipped_fraction=clipped/max(total,1),fingerprint=fingerprint)
    report['throughput_fps']=count/report['seconds']
    a.output.with_suffix(a.output.suffix+'.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    try: main()
    except (RuntimeError,ValueError,OSError,subprocess.SubprocessError) as e:
        print(f'filmforge-video: {e}',file=sys.stderr); sys.exit(1)
