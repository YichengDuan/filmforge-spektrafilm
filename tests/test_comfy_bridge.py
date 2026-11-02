import importlib.util
from pathlib import Path
import json
import numpy as np
import pytest

def module():
    path=Path('comfyui/ComfyUI-Spektrafilm/__init__.py')
    spec=importlib.util.spec_from_file_location('isolated_nodes',path)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_node_subprocess_roundtrip():
    mod=module()
    assert len(mod.NODE_CLASS_MAPPINGS)==3
    cfg=dict(film='kodak_portra_400',paper='kodak_portra_endura',backend='vulkan',grain=.35,
             halation=.1,diffusion=0,seed=1234,temporal_grain_correlation=.3)
    src=np.full((3,32,64,3),.4,np.float32)
    result=mod.process_numpy(src,json.dumps(cfg),45)
    again=mod.process_numpy(src,json.dumps(cfg),45)
    assert result.shape==src.shape and np.isfinite(result).all()
    np.testing.assert_array_equal(result,again)
    tail=mod.process_numpy(src[1:],json.dumps(cfg),46)
    np.testing.assert_array_equal(result[1:],tail)
    with pytest.raises(ValueError): mod.process_numpy(src*np.nan,cfg)
    assert 'film' in mod.SpektrafilmPreset.INPUT_TYPES()['required']
