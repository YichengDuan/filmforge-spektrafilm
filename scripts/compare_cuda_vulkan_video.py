#!/usr/bin/env python3
"""Compare complete CUDA/Vulkan MP4 processing with identical CPU encoders."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--fixture-dir',type=Path,default=ROOT/'benchmarks')
    args=p.parse_args()
    if args.output_dir.exists():p.error('Choose a new directory to preserve previous results')
    args.output_dir.mkdir(parents=True)
    rows=[]
    for height in (720,1080):
        for backend in ('vulkan','cuda-spectral'):
            output=args.output_dir/f'{backend}-{height}p.mp4'
            command=[sys.executable,'-B',str(ROOT/'src/filmforge.py'),
                     '--input',str(args.fixture_dir/f'synthetic-{height}p.mp4'),'--output',str(output),
                     '--backend',backend,'--film','kodak_portra_400','--print','kodak_portra_endura',
                     '--grain','.35','--halation','.3','--diffusion','.1','--seed','1234','--audio','--encoder','cpu']
            begin=time.perf_counter()
            with (args.output_dir/f'{backend}-{height}p.log').open('w') as log:
                result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:raise RuntimeError(f'{backend} {height}p failed; inspect the log')
            report=json.loads(output.with_suffix('.mp4.json').read_text())
            metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(output)]))
            video=next(s for s in metadata['streams'] if s['codec_type']=='video')
            audio=next(s for s in metadata['streams'] if s['codec_type']=='audio')
            assert int(video['nb_frames'])==250 and video['avg_frame_rate']=='25/1'
            assert abs(float(video['duration'])-float(audio['duration']))<1/25
            for key in ('color_space','color_transfer','color_primaries'):assert video[key]=='bt709'
            assert video['color_range']=='tv'
            row={'backend':backend,'height':height,'frames':report['frames'],'seconds':report['seconds'],
                 'fps':report['throughput_fps'],'whole_command_seconds':time.perf_counter()-begin,
                 'encoder':report['encoder'],'video_seconds':float(video['duration']),
                 'audio_seconds':float(audio['duration']),'transfer':video['color_transfer'],
                 'matrix':video['color_space'],'primaries':video['color_primaries'],'range':video['color_range'],
                 'config':report['config']}
            rows.append(row);(args.output_dir/'results.json').write_text(json.dumps(rows,indent=2));print(json.dumps(row),flush=True)


if __name__=='__main__':main()
