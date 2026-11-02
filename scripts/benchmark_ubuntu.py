#!/usr/bin/env python3
"""Measured end-to-end benchmarks. No generated performance estimates."""
import json
import os
import subprocess
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
OUT=ROOT/'benchmarks'


def run_measured(cmd,name):
    peak_rss=0; peak_gpu={}; baseline={}
    def gpu():
        r=subprocess.run(['nvidia-smi','--query-gpu=index,name,memory.used','--format=csv,noheader,nounits'],text=True,capture_output=True)
        values={}
        if r.returncode==0:
            for row in r.stdout.strip().splitlines():
                idx,model,memory=[s.strip() for s in row.split(',')]
                values[idx]={'name':model,'used_mib':float(memory)}
        return values
    baseline=gpu()
    begin=time.perf_counter()
    with (ROOT/'logs'/f'{name}.log').open('w') as log:
        proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
        while proc.poll() is None:
            try:
                status=Path(f'/proc/{proc.pid}/status').read_text()
                for line in status.splitlines():
                    if line.startswith('VmHWM:'): peak_rss=max(peak_rss,int(line.split()[1]))
            except FileNotFoundError: pass
            for idx,info in gpu().items():
                peak_gpu[idx]=max(peak_gpu.get(idx,0),info['used_mib'])
            time.sleep(.2)
    result={'command':cmd,'exit_code':proc.returncode,'wall_seconds':time.perf_counter()-begin,
            'parent_peak_rss_kib':peak_rss,'gpu_total_baseline':baseline,'gpu_total_peak_mib':peak_gpu,
            'memory_note':'nvidia-smi sampled total-device usage at 0.2s, includes desktop/other processes; RSS is Python parent, not codec children'}
    if proc.returncode: raise RuntimeError(f'{name} failed: logs/{name}.log')
    (OUT/f'{name}.metrics.json').write_text(json.dumps(result,indent=2))
    return result


def main():
    os.environ['VK_ICD_FILENAMES']='/usr/share/vulkan/icd.d/nvidia_icd.json'
    # vulkaninfo under this ICD enumerates A2000=0, RTX3070Ti=1 on this host.
    os.environ['SPEKTRAFILM_VULKAN_DEVICE_INDEX']='1'
    rows=[]
    for w,h in [(1280,720),(1920,1080)]:
        source=OUT/f'synthetic-{h}p.mp4'
        if not source.exists():
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'testsrc2=size={w}x{h}:rate=25:duration=10',
                '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=10',
                '-vf','drawbox=x=10:y=10:w=180:h=90:color=0xc09078:t=fill,drawbox=x=200:y=10:w=120:h=90:color=0x080808:t=fill,drawbox=x=330:y=10:w=120:h=90:color=white:t=fill',
                '-c:v','libx264','-threads','4','-preset','fast','-crf','18','-pix_fmt','yuv420p',
                '-c:a','aac','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',str(source)],check=True)
        target=OUT/f'rendered-{h}p.mp4'
        if target.exists():
            raise RuntimeError(f'Preserve prior result: {target} exists')
        command=[str(ROOT/'bin/filmforge-video'),'--input',str(source),'--output',str(target),
                 '--grain','.35','--halation','.3','--diffusion','.1','--audio','--benchmark']
        metrics=run_measured(command,f'video-{h}p')
        report=json.loads(target.with_suffix('.mp4.json').read_text())
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(target)]))
        target.with_suffix('.ffprobe.json').write_text(json.dumps(probe,indent=2))
        durations={s['codec_type']:float(s['duration']) for s in probe['streams'] if s['codec_type'] in ('video','audio')}
        assert report['frames']==250
        assert abs(durations['video']-durations['audio'])<=1/25
        assert all(s.get('color_transfer')=='bt709' for s in probe['streams'] if s['codec_type']=='video')
        rows.append({'height':h,'report':report,'metrics':metrics,'durations':durations})
    (OUT/'video-results.json').write_text(json.dumps(rows,indent=2))


if __name__=='__main__': main()
