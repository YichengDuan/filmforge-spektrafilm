#!/usr/bin/env python3
"""Clone pinned sources. Never reset or change an existing checkout."""
import json
import subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for name,spec in json.loads((root/'upstream/lock.json').read_text()).items():
    path=root/'upstream'/name
    if not path.exists():
        subprocess.run(['git','clone','--no-checkout',spec['url'],str(path)],check=True)
        subprocess.run(['git','-C',str(path),'checkout','--detach',spec['sha']],check=True)
    head=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
    if head!=spec['sha']:
        raise SystemExit(f'{name}: expected {spec["sha"]}, found {head}; existing tree left unchanged')
    if subprocess.check_output(['git','-C',str(path),'status','--porcelain'],text=True):
        raise SystemExit(f'{name}: local modifications exist; inspect them before rebuilding')
    print(name,head)
