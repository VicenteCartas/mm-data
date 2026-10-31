"""Sources for a plant material project from a photographic study (needs numpy, scipy and Pillow).

    python tools/materials/plant_sources.py cutout <study.png> tools/materials/<folder>/<name>/sources [--flip]
    python tools/materials/plant_sources.py bark <study.png> tools/materials/<folder>/<name>/sources

`cutout`: the study shows the plant part on a flat magenta (#FF00FF) background. It is keyed out, the magenta spill
removed, the part fitted into 512 px inside a transparent margin with its base just above the bottom edge's centre
(`--flip` turns a study whose base is at the top, such as hanging strands) and its colour bled past the edges for
mipmaps. Writes <name>.png and the height fields of a project cloned from vegetation/conifer-cutout: R height (edge
falloff plus brightness), G its broad neighbourhood, B brightness, A green tissue.
`bark`: the study fills the frame. The broad light is flattened, the tile made seamless (seamless.py) and the pigment
brought to the light neutral grey the models tint with their vertex colours. Writes pigment.png and the fields of a
project cloned from vegetation/bark: R and B height, G its one-texel neighbourhood, A one.
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seamless import seamless  # noqa: E402

SIZE = 512
LUMA = np.array([.2126, .7152, .0722])


def fields(stack, out):
    """Write H x W x 4 fields in [0, 1] as the high and low bytes of 16-bit codes."""
    codes = np.clip(np.round(stack * 65535), 0, 65535).astype(np.int64)
    Image.fromarray((codes // 256).astype(np.uint8), 'RGBA').save(out / 'structure-high.png')
    Image.fromarray((codes % 256).astype(np.uint8), 'RGBA').save(out / 'structure-low.png')


def cutout(study, out, flip):
    rgb = np.asarray(Image.open(study).convert('RGB'), float) / 255
    if flip:
        rgb = rgb[::-1, ::-1]
    # Magenta is high red and blue over low green; plants, bark and petals are not.
    magenta = np.minimum(rgb[..., 0], rgb[..., 2]) - rgb[..., 1]
    alpha = np.clip((.42 - magenta) / .3, 0, 1)
    # Spill raises red and blue together above green; browns, greys and whites keep one of them at or below it.
    excess = np.clip(magenta, 0, None)[..., None] * [1, 0, 1]
    rgb = rgb - excess
    # Bleed the part's colour outward, so neither the resampling nor mipmaps fetch the background.
    _, (iy, ix) = distance_transform_edt(alpha < .5, return_indices=True)
    rgb = np.where((alpha < .5)[..., None], rgb[iy, ix], rgb)
    rows, cols = np.nonzero(alpha > .5)
    top, bottom, left, right = rows.min(), rows.max(), cols.min(), cols.max()
    # Fit the part inside a transparent margin, so no card shows a hard edge, its base centred just above the bottom
    # edge (where the models' cards start, BASE_V in build_trees.py).
    centre = (left + right) / 2
    side = max((bottom - top + 1) / .95, (right - left + 1) / .94)
    base = bottom + 1 + .015 * side
    box = (centre - side / 2, base - side, centre + side / 2, base)
    image = Image.fromarray(np.uint8(np.dstack([rgb.clip(0, 1), alpha]) * 255 + .5), 'RGBA')
    part = np.asarray(image.transform((SIZE, SIZE), Image.EXTENT, box, Image.BICUBIC), float) / 255
    rgb, alpha = part[..., :3], part[..., 3]
    _, (iy, ix) = distance_transform_edt(alpha < .5, return_indices=True)
    rgb = np.where((alpha < .5)[..., None], rgb[iy, ix], rgb)
    name = Path(out).parent.name
    Image.fromarray(np.uint8(np.dstack([rgb, alpha]).clip(0, 1) * 255 + .5), 'RGBA').save(out / f'{name}.png')
    luma = (rgb * LUMA).sum(-1)
    bright = np.clip(luma / max(np.percentile(luma[alpha > .5], 99), 1e-3), 0, 1)
    height = np.clip(.3 * gaussian_filter(alpha, 2) + .3 * bright * alpha + .26, 0, 1)
    green = rgb[..., 1] - .5 * (rgb[..., 0] + rgb[..., 2])
    tissue = np.clip(green / max(np.percentile(green[alpha > .5], 99), 1e-3), 0, 1)
    fields(np.dstack([height, gaussian_filter(height, 10), bright, tissue]), out)


def bark(study, out):
    rgb = np.asarray(Image.open(study).convert('RGB').resize((SIZE, SIZE), Image.LANCZOS), float) / 255
    # Flatten the broad light; keep the wood's own streaks and checks.
    broad = gaussian_filter((rgb * LUMA).sum(-1), SIZE / 6, mode='reflect')
    rgb = rgb * (broad.mean() / broad)[..., None]
    luma = (rgb * LUMA).sum(-1)
    height = luma - gaussian_filter(luma, 24, mode='reflect')
    height = np.clip(.5 + height / (4 * height.std()), 0, 1)
    tiled = seamless(np.dstack([rgb, height]), [1, 1, 1, 2])
    rgb, height = tiled[..., :3], tiled[..., 3]
    # A light neutral grey under the models' vertex tints, its own hue kept faint.
    luma = (rgb * LUMA).sum(-1)
    rgb = luma[..., None] + .35 * (rgb - luma[..., None])
    rgb *= .7 / luma.mean()
    Image.fromarray(np.uint8(np.dstack([rgb.clip(0, 1), np.ones(luma.shape)]) * 255 + .5), 'RGBA').save(
        out / 'pigment.png')
    fields(np.dstack([height, gaussian_filter(height, 1, mode='wrap'), height, np.ones(height.shape)]), out)


if __name__ == '__main__':
    kind, study, target = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    target.mkdir(parents=True, exist_ok=True)
    cutout(study, target, '--flip' in sys.argv) if kind == 'cutout' else bark(study, target)
