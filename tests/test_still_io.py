import importlib.util
from pathlib import Path
import subprocess
import sys
import numpy as np
import OpenImageIO as oiio


def test_still_srgb_alpha_and_16bit_output(tmp_path):
    spec=importlib.util.spec_from_file_location('still',Path('scripts/test_still.py'))
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    rgba=np.full((16,32,4),.4,np.float32)
    rgba[...,3]=.25
    inp=tmp_path/'rgba.png'; out=tmp_path/'result.tiff'
    mod.write_image(inp,rgba,oiio.UINT8)
    np.testing.assert_allclose(mod.read_image(inp)[...,:3],102/255,atol=1/255)
    proc=subprocess.run([sys.executable,'scripts/test_still.py','--input',str(inp),'--input-space','srgb','--output',str(out)],capture_output=True,text=True)
    assert proc.returncode==0,proc.stderr
    data=mod.read_image(out)
    assert data.shape==rgba.shape
    np.testing.assert_allclose(data[...,3],64/255,atol=1/65535)
    image=oiio.ImageInput.open(str(out))
    assert image.spec().format==oiio.UINT16
    image.close()
    assert out.with_suffix('.png').exists()


def test_reject_nonfinite_and_negative(tmp_path):
    spec=importlib.util.spec_from_file_location('still',Path('scripts/test_still.py'))
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    inp=tmp_path/'negative.exr'
    mod.write_image(inp,np.full((8,8,3),-.1,np.float32))
    proc=subprocess.run([sys.executable,'scripts/test_still.py','--input',str(inp),'--input-space','linear-rec709','--output',str(tmp_path/'result.exr')],capture_output=True,text=True)
    assert proc.returncode!=0 and 'Negative' in proc.stderr
