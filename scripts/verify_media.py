#!/usr/bin/env python3
"""Exercise actual CLI decoding, lossless frames, resume and segmented rendering."""
import json
import os
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from filmforge import write_exr, read_image, probe

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
os.environ['SPEKTRAFILM_VULKAN_DEVICE_INDEX']='1'
os.environ['VK_ICD_FILENAMES']='/usr/share/vulkan/icd.d/nvidia_icd.json'
work=Path(tempfile.mkdtemp(prefix='media-test-',dir=ROOT/'examples'))
for sub in ['input','tail']: (work/sub).mkdir(exist_ok=True)
for i in range(8):
    frame=np.full((48,64,3),.18,np.float32)
    frame[10:24,(i*3)%40:(i*3)%40+12]=8
    write_exr(work/'input'/f'{i:04d}.exr',frame)
    if i>=4: write_exr(work/'tail'/f'{i:04d}.exr',frame)

def run(args,success=True,env=None):
    p=subprocess.run([str(ROOT/'bin/filmforge-video'),*args],text=True,capture_output=True,env=env)
    with (ROOT/'logs/media-tests.log').open('a') as f:
        f.write('$ filmforge-video '+' '.join(args)+'\n'+p.stdout+p.stderr+f'\nexit={p.returncode}\n')
    assert (p.returncode==0)==success
    return p

base=['--input',str(work/'input'),'--output',str(work/'full.mp4'),'--fps','25','--frames-dir',str(work/'full-frames'),'--grain','.4','--temporal-grain-correlation','.5']
run(base)
run(base+['--resume'])
run(['--input',str(work/'tail'),'--output',str(work/'tail.mp4'),'--fps','25','--frames-dir',str(work/'tail-frames'),'--grain','.4','--temporal-grain-correlation','.5','--start-frame','4'])
for i in range(4,8):
    np.testing.assert_array_equal(read_image(work/'full-frames'/f'{i:08d}.exr'),read_image(work/'tail-frames'/f'{i:08d}.exr'))
run(base+['--resume','--seed','999'],False)
run(['--input',str(work/'input'),'--output',str(work/'cpu.mp4'),'--fps','25','--backend','cpu-physical'])
bad=dict(os.environ,SPEKTRAFILM_VULKAN_DEVICE_INDEX='99999')
r=run(['--input',str(work/'input'/'0000.exr'),'--output',str(work/'bad.exr')],False,bad)
assert 'Vulkan' in r.stderr and 'device' in r.stderr
run(['--input',str(work/'input'/'0000.exr'),'--output',str(work/'hevc.mp4'),'--codec','hevc','--encoder','auto'])
assert probe(work/'hevc.mp4')['streams'][0]['codec_name']=='hevc'
run(['--input',str(work/'missing.mp4'),'--output',str(work/'missing-output.mp4')],False)
assert probe(work/'full.mp4')['streams'][0]['nb_frames']=='8'
(ROOT/'benchmarks/media-verification.json').write_text(json.dumps(dict(work_directory=str(work),lossless_exr_segment_equal=True,resume=True,config_mismatch_rejected=True,cpu_physical_video=True,invalid_vulkan_device_error=True,hevc_auto_encoder=True,missing_input_error=True),indent=2))
