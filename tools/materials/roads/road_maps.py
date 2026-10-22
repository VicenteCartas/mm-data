"""The road projects' maps without Material Maker: python tools/materials/roads/road_maps.py [--make-seamless] [name...]

Each road project (asphalt, dirt, gravel) builds its maps from sources/: pigment.png, and structure-high.png /
structure-low.png, the high and low bytes of four 16-bit fields (R height, G neighbour height, B and A unused). This is
its graph in numpy: the height quantized to 8 bits; normals from wrapped central differences of it times the relief;
roughness clamp(BaseRoughness + HeightRoughness * (.5 - h), .4, .98); occlusion exp(-CavityStrength * max(neighbour -
h, 0)). It wrote the shipped maps' bytes from the same sources (normals within one code on a few hundred texels), and
writes them into data/models/board/textures/roads, as the editor's export does. --make-seamless first makes the sources
tile (seamless.py); run it only on sources that show their tile grid. Needs numpy, scipy and Pillow.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, PngImagePlugin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import seamless  # noqa: E402

HERE = Path(__file__).resolve().parent
TEXTURES = HERE.parents[2] / 'data/models/board/textures/roads'


def fields(sources):
    high = np.asarray(Image.open(sources / 'structure-high.png').convert('RGBA')).astype(np.int64)
    low = np.asarray(Image.open(sources / 'structure-low.png').convert('RGBA')).astype(np.int64)
    return (high * 256 + low) / 65535.0


def encode(value):
    """The graph's PNG8 encoder puts a value at its code's bin centre; the export writes that code."""
    centre = np.clip((np.round(np.clip(value, 0, 1) * 255) + .5) / 255, 0, 1)
    return np.clip(np.floor(centre * 255), 0, 255).astype(np.uint8)


def maps(project):
    p = next(n['parameters'] for n in json.loads(project.read_text())['nodes'] if n['name'] == 'SurfaceResponse')
    sources = project.parent / 'sources'
    f = fields(sources)
    height = np.round(f[..., 0] * 255) / 255
    relief = np.round(p['ReliefMetres'] / (p['RepeatMetres'] * .1) * 255) / 255
    size = height.shape[1]
    du = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * (size / 2)
    dv = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * (size / 2)
    n = np.stack([-.1 * relief * du, -.1 * relief * dv, np.ones_like(du)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    engine = n * (127 / 255) + 128 / 255
    rough = np.clip(p['BaseRoughness'] + (.5 - height) * p['HeightRoughness'], .4, .98)
    ao = np.exp(-p['CavityStrength'] * np.maximum(f[..., 1] - height, 0))
    albedo = np.asarray(Image.open(sources / 'pigment.png').convert('RGB'))
    return {
        'albedo': np.concatenate([albedo, np.full(albedo.shape[:2] + (1,), 255, np.uint8)], -1),
        # Godot's green runs up the image: the export writes the engine code's complement.
        'normal': np.stack([encode(engine[..., 0]), 255 - encode(engine[..., 1]), encode(engine[..., 2])], -1),
        'heightmap': encode(height),
        'orm': np.stack([encode(ao), encode(rough), np.zeros(height.shape, np.uint8)], -1),
    }


def make_seamless(sources):
    pigment = np.asarray(Image.open(sources / 'pigment.png').convert('RGB')) / 255.0
    stack = np.concatenate([pigment, fields(sources)], -1)
    spread = stack.reshape(-1, stack.shape[-1]).var(0) + 1e-9
    # Where the cut runs follows what shows: pigment, height (twice: normals, roughness, occlusion) and neighbour.
    out = np.clip(seamless.seamless(stack, np.array([1, 1, 1, 2, 1, 0, 0]) / spread), 0, 1)
    Image.fromarray(np.round(out[..., :3] * 255).astype(np.uint8), 'RGB').save(sources / 'pigment.png')
    codes = np.round(out[..., 3:] * 65535).astype(np.int64)
    Image.fromarray((codes // 256).astype(np.uint8), 'RGBA').save(sources / 'structure-high.png')
    Image.fromarray((codes % 256).astype(np.uint8), 'RGBA').save(sources / 'structure-low.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--make-seamless', action='store_true')
    parser.add_argument('names', nargs='*', default=['asphalt', 'dirt', 'gravel'])
    args = parser.parse_args()
    for name in args.names:
        project = HERE / name / f'{name}.ptex'
        if args.make_seamless:
            make_seamless(project.parent / 'sources')
        written = maps(project)
        srgb = PngImagePlugin.PngInfo()
        srgb.add(b'sRGB', b'\x00')  # as the export writes its albedo
        Image.fromarray(written['albedo'], 'RGBA').save(TEXTURES / f'{name}_albedo.png', pnginfo=srgb)
        Image.fromarray(written['normal'], 'RGB').save(TEXTURES / f'{name}_normal.png')
        Image.fromarray(written['orm'], 'RGB').save(TEXTURES / f'{name}_orm.png')
        Image.fromarray(written['heightmap'], 'L').save(TEXTURES / f'{name}_heightmap.png')
        for kind, image in written.items():
            edge, inner = seamless.wrap_report(image)
            print(f'{name} {kind}: across the tile edge {edge:.1f}, between neighbours {inner:.1f}')


if __name__ == '__main__':
    main()
