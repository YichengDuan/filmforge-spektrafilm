#!/usr/bin/env python3
"""Execute the two video grading workflows on a separate ComfyUI test server."""
import json
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid
import argparse

root=Path(__file__).resolve().parents[1]
url='http://127.0.0.1:8189'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--workflow',action='append',choices=['Filmforge_Video_Full_Vulkan','Filmforge_Video_Fast_CUDA_LUT','Filmforge_Video_Native_CUDA'])
args=parser.parse_args()
def request(path,data=None):
    req=urllib.request.Request(url+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=90) as response: return json.load(response)

for _ in range(90):
    try: info=request('/object_info');break
    except OSError: time.sleep(.5)
else: raise RuntimeError('Isolated server unavailable')
assert 'cuda-spectral' in info['SpektrafilmPreset']['input']['required']['backend'][0]
assert 'input_transfer' in info['SpektrafilmVideoFrames']['input']['optional']
results=[]
for name in args.workflow or ('Filmforge_Video_Full_Vulkan','Filmforge_Video_Fast_CUDA_LUT','Filmforge_Video_Native_CUDA'):
    prompt=json.loads((root/f'examples/{name}.api.json').read_text())
    workflow=json.loads((root/f'examples/{name}.json').read_text())
    begin=time.perf_counter()
    queued=request('/prompt',{'prompt':prompt,'client_id':str(uuid.uuid4()),'extra_data':{'extra_pnginfo':{'workflow':workflow}}})
    assert not queued.get('node_errors'),queued
    for _ in range(600):
        history=request('/history/'+queued['prompt_id'])
        if queued['prompt_id'] in history:
            result=history[queued['prompt_id']];break
        time.sleep(.5)
    else: raise RuntimeError('Workflow timed out')
    (root/f'logs/{name}-history.json').write_text(json.dumps(result,indent=2))
    if result['status']['status_str']!='success': raise RuntimeError(f'{name} failed; inspect saved history')
    item=result['outputs']['6']['images'][0]
    file=root/'.local/comfyui-cuda-test/output'/item['subfolder']/item['filename']
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(file)]))
    durations={s['codec_type']:float(s['duration']) for s in probe['streams'] if s['codec_type'] in ('audio','video')}
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    assert int(video['nb_frames'])==250 and video['avg_frame_rate']=='25/1'
    assert 'audio' in durations and abs(durations['video']-durations['audio'])<.04
    row={'workflow':name,'success':True,'frames':250,'fps':25,'duration':durations,'wall_seconds':time.perf_counter()-begin,
         'width':int(video['width']),'height':int(video['height']),
         'gpu':'NVIDIA RTX A2000 Laptop GPU','input_transfer':'bt709','output_transfer':video.get('color_transfer'),
         'output':str(file),'prompt_id':queued['prompt_id']}
    results.append(row)
    (root/'logs/video-workflows-cuda-native.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(row),flush=True)
