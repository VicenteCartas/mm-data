"""Run with python tools/calibrate_impostors.py [--megamek PATH] [NAME...], after prepare_tree_lods.py's impostors.

Fits each plant impostor to the far mesh it replaces where the game switches to it (TreeLod's smallest threshold,
24 pixels), as the game draws them, for each row of frames (each height the impostor is seen from): its coverage, so
that it covers what the far mesh covers, and its colour, so that it is as bright and of the same hue on average over
the hours measured. The frames hold the far mesh's unlit colour, normals and depth, but at that size the mesh's detail
(its leaves' maps, its sub-pixel parts) shades and covers it somewhat differently, more so from some heights.

Each file's impostor material gets the alpha cutoff that fits its impostors over all rows; each atlas row, a linear RGB
factor on its pigment and an exponent on its coverage that moves the cutoff to where that row needs it. They are kept in
the impostor material's extras (`mmImpostorTint`: by atlas name, per row [r, g, b, exponent]; prepare_tree_lods.py bakes
them into a new atlas) and applied here to the atlas itself. A winter form kept in its plant's file (vegetation/pine-snow)
has rows of its own.

The game measures both: megamek's GpuImpostorCalibrationSmokeTest, run by Gradle in a megamek checkout with the GPU
board (by default the one beside mm-data, whose build stages this mm-data's models) with
-Dmegamek.gpu.impostorCalibration. Each run starts from the present files, so a second run refines the fit: the
coverage exponent acts on the atlas before the game filters it, which the measured cutoff assumes it does after, and
a run or two more corrects the difference. NAMEs (vegetation/pine, mars/fan-folded...) limit the plants it writes,
with the other forms kept in their files. The same test without the property checks the result.
"""
import argparse
import json
import math
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
ROWS = 4


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


def plant_file(name):
    """The GLB that holds a plant: its own, or for a winter form kept in its plant's file, that one."""
    path = BOARD / f'{name}.glb'
    return path if path.exists() else BOARD / f'{name.removesuffix("-snow")}.glb'


def exponent(cutoff, row_cutoff):
    """The coverage exponent that moves a row's threshold from `row_cutoff` to the material's `cutoff`."""
    if not 0 < row_cutoff < 1 or not 0 < cutoff < 1:
        return 1.0
    return min(max(math.log(cutoff) / math.log(row_cutoff), .2), 5.0)


def fit_rows(name, rows, cutoff):
    """A plant's rows: per row its colour ratio (far mesh to impostor) and the cutoff at which it covers what the far mesh
    does, against the material's `cutoff`; multiplied into its tint and applied to its atlas."""
    atlas = name.rsplit('/', 1)[-1]
    steps = [(ratio[:3], exponent(cutoff, ratio[3])) for ratio in rows]

    def change(material):
        fits = material.setdefault('extras', {}).setdefault('mmImpostorTint', {})
        old = fits.get(atlas) or [[1, 1, 1, 1]] * ROWS
        fits[atlas] = [[round(o * f, 4) for o, f in zip(row[:3], colour)] + [round(row[3] * power, 4)]
                       for row, (colour, power) in zip(old, steps)]
    edit_impostor(plant_file(name), change)
    path = IMPOSTORS / f'{atlas}.png'
    values = numpy.asarray(Image.open(path).convert('RGBA')).astype(numpy.float64) / 255
    frame = values.shape[0] // ROWS
    for row, (colour, power) in enumerate(steps):
        block = values[row * frame:(row + 1) * frame]
        linear = numpy.where(block[..., :3] <= .04045, block[..., :3] / 12.92, ((block[..., :3] + .055) / 1.055) ** 2.4)
        linear = numpy.clip(linear * numpy.asarray(colour), 0, 1)
        block[..., :3] = numpy.where(linear <= .0031308, linear * 12.92, 1.055 * linear ** (1 / 2.4) - .055)
        block[..., 3] = block[..., 3] ** power
    Image.fromarray(numpy.round(values * 255).astype(numpy.uint8), 'RGBA').save(path)


def apply(fitted, names=()):
    """A GpuImpostorCalibrationSmokeTest result into the GLBs and atlases (only the plants `names` when given, with the
    other forms in their files: the forms share the file's cutoff, so each takes its rows against the new one)."""
    files = {plant_file(name) for name in names}
    for name, rows in fitted['rows'].items():
        if names and plant_file(name) not in files:
            continue
        path = plant_file(name)
        cutoff = fitted['cutoffs'][path.relative_to(BOARD).with_suffix('').as_posix()]
        edit_impostor(path, lambda material: material.update(alphaCutoff=cutoff))
        fit_rows(name, rows, cutoff)
        print(name, cutoff, [[round(value, 3) for value in row] for row in rows])


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
    apply(fitted, arguments.names)


if __name__ == '__main__':
    main()
