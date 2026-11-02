#!/usr/bin/env python3
"""Render the existing 10-second SDR fixtures with native CUDA and verify A/V."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
rows=[]
for height in (720,1080):
    output=ROOT/f'benchmarks/cuda-native-full-{height}p.mp4'
    if output.exists():raise SystemExit(f'Preserve existing result: {output}')
    source=ROOT/f'benchmarks/synthetic-{height}p.mp4'
    command=[sys.executable,'-B',str(ROOT/'src/filmforge.py'),'--input',str(source),'--output',str(output),
             '--backend','cuda-spectral','--grain','.35','--halation','.3','--diffusion','.1',
             '--film','kodak_portra_400','--print','kodak_portra_endura','--audio','--encoder','cpu']
    begin=time.perf_counter()
    with (ROOT/f'logs/cuda-native-full-{height}p.log').open('w') as log:
        result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError(f'CUDA {height}p failed; inspect log')
    render=json.loads(output.with_suffix('.mp4.json').read_text())
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(output)]))
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
    assert int(video['nb_frames'])==250 and video['avg_frame_rate']=='25/1'
    assert abs(float(video['duration'])-float(audio['duration']))<1/25
    assert video['color_transfer']=='bt709' and video['color_primaries']=='bt709' and video['color_space']=='bt709' and video['color_range']=='tv'
    rows.append(dict(height=height,backend='cuda-spectral',frames=render['frames'],seconds=render['seconds'],
                     fps=render['throughput_fps'],wall_seconds=time.perf_counter()-begin,
                     encoder=render['encoder'],video_seconds=float(video['duration']),audio_seconds=float(audio['duration']),
                     output_transfer=video['color_transfer'],config=render['config']))
    (ROOT/'benchmarks/cuda-native-video.json').write_text(json.dumps(rows,indent=2))
    print(json.dumps(rows[-1]),flush=True)
