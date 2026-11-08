"""Run with python tools/calibrate_impostors.py [--megamek PATH] [NAME...], after prepare_tree_lods.py's impostors.

Fits each plant impostor to the far mesh it replaces where the game switches to it (TreeLod's smallest threshold,
24 pixels), as the game draws them: its alpha cutoff, so that it covers what the far mesh covers, and its colour, so
that it is as bright and of the same hue on average over the views and hours measured. The frames hold the far mesh's
unlit colour, normals and depth, but at that size the mesh's detail (its leaves' maps, leaf edges fading over the
ground) shades it differently. The colour is a linear RGB factor per atlas, kept in the impostor material's extras
(`mmImpostorTint`, by atlas name; prepare_tree_lods.py bakes it into the atlas) and applied here to the atlas itself.

The game measures both: megamek's GpuImpostorCalibrationSmokeTest, run by Gradle in a megamek checkout with the GPU
board (by default the one beside mm-data, whose build stages this mm-data's models) with
-Dmegamek.gpu.impostorCalibration. Each run starts from the present files, so a second run refines the colour. NAMEs
(vegetation/pine, mars/fan-folded...) limit the plants it writes; a winter form kept in its plant's file
(vegetation/pine-snow) has its own colour. The same test without the property checks the result.
"""
import argparse
import json
import os
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BOARD = ROOT / 'data/models/board'
IMPOSTORS = BOARD / 'textures/vegetation/impostors'
TEST = 'megamek.client.ui.clientGUI.boardview.gpu.GpuImpostorCalibrationSmokeTest'


def edit_impostor(path, change):
    """`change` applied to the GLB's impostor material (glTF JSON); its other bytes stay as they are."""
    data = path.read_bytes()
    length = struct.unpack('<I', data[12:16])[0]
    document = json.loads(data[20:20 + length])
    for material in document['materials']:
        if material.get('name') == 'impostor':
            change(material)
    text = json.dumps(document, separators=(',', ':')).encode('utf-8')
    text += b' ' * (-len(text) % 4)
    body = struct.pack('<I', len(text)) + b'JSON' + text + data[20 + length:]
    path.write_bytes(data[:8] + struct.pack('<I', 12 + len(body)) + body)


def set_cutoff(name, cutoff):
    edit_impostor(BOARD / f'{name}.glb', lambda material: material.update(alphaCutoff=cutoff))


def set_colour(name, ratio):
    """A plant's impostor colour times `ratio`: its atlas's texels and its tint in the file that holds it."""
    atlas = name.rsplit('/', 1)[-1]
    path = BOARD / f'{name}.glb'
    if not path.exists():
        # A winter form kept in its plant's file.
        path = BOARD / f'{name.removesuffix("-snow")}.glb'

    def scale(material):
        tints = material.setdefault('extras', {}).setdefault('mmImpostorTint', {})
        tints[atlas] = [round(old * factor, 4) for old, factor in zip(tints.get(atlas, (1, 1, 1)), ratio)]
    edit_impostor(path, scale)
    image = Image.open(IMPOSTORS / f'{atlas}.png').convert('RGBA')
    values = numpy.asarray(image).astype(numpy.float64) / 255
    linear = numpy.where(values[..., :3] <= .04045, values[..., :3] / 12.92, ((values[..., :3] + .055) / 1.055) ** 2.4)
    linear = numpy.clip(linear * numpy.asarray(ratio), 0, 1)
    encoded = numpy.where(linear <= .0031308, linear * 12.92, 1.055 * linear ** (1 / 2.4) - .055)
    values[..., :3] = encoded
    Image.fromarray(numpy.round(values * 255).astype(numpy.uint8), 'RGBA').save(IMPOSTORS / f'{atlas}.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[1])
    parser.add_argument('--megamek', type=Path, default=ROOT.parent / 'megamek', help='the megamek checkout')
    parser.add_argument('names', nargs='*')
    arguments = parser.parse_args()
    gradle = arguments.megamek / ('gradlew.bat' if os.name == 'nt' else 'gradlew')
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / 'calibration.json'
        subprocess.run([str(gradle), ':megamek:gpuBoardSmoke', '--tests', TEST, f'-Dmegamek.gpu.impostorCalibration={target}'],
                       cwd=arguments.megamek, check=True)
        fitted = json.loads(target.read_text())
    wanted = lambda name: not arguments.names or name in arguments.names
    for name, cutoff in fitted['cutoffs'].items():
        if wanted(name):
            set_cutoff(name, cutoff)
    for name, ratio in fitted['colours'].items():
        if wanted(name):
            set_colour(name, ratio)
            print(name, fitted['cutoffs'].get(name, ''), ratio)


if __name__ == '__main__':
    main()
