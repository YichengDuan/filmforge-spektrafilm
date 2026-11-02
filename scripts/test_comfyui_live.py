#!/usr/bin/env python3
"""Validate installed nodes through the running local ComfyUI prompt API."""
import json
from pathlib import Path
import struct
import time
import urllib.parse
import urllib.request
import uuid

root=Path(__file__).resolve().parents[1]
url='http://127.0.0.1:8188'


def request(path,data=None):
    body=None if data is None else json.dumps(data).encode()
    req=urllib.request.Request(url+path,data=body,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=60) as response:
        return json.load(response)


def execute(prompt,workflow=None):
    data={'prompt':prompt,'client_id':str(uuid.uuid4())}
    if workflow: data['extra_data']={'extra_pnginfo':{'workflow':workflow}}
    queued=request('/prompt',data)
    if queued.get('node_errors'): raise RuntimeError(queued['node_errors'])
    prompt_id=queued['prompt_id']
    for _ in range(180):
        history=request('/history/'+prompt_id)
        if prompt_id in history:
            result=history[prompt_id]
            if result.get('status',{}).get('status_str')!='success': raise RuntimeError(result)
            return {'prompt_id':prompt_id,'outputs':result['outputs'],'status':result['status']}
        time.sleep(.5)
    raise RuntimeError('Live node test timed out')


for _ in range(60):
    try:
        info=request('/object_info')
        break
    except (OSError,TimeoutError): time.sleep(.5)
else: raise RuntimeError('ComfyUI server did not become ready')
names=['SpektrafilmPreset','SpektrafilmImage','SpektrafilmVideoFrames']
assert all(n in info for n in names)
assert 'vulkan' in info['SpektrafilmPreset']['input']['required']['backend'][0]
before=set(json.loads((root/'logs/comfyui-nodes-before.json').read_text()))
missing=sorted(before-set(info))
assert not missing, f'Previously available nodes disappeared: {missing}'
q=request('/queue')
assert not q['queue_running'] and not q['queue_pending'], 'Do not queue test behind user work'
preset={'film':'kodak_portra_400','print_profile':'kodak_portra_endura','backend':'vulkan','grain':.3,'halation':.2,'diffusion':.1,'seed':1234,'temporal_grain_correlation':.3}
image={
 '1':{'class_type':'EmptyImage','inputs':{'width':256,'height':192,'batch_size':2,'color':8421504}},
 '2':{'class_type':'SpektrafilmPreset','inputs':preset},
 '3':{'class_type':'SpektrafilmImage','inputs':{'images':['1',0],'preset_json':['2',0]}},
 '4':{'class_type':'SaveImage','inputs':{'images':['3',0],'filename_prefix':'filmforge_smoke/image'}}}

workflow={'last_node_id':4,'last_link_id':3,'nodes':[
 {'id':1,'type':'EmptyImage','pos':[20,40],'size':[280,180],'flags':{},'order':0,'mode':0,'inputs':[],
  'outputs':[{'name':'IMAGE','type':'IMAGE','links':[1],'slot_index':0}],
  'properties':{'Node name for S&R':'EmptyImage'},'widgets_values':[256,192,2,8421504]},
 {'id':2,'type':'SpektrafilmPreset','pos':[20,290],'size':[320,330],'flags':{},'order':1,'mode':0,'inputs':[],
  'outputs':[{'name':'preset_json','type':'STRING','links':[2],'slot_index':0}],
  'properties':{'Node name for S&R':'SpektrafilmPreset'},'widgets_values':list(preset.values())},
 {'id':3,'type':'SpektrafilmImage','pos':[410,80],'size':[310,180],'flags':{},'order':2,'mode':0,
  'inputs':[{'name':'images','type':'IMAGE','link':1},{'name':'preset_json','type':'STRING','link':2,'widget':{'name':'preset_json'}}],
  'outputs':[{'name':'IMAGE','type':'IMAGE','links':[3],'slot_index':0}],
  'properties':{'Node name for S&R':'SpektrafilmImage'},'widgets_values':['']},
 {'id':4,'type':'SaveImage','pos':[810,80],'size':[340,320],'flags':{},'order':3,'mode':0,
  'inputs':[{'name':'images','type':'IMAGE','link':3}],
  'outputs':[{'name':'images','type':'IMAGE','links':None}],
  'properties':{'Node name for S&R':'SaveImage'},'widgets_values':['filmforge_smoke/image']}],
 'links':[[1,1,0,3,0,'IMAGE'],[2,2,0,3,1,'STRING'],[3,3,0,4,0,'IMAGE']],
 'groups':[],'config':{},'extra':{'ds':{'scale':.9,'offset':[30,30]}},'version':.4}
(root/'examples/comfyui_image_workflow.json').write_text(json.dumps(workflow,indent=2))
(root/'examples/comfyui_live_image_api.json').write_text(json.dumps(image,indent=2))
image_result=execute(image,workflow)
(root/'logs/comfyui-live-image-test.json').write_text(json.dumps(image_result,indent=2))
saved=image_result['outputs']['4']['images']
assert len(saved)==2
for i,item in enumerate(saved):
    query=urllib.parse.urlencode(item)
    with urllib.request.urlopen(url+'/view?'+query,timeout=30) as response: data=response.read()
    assert data[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',data[16:24])==(256,192)
    (root/f'examples/comfyui-live-{i}.png').write_bytes(data)

video={
 '1':{'class_type':'EmptyImage','inputs':{'width':256,'height':192,'batch_size':8,'color':8421504}},
 '2':{'class_type':'SpektrafilmPreset','inputs':preset},
 '3':{'class_type':'SpektrafilmVideoFrames','inputs':{'images':['1',0],'preset_json':['2',0],'fps':25,'start_frame':100}},
 '4':{'class_type':'CreateVideo','inputs':{'images':['3',0],'fps':['3',1],'bit_depth':'auto','color_space':'sRGB','codec':'none'}},
 '5':{'class_type':'SaveVideo','inputs':{'video':['4',0],'filename_prefix':'filmforge_smoke/video','format':'mp4','format.codec':'h264'}}}
(root/'examples/comfyui_live_video_api.json').write_text(json.dumps(video,indent=2))
video_result=execute(video)
report={'registered':names,'previous_nodes_missing':missing,'backend':'vulkan','worker':'existing host Python 3.12','image_test':image_result,'video_test':video_result}
(root/'logs/comfyui-live-test.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
