#!/usr/bin/env python3
"""Run the checked-out Python physical simulator; explicit transport semantics."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
import OpenImageIO as oiio
from PIL import Image
from spektrafilm import init_params, digest_params, Simulator


def read_image(path):
    config = oiio.ImageSpec()
    config.attribute('oiio:UnassociatedAlpha', 1)
    inp = oiio.ImageInput.open(str(path), config)
    if not inp:
        raise ValueError(oiio.geterror())
    try:
        data = inp.read_image(format=oiio.FLOAT)
    finally:
        inp.close()
    if data.ndim != 3 or data.shape[2] not in (3, 4):
        raise ValueError('Expected RGB or RGBA image')
    if not np.isfinite(data).all():
        raise ValueError('NaN/Inf input rejected')
    return data


def write_image(path, data, pixel_type=oiio.FLOAT):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = oiio.ImageOutput.create(str(path))
    if not out:
        raise RuntimeError(oiio.geterror())
    try:
        spec = oiio.ImageSpec(data.shape[1], data.shape[0], data.shape[2], pixel_type)
        spec.attribute('oiio:ColorSpace', 'sRGB')
        spec.attribute('oiio:UnassociatedAlpha', 1)
        if not out.open(str(path), spec) or not out.write_image(np.asarray(data, np.float32)):
            raise RuntimeError(out.geterror())
    finally:
        out.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', type=Path, help='Absent: synthetic linear Rec.709 HDR ramp')
    p.add_argument('--input-space', choices=['srgb', 'linear-rec709'], required=True)
    p.add_argument('--film', default='kodak_portra_400')
    p.add_argument('--print', dest='paper', default='kodak_portra_endura')
    p.add_argument('--output', type=Path, default=Path('examples/still.tiff'))
    p.add_argument('--spatial', action='store_true', help='Enable upstream spatial effects; stochastic effects stay off')
    args = p.parse_args()
    if args.output.suffix.lower() not in ('.tif', '.tiff', '.exr'):
        p.error('Output must be 16-bit TIFF or float EXR')
    if args.input:
        data = read_image(args.input)
    else:
        if args.input_space != 'linear-rec709':
            p.error('Synthetic test is scene-linear: select linear-rec709')
        ramp = np.geomspace(1e-4, 16, 256).astype(np.float32)
        data = np.broadcast_to(ramp[None, :, None], (64, 256, 3)).copy()
        data[24:40, 64:96] *= [1, .45, .22]
    rgb = data[..., :3]
    if np.any(rgb < 0):
        p.error('Negative RGB rejected; no silent clamp of spectral exposure input')
    if args.input_space == 'srgb' and np.any(rgb > 1):
        p.error('sRGB input outside [0,1]; use explicit linear-rec709 for scene values')
    params = init_params(args.film, args.paper)
    params.io.input_color_space = 'sRGB'
    params.io.input_cctf_decoding = args.input_space == 'srgb'
    params.io.output_color_space = 'sRGB'
    params.io.output_cctf_encoding = True
    params.io.crop = False
    params.io.upscale_factor = 1
    params.camera.auto_exposure = False
    params.debug.deactivate_spatial_effects = not args.spatial
    params.debug.deactivate_stochastic_effects = True
    sim = Simulator(digest_params(params))
    start = time.perf_counter()
    result = sim.process(rgb)
    elapsed = time.perf_counter() - start
    if not np.isfinite(result).all():
        raise RuntimeError('Non-finite simulator output')
    if data.shape[2] == 4:
        result = np.concatenate([result, data[..., 3:4]], axis=2)
    write_image(args.output, result, oiio.FLOAT if args.output.suffix == '.exr' else oiio.UINT16)
    preview = args.output.with_suffix('.png')
    Image.fromarray(np.rint(np.clip(result, 0, 1)*255).astype(np.uint8)).save(preview)
    report = dict(film=args.film, paper=args.paper, input_space=args.input_space,
                  output_space='sRGB encoded; TIFF16 or EXR float', seconds=elapsed,
                  timings=sim.get_timings(), minimum=float(result.min()), maximum=float(result.max()),
                  alpha='straight, preserved without simulation', spatial=args.spatial,
                  stochastic=False, shape=list(result.shape))
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
