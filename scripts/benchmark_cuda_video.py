#!/usr/bin/env python3
"""Compare end-to-end color-only video processing with unchanged CPU encoding."""
import json
from pathlib import Path
import subprocess
import sys
import time

root=Path(__file__).resolve().parents[1]
rows=[]
for h in (720,1080):
    for backend in ('vulkan','cuda-lut'):
        name=f'a2000-{backend}-{h}p'
        output=root/'benchmarks'/(name+'.mp4')
        if output.exists(): raise SystemExit(f'Preserve prior output: {output}')
        command=[sys.executable,'-B',str(root/'src/filmforge.py'),'--input',str(root/f'benchmarks/synthetic-{h}p.mp4'),
                 '--output',str(output),'--backend',backend,'--audio']
        begin=time.perf_counter()
        with (root/'logs'/(name+'.log')).open('w') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode: raise RuntimeError(f'{name} failed; inspect logs/{name}.log')
        report=json.loads(output.with_suffix('.mp4.json').read_text())
        assert report['frames']==250
        metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(output)]))
        durations={s['codec_type']:float(s['duration']) for s in metadata['streams'] if s['codec_type'] in ('audio','video')}
        assert abs(durations['audio']-durations['video'])<1/25
        row={'height':h,'backend':backend,'wall_seconds':time.perf_counter()-begin,
             'seconds':report['seconds'],'fps':report['throughput_fps'],'frames':report['frames'],
             'encoder':report['encoder'],'durations':durations,'config':report['config']}
        rows.append(row)
        (root/'benchmarks/cuda-video-a2000.json').write_text(json.dumps(rows,indent=2))
        print(json.dumps(row),flush=True)
