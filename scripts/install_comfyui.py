#!/usr/bin/env python3
"""Install only the node package; keep all rendering dependencies separate."""
import argparse
import datetime
import json
from pathlib import Path
import shutil

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--comfy-root',type=Path,required=True,help='ComfyUI source containing main.py')
p.add_argument('--device',type=int,help='Vulkan device index (not CUDA index)')
p.add_argument('--icd',help='Vulkan ICD manifest for the render subprocess only')
p.add_argument('--host-python',type=Path,help='Use an existing host interpreter for rendering without installing packages')
p.add_argument('--cuda-device',type=int,help='Physical CUDA index for rendering; enables CUDA LUT and the native spectral backend when built')
a=p.parse_args()
runtime=Path(__file__).resolve().parents[1]
host=a.comfy_root.resolve()
if not (host/'main.py').is_file(): p.error('ComfyUI main.py missing')
if not (runtime/'build/bridge/libfilmforge_vulkan.so').is_file(): p.error('Build Vulkan bridge first')
destination=host/'custom_nodes/ComfyUI-Spektrafilm'
backup=None
if destination.exists():
    backup=runtime/'.local/comfyui-backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(destination,backup)
destination.mkdir(parents=True,exist_ok=True)
shutil.copy2(runtime/'comfyui/ComfyUI-Spektrafilm/__init__.py',destination/'__init__.py')
for name in ('LICENSE','LICENSES.md','ACKNOWLEDGEMENTS.md'):
    shutil.copy2(runtime/name,destination/name)
config={'runtime_root':str(runtime)}
if a.device is not None: config['vulkan_device_index']=a.device
if a.icd: config['vulkan_icd']=a.icd
if a.host_python:
    if not a.host_python.is_file(): p.error('Host Python executable missing')
    config['python_executable']=str(a.host_python.absolute())
    config['backends']=['vulkan']
if a.cuda_device is not None:
    config['cuda_visible_devices']=a.cuda_device
    config['backends']=['vulkan','cuda-lut']
    if (runtime/'build/cuda-spectral/libfilmforge_cuda_spectral.so').is_file():
        config['backends'].insert(1,'cuda-spectral')
(destination/'filmforge.local.json').write_text(json.dumps(config,indent=2))
report={'installed':str(destination),'runtime_root':str(runtime),'backup':str(backup) if backup else None,'host_dependencies_modified':False,'startup_script_modified':False}
(runtime/'logs/comfyui-install.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
