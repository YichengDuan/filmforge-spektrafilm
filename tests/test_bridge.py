import json
import numpy as np
import pytest
from filmforge import Vulkan, srgb_decode, srgb_encode, bt709_encode, bt709_decode

CFG=dict(film='kodak_portra_400',paper='kodak_portra_endura',grain=.5,halation=0,diffusion=0,seed=42)


def test_transfer_roundtrip():
    x=np.linspace(0,1,1000)
    np.testing.assert_allclose(srgb_decode(srgb_encode(x)),x,atol=1e-12)
    np.testing.assert_allclose(bt709_decode(bt709_encode(x)),x,atol=6e-5)


def test_vulkan_stateless_100_frames():
    v=Vulkan()
    try:
        src=np.full((32,64,3),.18,np.float32)
        a=[v.render(src,CFG,i) for i in range(100)]
        b=[v.render(src,CFG,i) for i in range(100)]
        for x,y in zip(a,b): np.testing.assert_array_equal(x,y)
        # Revisit absolute indices in shuffled segment order.
        for i in [70,71,0,1,49,50,99]: np.testing.assert_array_equal(a[i],v.render(src,CFG,i))
        diff=np.mean(np.abs(a[0]-a[1]))
        assert diff>0, 'Animated upstream grain must actually change'
        raw=np.stack(a)
        residual=raw-raw.mean(axis=0,keepdims=True)
        corr=float(np.corrcoef(residual[:-1].ravel(),residual[1:].ravel())[0,1])
        means=raw.mean(axis=(1,2,3))
        np.save('benchmarks/temporal-reference.npy',raw,allow_pickle=False)
        report={'exact_repeat':True,'exact_segment_overlap':True,'frames':100,'mean_abs_adjacent_difference':float(diff),'texture_variance':float(residual.var()),'adjacent_correlation':corr,'frame_mean_std':float(means.std())}
        correlated=[v.render(src,{**CFG,'temporal_grain_correlation':.7},i) for i in range(20)]
        correlated=np.stack(correlated)
        # Measure spatial correlation with static mean of the deterministic color
        # removed, not temporal mean (which would remove the shared component).
        base=v.render(src,{**CFG,'grain':0},0)
        r=correlated-base
        report['rho07_spatial_adjacent_correlation']=float(np.corrcoef(r[:-1].ravel(),r[1:].ravel())[0,1])
        report['rho07_repeat']=bool(np.array_equal(correlated[5],v.render(src,{**CFG,'temporal_grain_correlation':.7},5)))
        assert report['rho07_repeat']
        assert report['rho07_spatial_adjacent_correlation']>.35
        Path=__import__('pathlib').Path
        Path('benchmarks/temporal.json').write_text(json.dumps(report,indent=2))
    finally: v.close()


def test_real_effects_and_alpha():
    v=Vulkan()
    try:
        img=np.full((64,96,4),.1,np.float32)
        img[20:35,35:50,:3]=8
        img[...,3]=.35
        cfg={**CFG,'grain':0}
        base=v.render(img,cfg)
        assert np.isfinite(base).all()
        assert np.mean(np.abs(base[...,:3]-img[...,:3]))>.01
        for effect in ['grain','halation','diffusion']:
            changed=v.render(img,{**cfg,effect:.5})
            assert np.mean(np.abs(changed[...,:3]-base[...,:3]))>1e-8,effect
            np.testing.assert_array_equal(changed[...,3],img[...,3])
        with pytest.raises(ValueError): v.render(img*np.nan,cfg)
        with pytest.raises(ValueError): v.render(-img,cfg)
    finally: v.close()
