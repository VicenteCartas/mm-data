"""Seamless 512 px sources (pigment.png, structure-high.png, structure-low.png) for a terrain surface, from a study.

    python tools/materials/terrain_sources.py <study.png> tools/materials/terrain/surfaces/<name>/sources [near wide]

Needs numpy, scipy and Pillow. The study is a top-down photograph in flat light, about the surface's repeat across.
Its broad light is flattened, the height estimated from its structure (luminance detail, speckle median-filtered),
both made to tile (seamless.py) and stored as a cloned terrain/surfaces project reads them: the pigment, and the
16-bit structure fields split into high and low bytes, R the height, G and B the height blurred by `near` and `wide`
texels (default 1.25 and 5; snow uses 2.5 and 13).
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, median_filter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seamless import seamless  # noqa: E402

SIZE = 512
LUMA = np.array([.2126, .7152, .0722])


def sources(study, out, near=1.25, wide=5.0):
    image = Image.open(study).convert('RGB')
    side = min(image.size)
    image = image.crop(((image.width - side) // 2, (image.height - side) // 2,
                        (image.width + side) // 2, (image.height + side) // 2))
    rgb = np.asarray(image.resize((SIZE, SIZE), Image.LANCZOS), float) / 255
    # The material's own shading comes from the game's lighting: flatten the study's broad light.
    broad = gaussian_filter((rgb * LUMA).sum(-1), SIZE / 6, mode='reflect')
    rgb = np.clip(rgb * (broad.mean() / broad)[..., None], 0, 1)
    luma = median_filter((rgb * LUMA).sum(-1), 3)
    height = luma - gaussian_filter(luma, 24, mode='reflect')
    height = np.clip(.5 + height / (4 * height.std()), 0, 1)
    tiled = seamless(np.dstack([rgb, height]), [1, 1, 1, 2])
    rgb, height = np.clip(tiled[..., :3], 0, 1), np.clip(tiled[..., 3], 0, 1)
    out.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.uint8(rgb * 255 + .5), 'RGB').save(out / 'pigment.png')
    fields = np.dstack([height, gaussian_filter(height, near, mode='wrap'), gaussian_filter(height, wide, mode='wrap')])
    codes = np.uint32(np.clip(fields, 0, 1) * 65535 + .5)
    Image.fromarray((codes // 256).astype(np.uint8), 'RGB').save(out / 'structure-high.png')
    Image.fromarray((codes % 256).astype(np.uint8), 'RGB').save(out / 'structure-low.png')


if __name__ == '__main__':
    blurs = [float(value) for value in sys.argv[3:5]]
    sources(Path(sys.argv[1]), Path(sys.argv[2]), *blurs)
